"""
Tool: Energy Tracker
Purpose: Infer user energy levels from observable activity patterns

This tool observes behavioral signals and builds energy profiles without
requiring any self-reporting from the user. ADHD users won't fill out
energy logs - their behavior tells the story.

Signals tracked:
- Response time: How quickly user responds (faster = higher energy)
- Message length: How much user writes (longer = more engaged)
- Active duration: How long sessions last (longer = flow state)
- Task completion: How many tasks done (more = productive period)

Usage:
    # Record an activity observation
    python tools/learning/energy_tracker.py --action record --user alice \\
        --signals '{"response_time_ms": 1200, "message_length": 45}'

    # Get current energy estimate
    python tools/learning/energy_tracker.py --action current --user alice

    # Get full energy profile (all hours)
    python tools/learning/energy_tracker.py --action profile --user alice

    # Get peak hours for a specific day
    python tools/learning/energy_tracker.py --action peak-hours --user alice --day monday

    # Rebuild aggregated profiles from observations
    python tools/learning/energy_tracker.py --action rebuild --user alice

Dependencies:
    - sqlite3 (stdlib)
    - yaml (PyYAML)

Output:
    JSON result with success status and data
"""

import argparse
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

import yaml


# Path constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "learning.db"
CONFIG_PATH = PROJECT_ROOT / "args" / "learning.yaml"

# Energy levels
ENERGY_LEVELS = ["low", "medium", "high", "peak"]

# Day name mapping
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f)
            return config.get("learning", {}).get("energy_tracking", {})
    # Return defaults if no config
    return {
        "enabled": True,
        "min_samples_for_pattern": 10,
        "confidence_threshold": 0.6,
        "decay_factor": 0.95,
        "signals": {
            "response_time_weight": 0.3,
            "message_length_weight": 0.2,
            "active_duration_weight": 0.3,
            "task_completion_weight": 0.2,
        },
        "thresholds": {"peak": 0.8, "high": 0.6, "medium": 0.4, "low": 0.0},
        "response_time_benchmarks": {"fast": 2000, "normal": 5000, "slow": 10000},
        "message_length_benchmarks": {"short": 20, "normal": 100, "long": 300},
        "session_duration_benchmarks": {"brief": 120, "normal": 600, "extended": 1800},
    }


def get_connection() -> sqlite3.Connection:
    """Get database connection, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    # Energy observations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS energy_observations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            observed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            hour INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            signals TEXT,
            inferred_energy TEXT CHECK(inferred_energy IN ('low', 'medium', 'high', 'peak')),
            energy_score REAL DEFAULT 0.5,
            confidence REAL DEFAULT 0.5
        )
    """)

    # Energy profiles table (aggregated)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS energy_profiles (
            user_id TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,
            hour INTEGER NOT NULL,
            avg_energy_score REAL DEFAULT 0.5,
            sample_count INTEGER DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, day_of_week, hour)
        )
    """)

    # Peak hours table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS peak_hours (
            user_id TEXT PRIMARY KEY,
            monday TEXT,
            tuesday TEXT,
            wednesday TEXT,
            thursday TEXT,
            friday TEXT,
            saturday TEXT,
            sunday TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_energy_obs_user ON energy_observations(user_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_energy_obs_time ON energy_observations(observed_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_energy_profiles_user ON energy_profiles(user_id)"
    )

    conn.commit()
    return conn


def row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON fields
    if d.get("signals"):
        try:
            d["signals"] = json.loads(d["signals"])
        except json.JSONDecodeError:
            pass
    return d


def normalize_signal(value: float, benchmarks: dict[str, float], inverse: bool = False) -> float:
    """
    Normalize a signal value to 0-1 scale based on benchmarks.

    Args:
        value: The raw signal value
        benchmarks: Dict with 'fast'/'short'/'brief', 'normal', 'slow'/'long'/'extended'
        inverse: If True, lower values = higher score (like response time)

    Returns:
        Normalized score between 0.0 and 1.0
    """
    # Get benchmark values (handle different key names)
    low_key = next((k for k in ["fast", "short", "brief"] if k in benchmarks), None)
    high_key = next((k for k in ["slow", "long", "extended"] if k in benchmarks), None)

    if not low_key or not high_key:
        return 0.5  # Can't normalize without benchmarks

    low = benchmarks[low_key]
    high = benchmarks[high_key]

    if inverse:
        # For response time: fast (low value) = high score
        if value <= low:
            return 1.0
        elif value >= high:
            return 0.0
        else:
            return 1.0 - (value - low) / (high - low)
    else:
        # For message length: high value = high score
        if value >= high:
            return 1.0
        elif value <= low:
            return 0.2  # Not 0 - even short messages show some engagement
        else:
            return 0.2 + 0.8 * (value - low) / (high - low)


def calculate_energy_score(signals: dict[str, Any], config: dict[str, Any]) -> tuple[float, float]:
    """
    Calculate energy score from activity signals.

    Args:
        signals: Dict with response_time_ms, message_length, active_duration_s, tasks_completed
        config: Configuration with weights and benchmarks

    Returns:
        Tuple of (energy_score, confidence)
    """
    weights = config.get("signals", {})
    score_components = []
    total_weight = 0

    # Response time (inverse - faster is better)
    if "response_time_ms" in signals:
        benchmarks = config.get(
            "response_time_benchmarks", {"fast": 2000, "normal": 5000, "slow": 10000}
        )
        rt_score = normalize_signal(signals["response_time_ms"], benchmarks, inverse=True)
        weight = weights.get("response_time_weight", 0.3)
        score_components.append(rt_score * weight)
        total_weight += weight

    # Message length
    if "message_length" in signals:
        benchmarks = config.get(
            "message_length_benchmarks", {"short": 20, "normal": 100, "long": 300}
        )
        ml_score = normalize_signal(signals["message_length"], benchmarks, inverse=False)
        weight = weights.get("message_length_weight", 0.2)
        score_components.append(ml_score * weight)
        total_weight += weight

    # Active duration
    if "active_duration_s" in signals:
        benchmarks = config.get(
            "session_duration_benchmarks", {"brief": 120, "normal": 600, "extended": 1800}
        )
        ad_score = normalize_signal(signals["active_duration_s"], benchmarks, inverse=False)
        weight = weights.get("active_duration_weight", 0.3)
        score_components.append(ad_score * weight)
        total_weight += weight

    # Task completion (simple: any completion is positive signal)
    if "tasks_completed" in signals:
        tc = signals["tasks_completed"]
        tc_score = min(1.0, tc * 0.3) if tc > 0 else 0.0  # Each task adds 0.3, cap at 1.0
        weight = weights.get("task_completion_weight", 0.2)
        score_components.append(tc_score * weight)
        total_weight += weight

    if total_weight == 0:
        return 0.5, 0.0  # No signals, no confidence

    # Normalize to 0-1 range
    energy_score = sum(score_components) / total_weight

    # Confidence based on number of signals provided
    signal_count = len(score_components)
    confidence = min(0.9, signal_count * 0.25)  # 25% per signal, cap at 90%

    return energy_score, confidence


def score_to_level(score: float, thresholds: dict[str, float]) -> str:
    """Convert energy score to named level."""
    if score >= thresholds.get("peak", 0.8):
        return "peak"
    elif score >= thresholds.get("high", 0.6):
        return "high"
    elif score >= thresholds.get("medium", 0.4):
        return "medium"
    else:
        return "low"


def record_observation(
    user_id: str, signals: dict[str, Any], timestamp: datetime | None = None
) -> dict[str, Any]:
    """
    Record an energy observation from activity signals.

    Args:
        user_id: User identifier
        signals: Activity signals (response_time_ms, message_length, etc.)
        timestamp: When observed (defaults to now)

    Returns:
        dict with success status and observation ID
    """
    config = load_config()

    if not config.get("enabled", True):
        return {"success": False, "error": "Energy tracking is disabled"}

    if not signals:
        return {"success": False, "error": "No signals provided"}

    ts = timestamp or datetime.now()
    hour = ts.hour
    day_of_week = ts.weekday()  # Monday = 0

    # Calculate energy score
    energy_score, confidence = calculate_energy_score(signals, config)
    energy_level = score_to_level(energy_score, config.get("thresholds", {}))

    obs_id = str(uuid.uuid4())[:8]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO energy_observations
        (id, user_id, observed_at, hour, day_of_week, signals, inferred_energy, energy_score, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            obs_id,
            user_id,
            ts.isoformat(),
            hour,
            day_of_week,
            json.dumps(signals),
            energy_level,
            energy_score,
            confidence,
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "observation_id": obs_id,
        "inferred_energy": energy_level,
        "energy_score": round(energy_score, 3),
        "confidence": round(confidence, 3),
        "hour": hour,
        "day": DAY_NAMES[day_of_week],
    }


def get_current_energy(user_id: str) -> dict[str, Any]:
    """
    Estimate current energy level based on recent activity and profiles.

    Args:
        user_id: User identifier

    Returns:
        dict with current energy estimate
    """
    config = load_config()
    now = datetime.now()
    hour = now.hour
    day_of_week = now.weekday()

    conn = get_connection()
    cursor = conn.cursor()

    # First, check for recent observations (last 30 minutes)
    recent_cutoff = (now - timedelta(minutes=30)).isoformat()
    cursor.execute(
        """
        SELECT AVG(energy_score) as avg_score, COUNT(*) as count
        FROM energy_observations
        WHERE user_id = ? AND observed_at >= ?
    """,
        (user_id, recent_cutoff),
    )

    recent = cursor.fetchone()

    if recent and recent["count"] and recent["count"] > 0:
        # Have recent data - use it
        energy_score = recent["avg_score"]
        source = "recent_activity"
        confidence = min(0.9, 0.5 + recent["count"] * 0.1)
    else:
        # Fall back to profile for this hour
        cursor.execute(
            """
            SELECT avg_energy_score, sample_count
            FROM energy_profiles
            WHERE user_id = ? AND day_of_week = ? AND hour = ?
        """,
            (user_id, day_of_week, hour),
        )

        profile = cursor.fetchone()

        if profile and profile["sample_count"] >= config.get("min_samples_for_pattern", 10):
            energy_score = profile["avg_energy_score"]
            source = "historical_profile"
            confidence = min(0.8, 0.3 + profile["sample_count"] * 0.02)
        else:
            # Not enough data
            conn.close()
            return {
                "success": True,
                "user_id": user_id,
                "energy_level": None,
                "energy_score": None,
                "confidence": 0.0,
                "source": "insufficient_data",
                "message": "I'm still learning your patterns - give me a few more days of activity.",
                "hour": hour,
                "day": DAY_NAMES[day_of_week],
            }

    conn.close()

    energy_level = score_to_level(energy_score, config.get("thresholds", {}))

    return {
        "success": True,
        "user_id": user_id,
        "energy_level": energy_level,
        "energy_score": round(energy_score, 3),
        "confidence": round(confidence, 3),
        "source": source,
        "hour": hour,
        "day": DAY_NAMES[day_of_week],
    }


def get_energy_profile(user_id: str) -> dict[str, Any]:
    """
    Get full energy profile for a user across all hours.

    Args:
        user_id: User identifier

    Returns:
        dict with energy profile by day and hour
    """
    config = load_config()
    min_samples = config.get("min_samples_for_pattern", 10)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT day_of_week, hour, avg_energy_score, sample_count
        FROM energy_profiles
        WHERE user_id = ?
        ORDER BY day_of_week, hour
    """,
        (user_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {
            "success": True,
            "user_id": user_id,
            "profile": {},
            "sufficient_data": False,
            "message": "No energy profile yet - I'm still learning your patterns.",
        }

    # Organize by day
    profile = {day: {} for day in DAY_NAMES}
    total_samples = 0

    for row in rows:
        day = DAY_NAMES[row["day_of_week"]]
        hour = row["hour"]
        score = row["avg_energy_score"]
        samples = row["sample_count"]
        total_samples += samples

        profile[day][hour] = {
            "score": round(score, 3),
            "level": score_to_level(score, config.get("thresholds", {})),
            "samples": samples,
            "reliable": samples >= min_samples,
        }

    sufficient_data = total_samples >= min_samples * 5  # At least 5 hours with sufficient data

    return {
        "success": True,
        "user_id": user_id,
        "profile": profile,
        "total_samples": total_samples,
        "sufficient_data": sufficient_data,
    }


def get_peak_hours(user_id: str, day: str | None = None) -> dict[str, Any]:
    """
    Get peak energy hours for a user.

    Args:
        user_id: User identifier
        day: Specific day name (optional, returns all days if not specified)

    Returns:
        dict with peak hours per day
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM peak_hours WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "success": True,
            "user_id": user_id,
            "peak_hours": {},
            "message": "Peak hours not yet calculated - need more activity data.",
        }

    peak_hours = {}
    for day_name in DAY_NAMES:
        day_data = row[day_name]
        if day_data:
            try:
                peak_hours[day_name] = json.loads(day_data)
            except json.JSONDecodeError:
                peak_hours[day_name] = []
        else:
            peak_hours[day_name] = []

    if day:
        day_lower = day.lower()
        if day_lower in peak_hours:
            return {
                "success": True,
                "user_id": user_id,
                "day": day_lower,
                "peak_hours": peak_hours[day_lower],
            }
        else:
            return {"success": False, "error": f"Invalid day: {day}"}

    return {
        "success": True,
        "user_id": user_id,
        "peak_hours": peak_hours,
        "updated_at": row["updated_at"],
    }


def rebuild_profiles(user_id: str, lookback_days: int = 30) -> dict[str, Any]:
    """
    Rebuild energy profiles from observations.

    Args:
        user_id: User identifier
        lookback_days: How many days back to analyze

    Returns:
        dict with rebuild status
    """
    config = load_config()
    decay_factor = config.get("decay_factor", 0.95)
    thresholds = config.get("thresholds", {"peak": 0.8})

    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    # Get all observations for user
    cursor.execute(
        """
        SELECT day_of_week, hour, energy_score, observed_at
        FROM energy_observations
        WHERE user_id = ? AND observed_at >= ?
        ORDER BY observed_at
    """,
        (user_id, cutoff),
    )

    rows = cursor.fetchall()

    if not rows:
        conn.close()
        return {
            "success": True,
            "user_id": user_id,
            "profiles_updated": 0,
            "message": "No observations to build profiles from.",
        }

    # Aggregate by day/hour
    aggregates = {}
    for row in rows:
        key = (row["day_of_week"], row["hour"])
        if key not in aggregates:
            aggregates[key] = []
        aggregates[key].append(row["energy_score"])

    # Update profiles
    profiles_updated = 0
    for (day_of_week, hour), scores in aggregates.items():
        avg_score = mean(scores)
        sample_count = len(scores)

        cursor.execute(
            """
            INSERT INTO energy_profiles (user_id, day_of_week, hour, avg_energy_score, sample_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, day_of_week, hour) DO UPDATE SET
                avg_energy_score = ?,
                sample_count = ?,
                last_updated = ?
        """,
            (
                user_id,
                day_of_week,
                hour,
                avg_score,
                sample_count,
                datetime.now().isoformat(),
                avg_score,
                sample_count,
                datetime.now().isoformat(),
            ),
        )
        profiles_updated += 1

    # Calculate peak hours for each day
    peak_threshold = thresholds.get("peak", 0.8)
    high_threshold = thresholds.get("high", 0.6)

    peak_hours_data = {day: [] for day in DAY_NAMES}

    for (day_of_week, hour), scores in aggregates.items():
        avg_score = mean(scores)
        # Consider it a peak hour if average score is in the high/peak range
        if avg_score >= high_threshold:
            day_name = DAY_NAMES[day_of_week]
            peak_hours_data[day_name].append(hour)

    # Sort peak hours
    for day in DAY_NAMES:
        peak_hours_data[day].sort()

    # Upsert peak hours
    cursor.execute(
        """
        INSERT INTO peak_hours (user_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            monday = ?, tuesday = ?, wednesday = ?, thursday = ?, friday = ?, saturday = ?, sunday = ?,
            updated_at = ?
    """,
        (
            user_id,
            json.dumps(peak_hours_data["monday"]),
            json.dumps(peak_hours_data["tuesday"]),
            json.dumps(peak_hours_data["wednesday"]),
            json.dumps(peak_hours_data["thursday"]),
            json.dumps(peak_hours_data["friday"]),
            json.dumps(peak_hours_data["saturday"]),
            json.dumps(peak_hours_data["sunday"]),
            datetime.now().isoformat(),
            # ON CONFLICT values
            json.dumps(peak_hours_data["monday"]),
            json.dumps(peak_hours_data["tuesday"]),
            json.dumps(peak_hours_data["wednesday"]),
            json.dumps(peak_hours_data["thursday"]),
            json.dumps(peak_hours_data["friday"]),
            json.dumps(peak_hours_data["saturday"]),
            json.dumps(peak_hours_data["sunday"]),
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "user_id": user_id,
        "profiles_updated": profiles_updated,
        "observations_analyzed": len(rows),
        "peak_hours": peak_hours_data,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Energy Tracker - Infer energy levels from activity patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Record an observation
    python energy_tracker.py --action record --user alice \\
        --signals '{"response_time_ms": 1200, "message_length": 45}'

    # Get current energy estimate
    python energy_tracker.py --action current --user alice

    # Get full energy profile
    python energy_tracker.py --action profile --user alice

    # Get peak hours for Monday
    python energy_tracker.py --action peak-hours --user alice --day monday

    # Rebuild profiles from observations
    python energy_tracker.py --action rebuild --user alice
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=["record", "current", "profile", "peak-hours", "rebuild"],
        help="Action to perform",
    )
    parser.add_argument("--user", required=True, help="User ID")
    parser.add_argument("--signals", help="JSON object with activity signals")
    parser.add_argument("--day", help="Day name for peak-hours (e.g., monday)")
    parser.add_argument(
        "--lookback", type=int, default=30, help="Days to look back for rebuild (default: 30)"
    )

    args = parser.parse_args()
    result = None

    if args.action == "record":
        if not args.signals:
            print(json.dumps({"success": False, "error": "--signals required for record action"}))
            sys.exit(1)

        try:
            signals = json.loads(args.signals)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON in --signals: {e}"}))
            sys.exit(1)

        result = record_observation(args.user, signals)

    elif args.action == "current":
        result = get_current_energy(args.user)

    elif args.action == "profile":
        result = get_energy_profile(args.user)

    elif args.action == "peak-hours":
        result = get_peak_hours(args.user, args.day)

    elif args.action == "rebuild":
        result = rebuild_profiles(args.user, args.lookback)

    if result:
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
