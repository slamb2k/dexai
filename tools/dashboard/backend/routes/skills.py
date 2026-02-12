"""
Skills API Routes

Provides endpoints to list and manage Claude Code skills from ~/.claude/skills/
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Models
# =============================================================================


class Skill(BaseModel):
    """A Claude Code skill."""

    name: str  # Directory name (e.g., "prime")
    display_name: str  # Human-readable name (e.g., "Prime")
    description: str | None = None
    status: str = "idle"  # 'idle', 'running' (future: track active skills)
    file_path: str
    has_instructions: bool = False
    category: str = "user"  # 'built-in' or 'user'
    dependencies: list[str] = []  # Python package dependencies
    version: str = "1.0.0"  # Semantic version from skill tracker
    version_history: list[dict] = []  # Version change history


class SkillsResponse(BaseModel):
    """Response for skills list."""

    skills: list[Skill]
    total: int
    skills_dir: str


class SkillDetail(BaseModel):
    """Detailed skill information."""

    name: str
    display_name: str
    description: str | None = None
    status: str = "idle"
    file_path: str
    instructions: str | None = None
    readme: str | None = None
    dependencies: list[str] = []  # Python package dependencies
    version: str = "1.0.0"  # Semantic version from skill tracker
    version_history: list[dict] = []  # Version change history


# =============================================================================
# Helpers
# =============================================================================


# Known built-in skill patterns (skills that come with Claude Code or DexAI)
BUILTIN_SKILL_PATTERNS = [
    "prime",
    "sync",
    "ship",
    "launchpad",
    "find-skills",
    "adhd-decomposition",
    "energy-matching",
    "rsd-safe-communication",
    "setup",
]


def detect_skill_category(skill_dir: str, name: str) -> str:
    """
    Detect whether a skill is built-in or user-created.

    Built-in skills are either:
    - Located in a plugins directory
    - Match known built-in skill patterns
    """
    # Check if in plugins directory
    if "/plugins/" in skill_dir or "\\plugins\\" in skill_dir:
        return "built-in"

    # Check known built-in patterns
    if name.lower() in BUILTIN_SKILL_PATTERNS:
        return "built-in"

    return "user"


def format_skill_name(name: str) -> str:
    """
    Convert skill directory name to human-readable display name.

    Examples:
        'prime' -> 'Prime'
        'web-artifacts-builder' -> 'Web Artifacts Builder'
        'frontend_design' -> 'Frontend Design'
    """
    # Replace hyphens and underscores with spaces
    formatted = re.sub(r"[-_]+", " ", name)
    # Title case
    return formatted.title()


def extract_yaml_frontmatter(content: str) -> dict:
    """
    Extract YAML frontmatter from markdown content.

    Frontmatter is enclosed between --- markers at the start of the file:
    ---
    name: skill-name
    description: What it does
    dependencies:
      - package>=1.0
    ---
    # Rest of content

    Returns:
        Dict with frontmatter data, or empty dict if none found
    """
    if not content.startswith("---"):
        return {}

    # Find the closing ---
    lines = content.split("\n")
    end_index = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index == -1:
        return {}

    # Parse YAML content between markers
    yaml_content = "\n".join(lines[1:end_index])
    try:
        return yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return {}


def extract_description(content: str) -> str | None:
    """
    Extract description from skill markdown content.

    Looks for:
    1. First paragraph after the title
    2. A line starting with "Description:"
    3. First non-heading paragraph
    """
    lines = content.strip().split("\n")

    # Skip title line if present
    start_idx = 0
    if lines and lines[0].startswith("#"):
        start_idx = 1

    # Look for first non-empty, non-heading paragraph
    description_lines = []
    in_paragraph = False

    for line in lines[start_idx:]:
        stripped = line.strip()

        # Skip empty lines before paragraph
        if not stripped and not in_paragraph:
            continue

        # Start of paragraph
        if stripped and not stripped.startswith("#") and not in_paragraph:
            in_paragraph = True
            description_lines.append(stripped)
            continue

        # Continue paragraph
        if stripped and in_paragraph and not stripped.startswith("#"):
            description_lines.append(stripped)
            continue

        # End of paragraph (empty line or heading)
        if in_paragraph and (not stripped or stripped.startswith("#")):
            break

    if description_lines:
        description = " ".join(description_lines)
        # Truncate if too long
        if len(description) > 200:
            description = description[:197] + "..."
        return description

    return None


def scan_skill_directory(skill_dir: Path) -> Skill | None:
    """
    Scan a skill directory and extract metadata.

    A valid skill directory must contain either:
    - SKILL.md (with YAML frontmatter)
    - instructions.md
    - README.md
    - A .md file matching the directory name
    """
    if not skill_dir.is_dir():
        return None

    name = skill_dir.name
    description = None
    has_instructions = False
    dependencies: list[str] = []

    # Check for SKILL.md first (preferred format with frontmatter)
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8")
            frontmatter = extract_yaml_frontmatter(content)

            # Extract dependencies from frontmatter
            deps = frontmatter.get("dependencies", [])
            if isinstance(deps, list):
                dependencies = [str(d) for d in deps]

            # Use description from frontmatter if available
            if frontmatter.get("description"):
                description = frontmatter.get("description")
            else:
                description = extract_description(content)

            # Use display name from frontmatter if available
            display_name = frontmatter.get("name", format_skill_name(name))
            if not display_name:
                display_name = format_skill_name(name)

        except Exception as e:
            logger.warning(f"Failed to read SKILL.md for {name}: {e}")
            description = None

    # Look for skill files in priority order
    possible_files = [
        skill_dir / "instructions.md",
        skill_dir / "README.md",
        skill_dir / f"{name}.md",
    ]

    main_file = None
    for f in possible_files:
        if f.exists():
            main_file = f
            has_instructions = f.name == "instructions.md"
            break

    # Also check for any .md file if none of the above exist
    if not main_file:
        md_files = list(skill_dir.glob("*.md"))
        if md_files:
            main_file = md_files[0]

    # If no markdown file found (and no SKILL.md), not a valid skill
    if not main_file and not skill_md.exists():
        return None

    # Extract description from the main file if not already extracted from SKILL.md
    if description is None and main_file:
        try:
            content = main_file.read_text(encoding="utf-8")
            description = extract_description(content)
        except Exception as e:
            logger.warning(f"Failed to read skill file {main_file}: {e}")

    version, version_history = _get_skill_version_info(name)

    return Skill(
        name=name,
        display_name=format_skill_name(name),
        description=description,
        status="idle",
        file_path=str(skill_dir),
        has_instructions=has_instructions,
        category=detect_skill_category(str(skill_dir), name),
        dependencies=dependencies,
        version=version,
        version_history=version_history,
    )


def _get_skill_version_info(skill_name: str) -> tuple[str, list[dict]]:
    """Get version and version history from the skill tracker.

    Args:
        skill_name: Name of the skill.

    Returns:
        Tuple of (version string, version history list).
    """
    try:
        from tools.agent.skill_tracker import SkillTracker

        tracker = SkillTracker()
        if skill_name in tracker.usage:
            skill_data = tracker.usage[skill_name]
            return skill_data.version, skill_data.version_history
    except Exception as e:
        logger.debug(f"Could not load version info for {skill_name}: {e}")

    return "1.0.0", []


def get_builtin_skills_dir() -> Path:
    """
    Get the built-in skills directory (read-only, baked into Docker image).

    Returns /app/.claude/skills/ which contains skills shipped with DexAI.
    """
    return PROJECT_ROOT / ".claude" / "skills"


def get_workspace_skills_dirs() -> list[Path]:
    """
    Get all workspace skills directories (user-created skills).

    Scans /app/data/workspaces/*/. claude/skills/ for user-created skills.
    Each user workspace may have its own skills.
    """
    workspaces_base = PROJECT_ROOT / "data" / "workspaces"
    skill_dirs: list[Path] = []

    if workspaces_base.exists():
        for workspace in workspaces_base.iterdir():
            if workspace.is_dir():
                workspace_skills = workspace / ".claude" / "skills"
                if workspace_skills.exists() and workspace_skills.is_dir():
                    skill_dirs.append(workspace_skills)

    return skill_dirs


def get_claude_skills_dir() -> Path:
    """
    Get the primary Claude skills directory path (for backwards compatibility).

    Returns the built-in skills directory.
    """
    return get_builtin_skills_dir()


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/skills", response_model=SkillsResponse)
async def list_skills():
    """
    List all Claude Code skills from built-in and workspace directories.

    Scans:
    1. Built-in skills from /app/.claude/skills/ (read-only, ships with DexAI)
    2. User skills from /app/data/workspaces/*/.claude/skills/ (user-created)

    Returns metadata for each skill including:
    - Name and display name
    - Description (extracted from markdown)
    - Status (idle/running)
    - Category (built-in or user)
    - File path
    """
    skills: list[Skill] = []
    seen_names: set[str] = set()

    # 1. Scan built-in skills (read-only)
    builtin_dir = get_builtin_skills_dir()
    if builtin_dir.exists() and builtin_dir.is_dir():
        for item in sorted(builtin_dir.iterdir()):
            skill = scan_skill_directory(item)
            if skill:
                skill.category = "built-in"  # Force category for built-in
                skills.append(skill)
                seen_names.add(skill.name)

    # 2. Scan workspace skills (user-created)
    for workspace_skills_dir in get_workspace_skills_dirs():
        for item in sorted(workspace_skills_dir.iterdir()):
            skill = scan_skill_directory(item)
            if skill and skill.name not in seen_names:
                skill.category = "user"  # Force category for user skills
                skills.append(skill)
                seen_names.add(skill.name)

    # Sort by category (built-in first) then by name
    skills.sort(key=lambda s: (0 if s.category == "built-in" else 1, s.name))

    return SkillsResponse(
        skills=skills,
        total=len(skills),
        skills_dir=str(builtin_dir),
    )


def find_skill_directory(name: str) -> Path | None:
    """
    Find a skill directory by name, checking built-in first then workspaces.

    Returns the path to the skill directory, or None if not found.
    """
    # Check built-in skills first
    builtin_dir = get_builtin_skills_dir() / name
    if builtin_dir.exists() and builtin_dir.is_dir():
        return builtin_dir

    # Check workspace skills
    for workspace_skills_dir in get_workspace_skills_dirs():
        skill_dir = workspace_skills_dir / name
        if skill_dir.exists() and skill_dir.is_dir():
            return skill_dir

    return None


@router.get("/skills/{name}", response_model=SkillDetail)
async def get_skill(name: str):
    """
    Get detailed information about a specific skill.

    Searches both built-in and workspace directories.
    Returns the skill metadata plus full content of instructions and readme.
    """
    skill_dir = find_skill_directory(name)

    if not skill_dir:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    skill = scan_skill_directory(skill_dir)
    if not skill:
        raise HTTPException(
            status_code=404, detail=f"Skill '{name}' is not a valid skill directory"
        )

    # Read full content
    instructions = None
    readme = None

    instructions_file = skill_dir / "instructions.md"
    readme_file = skill_dir / "README.md"

    if instructions_file.exists():
        try:
            instructions = instructions_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read instructions for {name}: {e}")

    if readme_file.exists():
        try:
            readme = readme_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read readme for {name}: {e}")

    version, version_history = _get_skill_version_info(name)

    return SkillDetail(
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description,
        status=skill.status,
        file_path=skill.file_path,
        instructions=instructions,
        readme=readme,
        dependencies=skill.dependencies,
        version=version,
        version_history=version_history,
    )


@router.get("/skills-summary")
async def get_skills_summary() -> dict[str, Any]:
    """
    Get a summary of skills for the dashboard.

    Scans both built-in and workspace directories.
    Returns counts and basic status useful for overview displays.
    """
    skills: list[Skill] = []
    seen_names: set[str] = set()

    # Scan built-in skills
    builtin_dir = get_builtin_skills_dir()
    if builtin_dir.exists() and builtin_dir.is_dir():
        for item in builtin_dir.iterdir():
            skill = scan_skill_directory(item)
            if skill:
                skill.category = "built-in"
                skills.append(skill)
                seen_names.add(skill.name)

    # Scan workspace skills
    for workspace_skills_dir in get_workspace_skills_dirs():
        for item in workspace_skills_dir.iterdir():
            skill = scan_skill_directory(item)
            if skill and skill.name not in seen_names:
                skill.category = "user"
                skills.append(skill)
                seen_names.add(skill.name)

    # Count by status (future: track which skills are actively running)
    active_count = sum(1 for s in skills if s.status == "running")
    idle_count = sum(1 for s in skills if s.status == "idle")

    # Count by category
    builtin_count = sum(1 for s in skills if s.category == "built-in")
    user_count = sum(1 for s in skills if s.category == "user")

    return {
        "total": len(skills),
        "active": active_count,
        "idle": idle_count,
        "builtin": builtin_count,
        "user": user_count,
        "skills_dir": str(builtin_dir),
        "exists": True,
    }
