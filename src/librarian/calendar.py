"""Fetching today's calendar events from a command-line backend.

Two backends speak the same protocol -- `<backend> eventsToday -o json` -- so
either can be used interchangeably:

* **calctl** (https://github.com/7robots/calctl), preferred. Ours, pure Python,
  and measurably more accurate than icalPal on recurring and all-day events.
* **icalPal** (https://github.com/ajrosen/icalPal), the original. Kept as a
  fallback so an existing install keeps working.

calctl exists because icalPal's *toolchain* broke here once: its shebang pointed
at a Ruby that Homebrew had autoremoved, through a dependency Librarian neither
controls nor can see. See docs/icalpal-python-port.md.
"""

import errno
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
# (2001-01-01), which is what both backends' integer timestamps count from.
APPLE_EPOCH_OFFSET = 978_307_200

# Tried in order when no command is configured. calctl first: it is the one we
# maintain, and switching to it needs no config change.
BACKENDS = ("calctl", "icalPal")

INSTALL_HINT = (
    "Install calctl: git clone https://github.com/7robots/calctl "
    "&& cd calctl && ./install.sh"
)


class CalendarError(Exception):
    """A calendar fetch failed.

    Raised rather than returning an empty list, so a broken backend is never
    reported to the user as a day with no meetings.
    """


@dataclass
class CalendarEvent:
    """A calendar event from a backend."""

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


def _is_path(command: str) -> bool:
    """Whether a configured value names a location rather than a command.

    `calctl` is looked up on PATH; `~/bin/calctl` and `/usr/local/bin/calctl` are
    used as given. This is the same rule the `reminders` and `projects` settings
    already follow, so all three behave alike.
    """
    return os.sep in command or command.startswith("~")


def _autodetect() -> str | None:
    """First backend found on PATH, in BACKENDS order."""
    for name in BACKENDS:
        found = shutil.which(name)
        if found:
            return found
    return None


def find_backend(command: str = "") -> str | None:
    """Find a calendar backend, falling back to auto-detection.

    Only checks that something executable is there. Whether it *runs* is not
    knowable cheaply -- `icalPal --version` writes to stderr and exits 1, so it
    cannot serve as a health check -- so the fetch itself reports what went
    wrong, via CalendarError.

    Lenient by design: an unusable `command` falls through to auto-detection.
    `resolve_backend` is the strict version, and the one the fetch uses.

    Args:
        command: Optional command name or path from config. Checked first.

    Returns:
        Path to a backend executable, or None if none was found.
    """
    if command:
        if _is_path(command):
            path = Path(command).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        else:
            found = shutil.which(command)
            if found:
                return found

    return _autodetect()


def resolve_backend(command: str = "") -> str:
    """Resolve the backend to run, or raise explaining why it cannot be used.

    A configured command that is not usable is reported rather than quietly
    replaced by whatever is on PATH -- a typo in `[calendar] command` should say
    so, not silently run a different binary.
    """
    if command:
        if not _is_path(command):
            found = shutil.which(command)
            if not found:
                raise CalendarError(
                    f"Configured calendar command not found on PATH: {command}"
                )
            return found

        path = Path(command).expanduser()
        if not path.exists():
            raise CalendarError(f"Configured calendar command does not exist: {path}")
        if not path.is_file():
            raise CalendarError(f"Configured calendar command is not a file: {path}")
        if not os.access(path, os.X_OK):
            raise CalendarError(f"Configured calendar command is not executable: {path}")
        return str(path)

    binary = _autodetect()
    if not binary:
        raise CalendarError(
            f"No calendar backend found. Tried {' and '.join(BACKENDS)}. {INSTALL_HINT}"
        )
    return binary


def _first_line(text: str) -> str:
    """First non-empty line of output, for use in a one-line error message."""
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _parse_event(raw: dict) -> CalendarEvent | None:
    """Parse a raw backend JSON event into a CalendarEvent."""
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
    """Whether an event repeats. Both backends spell this `has_recurrences`.

    Null is treated as absent rather than false, since icalPal writes explicit
    nulls for fields that do not apply to an event.
    """
    value = raw.get("has_recurrences")
    if value is None:
        value = raw.get("recurring", False)
    return bool(value)


def _parse_datetime(value) -> datetime | None:
    """Parse a datetime value from backend output.

    Always returns a timezone-aware datetime, so values from different fields
    can be compared and sorted together. Naive values are assumed to be local.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        # Backend integer timestamps count from Apple's reference date, not
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
    command: str = "",
    calendar_name: str = "",
    use_cache: bool = True,
) -> list[CalendarEvent]:
    """Fetch today's calendar events from a backend.

    Args:
        command: Backend command name or path (auto-detect if empty).
        calendar_name: Filter to specific calendar (empty = all).
        use_cache: Whether to use the TTL cache.

    Returns:
        List of CalendarEvent sorted by start time. An empty list means the day
        really is empty.

    Raises:
        CalendarError: The backend is missing, cannot run, or returned nothing
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

    binary = resolve_backend(command)
    name = Path(binary).name

    try:
        result = subprocess.run(
            [binary, "eventsToday", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise CalendarError(f"{name} timed out after 10s") from exc
    except OSError as exc:
        detail = exc.strerror or str(exc)
        if exc.errno == errno.ENOENT and Path(binary).is_file():
            # The file is there and executable, so a "no such file" from exec is
            # about something the *binary* needs -- classically a shebang naming
            # an interpreter that has been removed. Reporting the raw errno here
            # reads as "not installed", which sent a real diagnosis down the
            # wrong path once.
            raise CalendarError(
                f"{name} is installed but could not start: {detail}. "
                "Its interpreter is probably missing (a dangling #! line)."
            ) from exc
        raise CalendarError(f"Could not run {name}: {detail}") from exc

    if result.returncode != 0:
        detail = _first_line(result.stderr) or f"exit code {result.returncode}"
        raise CalendarError(f"{name} failed: {detail}")

    try:
        raw_events = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        detail = _first_line(result.stderr) or _first_line(result.stdout) or str(exc)
        raise CalendarError(f"Could not read {name} output: {detail}") from exc

    if not isinstance(raw_events, list):
        raise CalendarError(
            f"Unexpected {name} output: expected a list, got {type(raw_events).__name__}"
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
