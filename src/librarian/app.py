"""Main Textual application for Librarian."""

import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from .config import Config
from .database import get_all_tags, get_files_by_tag
from .scanner import scan_directory
from .watcher import FileWatcher
from .widgets import FileList, Preview, TagList


class LibrarianApp(App):
    """Librarian - Markdown Tag Browser TUI."""

    TITLE = "Librarian"
    SUB_TITLE = "Markdown Tag Browser"

    CSS = """
    #main-container {
        width: 100%;
        height: 100%;
    }

    #tag-list {
        width: 25%;
        height: 100%;
        border: solid $primary;
    }

    #right-panel {
        width: 75%;
        height: 100%;
    }

    #file-list {
        height: 33%;
        border: solid $primary;
    }

    #preview {
        height: 67%;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("e", "edit", "Edit"),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "focus_next", "Next Panel"),
        Binding("shift+tab", "focus_previous", "Prev Panel"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._watcher: FileWatcher | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield TagList(id="tag-list", classes="panel")
            with Vertical(id="right-panel"):
                yield FileList(id="file-list", classes="panel")
                yield Preview(id="preview", classes="panel")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app after mounting."""
        # Initial scan
        self.notify("Scanning for markdown files...")
        added, updated, removed = scan_directory(self.config)
        self.notify(f"Index updated: {added} added, {updated} updated, {removed} removed")

        # Load tags
        self._refresh_tags()

        # Start file watcher
        self._watcher = FileWatcher(self.config, self._on_file_change)
        self._watcher.start()

        # Focus the appropriate tag list initially
        tag_list = self.query_one("#tag-list", TagList)
        if self.config.tags.whitelist:
            tag_list.favorites_list_view.focus()
        else:
            tag_list.all_tags_list_view.focus()

    async def on_unmount(self) -> None:
        """Clean up when app closes."""
        if self._watcher:
            self._watcher.stop()

    def _refresh_tags(self) -> None:
        """Refresh the tag list from the database."""
        tags = get_all_tags()
        tag_list = self.query_one("#tag-list", TagList)
        tag_list.set_favorites(self.config.tags.whitelist)
        tag_list.update_tags(tags)

    def _on_file_change(self) -> None:
        """Handle file system changes (called from watcher thread)."""
        # Schedule refresh on the main thread
        self.call_from_thread(self._handle_file_change)

    def _handle_file_change(self) -> None:
        """Handle file changes on the main thread."""
        # Refresh tags
        self._refresh_tags()

        # Refresh current file list if a tag is selected
        tag_list = self.query_one("#tag-list", TagList)
        selected_tag = tag_list.get_selected_tag()
        if selected_tag:
            files = get_files_by_tag(selected_tag)
            file_paths = [f[0] for f in files]
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files(file_paths, selected_tag)

        self.notify("Index updated")

    async def on_tag_list_tag_selected(self, event: TagList.TagSelected) -> None:
        """Handle tag selection."""
        files = get_files_by_tag(event.tag_name)
        file_paths = [f[0] for f in files]
        file_list = self.query_one("#file-list", FileList)
        file_list.update_files(file_paths, event.tag_name)

        # Clear preview if no files
        if not file_paths:
            preview = self.query_one("#preview", Preview)
            await preview.show_file(None)
        else:
            # Focus the file list
            file_list.list_view.focus()

    async def on_file_list_file_highlighted(
        self, event: FileList.FileHighlighted
    ) -> None:
        """Handle file highlight (cursor moved) - update preview."""
        preview = self.query_one("#preview", Preview)
        await preview.show_file(event.file_path)

    async def on_file_list_file_selected(self, event: FileList.FileSelected) -> None:
        """Handle file selection (Enter pressed) - open in editor."""
        await self._edit_file(event.file_path)

    async def action_edit(self) -> None:
        """Edit the currently selected file."""
        file_list = self.query_one("#file-list", FileList)
        file_path = file_list.get_selected_file()
        if file_path:
            await self._edit_file(file_path)
        else:
            self.notify("No file selected", severity="warning")

    async def _edit_file(self, file_path: Path) -> None:
        """Open a file in the configured editor."""
        editor = self.config.editor

        # Suspend the TUI and run the editor
        with self.suspend():
            try:
                subprocess.run([editor, str(file_path)], check=False)
            except FileNotFoundError:
                self.notify(f"Editor '{editor}' not found", severity="error")
            except Exception as e:
                self.notify(f"Error opening editor: {e}", severity="error")

    async def action_refresh(self) -> None:
        """Manually refresh the index."""
        self.notify("Rescanning...")
        added, updated, removed = scan_directory(self.config, full_rescan=True)
        self._refresh_tags()

        # Refresh current file list
        tag_list = self.query_one("#tag-list", TagList)
        selected_tag = tag_list.get_selected_tag()
        if selected_tag:
            files = get_files_by_tag(selected_tag)
            file_paths = [f[0] for f in files]
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files(file_paths, selected_tag)

        self.notify(f"Rescan complete: {added} added, {updated} updated, {removed} removed")

    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "q=Quit, e=Edit, r=Refresh, Tab=Next, Arrow keys=Navigate",
            timeout=5,
        )


def run_app(config: Config) -> None:
    """Run the Librarian application."""
    app = LibrarianApp(config)
    app.run()
