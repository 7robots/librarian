"""Modal that hosts projection's projects panel below the tool tab strip.

The same frame `reminders_modal.py` uses, for the same reason: projection exposes
its UI as a widget (`ProjectsPanel`) rather than a Screen, so it can be mounted
inside another app.

The import is deliberately local to `is_available()` / `compose()`: projection is
an optional dependency and lives in a private repository, so Librarian must run
-- and its tests must pass -- without it installed.
"""

from __future__ import annotations

import inspect

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

# Rows the banner and the tool tab strip occupy, and the footer's single row --
# the modal is inset by these so all three stay visible. The strip stays in
# view so the user never loses where they are, but a ModalScreen blocks input
# to what it covers: switching tabs means closing the modal first.
BANNER_HEIGHT = 3
TAB_STRIP_HEIGHT = 3
FOOTER_HEIGHT = 1


def is_available() -> bool:
    """Whether projection is installed and its panel can be mounted."""
    try:
        import projection.panel  # noqa: F401
    except Exception:
        # ImportError, but also anything projection raises at import time -- a
        # missing optional dependency must never take Librarian down.
        return False
    return True


class ProjectsModal(ModalScreen[None]):
    """projection's projects panel, framed below the tab strip."""

    DEFAULT_CSS = f"""
    ProjectsModal {{
        /* Transparent, so Librarian stays visible around the panel. */
        background: transparent;
        align: right top;
    }}

    ProjectsModal > #projects-frame {{
        width: 100%;
        height: 100%;
        margin: {BANNER_HEIGHT + TAB_STRIP_HEIGHT} 0 {FOOTER_HEIGHT} 0;
        border: solid $accent;
        background: $surface;
    }}

    ProjectsModal #projects-frame:focus-within {{
        border: solid cyan;
    }}

    ProjectsModal > #projects-frame > #projects-hint {{
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $primary-background;
    }}
    """

    BINDINGS = [
        # The panel carries projection's own `q -> app.quit`, which here means
        # Librarian's quit. Without priority the panel is checked first -- it
        # holds focus -- and pressing `q` would close Librarian outright. Same
        # reason as RemindersModal; see the roadmap for why this whole scheme
        # deserves a rethink.
        #
        # Escape belongs to the panel's filter, so it is deliberately not bound.
        Binding("q", "close", "Close projects", priority=True),
    ]

    def __init__(self, client=None, **kwargs) -> None:
        """`client` is for tests only — production passes nothing.

        Which credential projection reads comes from projection's config, so
        handing it a client built here means handing it one with no credential
        reference at all. The tests pass a stub to keep the network and 1Password
        out of the suite; that is the only reason this parameter exists.
        """
        super().__init__(**kwargs)
        self._client = client

    def compose(self) -> ComposeResult:
        from projection.panel import ProjectsPanel

        with Vertical(id="projects-frame"):
            yield Static("PROJECTS", id="projects-hint")
            # No wordmark: the frame above already says what this is,
            # and three rows of sidebar are better spent on the lists. Older
            # projection builds lack the flag; the logo is cosmetic, so show it
            # rather than fail to open the panel at all.
            options = {}
            if "show_logo" in inspect.signature(ProjectsPanel).parameters:
                options["show_logo"] = False
            yield ProjectsPanel(self._client, id="projects-panel", **options)
            # The panel's keys differ from Librarian's, so the frame carries its
            # own footer rather than leaving Librarian's showing beneath.
            yield Footer()

    def action_close(self) -> None:
        self.dismiss(None)
