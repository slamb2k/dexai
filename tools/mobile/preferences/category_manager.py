"""
Tool: Notification Category Manager
Purpose: Manage notification categories and their default settings

Usage:
    from tools.mobile.preferences.category_manager import (
        get_categories,
        get_category,
        create_category,
        update_category,
        seed_default_categories,
    )
"""

import asyncio
from datetime import datetime
from typing import Any

from tools.mobile import get_connection
from tools.mobile.models import NotificationCategory, DEFAULT_CATEGORIES


async def get_categories() -> list[dict]:
    """
    List all notification categories.

    Returns:
        List of category dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM notification_categories ORDER BY name"
    )

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


async def get_category(category_id: str) -> dict | None:
    """
    Get a single category by ID.

    Args:
        category_id: The category ID

    Returns:
        Category dict or None
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM notification_categories WHERE id = ?",
        (category_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return dict(row)


async def create_category(
    category_id: str,
    name: str,
    description: str | None = None,
    default_priority: int = 5,
    default_icon: str | None = None,
    color: str | None = None,
    can_batch: bool = True,
    can_suppress: bool = True,
) -> dict:
    """
    Create a new notification category.

    Args:
        category_id: Unique category ID (e.g., 'task_reminder')
        name: Display name
        description: Description of the category
        default_priority: Default priority for notifications in this category
        default_icon: Icon identifier
        color: Hex color for UI
        can_batch: Whether notifications can be batched
        can_suppress: Whether flow state can suppress notifications

    Returns:
        {"success": True, "category": dict} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO notification_categories
            (id, name, description, default_priority, default_icon, color, can_batch, can_suppress, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id,
                name,
                description,
                default_priority,
                default_icon,
                color,
                can_batch,
                can_suppress,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        category = await get_category(category_id)
        return {"success": True, "category": category}

    except Exception as e:
        conn.close()
        if "UNIQUE constraint failed" in str(e):
            return {"success": False, "error": f"Category '{category_id}' already exists"}
        return {"success": False, "error": str(e)}


async def update_category(
    category_id: str,
    name: str | None = None,
    description: str | None = None,
    default_priority: int | None = None,
    default_icon: str | None = None,
    color: str | None = None,
    can_batch: bool | None = None,
    can_suppress: bool | None = None,
) -> dict:
    """
    Update an existing category.

    Args:
        category_id: The category ID
        **kwargs: Fields to update

    Returns:
        {"success": True, "category": dict} or {"success": False, "error": str}
    """
    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if default_priority is not None:
        updates["default_priority"] = default_priority
    if default_icon is not None:
        updates["default_icon"] = default_icon
    if color is not None:
        updates["color"] = color
    if can_batch is not None:
        updates["can_batch"] = can_batch
    if can_suppress is not None:
        updates["can_suppress"] = can_suppress

    if not updates:
        return {"success": False, "error": "No updates provided"}

    conn = get_connection()
    cursor = conn.cursor()

    set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [category_id]

    try:
        cursor.execute(
            f"UPDATE notification_categories SET {set_clauses} WHERE id = ?",
            values,
        )

        if cursor.rowcount == 0:
            conn.close()
            return {"success": False, "error": "Category not found"}

        conn.commit()
        conn.close()

        category = await get_category(category_id)
        return {"success": True, "category": category}

    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


async def delete_category(category_id: str) -> dict:
    """
    Delete a category.

    Note: This doesn't delete notifications in that category.

    Args:
        category_id: The category ID

    Returns:
        {"success": True} or {"success": False, "error": str}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM notification_categories WHERE id = ?",
        (category_id,),
    )

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": "Category not found"}

    conn.commit()
    conn.close()
    return {"success": True}


def seed_default_categories() -> dict:
    """
    Initialize default notification categories.

    Safe to call multiple times - won't overwrite existing categories.

    Returns:
        {"success": True, "created": int, "skipped": int}
    """
    conn = get_connection()
    cursor = conn.cursor()

    created = 0
    skipped = 0

    for category in DEFAULT_CATEGORIES:
        # Check if exists
        cursor.execute(
            "SELECT id FROM notification_categories WHERE id = ?",
            (category.id,),
        )

        if cursor.fetchone():
            skipped += 1
            continue

        # Create category
        cat_dict = category.to_dict()
        cursor.execute(
            """
            INSERT INTO notification_categories
            (id, name, description, default_priority, default_icon, color, can_batch, can_suppress, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cat_dict["id"],
                cat_dict["name"],
                cat_dict["description"],
                cat_dict["default_priority"],
                cat_dict["default_icon"],
                cat_dict["color"],
                cat_dict["can_batch"],
                cat_dict["can_suppress"],
                cat_dict["created_at"],
            ),
        )
        created += 1

    conn.commit()
    conn.close()

    return {"success": True, "created": created, "skipped": skipped}


async def get_category_stats() -> dict:
    """
    Get statistics about categories and their notifications.

    Returns:
        Statistics dict
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get category counts
    cursor.execute(
        """
        SELECT
            c.id,
            c.name,
            COUNT(n.id) as notification_count,
            SUM(CASE WHEN n.status = 'pending' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN n.status = 'sent' THEN 1 ELSE 0 END) as sent_count
        FROM notification_categories c
        LEFT JOIN notification_queue n ON c.id = n.category
        GROUP BY c.id, c.name
        """
    )

    rows = cursor.fetchall()
    conn.close()

    return {
        "categories": [dict(row) for row in rows],
        "total_categories": len(rows),
    }


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Notification category management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List categories
    list_parser = subparsers.add_parser("list", help="List all categories")

    # Get category
    get_parser = subparsers.add_parser("get", help="Get a category")
    get_parser.add_argument("category_id", help="Category ID")

    # Seed defaults
    seed_parser = subparsers.add_parser("seed", help="Seed default categories")

    # Stats
    stats_parser = subparsers.add_parser("stats", help="Get category statistics")

    args = parser.parse_args()

    if args.command == "list":
        categories = asyncio.run(get_categories())
        print(f"Found {len(categories)} categories:")
        for cat in categories:
            print(f"  {cat['id']}: {cat['name']} (priority: {cat['default_priority']})")

    elif args.command == "get":
        category = asyncio.run(get_category(args.category_id))
        if category:
            print(json.dumps(category, indent=2))
        else:
            print(f"Category not found: {args.category_id}")

    elif args.command == "seed":
        result = seed_default_categories()
        print(f"Created: {result['created']}, Skipped: {result['skipped']}")

    elif args.command == "stats":
        stats = asyncio.run(get_category_stats())
        print(json.dumps(stats, indent=2))

    else:
        parser.print_help()
