"""Main Textual application for Librarian."""

import subprocess
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Static
from textual.worker import Worker, get_current_worker

from .calendar import CalendarEvent, clear_cache, fetch_todays_events, find_icalpal
from .calendar_store import get_association, init_store, set_association
from .config import Config
from .database import (
    get_all_tags,
    get_files_by_tag,
    init_database,
    remove_file,
    resolve_wiki_link,
)
from .export import export_markdown
from .navigation import NavigationStack, NavigationState
from .scanner import rescan_file, scan_directory
from .watcher import FileWatcher
from .widgets import Banner, CalendarList, RenameModal, MoveModal, AssociateModal, FileList, Preview, TagList, load_file_content
from .widgets.tag_list import TagItem


class LibrarianApp(App):
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
        self._preview_timer: Timer | None = None  # For debouncing preview updates
        self._pending_preview_path: Path | None = None  # Track which file is being loaded

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
        # Load existing index immediately for fast startup
        init_database(self.config.get_index_path())
        init_store(self.config.data_directory)
        self._refresh_tags()

        # Focus the tools list initially
        tag_list = self.query_one("#tag-list", TagList)
        tag_list.tools_list_view.focus()

        # Start file watcher
        self._watcher = FileWatcher(self.config, self._on_file_change)
        self._watcher.start()

        # Run initial scan in background worker (thread=True for sync function)
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

        elif worker_name == "_fetch_calendar":
            result = event.worker.result
            if result is not None:
                tag_list = self.query_one("#tag-list", TagList)
                tag_list.calendar_list.update_events(result)

        elif worker_name == "_load_preview":
            # Preview content loaded in background thread
            file_path = self._pending_preview_path
            self._pending_preview_path = None

            if file_path is None:
                return

            # Verify this file is still the one we want to display
            file_list = self.query_one("#file-list", FileList)
            if file_path not in file_list._files:
                return

            result = event.worker.result
            if result:
                content, error = result
                # Update preview on main thread (no I/O, just widget update)
                preview = self.query_one("#preview", Preview)
                self.call_later(
                    lambda: preview.show_content(file_path, content, error)
                )

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
        """Handle file highlight (cursor moved) - update preview with debouncing."""
        # Cancel any pending preview update
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None

        # Ignore stale events for files no longer in the list
        file_list = self.query_one("#file-list", FileList)
        if event.file_path not in file_list._files:
            return

        # Capture the file path for the closure
        file_path = event.file_path

        # Debounce: wait 50ms before updating preview
        # This prevents lag when scrolling quickly through the file list
        self._preview_timer = self.set_timer(
            0.05,
            lambda: self._do_preview_update(file_path),
        )

    def _do_preview_update(self, file_path: Path) -> None:
        """Actually update the preview after debounce delay."""
        self._preview_timer = None

        # Verify the file is still in the list before starting work
        file_list = self.query_one("#file-list", FileList)
        if file_path not in file_list._files:
            return

        # Update header immediately for visual feedback
        preview = self.query_one("#preview", Preview)
        preview.query_one("#preview-header", Static).update(
            f"PREVIEW - {file_path.name}"
        )

        # Load file content in background thread to avoid blocking UI
        self.run_worker(
            lambda: load_file_content(file_path),
            name="_load_preview",
            thread=True,
            group="preview",
        )
        # Store the file path so we can check it when the worker completes
        self._pending_preview_path = file_path

    def _get_focus_widget(self, widget_id: str):
        """Get a focusable widget by ID."""
        tag_list = self.query_one("#tag-list", TagList)
        if widget_id == "tools-list-view":
            return tag_list.tools_list_view
        elif widget_id == "all-tags-list-view":
            # Focus the appropriate content panel based on active tool
            if tag_list.active_tool == "folders":
                return tag_list.directory_tree
            elif tag_list.active_tool == "calendar":
                return tag_list.calendar_list.list_view
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
            id(tag_list.tools_list_view): 0,
            id(file_list.list_view): 1,
            id(preview.scroll_view): 2,
            id(tag_list.all_tags_list_view): 3,
            id(tag_list.directory_tree): 3,  # Same position as all-tags
            id(tag_list.calendar_list.list_view): 3,  # Same position as all-tags
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
        """Open a file in the configured editor.

        For .taskpaper files, uses the taskpaper editor if configured.
        """
        if file_path.suffix == ".taskpaper" and self.config.taskpaper:
            editor = self.config.taskpaper
        else:
            editor = self.config.editor

        # Suspend the TUI and run the editor
        with self.suspend():
            try:
                subprocess.run([editor, str(file_path)], check=False)
            except FileNotFoundError:
                self.notify(f"Editor '{editor}' not found", severity="error")
            except Exception as e:
                self.notify(f"Error opening editor: {e}", severity="error")

    async def action_update(self) -> None:
        """Manually update the index."""
        self.notify("Updating...")
        self.run_worker(self._background_full_rescan, exclusive=True, thread=True)

    def _background_full_rescan(self) -> tuple[int, int, int]:
        """Run full rescan in background thread."""
        return scan_directory(self.config, full_rescan=True)

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

        # Update index with targeted changes instead of full rescan
        remove_file(old_path)
        rescan_file(new_path, self.config)

        # Refresh UI
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

        # Update index with targeted changes instead of full rescan
        remove_file(old_path)
        rescan_file(new_path, self.config)

        # Refresh UI
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

        # Use a simple confirmation via notify + delayed action pattern
        # We'll store the pending delete and require a second press
        if getattr(self, "_pending_delete", None) == file_path:
            # Second press — confirmed, delete the file
            self._pending_delete = None
            try:
                file_path.unlink()
            except OSError as e:
                self.notify(f"Error deleting file: {e}", severity="error")
                return

            self.notify(f"Deleted {file_path.name}")

            # Remove from index and refresh UI
            remove_file(file_path)
            self._refresh_tags()

            tag_list = self.query_one("#tag-list", TagList)
            selected_tag = tag_list.get_selected_tag()
            if selected_tag:
                files = get_files_by_tag(selected_tag)
                file_paths = [f[0] for f in files]
                file_list.update_files(file_paths, selected_tag)

            # Clear preview
            preview = self.query_one("#preview", Preview)
            preview.query_one("#preview-header", Static).update("PREVIEW")
        else:
            # First press — ask for confirmation
            self._pending_delete = file_path
            self.notify(
                f"Press d again to delete {file_path.name}",
                severity="warning",
                timeout=3,
            )

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

    def _select_taskpaper_tag(self) -> None:
        """Select the #taskpaper tag and show its files."""
        tag_list = self.query_one("#tag-list", TagList)
        tag_list._switch_panel("tags")
        tag_list.active_tool = "taskpaper"

        # Find and select the taskpaper tag in the all-tags list
        all_list = tag_list.all_tags_list_view
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name.lower() == "taskpaper":
                all_list.index = i
                # Post the tag selected message to trigger file list update
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

    def on_tag_list_calendar_refresh_requested(
        self, event: TagList.CalendarRefreshRequested
    ) -> None:
        """Handle calendar panel activation — fetch events in background."""
        self._fetch_calendar_events()

    def _fetch_calendar_events(self) -> None:
        """Fetch calendar events in a background worker."""
        if not self.config.calendar.enabled:
            tag_list = self.query_one("#tag-list", TagList)
            tag_list.calendar_list.show_error("Calendar disabled in config")
            return

        icalpal_bin = find_icalpal(self.config.calendar.icalpal_path)
        if not icalpal_bin:
            tag_list = self.query_one("#tag-list", TagList)
            tag_list.calendar_list.show_error(
                "icalPal not found.\nInstall: brew tap ajrosen/tap && brew install icalPal"
            )
            return

        self.run_worker(
            self._background_fetch_events,
            name="_fetch_calendar",
            thread=True,
            group="calendar",
        )

    def _background_fetch_events(self) -> list[CalendarEvent]:
        """Fetch calendar events in background thread."""
        return fetch_todays_events(
            icalpal_path=self.config.calendar.icalpal_path,
            calendar_name=self.config.calendar.calendar_name,
        )

    async def on_calendar_list_meeting_selected(
        self, event: CalendarList.MeetingSelected
    ) -> None:
        """Handle meeting highlight — show associated note in preview."""
        associated_file = get_association(event.event.uid)
        if associated_file:
            # Show associated file in file list and preview
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files([associated_file], navigation_target=event.event.title)
            preview = self.query_one("#preview", Preview)
            await preview.show_file(associated_file)
        else:
            # Show meeting info as preview
            preview = self.query_one("#preview", Preview)
            info = self._format_meeting_info(event.event)
            preview.show_content(None, info, None)
            preview.query_one("#preview-header", Static).update(
                f"PREVIEW - {event.event.title}"
            )
            # Update file list header
            file_list = self.query_one("#file-list", FileList)
            file_list.update_files([], navigation_target=event.event.title)

    def _format_meeting_info(self, event: CalendarEvent) -> str:
        """Format a CalendarEvent as markdown for preview."""
        lines = [f"# {event.title}", ""]
        lines.append(f"**Time:** {event.time_range_str}")
        if event.calendar_name:
            lines.append(f"**Calendar:** {event.calendar_name}")
        if event.location:
            lines.append(f"**Location:** {event.location}")
        if event.attendees:
            lines.append(f"**Attendees:** {', '.join(event.attendees)}")
        if event.notes:
            lines.extend(["", "---", "", event.notes])
        lines.extend(["", "", "*Press `a` to associate a note, or `n` to create one.*"])
        return "\n".join(lines)

    def action_associate_meeting(self) -> None:
        """Associate the selected meeting with a file from #meetings tag."""
        tag_list = self.query_one("#tag-list", TagList)
        if tag_list.active_tool != "calendar":
            return

        event = tag_list.calendar_list.get_selected_event()
        if not event:
            self.notify("No meeting selected", severity="warning")
            return

        files = get_files_by_tag("meetings")
        file_paths = [f[0] for f in files]

        if not file_paths:
            self.notify("No files with #meetings tag. Press 'n' to create one.", severity="warning")
            return

        self._associating_event_uid = event.uid
        self._associating_event_title = event.title
        self.push_screen(
            AssociateModal(event.title, file_paths),
            self._on_associate_dismissed,
        )

    async def _on_associate_dismissed(self, result) -> None:
        """Handle associate modal dismissal."""
        if result is None:
            return

        file_path = result
        event_uid = self._associating_event_uid
        event_title = self._associating_event_title

        set_association(event_uid, file_path)
        self.notify(f"Associated '{event_title}' with {file_path.name}")

        # Show the associated file in preview
        file_list = self.query_one("#file-list", FileList)
        file_list.update_files([file_path], navigation_target=event_title)
        preview = self.query_one("#preview", Preview)
        await preview.show_file(file_path)

    async def on_tag_list_file_selected(self, event: TagList.FileSelected) -> None:
        """Handle file selection from directory browser."""
        file_path = event.file_path

        # Clear navigation history
        self._nav_stack.clear()

        # Update file list to show single file
        file_list = self.query_one("#file-list", FileList)
        file_list.update_files([file_path], navigation_target=file_path.name)

        # Update preview
        preview = self.query_one("#preview", Preview)
        await preview.show_file(file_path)

        # Focus the file list
        file_list.list_view.focus()

    def action_help(self) -> None:
        """Show help information."""
        self.notify(
            "s=Search, n=New, e=Edit, d=Delete, x=Export, r=Rename, m=Move, t=TaskPaper, a=Associate, u=Update, q=Quit",
            timeout=5,
        )

    def action_search(self) -> None:
        """Enter search mode."""
        file_list = self.query_one("#file-list", FileList)
        if not file_list.is_search_mode():
            file_list.enter_search_mode()

    def on_file_list_search_mode_exited(
        self, event: FileList.SearchModeExited
    ) -> None:
        """Handle search mode exit - restore focus to tools list."""
        tag_list = self.query_one("#tag-list", TagList)
        tag_list.tools_list_view.focus()

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
        """Go back in navigation history or exit search mode."""
        # First check if we're in search mode
        file_list = self.query_one("#file-list", FileList)
        if file_list.is_search_mode():
            file_list.exit_search_mode()
            return

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
