"""icalPal wrapper for fetching calendar events."""

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """A calendar event from icalPal."""

    uid: str
    title: str
    start: datetime
    end: datetime
    calendar_name: str = ""
    location: str = ""
    notes: str = ""
    attendees: list[str] = field(default_factory=list)
    recurring: bool = False

    @property
    def time_str(self) -> str:
        """Format start time as human-readable string (e.g., '10:00 AM')."""
        return self.start.strftime("%-I:%M %p")

    @property
    def time_range_str(self) -> str:
        """Format time range (e.g., '10:00 AM - 11:00 AM')."""
        return f"{self.start.strftime('%-I:%M %p')} - {self.end.strftime('%-I:%M %p')}"


# Simple TTL cache for calendar events
_cache_result: list[CalendarEvent] | None = None
_cache_time: float = 0
_CACHE_TTL = 300  # 5 minutes


def find_icalpal(config_path: str = "") -> str | None:
    """Find the icalPal binary.

    Args:
        config_path: Optional path from config. Checked first.

    Returns:
        Path to icalPal binary, or None if not found.
    """
    if config_path:
        path = Path(config_path).expanduser()
        if path.exists() and path.is_file():
            return str(path)

    return shutil.which("icalPal")


def _parse_event(raw: dict) -> CalendarEvent | None:
    """Parse a raw icalPal JSON event into a CalendarEvent."""
    try:
        uid = raw.get("uid", raw.get("UUID", ""))
        title = raw.get("title", "Untitled")

        # icalPal outputs dates in various formats
        start_raw = raw.get("start_date", raw.get("sdate", raw.get("startDate", "")))
        end_raw = raw.get("end_date", raw.get("edate", raw.get("endDate", "")))

        start = _parse_datetime(start_raw)
        end = _parse_datetime(end_raw)

        if start is None or end is None:
            return None

        attendees_raw = raw.get("attendees", [])
        if isinstance(attendees_raw, list):
            attendees = [
                a.get("name", a.get("email", str(a)))
                if isinstance(a, dict)
                else str(a)
                for a in attendees_raw
            ]
        else:
            attendees = []

        return CalendarEvent(
            uid=str(uid),
            title=title,
            start=start,
            end=end,
            calendar_name=raw.get("calendar", ""),
            location=raw.get("location", "") or "",
            notes=raw.get("notes", "") or "",
            attendees=attendees,
            recurring=bool(raw.get("recurring", False)),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _parse_datetime(value) -> datetime | None:
    """Parse a datetime value from icalPal output."""
    if isinstance(value, (int, float)):
        # Unix timestamp
        return datetime.fromtimestamp(value)
    if isinstance(value, str):
        if not value:
            return None
        # Try ISO format first
        for fmt in (
            "%Y-%m-%d %H:%M:%S %z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def fetch_todays_events(
    icalpal_path: str = "",
    calendar_name: str = "",
    use_cache: bool = True,
) -> list[CalendarEvent]:
    """Fetch today's calendar events via icalPal.

    Args:
        icalpal_path: Path to icalPal binary (auto-detect if empty).
        calendar_name: Filter to specific calendar (empty = all).
        use_cache: Whether to use the TTL cache.

    Returns:
        List of CalendarEvent sorted by start time.
    """
    global _cache_result, _cache_time

    # Check cache
    if use_cache and _cache_result is not None:
        if time.time() - _cache_time < _CACHE_TTL:
            events = _cache_result
            if calendar_name:
                events = [e for e in events if e.calendar_name == calendar_name]
            return events

    binary = find_icalpal(icalpal_path)
    if not binary:
        return []

    try:
        result = subprocess.run(
            [binary, "eventsToday", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        raw_events = json.loads(result.stdout)
        if not isinstance(raw_events, list):
            return []

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to fetch calendar events: %s", e)
        return []

    events = []
    for raw in raw_events:
        event = _parse_event(raw)
        if event is not None:
            events.append(event)

    # Sort by start time
    events.sort(key=lambda e: e.start)

    # Update cache (before filtering)
    _cache_result = events
    _cache_time = time.time()
    logger.info("Fetched %d calendar events", len(events))

    # Filter by calendar name if specified
    if calendar_name:
        events = [e for e in events if e.calendar_name == calendar_name]

    return events


def clear_cache() -> None:
    """Clear the event cache, forcing a fresh fetch."""
    global _cache_result, _cache_time
    _cache_result = None
    _cache_time = 0
