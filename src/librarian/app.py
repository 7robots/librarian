"""Main Textual application for Librarian."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Static
from textual.worker import Worker

from .actions import CalendarActionsMixin, FileActionsMixin, NavigationActionsMixin
from .calendar import clear_cache as clear_calendar_cache
from .calendar_store import init_store
from .config import Config
from .database import (
    get_all_tags,
    get_files_by_tag,
    init_database,
)
from .navigation import NavigationStack
from .scanner import scan_directory
from .watcher import FileWatcher
from .widgets import Banner, CalendarList, FileList, Preview, TagList, load_file_content
from .widgets.tag_list import TagItem


class LibrarianApp(
    FileActionsMixin,
    CalendarActionsMixin,
    NavigationActionsMixin,
    App,
):
    """Librarian - Markdown Tag Browser TUI."""

    TITLE = "Librarian"
    SUB_TITLE = "Markdown Tag Browser"

    CSS = """
    #main-container {
        width: 100%;
        height: 1fr;
    }

    #tag-list {
        width: 25%;
        height: 100%;
        border: solid $accent;
    }

    #tag-list:focus-within {
        border: solid cyan;
    }

    #right-panel {
        width: 75%;
        height: 100%;
    }

    #file-list {
        height: 33%;
        border: solid $warning;
    }

    #file-list:focus-within {
        border: solid yellow;
    }

    #preview {
        height: 67%;
        border: solid $success;
    }

    #preview:focus-within {
        border: solid green;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_file", "New"),
        Binding("e", "edit", "Edit"),
        Binding("u", "update", "Update"),
        Binding("s", "search", "Search"),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("r", "rename_file", "Rename"),
        Binding("d", "delete_file", "Delete"),
        Binding("m", "move_file", "Move"),
        Binding("t", "launch_taskpaper", "TaskPaper", show=False),
        Binding("a", "associate_meeting", "Associate", show=False),
        Binding("x", "export", "Export"),
        Binding("?", "help", "Help"),
        Binding("escape", "go_back", "Back", show=False),
    ]

    # Custom focus order: tools -> files -> preview -> all tags (clockwise)
    FOCUS_ORDER = [
        "tools-list-view",
        "file-list-view",
        "preview",
        "all-tags-list-view",
    ]

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._watcher: FileWatcher | None = None
        self._nav_stack = NavigationStack()
        self._preview_timer: Timer | None = None
        self._pending_preview_path: Path | None = None

    def compose(self) -> ComposeResult:
        yield Banner()
        with Horizontal(id="main-container"):
            yield TagList(
                scan_directory=self.config.scan_directory,
                id="tag-list",
                classes="panel",
            )
            with Vertical(id="right-panel"):
                yield FileList(id="file-list", classes="panel")
                yield Preview(id="preview", classes="panel")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize the app after mounting."""
        init_database(self.config.get_index_path())
        init_store(self.config.data_directory)
        self._refresh_tags()

        tag_list = self.query_one("#tag-list", TagList)
        tag_list.tools_list_view.focus()

        self._watcher = FileWatcher(self.config, self._on_file_change)
        self._watcher.start()

        self.notify("Scanning files...")
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

        elif worker_name == "_fetch_calendar":
            result = event.worker.result
            if result is not None:
                tag_list = self.query_one("#tag-list", TagList)
                tag_list.calendar_list.update_events(result)

        elif worker_name == "_load_preview":
            file_path = self._pending_preview_path
            self._pending_preview_path = None

            if file_path is None:
                return

            file_list = self.query_one("#file-list", FileList)
            if file_path not in file_list._files:
                return

            result = event.worker.result
            if result:
                content, error = result
                preview = self.query_one("#preview", Preview)
                self.call_later(
                    lambda: preview.show_content(file_path, content, error)
                )

    def on_app_focus(self) -> None:
        """Handle app regaining focus — invalidate calendar cache."""
        clear_calendar_cache()
        tag_list = self.query_one("#tag-list", TagList)
        if tag_list.active_tool == "calendar":
            self._fetch_calendar_events()

    async def on_unmount(self) -> None:
        """Clean up when app closes."""
        if self._watcher:
            self._watcher.stop()

    def _refresh_tags(self) -> None:
        """Refresh the tag list from the database."""
        tags = get_all_tags()
        tag_list = self.query_one("#tag-list", TagList)
        tag_list.update_tags(tags)

    def _on_file_change(self) -> None:
        """Handle file system changes (called from watcher thread)."""
        self.call_from_thread(self._handle_file_change)

    def _handle_file_change(self) -> None:
        """Handle file changes on the main thread."""
        self._refresh_tags()

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
        self._nav_stack.clear()

        files = get_files_by_tag(event.tag_name)
        file_paths = [f[0] for f in files]
        file_list = self.query_one("#file-list", FileList)
        file_list.update_files(file_paths, event.tag_name)

        if not file_paths:
            preview = self.query_one("#preview", Preview)
            await preview.show_file(None)
        else:
            file_list.list_view.focus()

    async def on_file_list_file_highlighted(
        self, event: FileList.FileHighlighted
    ) -> None:
        """Handle file highlight (cursor moved) - update preview with debouncing."""
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None

        file_list = self.query_one("#file-list", FileList)
        if event.file_path not in file_list._files:
            return

        file_path = event.file_path

        self._preview_timer = self.set_timer(
            0.05,
            lambda: self._do_preview_update(file_path),
        )

    def _do_preview_update(self, file_path: Path) -> None:
        """Actually update the preview after debounce delay."""
        self._preview_timer = None

        file_list = self.query_one("#file-list", FileList)
        if file_path not in file_list._files:
            return

        preview = self.query_one("#preview", Preview)
        preview.query_one("#preview-header", Static).update(
            f"PREVIEW - {file_path.name}"
        )

        self.run_worker(
            lambda: load_file_content(file_path),
            name="_load_preview",
            thread=True,
            group="preview",
        )
        self._pending_preview_path = file_path

    def _select_taskpaper_tag(self) -> None:
        """Select the #taskpaper tag and show its files."""
        tag_list = self.query_one("#tag-list", TagList)
        tag_list._switch_panel("tags")
        tag_list.active_tool = "taskpaper"

        all_list = tag_list.all_tags_list_view
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name.lower() == "taskpaper":
                all_list.index = i
                tag_list.post_message(TagList.TagSelected("taskpaper"))
                return

        self.notify("No #taskpaper tag found in index", severity="warning")

    def action_launch_taskpaper(self) -> None:
        """Select the #taskpaper tag via the `t` keybinding."""
        self._select_taskpaper_tag()

    def on_tag_list_tool_launched(self, event: TagList.ToolLaunched) -> None:
        """Handle tool launches from the Tools menu."""
        if event.tool_name == "taskpaper":
            self._select_taskpaper_tag()
        elif event.tool_name == "agents":
            self.notify("Agents \u2014 coming soon")

    async def on_tag_list_file_selected(self, event: TagList.FileSelected) -> None:
        """Handle file selection from directory browser."""
        file_path = event.file_path

        self._nav_stack.clear()

        file_list = self.query_one("#file-list", FileList)
        file_list.update_files([file_path], navigation_target=file_path.name)

        preview = self.query_one("#preview", Preview)
        await preview.show_file(file_path)

        file_list.list_view.focus()

    async def action_update(self) -> None:
        """Manually update the index."""
        self.notify("Updating...")
        self.run_worker(self._background_full_rescan, exclusive=True, thread=True)


def run_app(config: Config) -> None:
    """Run the Librarian application."""
    app = LibrarianApp(config)
    app.run()
