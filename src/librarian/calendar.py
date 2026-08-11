"""icalPal wrapper for fetching calendar events."""

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Seconds between the Unix epoch (1970-01-01) and Apple's reference date
# (2001-01-01), which is what icalPal's integer timestamps count from.
APPLE_EPOCH_OFFSET = 978_307_200

INSTALL_HINT = "Install: brew tap ajrosen/tap && brew install icalPal"


class CalendarError(Exception):
    """A calendar fetch failed.

    Raised rather than returning an empty list, so a broken icalPal is never
    reported to the user as a day with no meetings.
    """


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

    Only checks that something executable is there. Whether it *runs* is not
    knowable cheaply -- `icalPal --version` writes to stderr and exits 1, so it
    cannot serve as a health check -- so the fetch itself reports what went
    wrong, via CalendarError.

    Args:
        config_path: Optional path from config. Checked first.

    Returns:
        Path to icalPal binary, or None if not found.
    """
    if config_path:
        path = Path(config_path).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    return shutil.which("icalPal")


def resolve_icalpal(config_path: str = "") -> str:
    """Resolve the icalPal binary, or raise explaining why it cannot be used.

    A configured path that is not usable is reported rather than quietly
    replaced by whatever is on PATH -- a typo in `icalpal_path` should say so,
    not silently run a different binary.
    """
    if config_path:
        path = Path(config_path).expanduser()
        if not path.exists():
            raise CalendarError(f"Configured icalpal_path does not exist: {path}")
        if not path.is_file():
            raise CalendarError(f"Configured icalpal_path is not a file: {path}")
        if not os.access(path, os.X_OK):
            raise CalendarError(f"Configured icalpal_path is not executable: {path}")
        return str(path)

    binary = shutil.which("icalPal")
    if not binary:
        raise CalendarError(f"icalPal not found. {INSTALL_HINT}")
    return binary


def _first_line(text: str) -> str:
    """First non-empty line of output, for use in a one-line error message."""
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _parse_event(raw: dict) -> CalendarEvent | None:
    """Parse a raw icalPal JSON event into a CalendarEvent."""
    try:
        uid = raw.get("uid", raw.get("UUID", ""))
        title = raw.get("title", "Untitled")

        # `sctime`/`ectime` are the fields to trust: they carry *this
        # occurrence* and a UTC offset. For a recurring event, start_date holds
        # the series' original start instead, which sorts the event away from
        # its real slot in today's list.
        start = _parse_datetime(raw.get("sctime"))
        end = _parse_datetime(raw.get("ectime"))

        if start is None:
            start_raw = raw.get("start_date", raw.get("sdate", raw.get("startDate", "")))
            start = _parse_datetime(start_raw)
        if end is None:
            end_raw = raw.get("end_date", raw.get("edate", raw.get("endDate", "")))
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
            recurring=_is_recurring(raw),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _is_recurring(raw: dict) -> bool:
    """Whether an event repeats. icalPal spells this `has_recurrences`.

    Null is treated as absent rather than false, since icalPal writes explicit
    nulls for fields that do not apply to an event.
    """
    value = raw.get("has_recurrences")
    if value is None:
        value = raw.get("recurring", False)
    return bool(value)


def _parse_datetime(value) -> datetime | None:
    """Parse a datetime value from icalPal output.

    Always returns a timezone-aware datetime, so values from different fields
    can be compared and sorted together. Naive values are assumed to be local.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # icalPal's integer timestamps count from Apple's reference date, not
        # the Unix epoch. Read as Unix they land 31 years in the past.
        return datetime.fromtimestamp(value + APPLE_EPOCH_OFFSET).astimezone()
    if isinstance(value, str):
        if not value:
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S %z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed if parsed.tzinfo is not None else parsed.astimezone()
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
        List of CalendarEvent sorted by start time. An empty list means the day
        really is empty.

    Raises:
        CalendarError: icalPal is missing, cannot run, or returned nothing
            usable. Never conflated with an empty day.
    """
    global _cache_result, _cache_time

    # Check cache
    if use_cache and _cache_result is not None:
        if time.time() - _cache_time < _CACHE_TTL:
            events = _cache_result
            if calendar_name:
                events = [e for e in events if e.calendar_name == calendar_name]
            return events

    binary = resolve_icalpal(icalpal_path)

    try:
        result = subprocess.run(
            [binary, "eventsToday", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise CalendarError("icalPal timed out after 10s") from exc
    except OSError as exc:
        raise CalendarError(
            f"Could not run icalPal: {exc.strerror or exc}"
        ) from exc

    if result.returncode != 0:
        detail = _first_line(result.stderr) or f"exit code {result.returncode}"
        raise CalendarError(f"icalPal failed: {detail}")

    try:
        raw_events = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = _first_line(result.stderr) or _first_line(result.stdout) or str(exc)
        raise CalendarError(f"Could not read icalPal output: {detail}") from exc

    if not isinstance(raw_events, list):
        raise CalendarError(
            f"Unexpected icalPal output: expected a list, got {type(raw_events).__name__}"
        )

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
