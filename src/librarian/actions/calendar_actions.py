"""Calendar action handlers for LibrarianApp."""

from __future__ import annotations

from pathlib import Path

from ..calendar import CalendarEvent, fetch_todays_events
from ..calendar_store import get_association, set_association
from ..database import get_files_by_tag
from ..widgets import AssociateModal, FileList, Preview, TagList
from ..widgets.calendar_list import CalendarList
from ..widgets.calendar_modal import CalendarModal



class CalendarActionsMixin:
    """Mixin providing calendar-related actions.

    The calendar lives in a modal over the right-hand panels, so everything here
    looks the view up rather than assuming where it is.
    """

    def _calendar_modal(self) -> CalendarModal | None:
        """The open calendar modal, if there is one."""
        for screen in reversed(self.screen_stack):
            if isinstance(screen, CalendarModal):
                return screen
        return None

    def _calendar_list(self) -> CalendarList | None:
        modal = self._calendar_modal()
        return modal.calendar_list if modal is not None else None

    def _calendar_preview(self) -> Preview:
        """The preview to write meeting details into.

        The modal carries its own, since it covers Librarian's.
        """
        modal = self._calendar_modal()
        if modal is not None:
            return modal.preview
        return self.query_one("#preview", Preview)

    def action_open_calendar(self) -> None:
        """Open today's meetings in a panel over the right-hand panels."""
        if not self.config.tools.calendar:
            self.notify(
                "Calendar is off. Set calendar = true under [tools] to enable it.",
                severity="warning",
            )
            return

        self.push_screen(CalendarModal())
        self._fetch_calendar_events()

    def _fetch_calendar_events(self) -> None:
        """Fetch calendar events in a background worker."""
        if not self.config.tools.calendar:
            calendar_list = self._calendar_list()
            if calendar_list is not None:
                calendar_list.show_error(
                    "Calendar is off. Set calendar = true under [tools] to enable it."
                )
            return

        self.run_worker(
            self._background_fetch_events,
            name="_fetch_calendar",
            thread=True,
            group="calendar",
            # A calendar that cannot be read is reported in the panel; it must
            # not take the app down, which run_worker does by default.
            exit_on_error=False,
        )

    def _background_fetch_events(self) -> list[CalendarEvent]:
        """Fetch calendar events in background thread."""
        return fetch_todays_events(
            command=self.config.calendar.command,
            calendar_name=self.config.calendar.calendar_name,
        )

    async def on_calendar_list_meeting_selected(
        self, event: CalendarList.MeetingSelected
    ) -> None:
        """Handle meeting highlight — show associated note in preview."""
        preview = self._calendar_preview()
        associated_file = get_association(event.event.uid)
        if associated_file:
            await preview.show_file(associated_file)
        else:
            info = self._format_meeting_info(event.event)
            await preview.show_markdown(event.event.title, info)

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
        calendar_list = self._calendar_list()
        if calendar_list is None:
            return

        event = calendar_list.get_selected_event()
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

        await self._calendar_preview().show_file(file_path)
