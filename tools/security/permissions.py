"""
Tool: Permission System
Purpose: Role-based access control for all operations

Features:
- 5 default roles: guest, user, power_user, admin, owner
- Permission check before every action
- Elevation prompts for sensitive ops
- Custom role creation
- Permission inheritance through role priority

Usage:
    python tools/security/permissions.py --check --user alice --permission "memory:write"
    python tools/security/permissions.py --grant --user bob --role power_user
    python tools/security/permissions.py --revoke --user bob --role power_user
    python tools/security/permissions.py --list-roles
    python tools/security/permissions.py --user-roles --user alice
    python tools/security/permissions.py --create-role --name "beta_tester" --permissions '["memory:read", "experimental:*"]'

Permission Format:
    resource:action
    Examples: memory:read, memory:write, secrets:access, admin:users, *:* (owner only)

Dependencies:
    - sqlite3 (stdlib)
    - fnmatch (stdlib) for wildcard matching
"""

import argparse
import fnmatch
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Database path
DB_PATH = Path(__file__).parent.parent.parent / "data" / "permissions.db"

# Default roles with their permissions (priority determines inheritance order)
DEFAULT_ROLES = {
    "guest": {
        "description": "Limited read-only access",
        "priority": 0,
        "permissions": ["memory:read", "help:*"],
    },
    "user": {
        "description": "Standard user with basic write access",
        "priority": 10,
        "permissions": [
            "memory:read",
            "memory:write",
            "chat:*",
            "help:*",
            "files:read",
            "files:write",
        ],
    },
    "power_user": {
        "description": "Advanced user with extended capabilities",
        "priority": 20,
        "permissions": [
            "memory:*",
            "chat:*",
            "help:*",
            "tools:execute",
            "experimental:*",
            "files:*",
            "system:execute",
            "network:request",
            "automation:read",
            "automation:execute",
        ],
    },
    "admin": {
        "description": "Administrator with management capabilities",
        "priority": 30,
        "permissions": [
            "memory:*",
            "chat:*",
            "help:*",
            "tools:*",
            "users:read",
            "users:manage",
            "audit:read",
            "settings:read",
            "settings:write",
            "files:*",
            "system:*",
            "network:*",
            "browser:*",
            "automation:*",
        ],
    },
    "owner": {
        "description": "Full system access",
        "priority": 100,
        "permissions": [
            "*:*"  # Superuser - all permissions
        ],
    },
}

# Actions that require elevation (re-authentication or confirmation)
ELEVATED_ACTIONS = ["users:delete", "secrets:*", "admin:*", "settings:write", "audit:delete"]


def get_connection():
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Roles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            permissions TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_system INTEGER DEFAULT 0
        )
    """)

    # User roles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role_name TEXT NOT NULL,
            granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            granted_by TEXT,
            expires_at DATETIME,
            UNIQUE(user_id, role_name),
            FOREIGN KEY (role_name) REFERENCES roles(name)
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_name)")

    conn.commit()

    # Initialize default roles if not present
    _init_default_roles(conn)

    return conn


def _init_default_roles(conn):
    """Initialize default roles if they don't exist."""
    cursor = conn.cursor()

    for role_name, role_data in DEFAULT_ROLES.items():
        cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        if not cursor.fetchone():
            cursor.execute(
                """
                INSERT INTO roles (name, description, permissions, priority, is_system)
                VALUES (?, ?, ?, ?, 1)
            """,
                (
                    role_name,
                    role_data["description"],
                    json.dumps(role_data["permissions"]),
                    role_data["priority"],
                ),
            )

    conn.commit()


def permission_matches(user_perm: str, required_perm: str) -> bool:
    """
    Check if a user permission matches a required permission.
    Supports wildcards: memory:* matches memory:read, *:* matches everything.
    """
    # Exact match
    if user_perm == required_perm:
        return True

    # Superuser check
    if user_perm == "*:*":
        return True

    # Split into resource:action
    user_parts = user_perm.split(":")
    req_parts = required_perm.split(":")

    if len(user_parts) != 2 or len(req_parts) != 2:
        return False

    user_resource, user_action = user_parts
    req_resource, req_action = req_parts

    # Resource match (exact or wildcard)
    resource_match = (
        user_resource == req_resource
        or user_resource == "*"
        or fnmatch.fnmatch(req_resource, user_resource)
    )

    # Action match (exact or wildcard)
    action_match = (
        user_action == req_action or user_action == "*" or fnmatch.fnmatch(req_action, user_action)
    )

    return resource_match and action_match


def get_user_permissions(user_id: str) -> list[str]:
    """Get all permissions for a user based on their roles."""
    conn = get_connection()
    cursor = conn.cursor()

    # Get all active roles for user
    cursor.execute(
        """
        SELECT r.permissions, r.priority
        FROM user_roles ur
        JOIN roles r ON ur.role_name = r.name
        WHERE ur.user_id = ?
        AND (ur.expires_at IS NULL OR ur.expires_at > datetime('now'))
        ORDER BY r.priority DESC
    """,
        (user_id,),
    )

    all_permissions = set()
    for row in cursor.fetchall():
        perms = json.loads(row["permissions"])
        all_permissions.update(perms)

    conn.close()
    return list(all_permissions)


def check_permission(
    user_id: str, permission: str, session_id: str | None = None
) -> dict[str, Any]:
    """
    Check if a user has a specific permission.

    Args:
        user_id: User identifier
        permission: Permission string (e.g., "memory:write")
        session_id: Optional session for audit logging

    Returns:
        dict with allowed status and details
    """
    user_permissions = get_user_permissions(user_id)

    # Check if any user permission matches
    has_permission = any(permission_matches(up, permission) for up in user_permissions)

    # Check if this is an elevated action
    requires_elevation = any(permission_matches(ea, permission) for ea in ELEVATED_ACTIONS)

    # Log the check
    try:
        from . import audit

        audit.log_event(
            event_type="permission",
            action="check",
            user_id=user_id,
            session_id=session_id,
            resource=permission,
            status="success" if has_permission else "failure",
        )
    except Exception:
        pass

    # Log to dashboard audit if permission denied
    if not has_permission:
        try:
            from tools.dashboard.backend.database import log_audit

            log_audit(
                event_type="permission.denied",
                severity="warning",
                actor=user_id,
                target=permission,
                details={"user_permissions": user_permissions},
            )
        except Exception:
            pass

    return {
        "success": True,
        "allowed": has_permission,
        "permission": permission,
        "user_id": user_id,
        "requires_elevation": requires_elevation and has_permission,
        "user_permissions": user_permissions,
    }


def grant_role(
    user_id: str, role_name: str, granted_by: str | None = None, expires_at: str | None = None
) -> dict[str, Any]:
    """
    Grant a role to a user.

    Args:
        user_id: User to grant role to
        role_name: Role to grant
        granted_by: Who is granting the role
        expires_at: Optional expiration datetime

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check role exists
    cursor.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    if not cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Role '{role_name}' does not exist"}

    # Grant role (upsert)
    cursor.execute(
        """
        INSERT INTO user_roles (user_id, role_name, granted_by, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, role_name) DO UPDATE SET
            granted_by = excluded.granted_by,
            granted_at = CURRENT_TIMESTAMP,
            expires_at = excluded.expires_at
    """,
        (user_id, role_name, granted_by, expires_at),
    )

    conn.commit()
    conn.close()

    # Log the grant
    try:
        from . import audit

        audit.log_event(
            event_type="permission",
            action="grant_role",
            user_id=granted_by,
            resource=f"{user_id}:{role_name}",
            status="success",
        )
    except Exception:
        pass

    return {
        "success": True,
        "user_id": user_id,
        "role": role_name,
        "message": f"Role '{role_name}' granted to user '{user_id}'",
    }


def revoke_role(user_id: str, role_name: str, revoked_by: str | None = None) -> dict[str, Any]:
    """Revoke a role from a user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM user_roles WHERE user_id = ? AND role_name = ?", (user_id, role_name)
    )

    if cursor.rowcount == 0:
        conn.close()
        return {"success": False, "error": f"User '{user_id}' does not have role '{role_name}'"}

    conn.commit()
    conn.close()

    # Log the revoke
    try:
        from . import audit

        audit.log_event(
            event_type="permission",
            action="revoke_role",
            user_id=revoked_by,
            resource=f"{user_id}:{role_name}",
            status="success",
        )
    except Exception:
        pass

    return {
        "success": True,
        "user_id": user_id,
        "role": role_name,
        "message": f"Role '{role_name}' revoked from user '{user_id}'",
    }


def get_user_roles(user_id: str) -> dict[str, Any]:
    """Get all roles for a user."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ur.role_name, ur.granted_at, ur.granted_by, ur.expires_at,
               r.description, r.priority
        FROM user_roles ur
        JOIN roles r ON ur.role_name = r.name
        WHERE ur.user_id = ?
        ORDER BY r.priority DESC
    """,
        (user_id,),
    )

    roles = []
    for row in cursor.fetchall():
        roles.append(
            {
                "role": row["role_name"],
                "description": row["description"],
                "priority": row["priority"],
                "granted_at": row["granted_at"],
                "granted_by": row["granted_by"],
                "expires_at": row["expires_at"],
                "active": row["expires_at"] is None
                or row["expires_at"] > datetime.now().isoformat(),
            }
        )

    conn.close()

    return {
        "success": True,
        "user_id": user_id,
        "roles": roles,
        "permissions": get_user_permissions(user_id),
    }


def list_roles() -> dict[str, Any]:
    """List all available roles."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, description, permissions, priority, is_system, created_at
        FROM roles
        ORDER BY priority ASC
    """)

    roles = []
    for row in cursor.fetchall():
        roles.append(
            {
                "name": row["name"],
                "description": row["description"],
                "permissions": json.loads(row["permissions"]),
                "priority": row["priority"],
                "is_system": bool(row["is_system"]),
                "created_at": row["created_at"],
            }
        )

    conn.close()

    return {"success": True, "roles": roles, "count": len(roles)}


def create_role(
    name: str, permissions: list[str], description: str | None = None, priority: int = 15
) -> dict[str, Any]:
    """
    Create a custom role.

    Args:
        name: Role name (must be unique)
        permissions: List of permission strings
        description: Role description
        priority: Role priority (higher = more privileged)

    Returns:
        dict with success status
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if role exists
    cursor.execute("SELECT id FROM roles WHERE name = ?", (name,))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "error": f"Role '{name}' already exists"}

    # Validate permissions format
    for perm in permissions:
        if ":" not in perm:
            conn.close()
            return {
                "success": False,
                "error": f"Invalid permission format: '{perm}'. Must be 'resource:action'",
            }

    cursor.execute(
        """
        INSERT INTO roles (name, description, permissions, priority, is_system)
        VALUES (?, ?, ?, ?, 0)
    """,
        (name, description, json.dumps(permissions), priority),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "role": name,
        "permissions": permissions,
        "message": f"Role '{name}' created",
    }


def delete_role(name: str) -> dict[str, Any]:
    """Delete a custom role (cannot delete system roles)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if system role
    cursor.execute("SELECT is_system FROM roles WHERE name = ?", (name,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": f"Role '{name}' not found"}

    if row["is_system"]:
        conn.close()
        return {"success": False, "error": f"Cannot delete system role '{name}'"}

    # Remove role from all users first
    cursor.execute("DELETE FROM user_roles WHERE role_name = ?", (name,))

    # Delete role
    cursor.execute("DELETE FROM roles WHERE name = ?", (name,))

    conn.commit()
    conn.close()

    return {"success": True, "role": name, "message": f"Role '{name}' deleted"}


def main():
    parser = argparse.ArgumentParser(description="Permission System")
    parser.add_argument("--check", action="store_true", help="Check if user has permission")
    parser.add_argument("--grant", action="store_true", help="Grant role to user")
    parser.add_argument("--revoke", action="store_true", help="Revoke role from user")
    parser.add_argument("--list-roles", action="store_true", help="List all roles")
    parser.add_argument("--user-roles", action="store_true", help="Get roles for a user")
    parser.add_argument("--create-role", action="store_true", help="Create a new role")
    parser.add_argument("--delete-role", action="store_true", help="Delete a role")

    parser.add_argument("--user", help="User ID")
    parser.add_argument("--permission", help="Permission to check")
    parser.add_argument("--role", help="Role name")
    parser.add_argument("--name", help="Role name (for create)")
    parser.add_argument("--permissions", help="JSON array of permissions")
    parser.add_argument("--description", help="Role description")
    parser.add_argument(
        "--priority", type=int, default=15, help="Role priority (higher = more privileged)"
    )
    parser.add_argument("--granted-by", help="Who is granting the role")
    parser.add_argument("--expires", help="Role expiration (ISO datetime)")

    args = parser.parse_args()
    result = None

    if args.check:
        if not args.user or not args.permission:
            print("Error: --user and --permission required for check")
            sys.exit(1)
        result = check_permission(args.user, args.permission)

    elif args.grant:
        if not args.user or not args.role:
            print("Error: --user and --role required for grant")
            sys.exit(1)
        result = grant_role(
            user_id=args.user,
            role_name=args.role,
            granted_by=args.granted_by,
            expires_at=args.expires,
        )

    elif args.revoke:
        if not args.user or not args.role:
            print("Error: --user and --role required for revoke")
            sys.exit(1)
        result = revoke_role(args.user, args.role, args.granted_by)

    elif args.list_roles:
        result = list_roles()

    elif args.user_roles:
        if not args.user:
            print("Error: --user required for user-roles")
            sys.exit(1)
        result = get_user_roles(args.user)

    elif args.create_role:
        if not args.name or not args.permissions:
            print("Error: --name and --permissions required for create-role")
            sys.exit(1)
        try:
            permissions = json.loads(args.permissions)
        except json.JSONDecodeError:
            print("Error: --permissions must be a valid JSON array")
            sys.exit(1)
        result = create_role(
            name=args.name,
            permissions=permissions,
            description=args.description,
            priority=args.priority,
        )

    elif args.delete_role:
        if not args.name:
            print("Error: --name required for delete-role")
            sys.exit(1)
        result = delete_role(args.name)

    else:
        print("Error: Must specify an action")
        sys.exit(1)

    if result.get("success"):
        if result.get("allowed") is False:
            print(f"DENIED Permission '{result.get('permission')}' not granted")
        else:
            print(f"OK {result.get('message', 'Success')}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
