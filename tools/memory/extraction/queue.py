"""
Extraction Queue — Async Background Memory Processing

Decouples message processing from memory storage, ensuring zero user-facing
latency impact. Conversation turns pass through the heuristic gate first,
then enter this queue for background extraction and storage.

See: goals/memory_context_compaction_design.md §5.2

Usage:
    from tools.memory.extraction.queue import ExtractionQueue

    queue = ExtractionQueue(provider)
    asyncio.create_task(queue.run())

    # From hook or after response delivery:
    await queue.enqueue(turn)

    # On shutdown:
    await queue.flush()
    await queue.stop()
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.agent import PROJECT_ROOT
from tools.memory.extraction.gate import should_extract, has_commitment_language
from tools.memory.extraction.extractor import extract_session_notes

logger = logging.getLogger(__name__)

_DB_PATH = PROJECT_ROOT / "data" / "extraction_queue.db"


def _get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_data TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


@dataclass
class ConversationTurn:
    """A single conversation turn for extraction processing."""
    user_message: str
    assistant_response: str
    user_id: str
    session_id: str | None = None
    channel: str = "direct"
    recent_context: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExtractionJob:
    """A queued extraction job."""
    turn: ConversationTurn
    gate_score: float
    enqueued_at: datetime = field(default_factory=datetime.now)


class ExtractionQueue:
    """
    Async queue that processes conversation turns for memory extraction.
    Runs in the background, never blocks the response path.
    """

    def __init__(
        self,
        provider: Any = None,
        batch_size: int = 5,
        flush_interval_seconds: float = 5.0,
        max_queue_size: int = 1000,
        gate_threshold: float = 0.3,
        extraction_model: str = "claude-haiku-4-5-20251001",
    ):
        """
        Initialize the extraction queue.

        Args:
            provider: MemoryProvider instance (or MemoryService)
            batch_size: Max items to process in one batch
            flush_interval_seconds: Seconds before flushing a partial batch
            max_queue_size: Max queue depth (prevents unbounded growth)
            gate_threshold: Heuristic gate threshold
            extraction_model: Model for LLM extraction
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._provider = provider
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._gate_threshold = gate_threshold
        self._extraction_model = extraction_model
        self._running = False
        self._task: asyncio.Task | None = None

        # Stats
        self._enqueued_count = 0
        self._processed_count = 0
        self._skipped_count = 0
        self._error_count = 0

    @property
    def stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        return {
            "queue_depth": self._queue.qsize(),
            "enqueued": self._enqueued_count,
            "processed": self._processed_count,
            "skipped": self._skipped_count,
            "errors": self._error_count,
            "running": self._running,
        }

    def set_provider(self, provider: Any) -> None:
        """Set or update the memory provider."""
        self._provider = provider

    async def enqueue(self, turn: ConversationTurn) -> bool:
        """
        Add a conversation turn to the extraction queue.

        Runs the heuristic gate first (< 1ms). If the gate doesn't fire,
        the turn is silently skipped. Persists to SQLite for crash recovery.

        Args:
            turn: Conversation turn to process

        Returns:
            True if enqueued, False if skipped by gate or queue full
        """
        # Run heuristic gate (< 1ms)
        do_extract, score = should_extract(
            turn.user_message,
            turn.recent_context,
            threshold=self._gate_threshold,
        )

        if not do_extract:
            self._skipped_count += 1
            return False

        job = ExtractionJob(
            turn=turn,
            gate_score=score,
        )

        # Persist to SQLite
        db_id = self._persist_job(job, "pending")

        try:
            self._queue.put_nowait(job)
            # Store db_id on job for status tracking
            job._db_id = db_id
            self._enqueued_count += 1
            logger.debug(f"Enqueued extraction job (score={score:.2f}, depth={self._queue.qsize()})")
            return True
        except asyncio.QueueFull:
            logger.warning(f"Extraction queue full ({self._queue.qsize()}), dropping oldest")
            # Drop oldest to make room
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(job)
                job._db_id = db_id
                self._enqueued_count += 1
                return True
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                self._update_job_status(db_id, "failed")
                self._error_count += 1
                return False

    def _persist_job(self, job: ExtractionJob, status: str) -> int | None:
        try:
            turn = job.turn
            item_data = json.dumps({
                "user_message": turn.user_message,
                "assistant_response": turn.assistant_response,
                "user_id": turn.user_id,
                "session_id": turn.session_id,
                "channel": turn.channel,
                "recent_context": turn.recent_context,
                "timestamp": turn.timestamp.isoformat(),
                "gate_score": job.gate_score,
            })
            conn = _get_connection()
            cursor = conn.execute(
                "INSERT INTO queue_items (item_data, status) VALUES (?, ?)",
                (item_data, status),
            )
            conn.commit()
            db_id = cursor.lastrowid
            conn.close()
            return db_id
        except Exception as e:
            logger.debug(f"Failed to persist extraction job: {e}")
            return None

    def _update_job_status(self, db_id: int | None, status: str) -> None:
        if db_id is None:
            return
        try:
            conn = _get_connection()
            conn.execute(
                "UPDATE queue_items SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.now().isoformat(), db_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to update job status: {e}")

    async def recover(self) -> int:
        try:
            conn = _get_connection()
            cursor = conn.execute(
                "SELECT id, item_data FROM queue_items WHERE status IN ('pending', 'processing')"
            )
            rows = cursor.fetchall()
            conn.close()

            recovered = 0
            for row in rows:
                try:
                    data = json.loads(row["item_data"])
                    turn = ConversationTurn(
                        user_message=data["user_message"],
                        assistant_response=data["assistant_response"],
                        user_id=data["user_id"],
                        session_id=data.get("session_id"),
                        channel=data.get("channel", "direct"),
                        recent_context=data.get("recent_context", []),
                        timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
                    )
                    job = ExtractionJob(
                        turn=turn,
                        gate_score=data.get("gate_score", 0.0),
                    )
                    job._db_id = row["id"]

                    try:
                        self._queue.put_nowait(job)
                        self._update_job_status(row["id"], "pending")
                        recovered += 1
                    except asyncio.QueueFull:
                        break
                except Exception as e:
                    logger.debug(f"Failed to recover job {row['id']}: {e}")
                    self._update_job_status(row["id"], "failed")

            if recovered > 0:
                logger.info(f"Recovered {recovered} extraction jobs from crash")
            return recovered
        except Exception as e:
            logger.warning(f"Failed to recover extraction queue: {e}")
            return 0

    async def run(self) -> None:
        """Background loop that processes the queue."""
        self._running = True
        logger.info("Extraction queue started")

        while self._running:
            batch: list[ExtractionJob] = []

            try:
                # Collect up to batch_size items or wait for flush interval
                while len(batch) < self._batch_size:
                    try:
                        job = await asyncio.wait_for(
                            self._queue.get(),
                            timeout=self._flush_interval,
                        )
                        batch.append(job)
                    except asyncio.TimeoutError:
                        break  # Flush what we have
            except asyncio.CancelledError:
                break

            if batch:
                await self._process_batch(batch)

        logger.info("Extraction queue stopped")

    async def stop(self) -> None:
        """Stop the queue processing loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def flush(self) -> int:
        """
        Process all remaining items in the queue immediately.

        Returns:
            Number of items flushed
        """
        batch: list[ExtractionJob] = []
        while not self._queue.empty():
            try:
                job = self._queue.get_nowait()
                batch.append(job)
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._process_batch(batch)

        return len(batch)

    def start_background(self) -> asyncio.Task:
        """Start the queue processing as a background task."""
        self._task = asyncio.create_task(self.run())
        return self._task

    async def _process_batch(self, batch: list[ExtractionJob]) -> None:
        """
        Extract and store memories from a batch of turns.

        Args:
            batch: List of extraction jobs to process
        """
        start_time = time.perf_counter()

        for job in batch:
            db_id = getattr(job, "_db_id", None)
            self._update_job_status(db_id, "processing")
            try:
                # Extract session notes using LLM
                notes = await extract_session_notes(
                    job.turn.user_message,
                    job.turn.assistant_response,
                    job.turn.session_id,
                    model=self._extraction_model,
                )

                if not notes:
                    self._processed_count += 1
                    self._update_job_status(db_id, "done")
                    continue

                # Store extracted notes
                if self._provider:
                    await self._store_notes(notes, job)

                # Extract commitments if detected in assistant response
                if has_commitment_language(job.turn.assistant_response or ""):
                    await self._extract_commitments(job)

                self._processed_count += 1
                self._update_job_status(db_id, "done")

            except Exception as e:
                self._error_count += 1
                self._update_job_status(db_id, "failed")
                logger.warning(f"Extraction failed for turn: {e}")
                # Non-fatal — memory extraction failures should never
                # impact the user experience

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"Processed batch of {len(batch)} turns in {duration_ms:.1f}ms "
            f"(total processed: {self._processed_count})"
        )

    async def _store_notes(
        self,
        notes: list,
        job: ExtractionJob,
    ) -> None:
        """
        Store extracted notes via the memory provider.

        For each note, checks for supersession against existing memories
        if the provider supports classify_update.

        Args:
            notes: List of ExtractedNote objects
            job: The extraction job context
        """
        for note in notes:
            try:
                # Check if provider supports supersession
                if hasattr(self._provider, "classify_update") and hasattr(self._provider, "search"):
                    # Search for similar existing memories
                    similar = await self._provider.search(
                        query=note.content,
                        limit=10,
                    )

                    if similar:
                        actions = await self._provider.classify_update(
                            note.content, similar
                        )
                        await self._apply_actions(actions, note, job)
                        continue

                # Default: add as session note
                if hasattr(self._provider, "add_session_note"):
                    await self._provider.add_session_note(
                        content=note.content,
                        session_id=job.turn.session_id or "unknown",
                        importance=note.importance,
                        metadata={
                            "type": note.note_type,
                            "user_id": job.turn.user_id,
                            "channel": job.turn.channel,
                            "gate_score": job.gate_score,
                            **note.metadata,
                        },
                    )
                elif hasattr(self._provider, "add"):
                    await self._provider.add(
                        content=note.content,
                        type=note.note_type.lower(),
                        importance=note.importance,
                        source="session",
                        tags=["extracted", note.note_type.lower()],
                        metadata={
                            "session_id": job.turn.session_id,
                            "user_id": job.turn.user_id,
                            "channel": job.turn.channel,
                            "gate_score": job.gate_score,
                        },
                    )
            except Exception as e:
                logger.warning(f"Failed to store note '{note.content[:50]}': {e}")

    async def _apply_actions(
        self,
        actions: list[dict],
        note: Any,
        job: ExtractionJob,
    ) -> None:
        """
        Apply AUDN classification actions.

        Args:
            actions: List of {action, memory_id, reason} dicts
            note: The ExtractedNote
            job: The extraction job context
        """
        for action_item in actions:
            action = action_item.get("action", "ADD").upper()

            if action == "NOOP":
                continue
            elif action == "ADD":
                if hasattr(self._provider, "add"):
                    await self._provider.add(
                        content=note.content,
                        type=note.note_type.lower(),
                        importance=note.importance,
                        source="session",
                        tags=["extracted", note.note_type.lower()],
                    )
            elif action == "UPDATE":
                memory_id = action_item.get("memory_id")
                if memory_id and hasattr(self._provider, "update"):
                    await self._provider.update(
                        memory_id,
                        content=note.content,
                        importance=note.importance,
                    )
            elif action == "SUPERSEDE":
                memory_id = action_item.get("memory_id")
                if memory_id and hasattr(self._provider, "supersede"):
                    await self._provider.supersede(
                        old_id=memory_id,
                        new_content=note.content,
                        reason=action_item.get("reason", "superseded by newer fact"),
                    )
                elif memory_id and hasattr(self._provider, "update"):
                    # Fallback: just update
                    await self._provider.update(
                        memory_id,
                        content=note.content,
                        importance=note.importance,
                    )

    async def _extract_commitments(self, job: ExtractionJob) -> None:
        """
        Extract and store commitments from a conversation turn.

        Uses the existing commitment extraction system.

        Args:
            job: The extraction job context
        """
        try:
            if hasattr(self._provider, "add_commitment"):
                from tools.memory.commitments import extract_commitments
                result = extract_commitments(
                    text=job.turn.assistant_response or "",
                    user_id=job.turn.user_id,
                )
                if result.get("success"):
                    logger.debug(
                        f"Extracted {result.get('data', {}).get('count', 0)} commitments"
                    )
        except Exception as e:
            logger.debug(f"Commitment extraction failed: {e}")
