"""Reminders action handlers for LibrarianApp.

Reminders are handled by launching [remtui](https://github.com/7robots/remtui)
as an external program, the same way the editor is launched: Librarian suspends,
remtui takes the terminal, and quitting it returns to Librarian's panels.

Reminders live in Apple Reminders rather than in files, so nothing here touches
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
        """Suspend Librarian and hand the terminal to remtui."""
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
