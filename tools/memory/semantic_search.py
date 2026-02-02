"""
Tool: Semantic Memory Search
Purpose: Search memory entries by semantic similarity using vector embeddings

This implements Moltbot-style semantic memory search:
- Generate embedding for query
- Find most similar memories using cosine similarity
- Return ranked results with similarity scores

Usage:
    python tools/memory/semantic_search.py --query "image generation preferences"
    python tools/memory/semantic_search.py --query "what tools do I use" --limit 10
    python tools/memory/semantic_search.py --query "meeting notes" --type event
    python tools/memory/semantic_search.py --query "learned behavior" --threshold 0.7

Dependencies:
    - openai (for query embedding)
    - numpy (for cosine similarity)
    - sqlite3 (stdlib)

Env Vars:
    - OPENAI_API_KEY (required)

Output:
    JSON with ranked results and similarity scores
"""

import os
import sys
import json
import argparse
import struct
import math
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
try:
    from embed_memory import generate_embedding, bytes_to_embedding, get_openai_client
    from memory_db import get_connection
except ImportError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    sys.exit(1)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Similarity score between -1 and 1
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have same length")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def get_all_embeddings(
    entry_type: Optional[str] = None,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Get all memory entries with embeddings.

    Args:
        entry_type: Optional type filter
        active_only: Only get active entries

    Returns:
        List of entries with their embeddings
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = ['embedding IS NOT NULL']
    params = []

    if active_only:
        conditions.append('is_active = 1')

    if entry_type:
        conditions.append('type = ?')
        params.append(entry_type)

    where_clause = ' AND '.join(conditions)

    cursor.execute(f'''
        SELECT id, type, content, source, importance, embedding, created_at, tags
        FROM memory_entries
        WHERE {where_clause}
        ORDER BY importance DESC
    ''', params)

    entries = []
    for row in cursor.fetchall():
        entry = dict(row)
        # Convert embedding bytes to list
        if entry['embedding']:
            entry['embedding'] = bytes_to_embedding(entry['embedding'])
        entries.append(entry)

    conn.close()
    return entries


def semantic_search(
    query: str,
    entry_type: Optional[str] = None,
    limit: int = 10,
    threshold: float = 0.5,
    client=None
) -> Dict[str, Any]:
    """
    Search memories by semantic similarity.

    Args:
        query: Search query
        entry_type: Optional type filter
        limit: Maximum results to return
        threshold: Minimum similarity threshold (0-1)
        client: Optional OpenAI client

    Returns:
        dict with ranked results
    """
    # Generate query embedding
    embed_result = generate_embedding(query, client)
    if not embed_result.get('success'):
        return embed_result

    query_embedding = embed_result['embedding']

    # Get all entries with embeddings
    entries = get_all_embeddings(entry_type=entry_type)

    if not entries:
        return {
            "success": True,
            "query": query,
            "results": [],
            "message": "No entries with embeddings found"
        }

    # Calculate similarities
    scored_entries = []
    for entry in entries:
        if entry.get('embedding'):
            similarity = cosine_similarity(query_embedding, entry['embedding'])
            if similarity >= threshold:
                scored_entries.append({
                    "id": entry['id'],
                    "type": entry['type'],
                    "content": entry['content'],
                    "source": entry['source'],
                    "importance": entry['importance'],
                    "similarity": round(similarity, 4),
                    "created_at": entry['created_at'],
                    "tags": json.loads(entry['tags']) if entry['tags'] else None
                })

    # Sort by similarity (descending)
    scored_entries.sort(key=lambda x: x['similarity'], reverse=True)

    # Limit results
    results = scored_entries[:limit]

    return {
        "success": True,
        "query": query,
        "results": results,
        "total_searched": len(entries),
        "above_threshold": len(scored_entries),
        "returned": len(results),
        "threshold": threshold,
        "tokens_used": embed_result['usage']['total_tokens']
    }


def find_similar(
    entry_id: int,
    limit: int = 5,
    threshold: float = 0.6
) -> Dict[str, Any]:
    """
    Find entries similar to a specific entry.

    Args:
        entry_id: Source entry ID
        limit: Maximum results
        threshold: Minimum similarity

    Returns:
        dict with similar entries
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get source entry embedding
    cursor.execute('SELECT content, embedding FROM memory_entries WHERE id = ?', (entry_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Entry {entry_id} not found"}

    if not row['embedding']:
        conn.close()
        return {"success": False, "error": f"Entry {entry_id} has no embedding"}

    source_embedding = bytes_to_embedding(row['embedding'])
    source_content = row['content']
    conn.close()

    # Get all other entries
    entries = get_all_embeddings()

    # Calculate similarities (excluding source)
    scored = []
    for entry in entries:
        if entry['id'] != entry_id and entry.get('embedding'):
            similarity = cosine_similarity(source_embedding, entry['embedding'])
            if similarity >= threshold:
                scored.append({
                    "id": entry['id'],
                    "type": entry['type'],
                    "content": entry['content'],
                    "similarity": round(similarity, 4)
                })

    scored.sort(key=lambda x: x['similarity'], reverse=True)

    return {
        "success": True,
        "source_id": entry_id,
        "source_content": source_content,
        "similar_entries": scored[:limit],
        "total_compared": len(entries) - 1
    }


def main():
    parser = argparse.ArgumentParser(description='Semantic Memory Search')
    parser.add_argument('--query', help='Search query')
    parser.add_argument('--type', help='Filter by memory type')
    parser.add_argument('--limit', type=int, default=10, help='Maximum results')
    parser.add_argument('--threshold', type=float, default=0.5,
                       help='Minimum similarity threshold (0-1)')
    parser.add_argument('--similar-to', type=int, help='Find entries similar to this ID')

    args = parser.parse_args()

    result = None

    if args.similar_to:
        result = find_similar(
            entry_id=args.similar_to,
            limit=args.limit,
            threshold=args.threshold
        )

    elif args.query:
        result = semantic_search(
            query=args.query,
            entry_type=args.type,
            limit=args.limit,
            threshold=args.threshold
        )

    else:
        parser.print_help()
        sys.exit(0)

    if result:
        if result.get('success'):
            count = len(result.get('results', result.get('similar_entries', [])))
            print(f"OK Found {count} results")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
