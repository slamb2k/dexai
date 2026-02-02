"""
Integration tests for task flow: create -> decompose -> complete steps.

Tests the complete task lifecycle:
- Creating tasks from vague input
- Decomposing tasks into concrete steps
- Completing steps and advancing to next
- Integration with commitments tracker

These tests ensure the ADHD task engine works end-to-end.
"""

from unittest.mock import patch


# ─────────────────────────────────────────────────────────────────────────────
# Task Creation and Decomposition Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskCreationFlow:
    """Tests for creating and decomposing tasks."""

    def test_create_task_from_vague_input(self, task_databases):
        """Should create a task from vague user input."""
        manager = task_databases

        result = manager.create_task(
            user_id="test_user",
            raw_input="do taxes",
        )

        assert result["success"] is True
        assert "task_id" in result["data"]
        assert result["data"]["task"]["raw_input"] == "do taxes"
        assert result["data"]["task"]["status"] == "pending"

    def test_decompose_task_creates_steps(self, task_databases):
        """Decomposition should create concrete steps for the task."""
        manager = task_databases

        # Create a task
        create_result = manager.create_task(
            user_id="test_user",
            raw_input="do taxes",
        )
        task_id = create_result["data"]["task_id"]

        # Add steps manually (simulating decomposition without LLM)
        manager.add_step(
            task_id=task_id,
            step_number=1,
            description="Find your income statement in email",
            action_verb="find",
            friction_notes="Search for 'payment summary' from employer",
            estimated_minutes=10,
        )
        manager.add_step(
            task_id=task_id,
            step_number=2,
            description="Gather receipts for deductions",
            action_verb="gather",
            estimated_minutes=15,
        )
        manager.add_step(
            task_id=task_id,
            step_number=3,
            description="Log into tax portal",
            action_verb="open",
            friction_notes="May need to reset password",
            estimated_minutes=5,
        )

        # Get task with steps
        task_result = manager.get_task(task_id)

        assert task_result["success"] is True
        assert len(task_result["data"]["steps"]) == 3
        assert task_result["data"]["steps"][0]["action_verb"] == "find"

    def test_simple_decomposition_without_llm(self, task_databases):
        """Test the simple rule-based decomposition."""
        from tools.tasks.decompose import decompose_simple

        # Tax task
        result = decompose_simple("do taxes")

        assert result["success"] is True
        assert "steps" in result["data"]
        assert len(result["data"]["steps"]) >= 2
        assert result["data"]["steps"][0]["action_verb"] == "find"

        # Email task
        result = decompose_simple("send an email to Sarah")

        assert result["success"] is True
        assert "steps" in result["data"]

        # Phone call task
        result = decompose_simple("call the dentist")

        assert result["success"] is True
        assert "steps" in result["data"]
        assert any("call" in step["description"].lower() for step in result["data"]["steps"])

    def test_decompose_task_integration(self, task_databases):
        """Full decompose_task integration (using simple decomposition)."""
        from tools.tasks.decompose import decompose_task

        result = decompose_task(
            user_id="test_user",
            raw_input="do taxes",
            depth="shallow",
            use_llm=False,  # Use simple decomposition
        )

        assert result["success"] is True
        assert "task_id" in result["data"]
        assert "first_step" in result["data"]
        assert result["data"]["total_steps"] >= 1

        # Verify the first step was set correctly

        with patch(
            "tools.tasks.manager.DB_PATH",
            task_databases.get_connection().execute("SELECT 1").connection,
        ):
            pass

        task_result = task_databases.get_task(result["data"]["task_id"])
        assert task_result["success"] is True
        assert task_result["data"]["current_step_id"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Step Completion Flow Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestStepCompletionFlow:
    """Tests for completing steps and advancing through tasks."""

    def test_complete_step_advances_to_next(self, task_databases):
        """Completing a step should advance to the next step."""
        manager = task_databases

        # Create task with steps
        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        step1 = manager.add_step(task_id, 1, "First step")
        step2 = manager.add_step(task_id, 2, "Second step")
        manager.add_step(task_id, 3, "Third step")

        step1_id = step1["data"]["id"]
        step2["data"]["id"]

        # Set current step to first
        manager.update_task(task_id, current_step_id=step1_id)

        # Complete first step
        result = manager.complete_step(step1_id)

        assert result["success"] is True
        assert result["data"]["next_step"] is not None
        assert result["data"]["next_step"]["step_number"] == 2
        assert result["data"]["all_steps_complete"] is False

    def test_complete_last_step_indicates_all_done(self, task_databases):
        """Completing the last step should indicate all steps are done."""
        manager = task_databases

        # Create task with single step
        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        step = manager.add_step(task_id, 1, "Only step")
        step_id = step["data"]["id"]

        # Complete the only step
        result = manager.complete_step(step_id)

        assert result["success"] is True
        assert result["data"]["all_steps_complete"] is True
        assert result["data"]["next_step"] is None

    def test_step_completion_sequence(self, task_databases):
        """Test completing all steps in sequence."""
        manager = task_databases

        # Create task with 3 steps
        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        steps = []
        for i in range(1, 4):
            step = manager.add_step(task_id, i, f"Step {i}")
            steps.append(step["data"]["id"])

        # Complete each step in sequence
        for i, step_id in enumerate(steps):
            result = manager.complete_step(step_id)
            assert result["success"] is True

            if i < len(steps) - 1:
                # Not the last step
                assert result["data"]["all_steps_complete"] is False
                assert result["data"]["next_step"]["step_number"] == i + 2
            else:
                # Last step
                assert result["data"]["all_steps_complete"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Task Status Flow Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskStatusFlow:
    """Tests for task status transitions."""

    def test_task_status_progression(self, task_databases):
        """Task should progress through status states correctly."""
        manager = task_databases

        # Create task
        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        # Initial status should be pending
        assert create_result["data"]["task"]["status"] == "pending"

        # Update to in_progress
        update_result = manager.update_task(task_id, status="in_progress")
        assert update_result["success"] is True
        assert update_result["data"]["status"] == "in_progress"
        assert update_result["data"]["started_at"] is not None

        # Complete the task
        complete_result = manager.complete_task(task_id)
        assert complete_result["success"] is True
        assert complete_result["data"]["status"] == "completed"
        assert complete_result["data"]["completed_at"] is not None

    def test_task_abandonment(self, task_databases):
        """Tasks can be abandoned without guilt."""
        manager = task_databases

        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        # Abandon with reason
        abandon_result = manager.abandon_task(task_id, reason="priorities changed")

        assert abandon_result["success"] is True
        # Message should be positive (no guilt language)
        assert "no longer needed" in abandon_result["message"]

        # Verify status and reason recorded
        task = manager.get_task(task_id)
        assert task["data"]["status"] == "abandoned"
        assert task["data"]["abandon_reason"] == "priorities changed"


# ─────────────────────────────────────────────────────────────────────────────
# Task with Commitments Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskCommitmentsIntegration:
    """Tests for task and commitments integration."""

    def test_create_commitment_from_task_context(self, commitment_database):
        """Commitments can be created alongside tasks."""
        commitments, _db_path = commitment_database

        # Add a commitment (as might happen when extracting from conversation)
        result = commitments.add_commitment(
            user_id="test_user",
            content="Send Sarah the API documentation",
            target_person="Sarah",
            due_date="tomorrow",
            source_channel="telegram",
        )

        assert result["success"] is True
        assert "id" in result["data"]
        assert result["data"]["target_person"] == "Sarah"

    def test_list_commitments_grouped_by_person(self, commitment_database):
        """Commitments should group by target person."""
        commitments, _db_path = commitment_database

        # Add commitments to different people
        commitments.add_commitment(
            user_id="test_user",
            content="Send API docs",
            target_person="Sarah",
        )
        commitments.add_commitment(
            user_id="test_user",
            content="Review PR",
            target_person="Sarah",
        )
        commitments.add_commitment(
            user_id="test_user",
            content="Schedule meeting",
            target_person="Bob",
        )

        # List grouped by person
        result = commitments.list_commitments(
            user_id="test_user",
            group_by_person=True,
        )

        assert result["success"] is True
        assert "commitments_by_person" in result["data"]
        assert "Sarah" in result["data"]["commitments_by_person"]
        assert "Bob" in result["data"]["commitments_by_person"]
        assert len(result["data"]["commitments_by_person"]["Sarah"]) == 2
        assert len(result["data"]["commitments_by_person"]["Bob"]) == 1

    def test_commitment_completion(self, commitment_database):
        """Commitments can be marked as completed."""
        commitments, _db_path = commitment_database

        # Add a commitment
        add_result = commitments.add_commitment(
            user_id="test_user",
            content="Send email to client",
            target_person="Client",
        )
        commitment_id = add_result["data"]["id"]

        # Complete it
        complete_result = commitments.complete_commitment(commitment_id)

        assert complete_result["success"] is True

        # Verify status
        get_result = commitments.get_commitment(commitment_id)
        assert get_result["data"]["status"] == "completed"
        assert get_result["data"]["completed_at"] is not None

    def test_due_soon_commitments(self, commitment_database):
        """Should retrieve commitments due within specified hours."""
        commitments, _db_path = commitment_database

        # Add commitment due today
        commitments.add_commitment(
            user_id="test_user",
            content="Urgent task",
            due_date="today",
        )

        # Add commitment due next week
        commitments.add_commitment(
            user_id="test_user",
            content="Later task",
            due_date="next week",
        )

        # Get commitments due within 24 hours
        result = commitments.get_due_soon(user_id="test_user", hours=24)

        assert result["success"] is True
        # Should include today's commitment
        assert result["data"]["count"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Full Task Flow Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFullTaskFlowIntegration:
    """End-to-end tests for the complete task flow."""

    def test_full_task_lifecycle(self, task_databases):
        """Test complete task lifecycle: create -> decompose -> complete."""
        manager = task_databases

        # 1. Create task from vague input
        create_result = manager.create_task(
            user_id="test_user",
            raw_input="send invoice to client",
            energy_level="low",
            priority=7,
        )
        task_id = create_result["data"]["task_id"]
        assert create_result["success"] is True

        # 2. Add decomposed steps
        step1 = manager.add_step(
            task_id=task_id,
            step_number=1,
            description="Find the invoice document",
            action_verb="find",
            estimated_minutes=5,
        )
        step2 = manager.add_step(
            task_id=task_id,
            step_number=2,
            description="Open email and compose message",
            action_verb="open",
            estimated_minutes=3,
        )
        step3 = manager.add_step(
            task_id=task_id,
            step_number=3,
            description="Attach invoice and send",
            action_verb="send",
            estimated_minutes=2,
        )

        # Set current step
        manager.update_task(task_id, current_step_id=step1["data"]["id"])

        # 3. Start working on task
        manager.update_task(task_id, status="in_progress")

        # 4. Complete steps one by one
        result1 = manager.complete_step(step1["data"]["id"])
        assert result1["success"] is True
        assert result1["data"]["next_step"]["description"] == "Open email and compose message"

        result2 = manager.complete_step(step2["data"]["id"])
        assert result2["success"] is True
        assert result2["data"]["next_step"]["description"] == "Attach invoice and send"

        result3 = manager.complete_step(step3["data"]["id"])
        assert result3["success"] is True
        assert result3["data"]["all_steps_complete"] is True

        # 5. Mark task as completed
        complete_result = manager.complete_task(task_id)
        assert complete_result["success"] is True

        # 6. Verify final state
        final_task = manager.get_task(task_id)
        assert final_task["data"]["status"] == "completed"
        assert final_task["data"]["completed_at"] is not None
        assert len(final_task["data"]["steps"]) == 3
        for step in final_task["data"]["steps"]:
            assert step["status"] == "completed"

    def test_task_with_friction_points(self, task_databases):
        """Tasks should track friction points that block progress."""
        manager = task_databases

        # Create task
        create_result = manager.create_task(
            user_id="test_user",
            raw_input="file taxes",
        )
        task_id = create_result["data"]["task_id"]

        # Add step with friction
        step = manager.add_step(
            task_id=task_id,
            step_number=1,
            description="Log into tax portal",
            friction_notes="Need to reset password",
        )

        # Add friction point
        friction_result = manager.add_friction(
            friction_type="password",
            description="Can't remember tax portal password",
            task_id=task_id,
            step_id=step["data"]["id"],
        )

        assert friction_result["success"] is True

        # Get task with friction
        task = manager.get_task(task_id)
        assert len(task["data"]["friction_points"]) == 1
        assert task["data"]["friction_points"][0]["friction_type"] == "password"

    def test_subtask_relationship(self, task_databases):
        """Tasks can have parent-child relationships."""
        manager = task_databases

        # Create parent task
        parent_result = manager.create_task(
            user_id="test_user",
            raw_input="prepare tax return",
            title="Prepare Tax Return",
        )
        parent_id = parent_result["data"]["task_id"]

        # Create subtasks
        manager.create_task(
            user_id="test_user",
            raw_input="gather documents",
            parent_task_id=parent_id,
        )
        manager.create_task(
            user_id="test_user",
            raw_input="fill out forms",
            parent_task_id=parent_id,
        )

        # List subtasks of parent
        subtasks = manager.list_tasks(
            user_id="test_user",
            parent_task_id=parent_id,
        )

        assert subtasks["success"] is True
        assert len(subtasks["data"]["tasks"]) == 2

        # List top-level tasks only
        top_level = manager.list_tasks(
            user_id="test_user",
            include_subtasks=False,
        )

        # Should not include subtasks
        assert all(t["parent_task_id"] is None for t in top_level["data"]["tasks"])


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases and Error Handling
# ─────────────────────────────────────────────────────────────────────────────


class TestTaskFlowEdgeCases:
    """Edge case tests for task flow."""

    def test_complete_nonexistent_step(self, task_databases):
        """Completing a non-existent step should fail gracefully."""
        manager = task_databases

        result = manager.complete_step("nonexistent_step_id")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_add_step_to_nonexistent_task(self, task_databases):
        """Adding step to non-existent task should fail."""
        manager = task_databases

        result = manager.add_step(
            task_id="nonexistent_task",
            step_number=1,
            description="Test step",
        )

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_task_with_unicode_content(self, task_databases):
        """Tasks should handle unicode content correctly."""
        manager = task_databases

        result = manager.create_task(
            user_id="test_user",
            raw_input="Send email to Muller - he said 'Dankeschon' for the help",
            title="Email Muller about project",
        )

        assert result["success"] is True
        assert "Muller" in result["data"]["task"]["raw_input"]

    def test_filter_tasks_by_energy_level(self, task_databases):
        """Should filter tasks by energy level for ADHD matching."""
        manager = task_databases

        # Create tasks with different energy levels
        manager.create_task(
            user_id="test_user",
            raw_input="Quick email",
            energy_level="low",
        )
        manager.create_task(
            user_id="test_user",
            raw_input="Complex analysis",
            energy_level="high",
        )
        manager.create_task(
            user_id="test_user",
            raw_input="Phone call",
            energy_level="medium",
        )

        # Filter by low energy
        low_energy = manager.list_tasks(
            user_id="test_user",
            energy_level="low",
        )

        assert low_energy["success"] is True
        assert len(low_energy["data"]["tasks"]) == 1
        assert low_energy["data"]["tasks"][0]["energy_level"] == "low"

    def test_task_deletion_cascades_to_steps(self, task_databases):
        """Deleting a task should also delete its steps."""
        manager = task_databases

        # Create task with steps
        create_result = manager.create_task(user_id="test_user", raw_input="test task")
        task_id = create_result["data"]["task_id"]

        step = manager.add_step(task_id, 1, "Test step")
        step_id = step["data"]["id"]

        # Delete task
        delete_result = manager.delete_task(task_id)
        assert delete_result["success"] is True

        # Step should also be gone
        step_result = manager.get_step(step_id)
        assert step_result["success"] is False
