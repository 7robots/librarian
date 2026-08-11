"""Reminders action handlers for LibrarianApp.

Two ways in, preferred in this order:

1. **Embedded panel.** With remtui installed (`uv sync --extra reminders`), its
   `RemindersPanel` is mounted in a modal over the Files and Preview panels, so
   the folder tree and Tools menu stay visible.
2. **External program.** Otherwise Librarian suspends and hands the terminal to
   the `remtui` executable, returning to the panels when it quits.

The fallback is not vestigial: remtui needs Python 3.12+, so on 3.10/3.11 the
package cannot be installed even though the binary may be on PATH.

Reminders live in Apple Reminders rather than in files, so neither path touches
the index, the file list, or the preview.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Used when no `reminders` path is configured.
DEFAULT_REMINDERS_COMMAND = "remtui"

INSTALL_HINT = "Install: https://github.com/7robots/remtui"


def resolve_reminders_command(configured: str = "") -> str | None:
    """Resolve the remtui executable, or None if it cannot be found.

    An absolute path is used as-is when it exists; otherwise the name is looked
    up on PATH.
    """
    command = configured.strip() or DEFAULT_REMINDERS_COMMAND

    path = Path(command).expanduser()
    if path.is_absolute():
        return str(path) if path.is_file() else None

    return shutil.which(command)


class RemindersActionsMixin:
    """Mixin providing the Reminders tool."""

    def action_launch_reminders(self) -> None:
        """Open reminders: embedded if remtui is importable, else external."""
        if not self.config.tools.reminders:
            # Hidden from the menu, so it should not be reachable another way.
            self.notify(
                "Reminders is off. Set reminders = true under [tools] to enable it.",
                severity="warning",
            )
            return

        if self._open_reminders_panel():
            return

        command = resolve_reminders_command(self.config.reminders)
        if command is None:
            configured = self.config.reminders.strip() or DEFAULT_REMINDERS_COMMAND
            self.notify(
                f"'{configured}' not found. {INSTALL_HINT}",
                severity="error",
                timeout=8,
            )
            return

        logger.info("Launching reminders TUI: %s", command)
        with self.suspend():
            try:
                subprocess.run([command], check=False)
            except FileNotFoundError:
                self.notify(f"'{command}' not found", severity="error")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                self.notify(f"Error running reminders: {exc}", severity="error")

    def _open_reminders_panel(self) -> bool:
        """Mount remtui's panel in a modal. False if that is not possible."""
        from ..widgets.reminders_modal import RemindersModal, is_available

        if not is_available():
            logger.debug("remtui not importable; falling back to the executable")
            return False

        try:
            from remtui.client import RemctlClient

            self.push_screen(RemindersModal(RemctlClient()))
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail
            logger.warning("Could not open the reminders panel: %s", exc)
            return False

        return True
