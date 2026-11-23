"""When the app runs the monitor: next run time and a plain description."""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from typing import Any, Dict, Optional

from amygda_ops_risk_score.monitor.spec import WEEKDAYS

_DAY_NAMES = dict(
    zip(
        WEEKDAYS,
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    )
)


def next_run(schedule: Optional[Dict[str, Any]], after: datetime) -> Optional[datetime]:
    """The first scheduled time strictly after ``after`` (local time).

    A paused or missing schedule has no next run.
    """
    if not schedule or schedule.get("paused"):
        return None
    midnight = after.replace(hour=0, minute=0, second=0, microsecond=0)
    if schedule["every"] == "hours":
        # Slots are counted from midnight, so they don't drift on a restart.
        step = timedelta(hours=schedule["hours"])
        slot = midnight
        while slot <= after:
            slot += step
        return slot
    hour, minute = (int(x) for x in schedule["at"].split(":"))
    slot = midnight.replace(hour=hour, minute=minute)
    if schedule["every"] == "day":
        return slot if slot > after else slot + timedelta(days=1)
    slot += timedelta(days=(WEEKDAYS.index(schedule["weekday"]) - slot.weekday()) % 7)
    return slot if slot > after else slot + timedelta(days=7)


def describe(schedule: Optional[Dict[str, Any]]) -> str:
    """The schedule in a few words, e.g. "Every day at 06:00"."""
    if not schedule:
        return "No schedule"
    if schedule["every"] == "hours":
        n = schedule["hours"]
        text = "Every hour" if n == 1 else f"Every {n} hours"
    elif schedule["every"] == "day":
        text = f"Every day at {schedule['at']}"
    else:
        text = f"Every {_DAY_NAMES[schedule['weekday']]} at {schedule['at']}"
    return f"{text} (paused)" if schedule.get("paused") else text
