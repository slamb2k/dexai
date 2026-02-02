"""Tests for tools/security/permissions.py

The permission system provides role-based access control (RBAC) for all operations.
Key functionality:
- 5 default roles with increasing privileges
- Permission checking with wildcards
- Role grant/revoke
- Custom role creation

These tests ensure access control works correctly.
"""

from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Setup: Patch DB_PATH to use temp database
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def permissions_temp_db(temp_db):
    """Patch permissions module to use temporary database."""
    with patch("tools.security.permissions.DB_PATH", temp_db):
        from tools.security import permissions

        # Force table and default role creation
        conn = permissions.get_connection()
        conn.close()

        yield permissions


# ─────────────────────────────────────────────────────────────────────────────
# Permission Matching Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPermissionMatches:
    """Tests for permission_matches function."""

    def test_exact_match(self, permissions_temp_db):
        """Exact permission should match."""
        assert permissions_temp_db.permission_matches("memory:read", "memory:read") is True

    def test_exact_mismatch(self, permissions_temp_db):
        """Different permissions should not match."""
        assert permissions_temp_db.permission_matches("memory:read", "memory:write") is False

    def test_action_wildcard(self, permissions_temp_db):
        """Action wildcard should match any action."""
        assert permissions_temp_db.permission_matches("memory:*", "memory:read") is True
        assert permissions_temp_db.permission_matches("memory:*", "memory:write") is True
        assert permissions_temp_db.permission_matches("memory:*", "memory:delete") is True

    def test_superuser_wildcard(self, permissions_temp_db):
        """Superuser wildcard should match everything."""
        assert permissions_temp_db.permission_matches("*:*", "memory:read") is True
        assert permissions_temp_db.permission_matches("*:*", "admin:users") is True
        assert permissions_temp_db.permission_matches("*:*", "anything:here") is True

    def test_wildcard_does_not_match_different_resource(self, permissions_temp_db):
        """Action wildcard should not match different resource."""
        assert permissions_temp_db.permission_matches("memory:*", "files:read") is False

    def test_invalid_format(self, permissions_temp_db):
        """Invalid permission format should not match."""
        assert permissions_temp_db.permission_matches("invalid", "memory:read") is False
        assert permissions_temp_db.permission_matches("memory:read", "invalid") is False


# ─────────────────────────────────────────────────────────────────────────────
# Default Roles Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDefaultRoles:
    """Tests for default role initialization."""

    def test_default_roles_created(self, permissions_temp_db):
        """All default roles should be created."""
        result = permissions_temp_db.list_roles()

        assert result["success"] is True
        role_names = {r["name"] for r in result["roles"]}

        assert "guest" in role_names
        assert "user" in role_names
        assert "power_user" in role_names
        assert "admin" in role_names
        assert "owner" in role_names

    def test_roles_have_correct_priority(self, permissions_temp_db):
        """Roles should have increasing priority."""
        result = permissions_temp_db.list_roles()
        roles = {r["name"]: r["priority"] for r in result["roles"]}

        assert roles["guest"] < roles["user"]
        assert roles["user"] < roles["power_user"]
        assert roles["power_user"] < roles["admin"]
        assert roles["admin"] < roles["owner"]

    def test_owner_has_superuser(self, permissions_temp_db):
        """Owner role should have *:* permission."""
        result = permissions_temp_db.list_roles()
        owner = next(r for r in result["roles"] if r["name"] == "owner")

        assert "*:*" in owner["permissions"]


# ─────────────────────────────────────────────────────────────────────────────
# Role Grant/Revoke Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGrantRole:
    """Tests for granting roles to users."""

    def test_grants_existing_role(self, permissions_temp_db, mock_user_id):
        """Should grant an existing role to a user."""
        result = permissions_temp_db.grant_role(
            user_id=mock_user_id,
            role_name="user",
        )

        assert result["success"] is True

    def test_rejects_nonexistent_role(self, permissions_temp_db, mock_user_id):
        """Should reject granting a nonexistent role."""
        result = permissions_temp_db.grant_role(
            user_id=mock_user_id,
            role_name="fake_role",
        )

        assert result["success"] is False
        assert "does not exist" in result["error"]

    def test_records_granted_by(self, permissions_temp_db, mock_user_id):
        """Should record who granted the role."""
        permissions_temp_db.grant_role(
            user_id=mock_user_id,
            role_name="user",
            granted_by="admin_user",
        )

        result = permissions_temp_db.get_user_roles(mock_user_id)
        role = result["roles"][0]

        assert role["granted_by"] == "admin_user"

    def test_upserts_on_duplicate(self, permissions_temp_db, mock_user_id):
        """Should update grant info on duplicate."""
        # Grant once
        permissions_temp_db.grant_role(
            user_id=mock_user_id,
            role_name="user",
            granted_by="admin1",
        )

        # Grant again with different granter
        permissions_temp_db.grant_role(
            user_id=mock_user_id,
            role_name="user",
            granted_by="admin2",
        )

        # Should have only one role entry, updated
        result = permissions_temp_db.get_user_roles(mock_user_id)
        user_roles = [r for r in result["roles"] if r["role"] == "user"]
        assert len(user_roles) == 1
        assert user_roles[0]["granted_by"] == "admin2"


class TestRevokeRole:
    """Tests for revoking roles from users."""

    def test_revokes_granted_role(self, permissions_temp_db, mock_user_id):
        """Should revoke a granted role."""
        permissions_temp_db.grant_role(mock_user_id, "user")

        result = permissions_temp_db.revoke_role(mock_user_id, "user")

        assert result["success"] is True

        # Verify role is gone
        roles = permissions_temp_db.get_user_roles(mock_user_id)
        role_names = [r["role"] for r in roles["roles"]]
        assert "user" not in role_names

    def test_fails_for_ungranted_role(self, permissions_temp_db, mock_user_id):
        """Should fail to revoke role user doesn't have."""
        result = permissions_temp_db.revoke_role(mock_user_id, "admin")

        assert result["success"] is False
        assert "does not have role" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Permission Check Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckPermission:
    """Tests for checking user permissions."""

    def test_user_without_roles_has_no_permissions(self, permissions_temp_db, mock_user_id):
        """User with no roles should have no permissions."""
        result = permissions_temp_db.check_permission(mock_user_id, "memory:read")

        assert result["success"] is True
        assert result["allowed"] is False

    def test_user_role_has_basic_permissions(self, permissions_temp_db, mock_user_id):
        """User role should have basic read/write permissions."""
        permissions_temp_db.grant_role(mock_user_id, "user")

        # Should have memory:read
        read = permissions_temp_db.check_permission(mock_user_id, "memory:read")
        assert read["allowed"] is True

        # Should have memory:write
        write = permissions_temp_db.check_permission(mock_user_id, "memory:write")
        assert write["allowed"] is True

    def test_user_role_lacks_admin_permissions(self, permissions_temp_db, mock_user_id):
        """User role should not have admin permissions."""
        permissions_temp_db.grant_role(mock_user_id, "user")

        result = permissions_temp_db.check_permission(mock_user_id, "admin:users")
        assert result["allowed"] is False

    def test_owner_has_all_permissions(self, permissions_temp_db, mock_user_id):
        """Owner role should have all permissions."""
        permissions_temp_db.grant_role(mock_user_id, "owner")

        # Should have everything
        assert permissions_temp_db.check_permission(mock_user_id, "memory:read")["allowed"]
        assert permissions_temp_db.check_permission(mock_user_id, "admin:users")["allowed"]
        assert permissions_temp_db.check_permission(mock_user_id, "anything:here")["allowed"]

    def test_multiple_roles_combine_permissions(self, permissions_temp_db, mock_user_id):
        """User with multiple roles should have combined permissions."""
        permissions_temp_db.grant_role(mock_user_id, "user")
        permissions_temp_db.grant_role(mock_user_id, "power_user")

        # Should have power_user permissions
        result = permissions_temp_db.check_permission(mock_user_id, "experimental:test")
        assert result["allowed"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Custom Role Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCustomRoles:
    """Tests for custom role creation and deletion."""

    def test_creates_custom_role(self, permissions_temp_db):
        """Should create a custom role with specified permissions."""
        result = permissions_temp_db.create_role(
            name="beta_tester",
            permissions=["experimental:*", "feedback:write"],
            description="Beta testing access",
        )

        assert result["success"] is True

        # Verify role exists
        roles = permissions_temp_db.list_roles()
        role_names = [r["name"] for r in roles["roles"]]
        assert "beta_tester" in role_names

    def test_rejects_duplicate_role(self, permissions_temp_db):
        """Should reject creating a role with existing name."""
        permissions_temp_db.create_role(name="custom1", permissions=["test:read"])

        result = permissions_temp_db.create_role(name="custom1", permissions=["test:write"])

        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_validates_permission_format(self, permissions_temp_db):
        """Should reject invalid permission format."""
        result = permissions_temp_db.create_role(
            name="bad_role",
            permissions=["invalid_no_colon"],  # Missing resource:action format
        )

        assert result["success"] is False
        assert "Invalid permission format" in result["error"]

    def test_deletes_custom_role(self, permissions_temp_db):
        """Should delete a custom role."""
        permissions_temp_db.create_role(name="temp_role", permissions=["test:read"])

        result = permissions_temp_db.delete_role("temp_role")

        assert result["success"] is True

    def test_cannot_delete_system_role(self, permissions_temp_db):
        """Should not delete system roles."""
        result = permissions_temp_db.delete_role("admin")

        assert result["success"] is False
        assert "Cannot delete system role" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# User Roles Query Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetUserRoles:
    """Tests for getting user role information."""

    def test_returns_all_user_roles(self, permissions_temp_db, mock_user_id):
        """Should return all roles for a user."""
        permissions_temp_db.grant_role(mock_user_id, "user")
        permissions_temp_db.grant_role(mock_user_id, "power_user")

        result = permissions_temp_db.get_user_roles(mock_user_id)

        assert result["success"] is True
        role_names = {r["role"] for r in result["roles"]}
        assert "user" in role_names
        assert "power_user" in role_names

    def test_includes_combined_permissions(self, permissions_temp_db, mock_user_id):
        """Should include combined permissions from all roles."""
        permissions_temp_db.grant_role(mock_user_id, "user")
        permissions_temp_db.grant_role(mock_user_id, "power_user")

        result = permissions_temp_db.get_user_roles(mock_user_id)

        assert "permissions" in result
        assert len(result["permissions"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_user_id(self, permissions_temp_db):
        """Should handle empty user ID."""
        result = permissions_temp_db.check_permission("", "memory:read")
        assert result["allowed"] is False

    def test_special_characters_in_permission(self, permissions_temp_db, mock_user_id):
        """Should handle special characters in permission strings."""
        permissions_temp_db.grant_role(mock_user_id, "owner")

        # Owner should match anything
        result = permissions_temp_db.check_permission(mock_user_id, "some_resource:some-action")
        assert result["allowed"] is True
