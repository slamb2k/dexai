"""
Tool: Memory Embedding Generator
Purpose: Generate vector embeddings for memory entries to enable semantic search

Uses OpenAI's text-embedding-3-small model (1536 dimensions, ~$0.02/1M tokens)
Stores embeddings as BLOBs in SQLite for use with sqlite-vec or manual cosine similarity.

Usage:
    python tools/memory/embed_memory.py --all              # Embed all entries without embeddings
    python tools/memory/embed_memory.py --id 5             # Embed a specific entry
    python tools/memory/embed_memory.py --content "text"   # Get embedding for arbitrary text
    python tools/memory/embed_memory.py --stats            # Show embedding statistics
    python tools/memory/embed_memory.py --reindex          # Re-embed all entries

Dependencies:
    - openai
    - numpy (for serialization)
    - sqlite3 (stdlib)

Env Vars:
    - OPENAI_API_KEY (required)
    - HELICONE_API_KEY (optional, for observability)

Output:
    JSON result with success status and embedding info
"""

import os
import sys
import json
import argparse
import struct
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Check for OpenAI
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("Warning: openai package not installed. Run: pip install openai", file=sys.stderr)

# Import memory_db functions
sys.path.insert(0, str(Path(__file__).parent))
try:
    from memory_db import (
        get_entries_without_embeddings,
        store_embedding,
        get_entry,
        get_connection
    )
except ImportError:
    print("Error: Could not import memory_db", file=sys.stderr)
    sys.exit(1)

# Constants
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def get_openai_client():
    """Get OpenAI client with optional Helicone proxy."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    # Check for Helicone
    helicone_key = os.getenv('HELICONE_API_KEY')
    if helicone_key:
        return OpenAI(
            api_key=api_key,
            base_url="https://oai.helicone.ai/v1",
            default_headers={
                "Helicone-Auth": f"Bearer {helicone_key}",
                "Helicone-Property-Tool": "embed_memory"
            }
        )
    else:
        return OpenAI(api_key=api_key)


def embedding_to_bytes(embedding: List[float]) -> bytes:
    """Convert embedding list to bytes for storage."""
    return struct.pack(f'{len(embedding)}f', *embedding)


def bytes_to_embedding(data: bytes) -> List[float]:
    """Convert bytes back to embedding list."""
    count = len(data) // 4  # 4 bytes per float
    return list(struct.unpack(f'{count}f', data))


def generate_embedding(text: str, client=None) -> Dict[str, Any]:
    """
    Generate embedding for a text string.

    Args:
        text: Text to embed
        client: Optional OpenAI client (creates one if not provided)

    Returns:
        dict with embedding and metadata
    """
    if not HAS_OPENAI:
        return {"success": False, "error": "openai package not installed"}

    if client is None:
        client = get_openai_client()

    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
            encoding_format="float"
        )

        embedding = response.data[0].embedding

        return {
            "success": True,
            "embedding": embedding,
            "model": EMBEDDING_MODEL,
            "dimensions": len(embedding),
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def embed_entry(entry_id: int, client=None) -> Dict[str, Any]:
    """
    Generate and store embedding for a memory entry.

    Args:
        entry_id: Memory entry ID
        client: Optional OpenAI client

    Returns:
        dict with success status
    """
    # Get the entry
    entry_result = get_entry(entry_id)
    if not entry_result.get('success'):
        return entry_result

    entry = entry_result['entry']
    content = entry.get('content', '')

    if not content:
        return {"success": False, "error": f"Entry {entry_id} has no content"}

    # Generate embedding
    embed_result = generate_embedding(content, client)
    if not embed_result.get('success'):
        return embed_result

    # Store embedding
    embedding_bytes = embedding_to_bytes(embed_result['embedding'])
    store_result = store_embedding(entry_id, embedding_bytes, EMBEDDING_MODEL)

    return {
        "success": store_result.get('success', False),
        "entry_id": entry_id,
        "content_preview": content[:100] + "..." if len(content) > 100 else content,
        "dimensions": embed_result['dimensions'],
        "tokens_used": embed_result['usage']['total_tokens'],
        "model": EMBEDDING_MODEL
    }


def embed_all_pending(batch_size: int = 50, client=None) -> Dict[str, Any]:
    """
    Embed all entries that don't have embeddings yet.

    Args:
        batch_size: Number of entries to process
        client: Optional OpenAI client

    Returns:
        dict with batch results
    """
    if client is None:
        client = get_openai_client()

    # Get entries without embeddings
    pending = get_entries_without_embeddings(limit=batch_size)
    if not pending.get('success'):
        return pending

    entries = pending.get('entries', [])
    if not entries:
        return {"success": True, "message": "No entries need embedding", "processed": 0}

    results = {
        "success": True,
        "processed": 0,
        "failed": 0,
        "total_tokens": 0,
        "entries": []
    }

    for entry in entries:
        entry_id = entry['id']
        result = embed_entry(entry_id, client)

        if result.get('success'):
            results['processed'] += 1
            results['total_tokens'] += result.get('tokens_used', 0)
        else:
            results['failed'] += 1

        results['entries'].append({
            "id": entry_id,
            "success": result.get('success', False),
            "error": result.get('error')
        })

    # Calculate cost (~$0.02 per 1M tokens)
    results['estimated_cost'] = f"${results['total_tokens'] * 0.00002:.6f}"

    return results


def reindex_all(batch_size: int = 100, client=None) -> Dict[str, Any]:
    """
    Re-embed all entries (regenerate all embeddings).

    Args:
        batch_size: Number of entries to process per batch
        client: Optional OpenAI client

    Returns:
        dict with reindex results
    """
    if client is None:
        client = get_openai_client()

    conn = get_connection()
    cursor = conn.cursor()

    # Clear existing embeddings
    cursor.execute('UPDATE memory_entries SET embedding = NULL, embedding_model = NULL')
    conn.commit()
    conn.close()

    # Now embed all
    return embed_all_pending(batch_size=batch_size, client=client)


def get_embedding_stats() -> Dict[str, Any]:
    """Get statistics about embeddings in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Total entries
    cursor.execute('SELECT COUNT(*) as total FROM memory_entries WHERE is_active = 1')
    total = cursor.fetchone()['total']

    # With embeddings
    cursor.execute('SELECT COUNT(*) as count FROM memory_entries WHERE embedding IS NOT NULL AND is_active = 1')
    with_embeddings = cursor.fetchone()['count']

    # Without embeddings
    cursor.execute('SELECT COUNT(*) as count FROM memory_entries WHERE embedding IS NULL AND is_active = 1')
    without_embeddings = cursor.fetchone()['count']

    # By model
    cursor.execute('''
        SELECT embedding_model, COUNT(*) as count
        FROM memory_entries
        WHERE embedding IS NOT NULL AND is_active = 1
        GROUP BY embedding_model
    ''')
    by_model = {row['embedding_model']: row['count'] for row in cursor.fetchall()}

    # Average content length for entries with embeddings
    cursor.execute('''
        SELECT AVG(LENGTH(content)) as avg_length
        FROM memory_entries
        WHERE embedding IS NOT NULL AND is_active = 1
    ''')
    avg_length = cursor.fetchone()['avg_length'] or 0

    conn.close()

    return {
        "success": True,
        "stats": {
            "total_active_entries": total,
            "with_embeddings": with_embeddings,
            "without_embeddings": without_embeddings,
            "coverage_percent": round(with_embeddings / total * 100, 1) if total > 0 else 0,
            "by_model": by_model,
            "avg_content_length": round(avg_length, 0)
        }
    }


def main():
    parser = argparse.ArgumentParser(description='Memory Embedding Generator')
    parser.add_argument('--all', action='store_true', help='Embed all entries without embeddings')
    parser.add_argument('--id', type=int, help='Embed a specific entry by ID')
    parser.add_argument('--content', help='Get embedding for arbitrary text (returns JSON)')
    parser.add_argument('--reindex', action='store_true', help='Re-embed all entries')
    parser.add_argument('--stats', action='store_true', help='Show embedding statistics')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size for --all')

    args = parser.parse_args()

    result = None

    if args.stats:
        result = get_embedding_stats()

    elif args.content:
        # Just get embedding for text
        if not HAS_OPENAI:
            print("Error: openai package not installed")
            sys.exit(1)
        result = generate_embedding(args.content)
        # Don't print full embedding, just metadata
        if result.get('success'):
            result['embedding_preview'] = result['embedding'][:5] + ['...']
            del result['embedding']

    elif args.id:
        result = embed_entry(args.id)

    elif args.reindex:
        print("Re-indexing all entries (this will clear existing embeddings)...")
        result = reindex_all(batch_size=args.batch_size)

    elif args.all:
        result = embed_all_pending(batch_size=args.batch_size)

    else:
        parser.print_help()
        sys.exit(0)

    if result:
        if result.get('success'):
            print(f"OK {result.get('message', 'Success')}")
        else:
            print(f"ERROR {result.get('error', 'Unknown error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
