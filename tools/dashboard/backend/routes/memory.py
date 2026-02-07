"""
Memory API Routes

Provides endpoints for memory-related functionality:
- GET /api/memory/search - Hybrid search across memories
- GET /api/memory/commitments - List active commitments
- GET /api/memory/contexts - List context snapshots
- GET /api/memory/providers - Memory provider status
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    content: str
    score: float
    entry_type: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None


class SearchResponse(BaseModel):
    """Response from memory search."""

    query: str
    results: list[SearchResult]
    total: int
    method: str = "hybrid"


class Commitment(BaseModel):
    """An active commitment."""

    id: str
    content: str
    target_person: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "active"
    created_at: str
    source: Optional[str] = None


class CommitmentsResponse(BaseModel):
    """Response for commitments list."""

    commitments: list[Commitment]
    total: int


class ContextSnapshot(BaseModel):
    """A saved context snapshot."""

    id: str
    title: str
    summary: Optional[str] = None
    task_description: Optional[str] = None
    created_at: str
    restored_at: Optional[str] = None


class ContextsResponse(BaseModel):
    """Response for context snapshots."""

    contexts: list[ContextSnapshot]
    total: int


class MemoryProvider(BaseModel):
    """Status of a memory provider."""

    name: str
    status: str  # active, inactive, error
    is_primary: bool = False
    storage_used: Optional[str] = None
    health_score: Optional[int] = None
    last_sync: Optional[str] = None
    error: Optional[str] = None


class ProvidersResponse(BaseModel):
    """Response for memory providers status."""

    providers: list[MemoryProvider]
    active_count: int
    primary_provider: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/search", response_model=SearchResponse)
async def search_memory(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    method: str = Query("hybrid", description="Search method: hybrid, semantic, keyword"),
):
    """
    Search memories using hybrid search (BM25 + semantic).

    Searches across all memory types including facts, preferences,
    events, and commitments.
    """
    try:
        # Try to use the hybrid search tool
        from tools.memory.hybrid_search import hybrid_search

        result = hybrid_search(query=q, limit=limit)

        if result.get("success"):
            results = []
            for r in result.get("results", []):
                results.append(
                    SearchResult(
                        id=str(r.get("id", "")),
                        content=r.get("content", ""),
                        score=r.get("combined_score", r.get("score", 0.0)),
                        entry_type=r.get("entry_type"),
                        source=r.get("source"),
                        created_at=r.get("created_at"),
                    )
                )

            return SearchResponse(
                query=q,
                results=results,
                total=len(results),
                method=method,
            )

    except ImportError:
        logger.warning("Hybrid search module not available")
    except Exception as e:
        logger.error(f"Search error: {e}")

    # Fallback: try direct database search
    try:
        from tools.memory.memory_db import search_memories

        result = search_memories(query=q, limit=limit)
        if result.get("success"):
            results = []
            for r in result.get("entries", []):
                results.append(
                    SearchResult(
                        id=str(r.get("id", "")),
                        content=r.get("content", ""),
                        score=0.5,  # No score from basic search
                        entry_type=r.get("entry_type"),
                        created_at=r.get("created_at"),
                    )
                )

            return SearchResponse(
                query=q,
                results=results,
                total=len(results),
                method="keyword",
            )
    except Exception:
        pass

    # Empty fallback
    return SearchResponse(query=q, results=[], total=0, method=method)


@router.get("/commitments", response_model=CommitmentsResponse)
async def list_commitments(
    status: str = Query("active", description="Filter by status: active, completed, all"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
):
    """
    List commitments (things waiting on you).

    Uses RSD-safe language - "waiting on you" not "overdue".
    """
    try:
        from tools.memory.commitments import list_commitments as get_commitments

        result = get_commitments(
            user_id=user_id,
            status=status if status != "all" else None,
            limit=limit,
        )

        if result.get("success"):
            data = result.get("data", {})
            commitment_list = data.get("commitments", [])

            return CommitmentsResponse(
                commitments=[
                    Commitment(
                        id=str(c.get("id", "")),
                        content=c.get("content", ""),
                        target_person=c.get("target_person"),
                        due_date=c.get("due_date"),
                        status=c.get("status", "active"),
                        created_at=c.get("created_at", datetime.now().isoformat()),
                        source=c.get("source"),
                    )
                    for c in commitment_list
                ],
                total=data.get("total", len(commitment_list)),
            )

    except ImportError:
        logger.warning("Commitments module not available")
    except Exception as e:
        logger.error(f"Error listing commitments: {e}")

    return CommitmentsResponse(commitments=[], total=0)


@router.get("/commitments/count")
async def count_commitments(
    user_id: Optional[str] = Query(None, description="Filter by user"),
):
    """
    Get count of active commitments.

    Useful for badges and quick status checks.
    """
    try:
        from tools.memory.commitments import list_commitments as get_commitments

        result = get_commitments(user_id=user_id, status="active", limit=100)

        if result.get("success"):
            data = result.get("data", {})
            return {"count": data.get("total", 0)}

    except Exception:
        pass

    return {"count": 0}


@router.get("/contexts", response_model=ContextsResponse)
async def list_context_snapshots(
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
):
    """
    List saved context snapshots.

    Context snapshots allow resuming work after interruptions.
    """
    try:
        from tools.memory.context_capture import list_contexts

        result = list_contexts(user_id=user_id, limit=limit)

        if result.get("success"):
            contexts = result.get("contexts", [])

            return ContextsResponse(
                contexts=[
                    ContextSnapshot(
                        id=str(c.get("id", "")),
                        title=c.get("title", "Untitled context"),
                        summary=c.get("summary"),
                        task_description=c.get("task_description"),
                        created_at=c.get("created_at", datetime.now().isoformat()),
                        restored_at=c.get("restored_at"),
                    )
                    for c in contexts
                ],
                total=len(contexts),
            )

    except ImportError:
        logger.warning("Context capture module not available")
    except Exception as e:
        logger.error(f"Error listing contexts: {e}")

    return ContextsResponse(contexts=[], total=0)


@router.post("/contexts/{context_id}/restore")
async def restore_context(context_id: str):
    """
    Restore a saved context snapshot.

    Returns the context data for the frontend to display.
    """
    try:
        from tools.memory.context_capture import restore_context as do_restore

        result = do_restore(context_id=context_id)

        if result.get("success"):
            return {
                "success": True,
                "context": result.get("context", {}),
            }

        raise HTTPException(
            status_code=404,
            detail=result.get("error", "Context not found"),
        )

    except ImportError:
        raise HTTPException(status_code=501, detail="Context capture not available")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers", response_model=ProvidersResponse)
async def get_memory_providers():
    """
    Get status of configured memory providers.

    Shows health and storage usage for each provider.
    """
    providers = []
    primary_provider = None
    active_count = 0

    # Check Native provider (always available)
    try:
        from tools.memory.memory_db import get_connection

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM memory_entries")
        count = cursor.fetchone()["count"]
        conn.close()

        providers.append(
            MemoryProvider(
                name="Native",
                status="active",
                is_primary=True,
                storage_used=f"{count} entries",
                health_score=100,
            )
        )
        primary_provider = "Native"
        active_count += 1

    except Exception as e:
        providers.append(
            MemoryProvider(
                name="Native",
                status="error",
                is_primary=True,
                error=str(e),
            )
        )

    # Check for Mem0 provider
    try:
        from tools.memory.providers.mem0_provider import Mem0Provider
        import os

        if os.getenv("MEM0_API_KEY"):
            providers.append(
                MemoryProvider(
                    name="Mem0",
                    status="active",
                    is_primary=False,
                    health_score=98,
                )
            )
            active_count += 1
        else:
            providers.append(
                MemoryProvider(
                    name="Mem0",
                    status="inactive",
                    is_primary=False,
                )
            )

    except ImportError:
        providers.append(
            MemoryProvider(
                name="Mem0",
                status="inactive",
                is_primary=False,
            )
        )

    # Check for Zep provider
    try:
        from tools.memory.providers.zep_provider import ZepProvider
        import os

        if os.getenv("ZEP_API_KEY"):
            providers.append(
                MemoryProvider(
                    name="Zep",
                    status="active",
                    is_primary=False,
                    health_score=95,
                )
            )
            active_count += 1
        else:
            providers.append(
                MemoryProvider(
                    name="Zep",
                    status="inactive",
                    is_primary=False,
                )
            )

    except ImportError:
        providers.append(
            MemoryProvider(
                name="Zep",
                status="inactive",
                is_primary=False,
            )
        )

    return ProvidersResponse(
        providers=providers,
        active_count=active_count,
        primary_provider=primary_provider,
    )
