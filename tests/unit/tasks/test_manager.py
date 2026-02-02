"""Tests for tools/tasks/manager.py

The task manager provides CRUD operations for ADHD-friendly task tracking.
Key functionality:
- Create tasks from vague input
- Track status progression
- Maintain parent/subtask relationships
- Record step completion

These tests ensure reliable task management.
"""

from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Setup: Patch DB_PATH to use temp database
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def task_manager_temp_db(temp_db):
    """Patch task manager to use temporary database."""
    with (
        patch("tools.tasks.manager.DB_PATH", temp_db),
        patch("tools.tasks.DB_PATH", temp_db),
    ):
        from tools.tasks import manager

        # Force table creation
        conn = manager.get_connection()
        conn.close()

        yield manager


# ─────────────────────────────────────────────────────────────────────────────
# Task Creation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateTask:
    """Tests for task creation."""

    def test_creates_basic_task(self, task_manager_temp_db, mock_user_id):
        """Should create a task with minimal fields."""
        result = task_manager_temp_db.create_task(
            user_id=mock_user_id,
            raw_input="do taxes",
        )

        assert result["success"] is True
        assert "task_id" in result["data"]
        assert result["data"]["task"]["raw_input"] == "do taxes"

    def test_creates_task_with_all_fields(self, task_manager_temp_db, mock_user_id, sample_task):
        """Should create task with all optional fields."""
        result = task_manager_temp_db.create_task(
            user_id=sample_task["user_id"],
            raw_input=sample_task["raw_input"],
            title=sample_task["title"],
            description=sample_task["description"],
            energy_level=sample_task["energy_level"],
            estimated_minutes=sample_task["estimated_minutes"],
            priority=sample_task["priority"],
        )

        assert result["success"] is True
        task = result["data"]["task"]
        assert task["title"] == sample_task["title"]
        assert task["energy_level"] == sample_task["energy_level"]

    def test_generates_unique_id(self, task_manager_temp_db, mock_user_id):
        """Should generate unique IDs for each task."""
        result1 = task_manager_temp_db.create_task(mock_user_id, "task 1")
        result2 = task_manager_temp_db.create_task(mock_user_id, "task 2")

        assert result1["data"]["task_id"] != result2["data"]["task_id"]

    def test_default_status_is_pending(self, task_manager_temp_db, mock_user_id):
        """New tasks should have 'pending' status."""
        result = task_manager_temp_db.create_task(mock_user_id, "new task")

        assert result["data"]["task"]["status"] == "pending"

    def test_rejects_invalid_energy_level(self, task_manager_temp_db, mock_user_id):
        """Should reject invalid energy level."""
        result = task_manager_temp_db.create_task(
            user_id=mock_user_id,
            raw_input="task",
            energy_level="super_high",  # Invalid
        )

        assert result["success"] is False
        assert "Invalid energy level" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Task Retrieval Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTask:
    """Tests for task retrieval."""

    def test_gets_existing_task(self, task_manager_temp_db, mock_user_id):
        """Should retrieve an existing task."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "my task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.get_task(task_id)

        assert result["success"] is True
        assert result["data"]["id"] == task_id

    def test_returns_error_for_nonexistent_task(self, task_manager_temp_db):
        """Should return error for non-existent task."""
        result = task_manager_temp_db.get_task("nonexistent_id")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_includes_steps_by_default(self, task_manager_temp_db, mock_user_id):
        """Should include steps by default."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task with steps")
        task_id = create_result["data"]["task_id"]

        # Add a step
        task_manager_temp_db.add_step(task_id, 1, "First step")

        result = task_manager_temp_db.get_task(task_id)

        assert "steps" in result["data"]
        assert len(result["data"]["steps"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Task List Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListTasks:
    """Tests for listing tasks."""

    def test_lists_user_tasks(self, task_manager_temp_db, mock_user_id):
        """Should list all tasks for a user."""
        task_manager_temp_db.create_task(mock_user_id, "task 1")
        task_manager_temp_db.create_task(mock_user_id, "task 2")
        task_manager_temp_db.create_task("other_user", "task 3")

        result = task_manager_temp_db.list_tasks(mock_user_id)

        assert result["success"] is True
        assert len(result["data"]["tasks"]) == 2

    def test_filters_by_status(self, task_manager_temp_db, mock_user_id):
        """Should filter tasks by status."""
        task_manager_temp_db.create_task(mock_user_id, "pending task")
        result2 = task_manager_temp_db.create_task(mock_user_id, "completed task")

        # Complete one task
        task_manager_temp_db.complete_task(result2["data"]["task_id"])

        pending = task_manager_temp_db.list_tasks(mock_user_id, status="pending")
        completed = task_manager_temp_db.list_tasks(mock_user_id, status="completed")

        assert len(pending["data"]["tasks"]) == 1
        assert len(completed["data"]["tasks"]) == 1

    def test_filters_by_energy_level(self, task_manager_temp_db, mock_user_id):
        """Should filter tasks by energy level."""
        task_manager_temp_db.create_task(mock_user_id, "low energy task", energy_level="low")
        task_manager_temp_db.create_task(mock_user_id, "high energy task", energy_level="high")

        result = task_manager_temp_db.list_tasks(mock_user_id, energy_level="low")

        assert len(result["data"]["tasks"]) == 1
        assert result["data"]["tasks"][0]["energy_level"] == "low"

    def test_respects_limit(self, task_manager_temp_db, mock_user_id):
        """Should respect limit parameter."""
        for i in range(10):
            task_manager_temp_db.create_task(mock_user_id, f"task {i}")

        result = task_manager_temp_db.list_tasks(mock_user_id, limit=5)

        assert len(result["data"]["tasks"]) == 5
        assert result["data"]["total"] == 10


# ─────────────────────────────────────────────────────────────────────────────
# Task Update Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateTask:
    """Tests for task updates."""

    def test_updates_title(self, task_manager_temp_db, mock_user_id):
        """Should update task title."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "original")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.update_task(task_id, title="updated title")

        assert result["success"] is True
        assert result["data"]["title"] == "updated title"

    def test_updates_status(self, task_manager_temp_db, mock_user_id):
        """Should update task status."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.update_task(task_id, status="in_progress")

        assert result["success"] is True
        assert result["data"]["status"] == "in_progress"

    def test_sets_started_at_on_in_progress(self, task_manager_temp_db, mock_user_id):
        """Should set started_at when status becomes in_progress."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.update_task(task_id, status="in_progress")

        assert result["data"]["started_at"] is not None

    def test_sets_completed_at_on_complete(self, task_manager_temp_db, mock_user_id):
        """Should set completed_at when status becomes completed."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.update_task(task_id, status="completed")

        assert result["data"]["completed_at"] is not None

    def test_rejects_invalid_status(self, task_manager_temp_db, mock_user_id):
        """Should reject invalid status value."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.update_task(task_id, status="invalid")

        assert result["success"] is False

    def test_returns_error_for_nonexistent_task(self, task_manager_temp_db):
        """Should return error for non-existent task."""
        result = task_manager_temp_db.update_task("nonexistent", title="new")

        assert result["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Task Completion Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCompleteTask:
    """Tests for task completion."""

    def test_completes_task(self, task_manager_temp_db, mock_user_id):
        """Should mark task as completed."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.complete_task(task_id)

        assert result["success"] is True
        assert result["data"]["status"] == "completed"


# ─────────────────────────────────────────────────────────────────────────────
# Task Abandon Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestAbandonTask:
    """Tests for task abandonment."""

    def test_abandons_task(self, task_manager_temp_db, mock_user_id):
        """Should mark task as abandoned."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.abandon_task(task_id)

        assert result["success"] is True
        # Message should be positive (no guilt!)
        assert "no longer needed" in result["message"]

    def test_records_abandon_reason(self, task_manager_temp_db, mock_user_id):
        """Should record reason for abandonment."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        task_manager_temp_db.abandon_task(task_id, reason="priorities changed")

        # Verify reason is stored
        get_result = task_manager_temp_db.get_task(task_id)
        assert get_result["data"]["abandon_reason"] == "priorities changed"


# ─────────────────────────────────────────────────────────────────────────────
# Task Step Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskSteps:
    """Tests for task step management."""

    def test_adds_step_to_task(self, task_manager_temp_db, mock_user_id):
        """Should add a step to a task."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.add_step(
            task_id=task_id,
            step_number=1,
            description="First step",
        )

        assert result["success"] is True
        assert result["data"]["description"] == "First step"

    def test_adds_step_with_all_fields(self, task_manager_temp_db, mock_user_id, sample_step):
        """Should add step with all optional fields."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.add_step(
            task_id=task_id,
            step_number=sample_step["step_number"],
            description=sample_step["description"],
            action_verb=sample_step["action_verb"],
            friction_notes=sample_step["friction_notes"],
            estimated_minutes=sample_step["estimated_minutes"],
        )

        assert result["success"] is True
        assert result["data"]["action_verb"] == sample_step["action_verb"]

    def test_rejects_step_for_nonexistent_task(self, task_manager_temp_db):
        """Should reject adding step to non-existent task."""
        result = task_manager_temp_db.add_step(
            task_id="nonexistent",
            step_number=1,
            description="Step",
        )

        assert result["success"] is False


class TestCompleteStep:
    """Tests for step completion."""

    def test_completes_step(self, task_manager_temp_db, mock_user_id):
        """Should mark step as completed."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]
        step_result = task_manager_temp_db.add_step(task_id, 1, "Step 1")
        step_id = step_result["data"]["id"]

        result = task_manager_temp_db.complete_step(step_id)

        assert result["success"] is True
        assert result["message"] == "Step completed"

    def test_returns_next_step(self, task_manager_temp_db, mock_user_id):
        """Should return next pending step after completion."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]
        step1 = task_manager_temp_db.add_step(task_id, 1, "Step 1")
        task_manager_temp_db.add_step(task_id, 2, "Step 2")
        step1_id = step1["data"]["id"]

        result = task_manager_temp_db.complete_step(step1_id)

        assert result["data"]["next_step"] is not None
        assert result["data"]["next_step"]["step_number"] == 2

    def test_indicates_all_steps_complete(self, task_manager_temp_db, mock_user_id):
        """Should indicate when all steps are complete."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]
        step_result = task_manager_temp_db.add_step(task_id, 1, "Only step")
        step_id = step_result["data"]["id"]

        result = task_manager_temp_db.complete_step(step_id)

        assert result["data"]["all_steps_complete"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Task Deletion Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDeleteTask:
    """Tests for task deletion."""

    def test_deletes_task(self, task_manager_temp_db, mock_user_id):
        """Should delete a task."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]

        result = task_manager_temp_db.delete_task(task_id)

        assert result["success"] is True

        # Verify task is gone
        get_result = task_manager_temp_db.get_task(task_id)
        assert get_result["success"] is False

    def test_cascades_to_steps(self, task_manager_temp_db, mock_user_id):
        """Should delete associated steps on task deletion."""
        create_result = task_manager_temp_db.create_task(mock_user_id, "task")
        task_id = create_result["data"]["task_id"]
        step_result = task_manager_temp_db.add_step(task_id, 1, "Step")
        step_id = step_result["data"]["id"]

        task_manager_temp_db.delete_task(task_id)

        # Step should also be gone
        get_step = task_manager_temp_db.get_step(step_id)
        assert get_step["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_handles_unicode_in_task(self, task_manager_temp_db, mock_user_id):
        """Should handle unicode in task content."""
        result = task_manager_temp_db.create_task(
            mock_user_id,
            "Send 日本語 email to 山田さん",
        )

        assert result["success"] is True
        assert "日本語" in result["data"]["task"]["raw_input"]

    def test_handles_special_characters(self, task_manager_temp_db, mock_user_id):
        """Should handle special characters."""
        result = task_manager_temp_db.create_task(
            mock_user_id,
            "Review O'Brien's PR #123 & comments",
        )

        assert result["success"] is True

    def test_handles_very_long_description(self, task_manager_temp_db, mock_user_id):
        """Should handle very long descriptions."""
        long_desc = "A" * 10000
        result = task_manager_temp_db.create_task(
            user_id=mock_user_id,
            raw_input="task",
            description=long_desc,
        )

        assert result["success"] is True
