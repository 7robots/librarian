"""Modal that shows today's meetings below the tool tab strip.

Calendar used to share the sidebar with Folders and Tags. Now that those two are
permanent, it moved here — the same frame the Reminders panel uses, so every tool
that shows its own data behaves the same way.

Unlike Reminders, the calendar is not self-contained: highlighting a meeting
shows either its associated note or the meeting's own details. So the frame
carries a `Preview` of its own rather than writing into the one behind it, which
the modal covers. The frame is full-width, covering the sidebar and both right
panels; the banner and the tab strip stay visible above it.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

from .calendar_list import CalendarList
from .preview import Preview

# Rows the banner and the tool tab strip occupy, and the footer's single row --
# the modal is inset by these so all three stay visible. The strip stays in
# view so the user never loses where they are, but a ModalScreen blocks input
# to what it covers: switching tabs means closing the modal first.
BANNER_HEIGHT = 3
TAB_STRIP_HEIGHT = 3
FOOTER_HEIGHT = 1


class CalendarModal(ModalScreen[None]):
    """Today's meetings, with a preview, framed below the tab strip."""

    DEFAULT_CSS = f"""
    CalendarModal {{
        /* Transparent, so Librarian stays visible around the frame. */
        background: transparent;
        align: right top;
    }}

    CalendarModal > #calendar-frame {{
        width: 100%;
        height: 100%;
        margin: {BANNER_HEIGHT + TAB_STRIP_HEIGHT} 0 {FOOTER_HEIGHT} 0;
        border: solid $accent;
        background: $surface;
    }}

    CalendarModal #calendar-frame:focus-within {{
        border: solid cyan;
    }}

    CalendarModal > #calendar-frame > #calendar-hint {{
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $primary-background;
    }}

    CalendarModal #calendar-list {{
        height: 40%;
    }}

    CalendarModal #calendar-preview {{
        height: 1fr;
        border-top: solid $accent;
    }}
    """

    BINDINGS = [
        # `priority=True` is defensive here rather than required: nothing this
        # modal contains claims `q`, and a modal screen is checked before the
        # app, so the plain binding would already win. It matters in
        # RemindersModal, whose embedded panel binds `q -> app.quit` and would
        # otherwise take Librarian down when closed. Keeping the two the same
        # means embedding another widget in this frame cannot reintroduce that.
        Binding("q,escape", "close", "Close calendar", priority=True),
        # A modal screen stops Librarian's app-level bindings entirely -- with
        # this modal open, `s` and `d` are simply unbound -- so the keys this
        # view needs are forwarded explicitly.
        Binding("a", "app.associate_meeting", "Associate note"),
        Binding("n", "app.new_file", "New meeting note"),
        Binding("e", "app.edit", "Edit note"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="calendar-frame"):
            yield Static("CALENDAR", id="calendar-hint")
            yield CalendarList(id="calendar-list")
            yield Preview(id="calendar-preview")
            yield Footer()

    @property
    def calendar_list(self) -> CalendarList:
        return self.query_one("#calendar-list", CalendarList)

    @property
    def preview(self) -> Preview:
        return self.query_one("#calendar-preview", Preview)

    def action_close(self) -> None:
        self.dismiss(None)
