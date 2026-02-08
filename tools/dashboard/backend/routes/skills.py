"""
Skills API Routes

Provides endpoints to list and manage Claude Code skills from ~/.claude/skills/
"""

import logging
import re
import sys
from pathlib import Path
from typing import Any

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


# =============================================================================
# Helpers
# =============================================================================


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
    - instructions.md
    - README.md
    - A .md file matching the directory name
    """
    if not skill_dir.is_dir():
        return None

    name = skill_dir.name
    description = None
    has_instructions = False

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

    # If no markdown file found, not a valid skill
    if not main_file:
        return None

    # Extract description from the main file
    try:
        content = main_file.read_text(encoding="utf-8")
        description = extract_description(content)
    except Exception as e:
        logger.warning(f"Failed to read skill file {main_file}: {e}")

    return Skill(
        name=name,
        display_name=format_skill_name(name),
        description=description,
        status="idle",
        file_path=str(skill_dir),
        has_instructions=has_instructions,
    )


def get_claude_skills_dir() -> Path:
    """Get the Claude skills directory path."""
    return Path.home() / ".claude" / "skills"


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/skills", response_model=SkillsResponse)
async def list_skills():
    """
    List all Claude Code skills from ~/.claude/skills/

    Scans the skills directory and returns metadata for each skill including:
    - Name and display name
    - Description (extracted from markdown)
    - Status (idle/running)
    - File path
    """
    skills_dir = get_claude_skills_dir()
    skills: list[Skill] = []

    if skills_dir.exists() and skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            skill = scan_skill_directory(item)
            if skill:
                skills.append(skill)

    return SkillsResponse(
        skills=skills,
        total=len(skills),
        skills_dir=str(skills_dir),
    )


@router.get("/skills/{name}", response_model=SkillDetail)
async def get_skill(name: str):
    """
    Get detailed information about a specific skill.

    Returns the skill metadata plus full content of instructions and readme.
    """
    skills_dir = get_claude_skills_dir()
    skill_dir = skills_dir / name

    if not skill_dir.exists() or not skill_dir.is_dir():
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

    return SkillDetail(
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description,
        status=skill.status,
        file_path=skill.file_path,
        instructions=instructions,
        readme=readme,
    )


@router.get("/skills-summary")
async def get_skills_summary() -> dict[str, Any]:
    """
    Get a summary of skills for the dashboard.

    Returns counts and basic status useful for overview displays.
    """
    skills_dir = get_claude_skills_dir()

    if not skills_dir.exists():
        return {
            "total": 0,
            "active": 0,
            "idle": 0,
            "skills_dir": str(skills_dir),
            "exists": False,
        }

    skills = []
    for item in skills_dir.iterdir():
        skill = scan_skill_directory(item)
        if skill:
            skills.append(skill)

    # Count by status (future: track which skills are actively running)
    active_count = sum(1 for s in skills if s.status == "running")
    idle_count = sum(1 for s in skills if s.status == "idle")

    return {
        "total": len(skills),
        "active": active_count,
        "idle": idle_count,
        "skills_dir": str(skills_dir),
        "exists": True,
    }
