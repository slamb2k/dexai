"""Tests for voice intent parsing.

Verifies that the intent parser correctly identifies command intents
from natural language voice transcripts.
"""

import pytest

from tools.voice.models import IntentType, EntityType
from tools.voice.parser.intent_parser import parse_intent, parse_command


# =============================================================================
# Intent Detection
# =============================================================================


class TestIntentDetection:
    """Test that intents are correctly detected from voice transcripts."""

    @pytest.mark.parametrize("text,expected", [
        ("add task buy groceries", IntentType.ADD_TASK),
        ("create a task call the dentist", IntentType.ADD_TASK),
        ("new task file taxes", IntentType.ADD_TASK),
        ("task: send invoice", IntentType.ADD_TASK),
        ("I need to email John", IntentType.ADD_TASK),
        ("remind me to call mom", IntentType.SET_REMINDER),
        ("don't forget to buy milk", IntentType.ADD_TASK),
        ("don't let me forget to water plants", IntentType.ADD_TASK),
    ])
    def test_add_task_intents(self, text: str, expected: IntentType):
        intent, confidence, _ = parse_intent(text)
        assert intent == expected
        assert confidence > 0.5

    @pytest.mark.parametrize("text,expected", [
        ("done", IntentType.COMPLETE_TASK),
        ("finished", IntentType.COMPLETE_TASK),
        ("complete", IntentType.COMPLETE_TASK),
        ("mark as done", IntentType.COMPLETE_TASK),
        ("mark as complete", IntentType.COMPLETE_TASK),
        ("completed", IntentType.COMPLETE_TASK),
    ])
    def test_complete_task_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("skip", IntentType.SKIP_TASK),
        ("next task", IntentType.SKIP_TASK),
        ("move on", IntentType.SKIP_TASK),
        ("pass", IntentType.SKIP_TASK),
    ])
    def test_skip_task_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("what's my next task", IntentType.QUERY_NEXT_TASK),
        ("what is my next task", IntentType.QUERY_NEXT_TASK),
        ("next step", IntentType.QUERY_NEXT_TASK),
        ("what should I do", IntentType.QUERY_NEXT_TASK),
    ])
    def test_query_next_task_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("what's on my calendar", IntentType.QUERY_SCHEDULE),
        ("today's schedule", IntentType.QUERY_SCHEDULE),
        ("what's my agenda", IntentType.QUERY_SCHEDULE),
        ("tomorrow's calendar", IntentType.QUERY_SCHEDULE),
    ])
    def test_query_schedule_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("how am I doing", IntentType.QUERY_STATUS),
        ("my progress", IntentType.QUERY_STATUS),
        ("my status", IntentType.QUERY_STATUS),
        ("summary", IntentType.QUERY_STATUS),
    ])
    def test_query_status_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("search for groceries", IntentType.QUERY_SEARCH),
        ("find project notes", IntentType.QUERY_SEARCH),
        ("look up meeting notes", IntentType.QUERY_SEARCH),
    ])
    def test_query_search_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("start focus mode", IntentType.START_FOCUS),
        ("enter focus", IntentType.START_FOCUS),
        ("do not disturb", IntentType.START_FOCUS),
        ("dnd", IntentType.START_FOCUS),
        ("quiet mode", IntentType.START_FOCUS),
    ])
    def test_start_focus_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("end focus mode", IntentType.END_FOCUS),
        ("stop focus", IntentType.END_FOCUS),
        ("resume", IntentType.END_FOCUS),
        ("I'm back", IntentType.END_FOCUS),
    ])
    def test_end_focus_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("cancel", IntentType.CANCEL),
        ("never mind", IntentType.CANCEL),
        ("stop", IntentType.CANCEL),
    ])
    def test_cancel_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("undo", IntentType.UNDO),
        ("undo that", IntentType.UNDO),
        ("undo last", IntentType.UNDO),
    ])
    def test_undo_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    @pytest.mark.parametrize("text,expected", [
        ("help", IntentType.HELP),
        ("what can I say", IntentType.HELP),
        ("what can you do", IntentType.HELP),
        ("commands", IntentType.HELP),
    ])
    def test_help_intents(self, text: str, expected: IntentType):
        intent, _, _ = parse_intent(text)
        assert intent == expected

    def test_unknown_intent(self):
        intent, confidence, _ = parse_intent("blah blah random words")
        assert intent == IntentType.UNKNOWN
        assert confidence == 0.0

    def test_empty_input(self):
        intent, confidence, _ = parse_intent("")
        assert intent == IntentType.UNKNOWN
        assert confidence == 0.0


# =============================================================================
# Full Command Parsing
# =============================================================================


class TestParseCommand:
    """Test full command parsing with entity extraction."""

    def test_add_task_with_description(self):
        cmd = parse_command("add task buy groceries")
        assert cmd.intent == IntentType.ADD_TASK
        desc = cmd.get_entity(EntityType.TASK_DESCRIPTION)
        assert desc is not None
        assert "buy groceries" in desc.value

    def test_add_task_with_priority(self):
        cmd = parse_command("add task urgent call the dentist")
        assert cmd.intent == IntentType.ADD_TASK
        priority = cmd.get_entity(EntityType.PRIORITY)
        assert priority is not None
        assert priority.value == "high"

    def test_reminder_with_datetime(self):
        cmd = parse_command("remind me to call mom tomorrow")
        assert cmd.intent in (IntentType.ADD_TASK, IntentType.SET_REMINDER)
        dt = cmd.get_entity(EntityType.DATETIME)
        assert dt is not None

    def test_reminder_with_time(self):
        cmd = parse_command("set a reminder to check email at 3pm")
        assert cmd.intent == IntentType.SET_REMINDER
        dt = cmd.get_entity(EntityType.DATETIME)
        assert dt is not None

    def test_confirmation_required_for_complete(self):
        cmd = parse_command("done")
        assert cmd.intent == IntentType.COMPLETE_TASK
        assert cmd.requires_confirmation is True

    def test_no_confirmation_for_queries(self):
        cmd = parse_command("what's my next task")
        assert cmd.intent == IntentType.QUERY_NEXT_TASK
        assert cmd.requires_confirmation is False

    def test_unknown_with_suggestion(self):
        cmd = parse_command("I have a task to do")
        if cmd.intent == IntentType.UNKNOWN:
            assert cmd.suggestion is not None
            assert len(cmd.suggestion) > 0

    def test_search_with_query(self):
        cmd = parse_command("search for meeting notes")
        assert cmd.intent == IntentType.QUERY_SEARCH
        search = cmd.get_entity(EntityType.SEARCH_QUERY)
        assert search is not None
        assert "meeting notes" in search.value

    def test_focus_with_duration(self):
        cmd = parse_command("start focus mode for 30 minutes")
        assert cmd.intent == IntentType.START_FOCUS
        duration = cmd.get_entity(EntityType.DURATION)
        assert duration is not None
        assert duration.value == "30"

    def test_energy_entity(self):
        cmd = parse_command("I'm tired what should I do")
        energy = cmd.get_entity(EntityType.ENERGY_LEVEL)
        assert energy is not None
        assert energy.value == "low"

    def test_to_dict_roundtrip(self):
        cmd = parse_command("add task buy groceries")
        d = cmd.to_dict()
        assert d["intent"] == "add_task"
        assert d["confidence"] > 0
        assert isinstance(d["entities"], list)
