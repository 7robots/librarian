"""Calendar action handlers for LibrarianApp."""

from __future__ import annotations

from pathlib import Path

from ..calendar import CalendarEvent, fetch_todays_events, find_icalpal
from ..calendar_store import get_association, set_association
from ..database import get_files_by_tag
from ..widgets import AssociateModal, FileList, Preview, TagList
from ..widgets.calendar_list import CalendarList

from textual.widgets import Static


class CalendarActionsMixin:
    """Mixin providing calendar-related actions."""

    def on_tag_list_calendar_refresh_requested(
        self, event: TagList.CalendarRefreshRequested
    ) -> None:
        """Handle calendar panel activation — fetch events in background."""
        self._fetch_calendar_events()

    def _fetch_calendar_events(self) -> None:
        """Fetch calendar events in a background worker."""
        if not self.config.calendar.enabled:
            tag_list = self.query_one("#tag-list", TagList)
            tag_list.calendar_list.show_error("Calendar disabled in config")
            return

        icalpal_bin = find_icalpal(self.config.calendar.icalpal_path)
        if not icalpal_bin:
            tag_list = self.query_one("#tag-list", TagList)
            tag_list.calendar_list.show_error(
                "icalPal not found.\nInstall: brew tap ajrosen/tap && brew install icalPal"
            )
            return

        self.run_worker(
            self._background_fetch_events,
            name="_fetch_calendar",
            thread=True,
            group="calendar",
        )

    def _background_fetch_events(self) -> list[CalendarEvent]:
        """Fetch calendar events in background thread."""
        return fetch_todays_events(
            icalpal_path=self.config.calendar.icalpal_path,
            calendar_name=self.config.calendar.calendar_name,
        )

    async def on_calendar_list_meeting_selected(
        self, event: CalendarList.MeetingSelected
    ) -> None:
        """Handle meeting highlight — show associated note in preview."""
        associated_file = get_association(event.event.uid)
        if associated_file:
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files([associated_file], navigation_target=event.event.title)
            preview = self.query_one("#preview", Preview)
            await preview.show_file(associated_file)
        else:
            preview = self.query_one("#preview", Preview)
            info = self._format_meeting_info(event.event)
            preview.show_content(None, info, None)
            preview.query_one("#preview-header", Static).update(
                f"PREVIEW - {event.event.title}"
            )
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files([], navigation_target=event.event.title)

    def _format_meeting_info(self, event: CalendarEvent) -> str:
        """Format a CalendarEvent as markdown for preview."""
        lines = [f"# {event.title}", ""]
        lines.append(f"**Time:** {event.time_range_str}")
        if event.calendar_name:
            lines.append(f"**Calendar:** {event.calendar_name}")
        if event.location:
            lines.append(f"**Location:** {event.location}")
        if event.attendees:
            lines.append(f"**Attendees:** {', '.join(event.attendees)}")
        if event.notes:
            lines.extend(["", "---", "", event.notes])
        lines.extend(["", "", "*Press `a` to associate a note, or `n` to create one.*"])
        return "\n".join(lines)

    def action_associate_meeting(self) -> None:
        """Associate the selected meeting with a file from #meetings tag."""
        tag_list = self.query_one("#tag-list", TagList)
        if tag_list.active_tool != "calendar":
            return

        event = tag_list.calendar_list.get_selected_event()
        if not event:
            self.notify("No meeting selected", severity="warning")
            return

        files = get_files_by_tag("meetings")
        file_paths = [f[0] for f in files]

        if not file_paths:
            self.notify("No files with #meetings tag. Press 'n' to create one.", severity="warning")
            return

        self._associating_event_uid = event.uid
        self._associating_event_title = event.title
        self.push_screen(
            AssociateModal(event.title, file_paths),
            self._on_associate_dismissed,
        )

    async def _on_associate_dismissed(self, result) -> None:
        """Handle associate modal dismissal."""
        if result is None:
            return

        file_path = result
        event_uid = self._associating_event_uid
        event_title = self._associating_event_title

        set_association(event_uid, file_path)
        self.notify(f"Associated '{event_title}' with {file_path.name}")

        file_list = self.query_one("#file-list", FileList)
        file_list.update_files([file_path], navigation_target=event_title)
        preview = self.query_one("#preview", Preview)
        await preview.show_file(file_path)
