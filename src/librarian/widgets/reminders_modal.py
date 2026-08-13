"""Modal that hosts remtui's reminders panel over Librarian's right-hand panels.

remtui exposes its UI as a widget (`RemindersPanel`), so this is a frame around
it: a modal screen sized and positioned to cover the Files and Preview panels,
leaving the banner, the folder tree, and the Tools menu visible behind.

The import is deliberately local to `is_available()` / `build()`: remtui is an
optional dependency, and Librarian must run without it.
"""

from __future__ import annotations

import inspect
import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

# Rows the banner occupies, and the footer's single row -- the modal is inset by
# these so both stay visible.
BANNER_HEIGHT = 3
FOOTER_HEIGHT = 1

# Matches the sidebar width in LibrarianApp.CSS, so the modal starts exactly
# where the right-hand panels do.
SIDEBAR_WIDTH_PERCENT = 25

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Whether remtui is installed *and usable*, so its panel can be mounted.

    Importable is not enough: remtui shells out to `remctl`, and a panel mounted
    without it can only fail on its first call — by which point the
    suspend-and-launch fallback is no longer an option. `remctl_found()` answers
    for the binary remtui itself would run, honouring `$REMTUI_REMCTL`, so a
    missing one falls back to the executable and remtui's own install message.

    Guarded with `getattr`: the helper is newer than this embed, and an older
    remtui should keep working rather than lose the panel entirely.
    """
    try:
        import remtui.panel  # noqa: F401
        from remtui import client as remtui_client
    except Exception:
        # ImportError, but also anything remtui raises at import time -- a
        # missing optional dependency must never take Librarian down.
        return False

    found = getattr(remtui_client, "remctl_found", None)
    if found is not None and not found():
        logger.debug("remctl is not installed; falling back to the executable")
        return False
    return True


class RemindersModal(ModalScreen[None]):
    """remtui's reminders panel, framed over Librarian's right-hand panels."""

    DEFAULT_CSS = f"""
    RemindersModal {{
        /* Transparent, so Librarian stays visible around the panel. */
        background: transparent;
        align: right top;
    }}

    RemindersModal > #reminders-frame {{
        width: {100 - SIDEBAR_WIDTH_PERCENT}%;
        height: 100%;
        margin: {BANNER_HEIGHT} 0 {FOOTER_HEIGHT} 0;
        border: solid $accent;
        background: $surface;
    }}

    RemindersModal #reminders-frame:focus-within {{
        border: solid cyan;
    }}

    RemindersModal > #reminders-frame > #reminders-hint {{
        height: 1;
        padding: 0 1;
        color: $text-muted;
        background: $primary-background;
    }}
    """

    BINDINGS = [
        # The panel carries remtui's own `q -> app.quit`, which here means
        # Librarian's quit: without priority, pressing `q` closes Librarian
        # outright (verified -- the app stops and the panel stays up). priority
        # makes this screen binding win wherever focus sits inside the panel.
        # Escape belongs to the panel's filter, so it is deliberately not bound.
        Binding("q", "close", "Close reminders", priority=True),
    ]

    def __init__(self, client=None, **kwargs) -> None:
        """`client` is for tests only — production passes nothing.

        remtui resolves the `remctl` binary and its key profile from its own
        settings, so a client built here would carry neither. The tests pass a
        stub to keep the real Reminders store out of the suite; that is the only
        reason this parameter exists.
        """
        super().__init__(**kwargs)
        self._client = client

    def compose(self) -> ComposeResult:
        from remtui.panel import RemindersPanel

        with Vertical(id="reminders-frame"):
            yield Static("REMINDERS", id="reminders-hint")
            # No wordmark: the frame above already says what this is,
            # and three rows of sidebar are better spent on the lists. Older
            # remtui builds lack the flag; the logo is cosmetic, so show it
            # rather than fail to open the panel at all.
            options = {}
            if "show_logo" in inspect.signature(RemindersPanel).parameters:
                options["show_logo"] = False
            yield RemindersPanel(self._client, id="reminders-panel", **options)
            # The panel's keys differ from Librarian's, so the frame carries its
            # own footer rather than leaving Librarian's showing beneath.
            yield Footer()

    def action_close(self) -> None:
        self.dismiss(None)
