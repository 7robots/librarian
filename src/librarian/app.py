"""Main Textual application for Librarian."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static
from textual.worker import Worker, get_current_worker

from .config import Config
from .database import get_all_tags, get_files_by_tag, init_database, resolve_wiki_link
from .export import export_markdown
from .navigation import NavigationStack, NavigationState
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
        Binding("n", "new_file", "New"),
        Binding("e", "edit", "Edit"),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("p", "show_path", "Show Path"),
        Binding("x", "export", "Export"),
        Binding("?", "help", "Help"),
        Binding("escape", "go_back", "Back", show=False),
    ]

    # Custom focus order: favorites -> files -> preview -> all tags (clockwise)
    FOCUS_ORDER = [
        "favorites-list-view",
        "file-list-view",
        "preview",
        "all-tags-list-view",
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._watcher: FileWatcher | None = None
        self._nav_stack = NavigationStack()

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
        # Load existing index immediately for fast startup
        init_database()
        self._refresh_tags()

        # Focus the appropriate tag list initially
        tag_list = self.query_one("#tag-list", TagList)
        if self.config.tags.whitelist:
            tag_list.favorites_list_view.focus()
        else:
            tag_list.all_tags_list_view.focus()

        # Start file watcher
        self._watcher = FileWatcher(self.config, self._on_file_change)
        self._watcher.start()

        # Run initial scan in background worker (thread=True for sync function)
        self.notify("Scanning for markdown files...")
        self.run_worker(self._background_scan, exclusive=True, thread=True)

    def _background_scan(self) -> tuple[int, int, int]:
        """Run directory scan in background thread."""
        return scan_directory(self.config)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle background worker completion."""
        worker_name = event.worker.name

        if event.state.name == "ERROR":
            if worker_name == "_export_file":
                self.notify(f"Export failed: {event.worker.error}", severity="error")
            return

        if event.state.name != "SUCCESS":
            return

        if worker_name in ("_background_scan", "_background_full_rescan"):
            result = event.worker.result
            if result:
                added, updated, removed = result
                if worker_name == "_background_full_rescan":
                    self.notify(f"Rescan complete: {added} added, {updated} updated, {removed} removed")
                else:
                    self.notify(f"Index updated: {added} added, {updated} updated, {removed} removed")
                self._refresh_tags()

                # Refresh current file list if a tag is selected
                tag_list = self.query_one("#tag-list", TagList)
                selected_tag = tag_list.get_selected_tag()
                if selected_tag:
                    files = get_files_by_tag(selected_tag)
                    file_paths = [f[0] for f in files]
                    file_list = self.query_one("#file-list", FileList)
                    file_list.update_files(file_paths, selected_tag)

        elif worker_name == "_export_file":
            result = event.worker.result
            if result:
                output_path, fmt = result
                self.notify(f"Exported to {output_path.name} ({fmt.upper()})", timeout=5)

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
        # Clear navigation history when selecting a new tag
        self._nav_stack.clear()

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

    def _get_focus_widget(self, widget_id: str):
        """Get a focusable widget by ID."""
        tag_list = self.query_one("#tag-list", TagList)
        if widget_id == "favorites-list-view":
            return tag_list.favorites_list_view
        elif widget_id == "all-tags-list-view":
            return tag_list.all_tags_list_view
        elif widget_id == "file-list-view":
            return self.query_one("#file-list", FileList).list_view
        elif widget_id == "preview":
            return self.query_one("#preview", Preview).scroll_view
        return None

    def _get_current_focus_index(self) -> int:
        """Get the index of the currently focused widget in FOCUS_ORDER."""
        focused = self.focused
        if focused is None:
            return -1

        tag_list = self.query_one("#tag-list", TagList)
        file_list = self.query_one("#file-list", FileList)
        preview = self.query_one("#preview", Preview)

        focus_map = {
            id(tag_list.favorites_list_view): 0,
            id(file_list.list_view): 1,
            id(preview.scroll_view): 2,
            id(tag_list.all_tags_list_view): 3,
        }
        return focus_map.get(id(focused), -1)

    def action_focus_next(self) -> None:
        """Focus the next panel in clockwise order."""
        current = self._get_current_focus_index()
        next_index = (current + 1) % len(self.FOCUS_ORDER)
        widget = self._get_focus_widget(self.FOCUS_ORDER[next_index])
        if widget:
            widget.focus()

    def action_focus_previous(self) -> None:
        """Focus the previous panel in counter-clockwise order."""
        current = self._get_current_focus_index()
        prev_index = (current - 1) % len(self.FOCUS_ORDER)
        widget = self._get_focus_widget(self.FOCUS_ORDER[prev_index])
        if widget:
            widget.focus()

    async def action_edit(self) -> None:
        """Edit the currently previewed file."""
        # Use the preview's current file (works in both normal and navigation mode)
        preview = self.query_one("#preview", Preview)
        file_path = preview.get_current_file()
        if file_path:
            await self._edit_file(file_path)
        else:
            self.notify("No file selected", severity="warning")

    async def action_new_file(self) -> None:
        """Create a new markdown file with template."""
        # Get current tag from file list (if any)
        file_list = self.query_one("#file-list", FileList)
        tag, _, _ = file_list.get_navigation_info()

        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"new-note-{timestamp}.md"
        file_path = self.config.scan_directory / filename

        # Create template content
        lines = ["# Title", ""]
        if tag:
            lines.append(f"#{tag}")
            lines.append("")
        content = "\n".join(lines)

        # Write template to file
        file_path.write_text(content, encoding="utf-8")

        # Open in editor
        await self._edit_file(file_path)

        # Trigger a rescan to pick up the new file
        self.run_worker(self._background_full_rescan, exclusive=True, thread=True)

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
        self.run_worker(self._background_full_rescan, exclusive=True, thread=True)

    def _background_full_rescan(self) -> tuple[int, int, int]:
        """Run full rescan in background thread."""
        return scan_directory(self.config, full_rescan=True)

    def action_show_path(self) -> None:
        """Show the full path of the currently selected file."""
        file_list = self.query_one("#file-list", FileList)
        file_path = file_list.get_selected_file()
        if file_path:
            self.notify(str(file_path), timeout=10)
        else:
            self.notify("No file selected", severity="warning")

    def action_export(self) -> None:
        """Export the currently previewed file to PDF or HTML."""
        preview = self.query_one("#preview", Preview)
        file_path = preview.get_current_file()

        if not file_path:
            self.notify("No file to export", severity="warning")
            return

        # Run export in background worker
        self.notify(f"Exporting {file_path.name}...")
        self.run_worker(
            lambda: export_markdown(file_path, self.config.export_directory),
            name="_export_file",
            thread=True,
        )

    def _on_export_complete(self, output_path: Path, fmt: str) -> None:
        """Handle export completion."""
        self.notify(f"Exported to {output_path.name} ({fmt.upper()})", timeout=5)

    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "n=New, e=Edit, x=Export, p=Path, r=Refresh, Esc=Back, q=Quit",
            timeout=5,
        )

    async def on_preview_wiki_link_clicked(
        self, event: Preview.WikiLinkClicked
    ) -> None:
        """Handle wiki link clicks in the preview."""
        # Resolve the wiki link target to a file path
        resolved = resolve_wiki_link(event.target, event.current_file)

        if resolved is None:
            self.notify(f"Link target not found: {event.target}", severity="warning")
            return

        # Save current state to navigation stack
        file_list = self.query_one("#file-list", FileList)
        tag, files, index = file_list.get_navigation_info()
        header_text = file_list.get_header_text()
        state = NavigationState(
            tag=tag,
            files=files,
            selected_index=index,
            header_text=header_text,
        )
        self._nav_stack.push(state)

        # Update file list to show single navigated file
        file_list.update_files([resolved], navigation_target=resolved.name)

        # Update preview
        preview = self.query_one("#preview", Preview)
        await preview.show_file(resolved)

        # Focus the file list and activate cursor
        def activate_file_list():
            file_list.list_view.focus()
            # Force cursor activation by moving down then back up
            if len(file_list._files) > 1:
                file_list.list_view.action_cursor_down()
                file_list.list_view.action_cursor_up()

        self.set_timer(0.1, activate_file_list)

    async def action_go_back(self) -> None:
        """Go back in navigation history."""
        if self._nav_stack.is_empty():
            return

        state = self._nav_stack.pop()
        if state is None:
            return

        # Restore file list state
        file_list = self.query_one("#file-list", FileList)
        file_list.restore_state(
            files=state.files,
            tag=state.tag,
            selected_index=state.selected_index,
            header_text=state.header_text,
        )

        # Update preview with the restored selection
        if state.files and 0 <= state.selected_index < len(state.files):
            preview = self.query_one("#preview", Preview)
            await preview.show_file(state.files[state.selected_index])

        # Focus the file list and activate cursor
        def activate_file_list():
            file_list.list_view.focus()
            # Force cursor activation by moving down then back up
            if len(state.files) > 1:
                file_list.list_view.action_cursor_down()
                file_list.list_view.action_cursor_up()

        self.set_timer(0.1, activate_file_list)


def run_app(config: Config) -> None:
    """Run the Librarian application."""
    app = LibrarianApp(config)
    app.run()
