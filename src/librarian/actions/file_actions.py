"""File operation action handlers for LibrarianApp."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from ..calendar_store import set_association
from ..database import get_files_by_tag, remove_file
from ..export import export_markdown
from ..scanner import rescan_file, scan_directory
from ..widgets import FileList, MoveModal, Preview, RenameModal, TagList

from textual.widgets import Static


class FileActionsMixin:
    """Mixin providing file operation actions (new, edit, rename, move, delete, export)."""

    async def action_edit(self) -> None:
        """Edit the currently previewed file."""
        preview = self.query_one("#preview", Preview)
        file_path = preview.get_current_file()
        if file_path:
            await self._edit_file(file_path)
        else:
            self.notify("No file selected", severity="warning")

    async def action_new_file(self) -> None:
        """Create a new file. Uses .taskpaper when TaskPaper tool is active, .md otherwise."""
        tag_list = self.query_one("#tag-list", TagList)
        file_list = self.query_one("#file-list", FileList)
        tag, _, _ = file_list.get_navigation_info()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        if tag_list.active_tool == "taskpaper":
            filename = f"new-note-{timestamp}.taskpaper"
            file_path = self.config.scan_directory / filename
            content = "Inbox:\n\t- \n\n#taskpaper\n"
        elif tag_list.active_tool == "calendar":
            # Create meeting note from selected event
            event = tag_list.calendar_list.get_selected_event()
            if event:
                safe_title = "".join(
                    c if c.isalnum() or c in " -_" else "" for c in event.title
                ).strip().replace(" ", "-")
                date_str = datetime.now().strftime("%Y-%m-%d")
                filename = f"{date_str}-{safe_title}.md"
                file_path = self.config.scan_directory / filename

                lines = [f"# {event.title}", ""]
                lines.append(f"**Date:** {date_str}")
                lines.append(f"**Time:** {event.time_range_str}")
                if event.location:
                    lines.append(f"**Location:** {event.location}")
                if event.attendees:
                    lines.extend(["", "## Attendees", ""])
                    for attendee in event.attendees:
                        lines.append(f"- {attendee}")
                lines.extend(["", "## Notes", "", "", "", "#meetings"])
                content = "\n".join(lines)

                file_path.write_text(content, encoding="utf-8")
                await self._edit_file(file_path)

                # Auto-associate the new note with the event
                set_association(event.uid, file_path)

                self.run_worker(self._background_full_rescan, exclusive=True, thread=True)
                return
            else:
                filename = f"meeting-{timestamp}.md"
                file_path = self.config.scan_directory / filename
                content = "# Meeting\n\n## Notes\n\n\n\n#meetings\n"
        else:
            filename = f"new-note-{timestamp}.md"
            file_path = self.config.scan_directory / filename
            lines = ["# Title", ""]
            if tag:
                lines.append(f"#{tag}")
                lines.append("")
            content = "\n".join(lines)

        file_path.write_text(content, encoding="utf-8")
        await self._edit_file(file_path)

        # Trigger a rescan to pick up the new file
        self.run_worker(self._background_full_rescan, exclusive=True, thread=True)

    async def _edit_file(self, file_path: Path) -> None:
        """Open a file in the configured editor."""
        if file_path.suffix == ".taskpaper" and self.config.taskpaper:
            editor = self.config.taskpaper
        else:
            editor = self.config.editor

        with self.suspend():
            try:
                subprocess.run([editor, str(file_path)], check=False)
            except FileNotFoundError:
                self.notify(f"Editor '{editor}' not found", severity="error")
            except Exception as e:
                self.notify(f"Error opening editor: {e}", severity="error")

    def action_rename_file(self) -> None:
        """Show rename modal for the currently selected file."""
        file_list = self.query_one("#file-list", FileList)
        file_path = file_list.get_selected_file()
        if file_path:
            self.push_screen(RenameModal(file_path), self._on_rename_dismissed)
        else:
            self.notify("No file selected", severity="warning")

    def _on_rename_dismissed(self, result) -> None:
        """Handle rename modal dismissal."""
        if result is None:
            return

        action, old_path, new_path = result

        if action == "renamed":
            self.notify(f"Renamed to {new_path.name}")

        remove_file(old_path)
        rescan_file(new_path, self.config)

        self._refresh_tags()
        tag_list = self.query_one("#tag-list", TagList)
        selected_tag = tag_list.get_selected_tag()
        if selected_tag:
            files = get_files_by_tag(selected_tag)
            file_paths = [f[0] for f in files]
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files(file_paths, selected_tag)

    def action_move_file(self) -> None:
        """Show move modal for the currently selected file."""
        file_list = self.query_one("#file-list", FileList)
        file_path = file_list.get_selected_file()
        if file_path:
            self.push_screen(MoveModal(file_path), self._on_move_dismissed)
        else:
            self.notify("No file selected", severity="warning")

    def _on_move_dismissed(self, result) -> None:
        """Handle move modal dismissal."""
        if result is None:
            return

        action, old_path, new_path = result

        if action == "moved":
            self.notify(f"Moved to {new_path.parent}")

        remove_file(old_path)
        rescan_file(new_path, self.config)

        self._refresh_tags()
        tag_list = self.query_one("#tag-list", TagList)
        selected_tag = tag_list.get_selected_tag()
        if selected_tag:
            files = get_files_by_tag(selected_tag)
            file_paths = [f[0] for f in files]
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files(file_paths, selected_tag)

    def action_delete_file(self) -> None:
        """Delete the currently selected file after confirmation."""
        file_list = self.query_one("#file-list", FileList)
        file_path = file_list.get_selected_file()
        if not file_path:
            self.notify("No file selected", severity="warning")
            return

        if getattr(self, "_pending_delete", None) == file_path:
            self._pending_delete = None
            try:
                file_path.unlink()
            except OSError as e:
                self.notify(f"Error deleting file: {e}", severity="error")
                return

            self.notify(f"Deleted {file_path.name}")

            remove_file(file_path)
            self._refresh_tags()

            tag_list = self.query_one("#tag-list", TagList)
            selected_tag = tag_list.get_selected_tag()
            if selected_tag:
                files = get_files_by_tag(selected_tag)
                file_paths = [f[0] for f in files]
                file_list.update_files(file_paths, selected_tag)

            preview = self.query_one("#preview", Preview)
            preview.query_one("#preview-header", Static).update("PREVIEW")
        else:
            self._pending_delete = file_path
            self.notify(
                f"Press d again to delete {file_path.name}",
                severity="warning",
                timeout=3,
            )

    def action_export(self) -> None:
        """Export the currently previewed file to HTML."""
        preview = self.query_one("#preview", Preview)
        file_path = preview.get_current_file()

        if not file_path:
            self.notify("No file to export", severity="warning")
            return

        self.notify(f"Exporting {file_path.name}...")
        self.run_worker(
            lambda: export_markdown(file_path, self.config.export_directory),
            name="_export_file",
            thread=True,
        )

    def _background_full_rescan(self) -> tuple[int, int, int]:
        """Run full rescan in background thread."""
        return scan_directory(self.config, full_rescan=True)
