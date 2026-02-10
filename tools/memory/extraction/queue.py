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
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tools.memory.extraction.gate import should_extract, has_commitment_language
from tools.memory.extraction.extractor import extract_session_notes

logger = logging.getLogger(__name__)


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
        the turn is silently skipped.

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

        try:
            self._queue.put_nowait(job)
            self._enqueued_count += 1
            logger.debug(f"Enqueued extraction job (score={score:.2f}, depth={self._queue.qsize()})")
            return True
        except asyncio.QueueFull:
            logger.warning(f"Extraction queue full ({self._queue.qsize()}), dropping oldest")
            # Drop oldest to make room
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(job)
                self._enqueued_count += 1
                return True
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                self._error_count += 1
                return False

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
                    continue

                # Store extracted notes
                if self._provider:
                    await self._store_notes(notes, job)

                # Extract commitments if detected in assistant response
                if has_commitment_language(job.turn.assistant_response or ""):
                    await self._extract_commitments(job)

                self._processed_count += 1

            except Exception as e:
                self._error_count += 1
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
