"""Tests for parsing icalPal output into calendar events.

Fixtures use the field shapes icalPal 4.x actually emits: integer timestamps in
Apple's reference epoch, plus `sctime`/`ectime` strings carrying the occurrence
and a UTC offset.
"""

from datetime import datetime

import pytest

from librarian.calendar import (
    APPLE_EPOCH_OFFSET,
    CalendarEvent,
    _parse_datetime,
    _parse_event,
    find_icalpal,
)

# 2026-08-11 08:45:00 -0400, in the epoch icalPal uses.
APPLE_TS = 808145100


def raw_event(**overrides):
    """A raw icalPal event, shaped like the real thing."""
    event = {
        "UUID": "abc-123",
        "title": "Standup",
        "start_date": APPLE_TS,
        "end_date": APPLE_TS + 900,
        "sctime": "2026-08-11 08:45:00 -0400",
        "ectime": "2026-08-11 09:00:00 -0400",
        "sdate": "today",
        "edate": "today",
        "calendar": "Work",
        "location": "Room 1",
        "notes": "",
        "attendees": ["Burson, Jefferson"],
        "has_recurrences": 0,
        "all_day": 0,
    }
    event.update(overrides)
    return event


class TestParseDatetime:
    def test_integer_uses_the_apple_epoch(self):
        """Read as a Unix timestamp this lands in 1995."""
        parsed = _parse_datetime(APPLE_TS)
        assert parsed is not None
        assert parsed.year == 2026
        assert parsed == datetime.fromtimestamp(
            APPLE_TS + APPLE_EPOCH_OFFSET
        ).astimezone()

    def test_offset_string(self):
        parsed = _parse_datetime("2026-08-11 08:45:00 -0400")
        assert parsed is not None
        assert (parsed.year, parsed.month, parsed.day) == (2026, 8, 11)
        assert parsed.utcoffset().total_seconds() == -4 * 3600

    @pytest.mark.parametrize(
        "value",
        [
            "2026-08-11 08:45:00",
            "2026-08-11T08:45:00",
            "2026-08-11T08:45:00-0400",
        ],
    )
    def test_other_accepted_formats(self, value):
        assert _parse_datetime(value) is not None

    def test_everything_is_timezone_aware(self):
        """Mixed naive and aware values would break sorting."""
        for value in (APPLE_TS, "2026-08-11 08:45:00", "2026-08-11 08:45:00 -0400"):
            parsed = _parse_datetime(value)
            assert parsed is not None and parsed.tzinfo is not None, value

    @pytest.mark.parametrize("value", ["", "today", "not a date", None, True, {}])
    def test_unparseable_values(self, value):
        assert _parse_datetime(value) is None


class TestParseEvent:
    def test_uses_occurrence_fields(self):
        event = _parse_event(raw_event())
        assert event is not None
        assert event.start.date().isoformat() == "2026-08-11"
        assert event.time_range_str == "8:45 AM - 9:00 AM"

    def test_recurring_occurrence_beats_series_start(self):
        """start_date holds the series start for recurring events."""
        series_start = APPLE_TS - 150 * 86400  # months earlier
        event = _parse_event(
            raw_event(
                start_date=series_start,
                end_date=series_start + 900,
                sctime="2026-08-11 10:00:00 -0400",
                ectime="2026-08-11 10:15:00 -0400",
                has_recurrences=1,
            )
        )

        assert event is not None
        assert event.start.date().isoformat() == "2026-08-11"
        assert event.start.strftime("%H:%M") == "10:00"
        assert event.recurring is True

    def test_falls_back_to_timestamps_without_sctime(self):
        event = _parse_event(raw_event(sctime=None, ectime=None))
        assert event is not None
        assert event.start.year == 2026

    def test_recurring_flag_from_has_recurrences(self):
        assert _parse_event(raw_event(has_recurrences=1)).recurring is True
        assert _parse_event(raw_event(has_recurrences=0)).recurring is False

    def test_legacy_recurring_key_still_honored(self):
        event = _parse_event(raw_event(has_recurrences=None, recurring=True))
        assert event is not None and event.recurring is True

    def test_fields_carried_through(self):
        event = _parse_event(raw_event())
        assert event.uid == "abc-123"
        assert event.title == "Standup"
        assert event.calendar_name == "Work"
        assert event.location == "Room 1"
        assert event.attendees == ["Burson, Jefferson"]

    def test_attendee_dicts_are_flattened(self):
        event = _parse_event(
            raw_event(attendees=[{"name": "Ada"}, {"email": "b@example.com"}, "Cy"])
        )
        assert event.attendees == ["Ada", "b@example.com", "Cy"]

    def test_null_location_and_notes_become_empty(self):
        event = _parse_event(raw_event(location=None, notes=None))
        assert event.location == ""
        assert event.notes == ""

    def test_unparseable_dates_drop_the_event(self):
        assert _parse_event(raw_event(sctime=None, start_date="today")) is None
        assert _parse_event(raw_event(ectime=None, end_date=None)) is None

    def test_events_from_mixed_field_sources_sort_together(self):
        """The real regression: recurring events sorted out of place."""
        events = [
            _parse_event(raw_event(sctime="2026-08-11 14:00:00 -0400",
                                   ectime="2026-08-11 14:30:00 -0400")),
            _parse_event(raw_event(sctime=None, ectime=None)),  # 08:45 via timestamp
            _parse_event(raw_event(sctime="2026-08-11 10:00:00 -0400",
                                   ectime="2026-08-11 10:15:00 -0400",
                                   start_date=APPLE_TS - 150 * 86400,
                                   has_recurrences=1)),
        ]
        events.sort(key=lambda e: e.start)

        assert [e.start.strftime("%H:%M") for e in events] == ["08:45", "10:00", "14:00"]


class TestFindIcalpal:
    def test_configured_path_used_when_it_exists(self, tmp_path):
        binary = tmp_path / "icalPal"
        binary.write_text("#!/bin/sh\n")
        assert find_icalpal(str(binary)) == str(binary)

    def test_falls_back_to_path_lookup(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "librarian.calendar.shutil.which", lambda name: "/opt/bin/icalPal"
        )
        assert find_icalpal(str(tmp_path / "missing")) == "/opt/bin/icalPal"

    def test_none_when_not_found(self, monkeypatch):
        monkeypatch.setattr("librarian.calendar.shutil.which", lambda name: None)
        assert find_icalpal("") is None


class TestCalendarEvent:
    def test_time_formatting(self):
        event = CalendarEvent(
            uid="x",
            title="t",
            start=datetime(2026, 8, 11, 8, 45).astimezone(),
            end=datetime(2026, 8, 11, 9, 5).astimezone(),
        )
        assert event.time_str == "8:45 AM"
        assert event.time_range_str == "8:45 AM - 9:05 AM"


class TestMeetingPreview:
    """Highlighting a meeting with no associated note must render its details.

    This path previously called an async method without awaiting it, so the
    preview silently stayed blank -- and would have raised on a None path had
    the coroutine ever run.
    """

    @pytest.fixture
    def app(self, tmp_path, tmp_index):
        from librarian.app import LibrarianApp
        from librarian.calendar_store import init_store
        from librarian.config import CalendarConfig, Config, TagConfig

        root = tmp_path / "notes"
        root.mkdir()
        init_store(tmp_path / "store")
        return LibrarianApp(
            Config(
                scan_directory=root,
                editor="vim",
                tags=TagConfig(),
                export_directory=tmp_path / "exports",
                data_directory=tmp_path / "data",
                calendar=CalendarConfig(enabled=True),
            )
        )

    async def test_meeting_details_render_in_preview(self, app):
        from librarian.widgets import Preview, TagList

        event = _parse_event(raw_event(title="Standup", location="Room 1"))

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            tag_list = app.query_one(TagList)
            tag_list._switch_panel("calendar")
            await pilot.pause()

            tag_list.calendar_list.update_events([event])
            await pilot.pause()
            tag_list.calendar_list.list_view.index = 0
            await pilot.pause()
            await pilot.pause()

            preview = app.query_one(Preview)
            header = preview.query_one("#preview-header")
            assert "Standup" in str(header.render())
            # A meeting is not a file, so there is no current file to link from.
            assert preview.get_current_file() is None
            assert len(list(preview.markdown_widget.children)) > 0

    async def test_preview_show_markdown_clears_current_file(self, app):
        from librarian.widgets import Preview

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            preview = app.query_one(Preview)

            await preview.show_file(None)
            await preview.show_markdown("Some Meeting", "# Some Meeting\n\nbody")
            await pilot.pause()

            assert preview.get_current_file() is None
            assert "Some Meeting" in str(
                preview.query_one("#preview-header").render()
            )
