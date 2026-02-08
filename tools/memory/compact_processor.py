"""
Tool: Compaction Memory Processor
Purpose: Background service that processes compaction queue files, extracts
         important data, and reconciles against existing memory records.

Architecture:
    PreCompact hook (fast) → writes JSON to data/compaction_queue/
    This service (slow)    → picks up files, extracts, reconciles, saves

The processor runs as a background task or standalone service. It:
1. Watches data/compaction_queue/ for pending_*.json files
2. Extracts important items using heuristics (regex patterns)
3. Optionally enriches with a lightweight model (Haiku) for classification
4. Searches existing memory for related/superseded entries
5. Saves new entries and marks superseded ones
6. Moves processed files to data/compaction_queue/processed/

Usage:
    # Run once (process all pending files)
    python tools/memory/compact_processor.py --run-once

    # Run as daemon (watch for new files)
    python tools/memory/compact_processor.py --daemon --poll-interval 30

    # Process a specific file
    python tools/memory/compact_processor.py --file data/compaction_queue/pending_xyz.json

    # Dry run (extract but don't save)
    python tools/memory/compact_processor.py --run-once --dry-run
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
QUEUE_DIR = PROJECT_ROOT / "data" / "compaction_queue"
PROCESSED_DIR = QUEUE_DIR / "processed"

sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


# =============================================================================
# Extraction Patterns (heuristic, no LLM needed)
# =============================================================================

# Patterns that indicate extractable items in conversation transcripts.
# Each pattern maps to a memory type and importance level.
EXTRACTION_PATTERNS: list[dict[str, Any]] = [
    # Commitments / promises
    {
        "name": "commitment",
        "patterns": [
            r"(?:I(?:'ll| will)|let me|I(?:'m going| am going) to)\s+(.{10,120}?)(?:\.|$)",
            r"(?:I promise|I commit|you have my word)\s+(.{10,120}?)(?:\.|$)",
        ],
        "type": "task",
        "importance": 7,
        "direction": "outbound",  # Only from assistant
    },
    # User preferences stated explicitly
    {
        "name": "preference",
        "patterns": [
            r"(?:I prefer|I like|I want|I need|I always|I never|I hate)\s+(.{10,120}?)(?:\.|$)",
            r"(?:please (?:always|never|don't))\s+(.{10,120}?)(?:\.|$)",
            r"(?:my (?:preferred|favorite|default))\s+(?:\w+\s+)?(?:is|are)\s+(.{10,120}?)(?:\.|$)",
        ],
        "type": "preference",
        "importance": 7,
        "direction": "inbound",  # Only from user
    },
    # Facts / information shared
    {
        "name": "fact",
        "patterns": [
            r"(?:my (?:name|email|company|team|role|timezone|stack) is)\s+(.{3,80}?)(?:\.|$)",
            r"(?:I(?:'m| am) (?:a |an |the )?)\s*(\w[\w\s]{5,60}?)(?:\.|$)",
            r"(?:we use|we're using|our stack is|we run)\s+(.{5,80}?)(?:\.|$)",
        ],
        "type": "fact",
        "importance": 6,
        "direction": "inbound",
    },
    # Decisions made
    {
        "name": "decision",
        "patterns": [
            r"(?:let's go with|we(?:'ll| will) use|decided to|going with)\s+(.{10,120}?)(?:\.|$)",
            r"(?:the (?:plan|approach|strategy|solution) is)\s+(.{10,120}?)(?:\.|$)",
        ],
        "type": "insight",
        "importance": 6,
        "direction": None,  # Either direction
    },
    # Key technical context
    {
        "name": "technical_context",
        "patterns": [
            r"(?:the (?:bug|issue|error|problem) (?:is|was))\s+(.{10,150}?)(?:\.|$)",
            r"(?:fixed by|solved by|the fix (?:is|was))\s+(.{10,150}?)(?:\.|$)",
            r"(?:root cause|the reason)\s+(?:is|was)\s+(.{10,150}?)(?:\.|$)",
        ],
        "type": "insight",
        "importance": 5,
        "direction": None,
    },
]


def extract_items_heuristic(transcript: str) -> list[dict[str, Any]]:
    """
    Extract important items from a transcript using regex heuristics.

    Fast extraction pass — no LLM calls. Returns candidate items
    with type, content, importance, and source pattern name.

    Args:
        transcript: Full conversation transcript text

    Returns:
        List of extracted items with metadata
    """
    items = []
    seen_content = set()

    for pattern_group in EXTRACTION_PATTERNS:
        for pattern in pattern_group["patterns"]:
            for match in re.finditer(pattern, transcript, re.IGNORECASE | re.MULTILINE):
                content = match.group(1).strip()

                # Skip too short or duplicate content
                if len(content) < 10:
                    continue
                content_key = content.lower()[:50]
                if content_key in seen_content:
                    continue
                seen_content.add(content_key)

                items.append({
                    "content": content,
                    "type": pattern_group["type"],
                    "importance": pattern_group["importance"],
                    "source_pattern": pattern_group["name"],
                    "confidence": 0.6,  # Heuristic extraction = moderate confidence
                })

    return items


# =============================================================================
# Memory Reconciliation
# =============================================================================


def find_related_memories(
    content: str,
    memory_type: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search existing memory for entries related to the given content.

    Uses hybrid search (keyword + semantic) to find potential duplicates
    or entries that should be superseded.

    Args:
        content: Content to search for related memories
        memory_type: Type of memory to filter by
        limit: Max results

    Returns:
        List of related memory entries with similarity scores
    """
    try:
        from tools.memory.hybrid_search import hybrid_search

        results = hybrid_search(
            query=content,
            limit=limit,
            keyword_only=True,  # Fast path — no embeddings needed
        )

        # Filter by type if we got results
        entries = results.get("results", [])
        return [
            e for e in entries
            if e.get("type") == memory_type and e.get("is_active", 1) == 1
        ]

    except Exception as e:
        logger.warning(f"Failed to search related memories: {e}")
        return []


def determine_relationship(
    new_content: str,
    existing: dict[str, Any],
) -> str:
    """
    Determine the relationship between a new item and an existing memory.

    Uses simple heuristics. For more nuanced classification, the optional
    LLM enrichment pass handles this.

    Args:
        new_content: New extracted content
        existing: Existing memory entry dict

    Returns:
        One of: "duplicate", "supersedes", "supplements", "unrelated"
    """
    existing_content = existing.get("content", "").lower()
    new_lower = new_content.lower()

    # Exact or near-exact duplicate
    if existing_content == new_lower:
        return "duplicate"

    # Check for high word overlap (>70% shared words)
    existing_words = set(existing_content.split())
    new_words = set(new_lower.split())

    if existing_words and new_words:
        overlap = len(existing_words & new_words)
        max_words = max(len(existing_words), len(new_words))
        overlap_ratio = overlap / max_words if max_words > 0 else 0

        if overlap_ratio > 0.7:
            # High overlap — newer content supersedes older
            return "supersedes"
        elif overlap_ratio > 0.3:
            return "supplements"

    return "unrelated"


def save_extracted_item(
    item: dict[str, Any],
    session_id: str,
    user_id: str,
    supersedes_id: int | None = None,
    lineage_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Save an extracted item to the memory database.

    Handles supersession: if this item supersedes an existing entry,
    marks the old one as superseded and links them.

    Args:
        item: Extracted item dict (content, type, importance, confidence)
        session_id: Source session ID
        user_id: User who owns this memory
        supersedes_id: ID of the entry this supersedes (if any)
        lineage_id: Lineage group ID (if continuing a chain)
        dry_run: If True, log but don't write

    Returns:
        Dict with success status and entry details
    """
    if dry_run:
        logger.info(
            f"[DRY RUN] Would save: type={item['type']} "
            f"content={item['content'][:60]}... "
            f"supersedes={supersedes_id}"
        )
        return {"success": True, "dry_run": True}

    from tools.memory.memory_db import add_entry, get_connection

    # Add the new entry
    result = add_entry(
        content=item["content"],
        entry_type=item["type"],
        source="inferred",
        confidence=item.get("confidence", 0.6),
        importance=item.get("importance", 5),
        tags=json.dumps([item.get("source_pattern", "compact_extract")]),
        context=json.dumps({
            "extracted_from": session_id,
            "user_id": user_id,
            "extraction_method": "heuristic",
            "source_pattern": item.get("source_pattern"),
        }),
    )

    if not result.get("success"):
        return result

    new_id = result.get("id")

    # Set supersession columns on the new entry
    conn = get_connection()
    cursor = conn.cursor()
    try:
        updates = {"extracted_from": session_id}
        if lineage_id:
            updates["lineage_id"] = lineage_id
        if supersedes_id:
            updates["supersedes"] = supersedes_id

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        cursor.execute(
            f"UPDATE memory_entries SET {set_clause} WHERE id = ?",
            [*updates.values(), new_id],
        )

        # Mark the old entry as superseded
        if supersedes_id:
            cursor.execute(
                "UPDATE memory_entries SET superseded_by = ?, is_active = 0, "
                "updated_at = ? WHERE id = ?",
                (new_id, datetime.now().isoformat(), supersedes_id),
            )
            logger.info(
                f"Memory #{supersedes_id} superseded by #{new_id}"
            )

        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to update supersession: {e}")
    finally:
        conn.close()

    return {
        "success": True,
        "id": new_id,
        "supersedes": supersedes_id,
        "lineage_id": lineage_id,
    }


# =============================================================================
# Queue Processing
# =============================================================================


def process_queue_file(
    filepath: Path,
    dry_run: bool = False,
    use_llm: bool = False,
) -> dict[str, Any]:
    """
    Process a single compaction queue file.

    Steps:
    1. Read the queue file
    2. Extract items using heuristics
    3. For each item, search for related memories
    4. Determine relationship (new, duplicate, supersedes)
    5. Save new items, mark superseded ones
    6. Move file to processed/

    Args:
        filepath: Path to the queue JSON file
        dry_run: If True, extract but don't save
        use_llm: If True, use lightweight model for enrichment (TODO)

    Returns:
        Processing result dict
    """
    filepath = Path(filepath)

    if not filepath.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    # Read queue entry
    try:
        data = json.loads(filepath.read_text())
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {e}"}

    transcript = data.get("transcript")
    if not transcript:
        # No transcript — nothing to extract, just move to processed
        _move_to_processed(filepath)
        return {"success": True, "items_extracted": 0, "reason": "no_transcript"}

    session_id = data.get("session_id", "unknown")
    user_id = data.get("user_id", "unknown")

    logger.info(
        f"Processing {filepath.name}: session={session_id}, "
        f"transcript_length={len(transcript)}"
    )

    # Extract items using heuristics
    items = extract_items_heuristic(transcript)
    logger.info(f"Extracted {len(items)} candidate items from {filepath.name}")

    # Reconcile each item against existing memory
    saved = 0
    skipped = 0
    superseded = 0

    for item in items:
        # Search for related existing memories
        related = find_related_memories(item["content"], item["type"])

        supersedes_id = None
        lineage_id = None
        skip = False

        for existing in related:
            relationship = determine_relationship(item["content"], existing)

            if relationship == "duplicate":
                logger.debug(f"Skipping duplicate: {item['content'][:50]}...")
                skip = True
                skipped += 1
                break
            elif relationship == "supersedes":
                supersedes_id = existing.get("id")
                lineage_id = existing.get("lineage_id") or f"lineage_{supersedes_id}"
                superseded += 1
                break
            # "supplements" and "unrelated" — save as new entry

        if skip:
            continue

        result = save_extracted_item(
            item=item,
            session_id=session_id,
            user_id=user_id,
            supersedes_id=supersedes_id,
            lineage_id=lineage_id,
            dry_run=dry_run,
        )

        if result.get("success"):
            saved += 1

    # Move to processed
    if not dry_run:
        _move_to_processed(filepath)

    result = {
        "success": True,
        "file": filepath.name,
        "session_id": session_id,
        "items_extracted": len(items),
        "saved": saved,
        "skipped_duplicates": skipped,
        "superseded": superseded,
    }

    logger.info(
        f"Processed {filepath.name}: "
        f"{saved} saved, {skipped} skipped, {superseded} superseded"
    )

    return result


def _move_to_processed(filepath: Path) -> None:
    """Move a processed queue file to the processed directory."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / filepath.name.replace("pending_", "processed_")
    try:
        filepath.rename(dest)
    except Exception as e:
        logger.warning(f"Failed to move {filepath} to processed: {e}")


def process_all_pending(dry_run: bool = False) -> list[dict[str, Any]]:
    """
    Process all pending queue files.

    Returns:
        List of processing results, one per file
    """
    if not QUEUE_DIR.exists():
        logger.info("No compaction queue directory found")
        return []

    pending_files = sorted(QUEUE_DIR.glob("pending_*.json"))

    if not pending_files:
        logger.info("No pending files to process")
        return []

    logger.info(f"Found {len(pending_files)} pending compaction files")

    results = []
    for filepath in pending_files:
        try:
            result = process_queue_file(filepath, dry_run=dry_run)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
            results.append({
                "success": False,
                "file": filepath.name,
                "error": str(e),
            })

    return results


def run_daemon(poll_interval: int = 30) -> None:
    """
    Run as a daemon, polling for new files.

    Args:
        poll_interval: Seconds between polls
    """
    logger.info(
        f"Starting compact processor daemon "
        f"(poll_interval={poll_interval}s, queue={QUEUE_DIR})"
    )

    while True:
        try:
            results = process_all_pending()
            if results:
                total_saved = sum(r.get("saved", 0) for r in results)
                total_superseded = sum(r.get("superseded", 0) for r in results)
                logger.info(
                    f"Batch complete: {len(results)} files, "
                    f"{total_saved} saved, {total_superseded} superseded"
                )
        except Exception as e:
            logger.error(f"Daemon error: {e}")

        time.sleep(poll_interval)


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Compaction Memory Processor - extract and reconcile memory from compacted conversations"
    )
    parser.add_argument("--run-once", action="store_true", help="Process all pending files and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--poll-interval", type=int, default=30, help="Daemon poll interval (seconds)")
    parser.add_argument("--file", type=str, help="Process a specific queue file")
    parser.add_argument("--dry-run", action="store_true", help="Extract but don't save to memory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.file:
        result = process_queue_file(Path(args.file), dry_run=args.dry_run)
        print(json.dumps(result, indent=2))

    elif args.daemon:
        run_daemon(poll_interval=args.poll_interval)

    elif args.run_once:
        results = process_all_pending(dry_run=args.dry_run)
        print(json.dumps({"results": results, "total": len(results)}, indent=2))

    else:
        # Default: show queue status
        if not QUEUE_DIR.exists():
            print("No compaction queue directory found.")
            return

        pending = list(QUEUE_DIR.glob("pending_*.json"))
        processed = list(PROCESSED_DIR.glob("processed_*.json")) if PROCESSED_DIR.exists() else []

        print(f"Queue directory: {QUEUE_DIR}")
        print(f"Pending files:   {len(pending)}")
        print(f"Processed files: {len(processed)}")

        if pending:
            print("\nPending:")
            for f in sorted(pending)[:10]:
                data = json.loads(f.read_text())
                print(
                    f"  {f.name}  "
                    f"user={data.get('user_id', '?')}  "
                    f"session={data.get('session_id', '?')[:12]}...  "
                    f"chars={data.get('transcript_length', 0)}"
                )
            if len(pending) > 10:
                print(f"  ... and {len(pending) - 10} more")


if __name__ == "__main__":
    main()
