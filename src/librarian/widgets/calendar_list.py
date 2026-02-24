"""Calendar list widget for displaying today's meetings."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static

from ..calendar import CalendarEvent


class MeetingItem(ListItem):
    """A list item representing a calendar meeting."""

    def __init__(self, event: CalendarEvent) -> None:
        super().__init__()
        self.event = event

    def compose(self) -> ComposeResult:
        yield Label(f"{self.event.time_str}  {self.event.title}")


class CalendarList(Vertical):
    """Widget displaying today's calendar meetings."""

    DEFAULT_CSS = """
    CalendarList {
        width: 1fr;
        height: 1fr;
    }

    CalendarList > #calendar-header {
        background: $primary-background;
        color: $warning;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    CalendarList > #calendar-list-view {
        height: 1fr;
    }

    CalendarList > #calendar-status {
        padding: 1 2;
        color: $text-muted;
    }

    CalendarList ListItem {
        padding: 0 1;
    }

    CalendarList ListItem:hover {
        background: $boost;
    }

    CalendarList ListItem.--highlight {
        background: $accent;
    }
    """

    class MeetingSelected(Message):
        """Message emitted when a meeting is highlighted."""

        def __init__(self, event: CalendarEvent) -> None:
            super().__init__()
            self.event = event

    class MeetingAssociated(Message):
        """Message emitted when a meeting is associated with a file."""

        def __init__(self, event_uid: str, file_path: Path) -> None:
            super().__init__()
            self.event_uid = event_uid
            self.file_path = file_path

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._events: list[CalendarEvent] = []

    def compose(self) -> ComposeResult:
        yield Static("CALENDAR", id="calendar-header")
        yield ListView(id="calendar-list-view")
        yield Static("", id="calendar-status")

    @property
    def list_view(self) -> ListView:
        return self.query_one("#calendar-list-view", ListView)

    @property
    def status_label(self) -> Static:
        return self.query_one("#calendar-status", Static)

    def update_events(self, events: list[CalendarEvent]) -> None:
        """Update the meeting list with new events."""
        self._events = events
        list_view = self.list_view

        list_view.clear()

        if not events:
            self.status_label.update("No meetings today")
            return

        self.status_label.update("")
        for event in events:
            list_view.append(MeetingItem(event))

        if events:
            list_view.index = 0

    def show_error(self, message: str) -> None:
        """Show an error message in the status area."""
        self.list_view.clear()
        self._events = []
        self.status_label.update(message)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle meeting highlight (cursor moved)."""
        if event.item is not None and isinstance(event.item, MeetingItem):
            self.post_message(self.MeetingSelected(event.item.event))

    def get_selected_event(self) -> CalendarEvent | None:
        """Get the currently highlighted meeting event."""
        list_view = self.list_view
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, MeetingItem):
                return item.event
        return None
