"""
Integration tests for tools/dashboard/backend API endpoints.

Tests the FastAPI dashboard routes:
- /api/status endpoint (Dex avatar state)
- /api/tasks CRUD operations
- /api/activity listing and creation

These tests use an isolated test database and FastAPI TestClient.
"""

from datetime import datetime

import pytest


# Skip all tests in this module if FastAPI is not installed
try:
    from fastapi.testclient import TestClient  # noqa: F401

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Status Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusEndpoint:
    """Tests for /api/status endpoint."""

    def test_get_status_returns_dex_state(self, test_client):
        """GET /api/status should return current Dex state."""
        response = test_client.get("/api/status")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "state" in data
        assert "current_task" in data
        assert "uptime_seconds" in data
        assert "version" in data

        # Default state should be idle
        assert data["state"] == "idle"

    def test_put_status_updates_state(self, test_client):
        """PUT /api/status should update Dex state."""
        response = test_client.put(
            "/api/status", params={"state": "working", "current_task": "Processing request"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["state"] == "working"
        assert data["current_task"] == "Processing request"

    def test_put_status_to_thinking(self, test_client):
        """Should be able to set state to 'thinking'."""
        response = test_client.put("/api/status", params={"state": "thinking"})

        assert response.status_code == 200
        assert response.json()["state"] == "thinking"

    def test_put_status_invalid_state(self, test_client):
        """PUT /api/status with invalid state should return error."""
        response = test_client.put("/api/status", params={"state": "invalid_state"})

        assert response.status_code == 422  # Validation error

    def test_status_persists_between_requests(self, test_client):
        """Status changes should persist between requests."""
        # Set state
        test_client.put("/api/status", params={"state": "hyperfocus"})

        # Get state
        response = test_client.get("/api/status")

        assert response.json()["state"] == "hyperfocus"


# ─────────────────────────────────────────────────────────────────────────────
# Tasks Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTasksEndpoint:
    """Tests for /api/tasks endpoints."""

    def test_list_tasks_empty(self, test_client):
        """GET /api/tasks should return empty list initially."""
        response = test_client.get("/api/tasks")

        assert response.status_code == 200
        data = response.json()

        assert "tasks" in data
        assert "total" in data
        assert data["total"] == 0
        assert data["tasks"] == []

    def test_list_tasks_with_pagination(self, test_client, temp_activity_db):
        """GET /api/tasks should support pagination."""
        import sqlite3

        # Insert test tasks directly into the database
        conn = sqlite3.connect(str(temp_activity_db))
        for i in range(25):
            conn.execute(
                "INSERT INTO tasks (id, source, request, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (f"task_{i}", "test", f"Task {i}", "pending", datetime.now().isoformat()),
            )
        conn.commit()
        conn.close()

        # Test pagination
        response = test_client.get("/api/tasks", params={"page": 1, "page_size": 10})
        data = response.json()

        assert response.status_code == 200
        assert len(data["tasks"]) == 10
        assert data["total"] == 25
        assert data["has_more"] is True

        # Second page
        response = test_client.get("/api/tasks", params={"page": 2, "page_size": 10})
        data = response.json()

        assert len(data["tasks"]) == 10
        assert data["page"] == 2

    def test_list_tasks_filter_by_status(self, test_client, temp_activity_db):
        """GET /api/tasks should filter by status."""
        import sqlite3

        # Insert tasks with different statuses
        conn = sqlite3.connect(str(temp_activity_db))
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_1", "test", "Pending task", "pending"),
        )
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_2", "test", "Completed task", "completed"),
        )
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_3", "test", "Running task", "running"),
        )
        conn.commit()
        conn.close()

        # Filter by pending
        response = test_client.get("/api/tasks", params={"status": "pending"})
        data = response.json()

        assert response.status_code == 200
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "pending"

        # Filter by completed
        response = test_client.get("/api/tasks", params={"status": "completed"})
        data = response.json()

        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["status"] == "completed"

    def test_list_tasks_filter_by_channel(self, test_client, temp_activity_db):
        """GET /api/tasks should filter by channel/source."""
        import sqlite3

        conn = sqlite3.connect(str(temp_activity_db))
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_1", "telegram", "Telegram task", "pending"),
        )
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_2", "discord", "Discord task", "pending"),
        )
        conn.commit()
        conn.close()

        response = test_client.get("/api/tasks", params={"channel": "telegram"})
        data = response.json()

        assert response.status_code == 200
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["channel"] == "telegram"

    def test_list_tasks_search(self, test_client, temp_activity_db):
        """GET /api/tasks should support search."""
        import sqlite3

        conn = sqlite3.connect(str(temp_activity_db))
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_1", "test", "Send invoice to client", "pending"),
        )
        conn.execute(
            "INSERT INTO tasks (id, source, request, status) VALUES (?, ?, ?, ?)",
            ("task_2", "test", "Review pull request", "pending"),
        )
        conn.commit()
        conn.close()

        response = test_client.get("/api/tasks", params={"search": "invoice"})
        data = response.json()

        assert response.status_code == 200
        assert len(data["tasks"]) == 1
        assert "invoice" in data["tasks"][0]["request"].lower()

    def test_get_task_by_id(self, test_client, temp_activity_db):
        """GET /api/tasks/{task_id} should return task details."""
        import sqlite3

        conn = sqlite3.connect(str(temp_activity_db))
        conn.execute(
            "INSERT INTO tasks (id, source, request, status, summary) VALUES (?, ?, ?, ?, ?)",
            ("task_123", "test", "Test task", "completed", "Task completed successfully"),
        )
        conn.commit()
        conn.close()

        response = test_client.get("/api/tasks/task_123")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == "task_123"
        assert data["request"] == "Test task"
        assert data["status"] == "completed"
        assert data["response"] == "Task completed successfully"

    def test_get_task_not_found(self, test_client):
        """GET /api/tasks/{task_id} should return 404 for non-existent task."""
        response = test_client.get("/api/tasks/nonexistent_task")

        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Activity Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestActivityEndpoint:
    """Tests for /api/activity endpoints."""

    def test_get_activity_empty(self, test_client):
        """GET /api/activity should return empty list initially."""
        response = test_client.get("/api/activity")

        assert response.status_code == 200
        data = response.json()

        assert "events" in data
        assert "total" in data
        assert data["total"] == 0

    def test_post_activity_creates_event(self, test_client):
        """POST /api/activity should create a new event."""
        event_data = {
            "event_type": "message",
            "summary": "User sent a message",
            "channel": "telegram",
            "user_id": "user_123",
            "severity": "info",
        }

        response = test_client.post("/api/activity", json=event_data)

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "event_id" in data

    def test_get_activity_returns_created_events(self, test_client):
        """GET /api/activity should return previously created events."""
        # Create an event
        test_client.post(
            "/api/activity",
            json={
                "event_type": "task",
                "summary": "Task completed",
                "severity": "info",
            },
        )

        # Get events
        response = test_client.get("/api/activity")
        data = response.json()

        assert response.status_code == 200
        assert data["total"] >= 1
        assert len(data["events"]) >= 1

    def test_activity_filter_by_type(self, test_client):
        """GET /api/activity should filter by event type."""
        # Create events of different types
        test_client.post(
            "/api/activity", json={"event_type": "message", "summary": "Message event"}
        )
        test_client.post("/api/activity", json={"event_type": "task", "summary": "Task event"})
        test_client.post("/api/activity", json={"event_type": "system", "summary": "System event"})

        # Filter by message type
        response = test_client.get("/api/activity", params={"event_type": "message"})
        data = response.json()

        assert response.status_code == 200
        for event in data["events"]:
            assert event["event_type"] == "message"

    def test_activity_filter_by_severity(self, test_client):
        """GET /api/activity should filter by severity."""
        test_client.post(
            "/api/activity",
            json={"event_type": "system", "summary": "Info event", "severity": "info"},
        )
        test_client.post(
            "/api/activity",
            json={"event_type": "error", "summary": "Error event", "severity": "error"},
        )

        # Filter by error severity
        response = test_client.get("/api/activity", params={"severity": "error"})
        data = response.json()

        assert response.status_code == 200
        for event in data["events"]:
            assert event["severity"] == "error"

    def test_activity_pagination(self, test_client):
        """GET /api/activity should support cursor-based pagination."""
        # Create multiple events
        for i in range(15):
            test_client.post(
                "/api/activity", json={"event_type": "system", "summary": f"Event {i}"}
            )

        # First page
        response = test_client.get("/api/activity", params={"limit": 5})
        data = response.json()

        assert response.status_code == 200
        assert len(data["events"]) == 5
        assert data["has_more"] is True
        assert data["cursor"] is not None

        # Next page
        response = test_client.get("/api/activity", params={"limit": 5, "cursor": data["cursor"]})
        data2 = response.json()

        assert len(data2["events"]) == 5


# ─────────────────────────────────────────────────────────────────────────────
# Health Check Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_check_returns_status(self, test_client):
        """GET /api/health should return system health."""
        response = test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "services" in data
        assert "timestamp" in data

    def test_health_check_database_status(self, test_client):
        """Health check should include database status."""
        response = test_client.get("/api/health")
        data = response.json()

        assert "database" in data["services"]
        assert data["services"]["database"] in ["healthy", "unhealthy"]


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for API error handling."""

    def test_invalid_endpoint_returns_404(self, test_client):
        """Invalid endpoints should return 404."""
        response = test_client.get("/api/nonexistent")

        assert response.status_code == 404

    def test_invalid_query_params(self, test_client):
        """Invalid query parameters should return validation error."""
        response = test_client.get("/api/tasks", params={"page": -1})

        assert response.status_code == 422  # Validation error

    def test_invalid_json_body(self, test_client):
        """Invalid JSON body should return error."""
        response = test_client.post(
            "/api/activity",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
