"""Tests for voice entity extraction.

Verifies datetime, duration, priority, and energy extraction from
natural language voice input.
"""

import pytest
from datetime import datetime, timedelta

from tools.voice.models import EntityType
from tools.voice.parser.entity_extractor import (
    extract_datetime_entities,
    extract_duration_entities,
    extract_energy_entity,
    extract_entities,
    extract_priority_entity,
)


class TestDatetimeExtraction:
    """Test date/time entity extraction."""

    def test_today(self):
        entities = extract_datetime_entities("do it today")
        assert any(e.type == EntityType.DATETIME for e in entities)
        today = datetime.now().strftime("%Y-%m-%d")
        assert any(today in e.value for e in entities)

    def test_tomorrow(self):
        entities = extract_datetime_entities("call mom tomorrow")
        assert any(e.type == EntityType.DATETIME for e in entities)
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        assert any(tomorrow in e.value for e in entities)

    def test_in_hours(self):
        entities = extract_datetime_entities("remind me in 2 hours")
        assert any(e.type == EntityType.DATETIME for e in entities)

    def test_in_minutes(self):
        entities = extract_datetime_entities("remind me in 30 minutes")
        assert any(e.type == EntityType.DATETIME for e in entities)

    def test_at_time(self):
        entities = extract_datetime_entities("meeting at 3pm")
        assert any(e.type == EntityType.DATETIME for e in entities)
        assert any("15:00" in e.value for e in entities)

    def test_at_time_with_minutes(self):
        entities = extract_datetime_entities("call at 2:30 pm")
        assert any(e.type == EntityType.DATETIME for e in entities)
        assert any("14:30" in e.value for e in entities)

    def test_this_afternoon(self):
        entities = extract_datetime_entities("do it this afternoon")
        assert any(e.type == EntityType.DATETIME for e in entities)
        assert any("T14:00" in e.value for e in entities)

    def test_tonight(self):
        entities = extract_datetime_entities("pack tonight")
        assert any(e.type == EntityType.DATETIME for e in entities)
        assert any("T19:00" in e.value for e in entities)

    def test_day_of_week(self):
        entities = extract_datetime_entities("meeting next monday")
        assert any(e.type == EntityType.DATETIME for e in entities)

    def test_no_datetime(self):
        entities = extract_datetime_entities("buy groceries")
        dt_entities = [e for e in entities if e.type == EntityType.DATETIME]
        assert len(dt_entities) == 0


class TestDurationExtraction:
    """Test duration entity extraction."""

    def test_minutes(self):
        entities = extract_duration_entities("for 30 minutes")
        assert any(e.type == EntityType.DURATION and e.value == "30" for e in entities)

    def test_hours(self):
        entities = extract_duration_entities("for 2 hours")
        assert any(e.type == EntityType.DURATION and e.value == "120" for e in entities)

    def test_half_hour(self):
        entities = extract_duration_entities("half an hour")
        assert any(e.type == EntityType.DURATION and e.value == "30" for e in entities)

    def test_no_duration(self):
        entities = extract_duration_entities("buy groceries")
        assert len(entities) == 0


class TestPriorityExtraction:
    """Test priority entity extraction."""

    def test_urgent(self):
        entities = extract_priority_entity("urgent call the dentist")
        assert any(e.type == EntityType.PRIORITY and e.value == "high" for e in entities)

    def test_high_priority(self):
        entities = extract_priority_entity("high priority task")
        assert any(e.type == EntityType.PRIORITY and e.value == "high" for e in entities)

    def test_low_priority(self):
        entities = extract_priority_entity("low priority cleanup")
        assert any(e.type == EntityType.PRIORITY and e.value == "low" for e in entities)

    def test_no_rush(self):
        entities = extract_priority_entity("no rush on this")
        assert any(e.type == EntityType.PRIORITY and e.value == "low" for e in entities)

    def test_no_priority(self):
        entities = extract_priority_entity("buy groceries")
        assert len(entities) == 0


class TestEnergyExtraction:
    """Test energy level entity extraction."""

    def test_tired(self):
        entities = extract_energy_entity("I'm tired")
        assert any(e.type == EntityType.ENERGY_LEVEL and e.value == "low" for e in entities)

    def test_exhausted(self):
        entities = extract_energy_entity("feeling exhausted")
        assert any(e.type == EntityType.ENERGY_LEVEL and e.value == "low" for e in entities)

    def test_great(self):
        entities = extract_energy_entity("feeling great today")
        assert any(e.type == EntityType.ENERGY_LEVEL and e.value == "high" for e in entities)

    def test_okay(self):
        entities = extract_energy_entity("I'm okay")
        assert any(e.type == EntityType.ENERGY_LEVEL and e.value == "medium" for e in entities)

    def test_no_energy(self):
        entities = extract_energy_entity("buy groceries")
        assert len(entities) == 0


class TestCombinedExtraction:
    """Test extraction of multiple entities from complex inputs."""

    def test_task_with_priority_and_time(self):
        entities = extract_entities("urgent call dentist tomorrow at 3pm")
        types = {e.type for e in entities}
        assert EntityType.PRIORITY in types
        assert EntityType.DATETIME in types

    def test_reminder_with_duration(self):
        entities = extract_entities("focus for 30 minutes starting now")
        types = {e.type for e in entities}
        assert EntityType.DURATION in types
