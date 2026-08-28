"""Main Textual application for Librarian."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.timer import Timer
from textual.widgets import Footer, Static
from textual.worker import Worker

from .actions import (
    CalendarActionsMixin,
    CraftActionsMixin,
    FileActionsMixin,
    NavigationActionsMixin,
    ProjectsActionsMixin,
    RemindersActionsMixin,
)
from .appearance import build_folder_appearance
from .calendar import clear_cache as clear_calendar_cache
from .calendar_store import init_store
from .config import Config
from .database import (
    get_all_tags,
    get_files_by_tag,
    init_database,
)
from .navigation import NavigationStack
from .scanner import list_folder_files, scan_directory
from .watcher import FileWatcher
from .widgets import Banner, CalendarList, FileList, Preview, TagList, load_file_content
from .widgets.preview import AUTO_COMPLETE_LINES, BROWSE_LINES
from .widgets.tag_list import ALL_TOOLS, TagItem


# How long the file cursor must be still before the preview is rendered at all.
# The old value was 0.05, shorter than a held arrow key's repeat interval, so
# every file scrolled past rendered in full — and a render cannot be interrupted
# once it starts. Scrolling eight long notes cost 3.4 s of frozen UI.
PREVIEW_DEBOUNCE = 0.15

# ...and how long after that before the remainder of a long note is filled in.
# Long enough that scrolling never triggers it, short enough to feel automatic.
PREVIEW_SETTLE = 0.35


class LibrarianApp(
    # Craft precedes File so its `action_edit` sees Craft docs first and
    # defers to the file-based edit via super().
    CraftActionsMixin,
    FileActionsMixin,
    CalendarActionsMixin,
    NavigationActionsMixin,
    ProjectsActionsMixin,
    RemindersActionsMixin,
    App,
):
    """Librarian - Terminal Notes & Tasks."""

    TITLE = "Librarian"
    SUB_TITLE = "Terminal Notes & Tasks"

    CSS = """
    #main-container {
        width: 100%;
        height: 1fr;
    }

    #tag-list {
        width: 25%;
        height: 100%;
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
        # Two meanings for `a`, disambiguated by check_action: add-occurrence
        # is enabled only while a Craft document is selected, and disabled
        # means Textual keeps looking, falling through to associate. Listed
        # first so it wins when enabled.
        Binding("a", "craft_add_occurrence", "Add occurrence", show=False),
        Binding("a", "associate_meeting", "Associate", show=False),
        Binding("x", "export", "Export"),
        Binding("?", "help", "Help"),
        Binding("escape", "go_back", "Back", show=False),
        # Vim keys, live only when [keys] vim is on -- `check_action` disables
        # every one of them otherwise, so with the switch off `ctrl+w` still
        # means delete-word-left in an Input and `h` is just a letter.
        Binding("ctrl+w", "vim_prefix", "Vim panel prefix", show=False),
        # `priority=True` puts these ahead of the focused widget, so with the
        # prefix pending `j` moves between panels and the list underneath does
        # not also move its cursor. `check_action` keeps them inert until then,
        # which is what lets the same keys mean cursor movement the rest of the
        # time.
        #
        # It is the *order-independent* half of that guarantee, not the only
        # one: Textual tries every binding registered for a key in turn, so
        # these winning also relies on nothing else claiming `j` first. Both
        # were mutated -- dropping priority alone passes, listing the in-panel
        # bindings first alone passes, doing both fails ten tests. Priority
        # stays so that reordering this list cannot quietly break the prefix.
        Binding("h", "vim_focus('left')", "Panel left", show=False, priority=True),
        Binding("j", "vim_focus('down')", "Panel down", show=False, priority=True),
        Binding("k", "vim_focus('up')", "Panel up", show=False, priority=True),
        Binding("l", "vim_focus('right')", "Panel right", show=False, priority=True),
        # The same letters again, without priority and without the prefix: these
        # are reached only after the priority pass declines and no focused widget
        # claims the key, which is exactly when h/j/k/l should mean "move inside
        # this panel". Textual tries every binding registered for a key in turn,
        # so the pair coexists on one node.
        Binding("j", "vim_cursor('down')", "Cursor down", show=False),
        Binding("k", "vim_cursor('up')", "Cursor up", show=False),
        Binding("g", "vim_edge('top')", "Top", show=False),
        Binding("G", "vim_edge('bottom')", "Bottom", show=False),
        Binding("l", "vim_expand", "Expand", show=False),
        Binding("h", "vim_collapse", "Collapse", show=False),
    ]

    # Focus order: down the left column, then down the right. Optional panels
    # (Folders, Craft, an empty Tools menu) are skipped when their lookup
    # returns None.
    FOCUS_ORDER = [
        "directory-tree",
        "craft-tree",
        "all-tags-list-view",
        "tools-list-view",
        "file-list-view",
        "preview",
    ]

    # The same panels as FOCUS_ORDER, arranged the way they sit on screen:
    # the sidebar's stacked panels, then the two on the right. Tab walks
    # the flat order; ctrl+w needs to know which are neighbours.
    PANEL_GRID = (
        ("directory-tree", "craft-tree", "all-tags-list-view", "tools-list-view"),
        ("file-list-view", "preview"),
    )

    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self._watcher: FileWatcher | None = None
        self._nav_stack = NavigationStack()
        self._preview_timer: Timer | None = None
        # Set once a capped preview is on screen, to fill in the rest if the
        # cursor stays put. Cancelled by the next highlight.
        self._preview_full_timer: Timer | None = None
        # Vim panel movement: whether ctrl+w is awaiting its direction, the
        # timer that expires it, and the panel last focused in each column --
        # h/l return to where you were, since the columns' rows do not line up.
        self._vim_pending = False
        self._vim_prefix_timer: Timer | None = None
        self._vim_column = ["directory-tree", "file-list-view"]
        # Built by _init_craft() when [tools] craft is on; None otherwise.
        self._craft = None

    def visible_tools(self) -> tuple[str, ...]:
        """Tools to show in the menu, dropping those disabled in config."""
        return tuple(
            name for name in ALL_TOOLS if self.config.tools.is_enabled(name)
        )

    def compose(self) -> ComposeResult:
        yield Banner()
        with Horizontal(id="main-container"):
            yield TagList(
                scan_directory=self.config.scan_directory,
                appearance=build_folder_appearance(self.config),
                tools=self.visible_tools(),
                show_folders=self.config.tools.is_enabled("folders"),
                show_craft=self.config.tools.is_enabled("craft"),
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
        tag_list.initialize()

        self._watcher = FileWatcher(self.config, self._on_file_change)
        self._watcher.start()

        if self.config.tools.is_enabled("craft"):
            self._init_craft()

        self.notify("Scanning files...")
        self.run_worker(self._background_scan, exclusive=True, thread=True)

    def _background_scan(self) -> tuple[int, int, int]:
        """Run directory scan in background thread."""
        return scan_directory(self.config)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle background worker completion.

        Workers can finish while the app is shutting down, after the widgets
        they report into have gone away.
        """
        try:
            self._handle_worker_state(event)
        except NoMatches:
            return

    def _handle_worker_state(self, event: Worker.StateChanged) -> None:
        """Route a finished worker's result to the widgets that display it."""
        worker_name = event.worker.name

        if event.state.name == "ERROR":
            if worker_name == "_export_file":
                self.notify(f"Export failed: {event.worker.error}", severity="error")
            elif worker_name == "_fetch_craft_folders":
                # Show why in the panel, so a broken connection is never
                # mistaken for a space with no folders.
                message = str(event.worker.error) or "Craft fetch failed"
                tree = self._craft_tree()
                if tree is not None:
                    tree.show_message(message)
                self.notify(message, severity="error", timeout=8)
            elif worker_name in ("_fetch_craft_docs", "_load_craft_preview"):
                message = str(event.worker.error) or "Craft fetch failed"
                self.notify(message, severity="error", timeout=8)
            elif worker_name == "_craft_prepend":
                # The write failed; the note is untouched. Report verbatim.
                message = str(event.worker.error) or "Craft prepend failed"
                self.notify(message, severity="error", timeout=8)
            elif worker_name == "_fetch_calendar":
                # Show why in the panel, so a broken icalPal is never mistaken
                # for a day with no meetings.
                message = str(event.worker.error) or "Calendar fetch failed"
                calendar_list = self._calendar_list()
                if calendar_list is not None:
                    calendar_list.show_error(message)
                self.notify(message, severity="error", timeout=8)
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
                self._refresh_file_panel()

        elif worker_name == "_export_file":
            result = event.worker.result
            if result:
                output_path, fmt = result
                self.notify(f"Exported to {output_path.name} ({fmt.upper()})", timeout=5)

        elif worker_name == "_fetch_calendar":
            result = event.worker.result
            if result is not None:
                calendar_list = self._calendar_list()
                if calendar_list is not None:
                    calendar_list.update_events(result)

        elif worker_name == "_fetch_craft_folders":
            result = event.worker.result
            if result is not None:
                tree = self._craft_tree()
                if tree is not None:
                    tree.update_folders(result)

        elif worker_name == "_fetch_craft_docs":
            result = event.worker.result
            if result is not None:
                folder, docs = result
                tag_list = self.query_one("#tag-list", TagList)
                # Stale results must not overwrite a source the user has since
                # moved on to.
                if tag_list.active_source == "craft":
                    file_list = self.query_one("#file-list", FileList)
                    file_list.update_craft_docs(docs, folder.name)

        elif worker_name == "_load_craft_preview":
            result = event.worker.result
            if result is not None:
                doc, markdown = result
                file_list = self.query_one("#file-list", FileList)
                selected = file_list.get_selected_craft_doc()
                if selected is None or selected.id != doc.id:
                    return
                preview = self.query_one("#preview", Preview)
                self.call_later(preview.show_markdown, doc.title, markdown)

        elif worker_name == "_craft_prepend":
            result = event.worker.result
            if result is not None:
                doc, _ = result
                self.notify(f"Added to '{doc.title}'")
                # The client invalidated the doc's cached markdown; refetch so
                # the preview shows the note with its new occurrence on top.
                self._do_craft_preview(doc)

        elif worker_name == "_load_preview":
            result = event.worker.result
            if not result:
                return
            file_path, (content, error) = result

            file_list = self.query_one("#file-list", FileList)
            if file_path not in file_list._files:
                return

            preview = self.query_one("#preview", Preview)
            self.call_later(
                lambda: self._show_preview(preview, file_path, content, error)
            )

    async def _show_preview(
        self,
        preview: Preview,
        file_path: Path,
        content: str | None,
        error: str | None,
    ) -> None:
        """Show the head of a file now, and the rest if the cursor settles.

        Rendering is the whole cost of a preview -- Textual mounts a widget per
        markdown block, on the message loop -- so a long note freezes the UI for
        as long as it takes. Showing a screenful keeps browsing responsive; the
        remainder follows shortly after the cursor stops, so nothing is
        permanently hidden and there is no mode to notice.
        """
        truncated = await preview.show_content(
            file_path, content, error, max_lines=BROWSE_LINES
        )
        if not truncated:
            return

        # Long notes are left truncated until the pane is focused; completing one
        # costs as much as rendering it did, and paying that for a pause is the
        # freeze this change exists to remove. Shorter ones cost little, so they
        # complete themselves and the truncation is never noticed.
        if len((content or "").splitlines()) > AUTO_COMPLETE_LINES:
            return

        def fill_in() -> None:
            self._preview_full_timer = None
            self.call_later(preview.render_full)

        self._preview_full_timer = self.set_timer(PREVIEW_SETTLE, fill_in)

    def on_app_focus(self) -> None:
        """Handle app regaining focus — invalidate calendar cache."""
        clear_calendar_cache()
        if self._calendar_list() is not None:
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
        """Handle file changes on the main thread.

        The watcher lives in its own thread and debounces, so a change can land
        after the panels are gone -- a file written just before quit is enough.
        Missing widgets mean the app is going away, so there is nothing to
        refresh.
        """
        try:
            self._refresh_tags()
            self._refresh_file_panel()
        except NoMatches:
            return
        self.notify("Index updated")

    def _refresh_file_panel(self) -> None:
        """Repopulate the Files panel for whichever tool is active.

        Folder listings come from the filesystem and tag listings from the
        index, so an index update must not overwrite a folder view with the
        highlighted tag's files.
        """
        tag_list = self.query_one("#tag-list", TagList)
        file_list = self.query_one("#file-list", FileList)

        if file_list.is_search_mode() or file_list.is_navigation_mode():
            return

        if tag_list.active_source == "folders":
            folder = tag_list.get_selected_folder()
            if folder is not None:
                self.call_later(self._show_folder_files, folder)
            return

        if tag_list.active_source == "craft":
            # Remote listing: the index update that got us here cannot have
            # changed it, but leaving search mode clears the panel, so relist
            # (cached, so usually free).
            self._refresh_craft_docs()
            return

        selected_tag = tag_list.get_selected_tag()
        if selected_tag:
            files = get_files_by_tag(selected_tag)
            file_list.update_files([f[0] for f in files], selected_tag)

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
        """Handle file highlight (cursor moved) - update preview with debouncing.

        Staleness is checked *before* cancelling: ListView emits highlights
        asynchronously, so an event for a listing that has since been replaced
        (e.g. by Craft docs) can arrive after the new listing armed its own
        preview timer -- cancelling first would kill that timer and show
        nothing.
        """
        file_list = self.query_one("#file-list", FileList)
        if event.file_path not in file_list._files:
            return

        self._cancel_preview_timers()
        file_path = event.file_path

        self._preview_timer = self.set_timer(
            PREVIEW_DEBOUNCE,
            lambda: self._do_preview_update(file_path),
        )

    def _cancel_preview_timers(self) -> None:
        """Drop any pending preview work: the cursor has moved on."""
        for name in ("_preview_timer", "_preview_full_timer"):
            timer = getattr(self, name)
            if timer is not None:
                timer.stop()
                setattr(self, name, None)

    def _do_preview_update(self, file_path: Path) -> None:
        """Actually update the preview after debounce delay."""
        self._preview_timer = None

        # The debounce timer can fire while the app is shutting down, after the
        # widgets have gone away.
        try:
            file_list = self.query_one("#file-list", FileList)
            preview = self.query_one("#preview", Preview)
        except NoMatches:
            return

        if file_path not in file_list._files:
            return

        preview.query_one("#preview-header", Static).update(
            f"PREVIEW - {file_path.name}"
        )

        # `exclusive` so a highlight that arrives mid-load cancels the load it
        # supersedes, and the path travels *with* the result rather than in an
        # instance attribute -- two loads in flight used to race for one slot,
        # which could apply one file's content under another file's name.
        self.run_worker(
            lambda: (file_path, load_file_content(file_path)),
            name="_load_preview",
            thread=True,
            group="preview",
            exclusive=True,
        )

    def _select_taskpaper_tag(self) -> None:
        """Select the #taskpaper tag and show its files."""
        tag_list = self.query_one("#tag-list", TagList)
        tag_list.active_source = "tags"

        all_list = tag_list.all_tags_list_view
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name.lower() == "taskpaper":
                all_list.index = i
                tag_list.post_message(TagList.TagSelected("taskpaper"))
                return

        self.notify("No #taskpaper tag found in index", severity="warning")

    def action_launch_taskpaper(self) -> None:
        """Select the #taskpaper tag via the `t` keybinding."""
        if not self.config.tools.taskpaper:
            # The tool is hidden, so the shortcut should not be a hidden way in.
            self.notify(
                "TaskPaper is off. Set taskpaper = true under [tools] to enable it.",
                severity="warning",
            )
            return
        self._select_taskpaper_tag()

    def on_tag_list_tool_launched(self, event: TagList.ToolLaunched) -> None:
        """Handle tool launches from the Tools menu."""
        if event.tool_name == "taskpaper":
            self._select_taskpaper_tag()
        elif event.tool_name == "reminders":
            self.action_launch_reminders()
        elif event.tool_name == "calendar":
            self.action_open_calendar()
        elif event.tool_name == "projects":
            self.action_launch_projects()

    async def on_tag_list_folder_highlighted(
        self, event: TagList.FolderHighlighted
    ) -> None:
        """Show the highlighted folder's files in the Files panel."""
        self._nav_stack.clear()
        await self._show_folder_files(event.folder_path)

    async def _show_folder_files(self, folder: Path) -> None:
        """List a folder's files, labelling the panel with the folder name."""
        files = list_folder_files(folder)

        # Nested folders show their path relative to the scan directory; the
        # scan directory itself has no relative path, so use its own name.
        try:
            label = str(folder.relative_to(self.config.scan_directory))
        except ValueError:
            label = folder.name
        if label == ".":
            label = folder.name

        file_list = self.query_one("#file-list", FileList)
        file_list.update_files(files, folder=label)

        if not files:
            preview = self.query_one("#preview", Preview)
            await preview.show_file(None)

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
