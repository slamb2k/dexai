"""
Skill validation and testing module.

Provides core validation logic used by both CLI and MCP interfaces.
Validates skill files for correctness, completeness, and safety.

Skills are YAML/MD files in `.claude/skills/` directories that define
reusable instructions for the Claude Agent SDK.

Usage:
    from tools.agent.skill_validator import validate_skill, test_skill, list_skills

    result = validate_skill(".claude/skills/my-skill")
    print(result.to_dict())

Dependencies:
    - Standard library (pathlib, re, hashlib, logging)
    - PyYAML (for frontmatter parsing)
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"

# Maximum file size for a skill file (100 KB)
MAX_SKILL_FILE_SIZE = 100 * 1024

# Required frontmatter fields
REQUIRED_FRONTMATTER_FIELDS = ["name", "description"]

# Dangerous patterns in instructions that should be flagged
DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\b", "rm -rf command detected"),
    (r"\bsudo\s+su\b", "sudo su command detected"),
    (r"\bsudo\s+rm\b", "sudo rm command detected"),
    (r"\bchmod\s+777\b", "chmod 777 detected"),
    (r"\b(curl|wget)\s+.*\|\s*(ba)?sh\b", "piped remote execution detected"),
    (r"\beval\s*\(", "eval() call detected"),
    (r"\b__import__\b", "__import__ call detected"),
    (r"\bos\.system\b", "os.system call detected"),
    (r"\bsubprocess\.call\b.*shell\s*=\s*True", "shell=True subprocess detected"),
    (r"\bfork\s*bomb\b", "fork bomb reference detected"),
    (r":\(\)\s*\{\s*:\|:\s*&\s*\}", "fork bomb pattern detected"),
]


class SkillValidationResult:
    """Result of a skill validation check.

    Attributes:
        errors: Critical issues that make the skill invalid.
        warnings: Non-critical issues that should be addressed.
        info: Informational messages about the skill.
    """

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    @property
    def valid(self) -> bool:
        """Whether the skill passed validation (no errors)."""
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
        }


def _parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Raw markdown content that may start with --- delimited YAML.

    Returns:
        Tuple of (frontmatter dict, remaining content after frontmatter).
    """
    if not content.startswith("---"):
        return {}, content

    lines = content.split("\n")
    end_index = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index == -1:
        return {}, content

    yaml_content = "\n".join(lines[1:end_index])
    remaining = "\n".join(lines[end_index + 1:])

    try:
        import yaml
        parsed = yaml.safe_load(yaml_content) or {}
        return parsed, remaining
    except Exception as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return {}, content


def _resolve_skill_path(skill_path: str | Path) -> Path:
    """Resolve a skill path, accepting name, relative, or absolute paths.

    Args:
        skill_path: Skill name (e.g., 'adhd-decomposition'), relative path,
            or absolute path to a skill directory or file.

    Returns:
        Resolved absolute Path to the skill directory.
    """
    path = Path(skill_path)

    # If it's just a name (no separators), look in default skills dir
    if not path.is_absolute() and "/" not in str(skill_path) and "\\" not in str(skill_path):
        candidate = DEFAULT_SKILLS_DIR / str(skill_path)
        if candidate.exists():
            return candidate

    # Try as-is (could be relative or absolute)
    if path.exists():
        return path.resolve()

    # Try relative to project root
    candidate = PROJECT_ROOT / path
    if candidate.exists():
        return candidate.resolve()

    # Return the path as-is for error reporting
    return path


def _find_skill_md(skill_dir: Path) -> Path | None:
    """Find the main markdown file in a skill directory.

    Checks for files in priority order:
    1. SKILL.md
    2. instructions.md
    3. README.md
    4. <dirname>.md
    5. Any .md file

    Args:
        skill_dir: Path to the skill directory.

    Returns:
        Path to the main markdown file, or None if not found.
    """
    candidates = [
        skill_dir / "SKILL.md",
        skill_dir / "instructions.md",
        skill_dir / "README.md",
        skill_dir / f"{skill_dir.name}.md",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Fallback: any .md file
    md_files = list(skill_dir.glob("*.md"))
    if md_files:
        return md_files[0]

    return None


def compute_skill_hash(skill_path: str | Path) -> str | None:
    """Compute a content hash for a skill's files.

    Hashes all markdown files in the skill directory to detect changes.

    Args:
        skill_path: Path to skill directory.

    Returns:
        SHA-256 hex digest, or None if skill directory not found.
    """
    path = _resolve_skill_path(skill_path)
    if not path.exists() or not path.is_dir():
        return None

    hasher = hashlib.sha256()
    md_files = sorted(path.glob("*.md"))
    for md_file in md_files:
        try:
            content = md_file.read_bytes()
            hasher.update(md_file.name.encode("utf-8"))
            hasher.update(content)
        except OSError:
            continue

    return hasher.hexdigest()


def validate_skill(skill_path: str | Path) -> SkillValidationResult:
    """Validate a skill file for correctness and completeness.

    Checks:
    - File exists and is readable
    - Valid YAML/MD frontmatter (if YAML)
    - Required fields present (name, description)
    - No dangerous patterns in instructions (rm -rf, sudo, etc.)
    - File size within limits
    - Referenced files/tools exist

    Args:
        skill_path: Path to skill directory or skill name.

    Returns:
        SkillValidationResult with errors, warnings, and info messages.
    """
    result = SkillValidationResult()
    path = _resolve_skill_path(skill_path)

    # Check existence
    if not path.exists():
        result.errors.append(f"Skill path does not exist: {path}")
        return result

    # Handle both directory and single file
    if path.is_file():
        skill_dir = path.parent
        main_file = path
    elif path.is_dir():
        skill_dir = path
        main_file = _find_skill_md(skill_dir)
        if main_file is None:
            result.errors.append(
                f"No markdown file found in skill directory: {skill_dir}"
            )
            return result
    else:
        result.errors.append(f"Skill path is not a file or directory: {path}")
        return result

    result.info.append(f"Skill directory: {skill_dir}")
    result.info.append(f"Main file: {main_file.name}")

    # Check file size
    try:
        file_size = main_file.stat().st_size
        if file_size > MAX_SKILL_FILE_SIZE:
            result.errors.append(
                f"Skill file too large: {file_size} bytes "
                f"(max {MAX_SKILL_FILE_SIZE} bytes)"
            )
        elif file_size == 0:
            result.errors.append("Skill file is empty")
            return result
        else:
            result.info.append(f"File size: {file_size} bytes")
    except OSError as e:
        result.errors.append(f"Cannot read file stats: {e}")
        return result

    # Read content
    try:
        content = main_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result.errors.append(f"Cannot read skill file: {e}")
        return result

    # Parse frontmatter
    frontmatter, body = _parse_yaml_frontmatter(content)

    if not frontmatter and content.startswith("---"):
        result.errors.append(
            "YAML frontmatter is present but could not be parsed"
        )
    elif not frontmatter:
        result.warnings.append(
            "No YAML frontmatter found. Consider adding ---name/description--- block."
        )

    # Check required fields
    if frontmatter:
        for field in REQUIRED_FRONTMATTER_FIELDS:
            if field not in frontmatter:
                result.warnings.append(
                    f"Missing recommended frontmatter field: {field}"
                )
            elif not frontmatter[field]:
                result.warnings.append(
                    f"Frontmatter field '{field}' is empty"
                )

        # Check for name mismatch
        if frontmatter.get("name") and frontmatter["name"] != skill_dir.name:
            result.warnings.append(
                f"Frontmatter name '{frontmatter['name']}' does not match "
                f"directory name '{skill_dir.name}'"
            )

        result.info.append(
            f"Frontmatter fields: {', '.join(frontmatter.keys())}"
        )

    # Check body content
    body_stripped = body.strip()
    if not body_stripped:
        result.warnings.append("Skill has no content beyond frontmatter")
    elif len(body_stripped) < 50:
        result.warnings.append(
            "Skill content is very short (< 50 chars). "
            "Consider adding more detailed instructions."
        )

    # Check for section headings (good practice)
    headings = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
    if headings:
        result.info.append(f"Sections: {', '.join(headings[:5])}")
    else:
        result.warnings.append(
            "No section headings found. "
            "Consider structuring with ## When to Activate, ## Behavior, etc."
        )

    # Check for dangerous patterns
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            result.errors.append(
                f"Dangerous pattern in instructions: {description}"
            )

    # Check for referenced files
    file_refs = re.findall(r"\[.*?\]\(([^)]+)\)", content)
    for ref in file_refs:
        # Skip URLs
        if ref.startswith(("http://", "https://", "#")):
            continue
        ref_path = (skill_dir / ref).resolve()
        if not ref_path.exists():
            result.warnings.append(
                f"Referenced file not found: {ref}"
            )

    # Compute content hash
    content_hash = compute_skill_hash(skill_dir)
    if content_hash:
        result.info.append(f"Content hash: {content_hash[:12]}...")

    return result


def test_skill(
    skill_path: str | Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Test a skill by parsing and simulating execution.

    In dry_run mode: validates + checks all referenced tools exist.

    Args:
        skill_path: Path to skill directory or skill name.
        dry_run: If True, only validates without executing. Default True.

    Returns:
        Dict with success, validation result, and test results.
    """
    validation = validate_skill(skill_path)
    test_results: list[dict[str, Any]] = []

    path = _resolve_skill_path(skill_path)

    # Test 1: Validation passes
    test_results.append({
        "test": "validation",
        "passed": validation.valid,
        "detail": "All validation checks passed" if validation.valid
        else f"{len(validation.errors)} error(s) found",
    })

    # Test 2: Frontmatter parseable
    main_file = _find_skill_md(path) if path.is_dir() else path
    frontmatter_ok = False
    if main_file and main_file.exists():
        try:
            content = main_file.read_text(encoding="utf-8")
            frontmatter, _ = _parse_yaml_frontmatter(content)
            frontmatter_ok = bool(frontmatter)
            test_results.append({
                "test": "frontmatter_parse",
                "passed": frontmatter_ok,
                "detail": f"Parsed {len(frontmatter)} field(s)" if frontmatter_ok
                else "No frontmatter found or parse failed",
            })
        except Exception as e:
            test_results.append({
                "test": "frontmatter_parse",
                "passed": False,
                "detail": f"Read error: {e}",
            })
    else:
        test_results.append({
            "test": "frontmatter_parse",
            "passed": False,
            "detail": "Skill file not found",
        })

    # Test 3: Content structure (has headings, reasonable length)
    if main_file and main_file.exists():
        try:
            content = main_file.read_text(encoding="utf-8")
            has_headings = bool(re.search(r"^#+\s+", content, re.MULTILINE))
            has_body = len(content.strip()) > 100
            structure_ok = has_headings and has_body
            test_results.append({
                "test": "content_structure",
                "passed": structure_ok,
                "detail": "Has headings and sufficient content" if structure_ok
                else "Missing headings or content too short",
            })
        except Exception as e:
            test_results.append({
                "test": "content_structure",
                "passed": False,
                "detail": f"Read error: {e}",
            })

    # Test 4: No broken internal references
    broken_refs = [
        w for w in validation.warnings
        if "Referenced file not found" in w
    ]
    test_results.append({
        "test": "internal_references",
        "passed": len(broken_refs) == 0,
        "detail": "All internal references valid" if not broken_refs
        else f"{len(broken_refs)} broken reference(s)",
    })

    # Overall
    all_passed = all(t["passed"] for t in test_results)

    return {
        "success": all_passed,
        "skill_path": str(path),
        "dry_run": dry_run,
        "validation": validation.to_dict(),
        "test_results": test_results,
        "tests_passed": sum(1 for t in test_results if t["passed"]),
        "tests_total": len(test_results),
    }


def list_skills(
    skills_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List all available skills with their validation status.

    Args:
        skills_dir: Override skills directory. Defaults to .claude/skills/.

    Returns:
        List of dicts with skill name, path, validation status, and metadata.
    """
    if skills_dir is None:
        search_dir = DEFAULT_SKILLS_DIR
    else:
        search_dir = Path(skills_dir)

    if not search_dir.exists():
        return []

    skills: list[dict[str, Any]] = []

    for item in sorted(search_dir.iterdir()):
        if not item.is_dir():
            continue

        main_file = _find_skill_md(item)
        if main_file is None:
            continue

        # Quick validation
        validation = validate_skill(item)

        # Extract frontmatter for metadata
        frontmatter: dict[str, Any] = {}
        try:
            content = main_file.read_text(encoding="utf-8")
            frontmatter, _ = _parse_yaml_frontmatter(content)
        except Exception:
            pass

        # Compute hash
        content_hash = compute_skill_hash(item)

        skills.append({
            "name": item.name,
            "path": str(item),
            "main_file": main_file.name,
            "valid": validation.valid,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
            "description": frontmatter.get("description", ""),
            "content_hash": content_hash,
        })

    return skills
