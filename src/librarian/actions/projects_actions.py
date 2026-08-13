"""Projects action handlers for LibrarianApp.

Two ways in, preferred in this order:

1. **Embedded panel.** With projection importable, its `ProjectsPanel` is
   mounted in a modal over the Files and Preview panels, so the folder tree and
   Tools menu stay visible.
2. **External program.** Otherwise Librarian suspends and hands the terminal to
   the `projection` executable, returning to the panels when it quits.

The fallback carries more weight here than it does for Reminders: projection
lives in a **private** repository, so it cannot be declared as an optional
dependency of a public project. Anyone with access installs it by hand; everyone
else gets the handoff, or nothing.

Projects live in Smartsheet rather than in files, so neither path touches the
index, the file list, or the preview.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Used when no `projects` path is configured.
DEFAULT_PROJECTS_COMMAND = "projection"

INSTALL_HINT = "Install: https://github.com/7robots/projection"


def resolve_projects_command(configured: str = "") -> str | None:
    """Resolve the projection executable, or None if it cannot be found.

    An absolute path is used as-is when it exists; otherwise the name is looked
    up on PATH.
    """
    command = configured.strip() or DEFAULT_PROJECTS_COMMAND

    path = Path(command).expanduser()
    if path.is_absolute():
        return str(path) if path.is_file() else None

    return shutil.which(command)


class ProjectsActionsMixin:
    """Mixin providing the Projects tool."""

    def action_launch_projects(self) -> None:
        """Open projects: embedded if projection is importable, else external."""
        if not self.config.tools.projects:
            # Hidden from the menu, so it should not be reachable another way.
            self.notify(
                "Projects is off. Set projects = true under [tools] to enable it.",
                severity="warning",
            )
            return

        if self._open_projects_panel():
            return

        command = resolve_projects_command(self.config.projects)
        if command is None:
            configured = self.config.projects.strip() or DEFAULT_PROJECTS_COMMAND
            self.notify(
                f"'{configured}' not found. {INSTALL_HINT}",
                severity="error",
                timeout=8,
            )
            return

        logger.info("Launching projects TUI: %s", command)
        with self.suspend():
            try:
                subprocess.run([command], check=False)
            except FileNotFoundError:
                self.notify(f"'{command}' not found", severity="error")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                self.notify(f"Error running projects: {exc}", severity="error")

    def _open_projects_panel(self) -> bool:
        """Mount projection's panel in a modal. False if that is not possible."""
        from ..widgets.projects_modal import ProjectsModal, is_available

        if not is_available():
            logger.debug("projection not importable; falling back to the executable")
            return False

        try:
            # Deliberately **no client**. Librarian used to construct projection's
            # `SmartsheetClient()` here, which looked harmless and broke the embed:
            # which credential to read comes from projection's own config
            # (`token_ref`), a bare client carries none, and a client the panel is
            # handed is used as-is — so the panel could not find a token that the
            # standalone app found fine. The panel builds its own, and closes it.
            self.push_screen(ProjectsModal())
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail
            logger.warning("Could not open the projects panel: %s", exc)
            return False

        return True
