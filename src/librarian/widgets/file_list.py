"""File list widget for displaying files with a selected tag."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.message import Message
from textual.widgets import Input, Label, ListItem, ListView, Static

# Maximum files to display before showing "Show more" item
MAX_DISPLAY_FILES = 500


class FileItem(ListItem):
    """A list item representing a file."""

    def __init__(self, file_path: Path, match_info: str | None = None) -> None:
        super().__init__()
        self.file_path = file_path
        self.match_info = match_info

    def compose(self) -> ComposeResult:
        if self.match_info:
            yield Label(f"{self.file_path.name}  [{self.match_info}]")
        else:
            yield Label(self.file_path.name)


class ShowMoreFilesItem(ListItem):
    """A list item that triggers loading the full file collection."""

    DEFAULT_CSS = """
    ShowMoreFilesItem {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, total_count: int, displayed_count: int) -> None:
        super().__init__()
        self.total_count = total_count
        self.remaining = total_count - displayed_count

    def compose(self) -> ComposeResult:
        yield Label(f"... show {self.remaining} more ({self.total_count} total)")


class FileList(Vertical):
    """Widget displaying a list of files."""

    DEFAULT_CSS = """
    FileList {
        width: 1fr;
        height: 1fr;
    }

    FileList > #file-header {
        background: $primary-background;
        color: $accent;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    FileList > #search-input {
        height: 1;
        border: none;
        padding: 0 1;
        display: none;
    }

    FileList > #search-input.visible {
        display: block;
    }

    FileList > #file-list-view {
        height: 1fr;
    }

    FileList ListItem {
        padding: 0 1;
    }

    FileList ListItem:hover {
        background: $boost;
    }

    FileList ListItem.--highlight {
        background: $accent;
    }
    """

    class FileSelected(Message):
        """Message emitted when a file is selected."""

        def __init__(self, file_path: Path) -> None:
            super().__init__()
            self.file_path = file_path

    class FileHighlighted(Message):
        """Message emitted when a file is highlighted (cursor moved)."""

        def __init__(self, file_path: Path) -> None:
            super().__init__()
            self.file_path = file_path

    class SearchModeExited(Message):
        """Message emitted when search mode is exited."""

        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._files: list[Path] = []
        self._all_files: list[Path] = []  # Full list before truncation
        self._current_tag: str | None = None
        self._navigation_target: str | None = None
        self._search_mode: bool = False
        self._match_info: dict[Path, str] = {}
        self._files_show_all: bool = False

    def compose(self) -> ComposeResult:
        yield Static("FILES", id="file-header")
        yield Input(placeholder="Search files and tags...", id="search-input")
        yield ListView(id="file-list-view")

    @property
    def list_view(self) -> ListView:
        return self.query_one("#file-list-view", ListView)

    def update_files(
        self,
        files: list[Path],
        tag: str | None = None,
        navigation_target: str | None = None,
    ) -> None:
        """Update the list of files.

        Args:
            files: List of file paths to display
            tag: Current tag filter (used for header display)
            navigation_target: Wiki link target being navigated to (navigation mode)
        """
        self._all_files = files
        self._current_tag = tag
        self._navigation_target = navigation_target
        self._match_info = {}
        self._search_mode = False
        self._files_show_all = False
        list_view = self.list_view
        list_view.clear()

        # Hide search input if visible
        search_input = self.search_input
        search_input.remove_class("visible")
        search_input.value = ""

        # Update header
        header = self.query_one("#file-header", Static)
        if navigation_target:
            header.update(f"FILES (-> {navigation_target})")
        elif tag:
            header.update(f"FILES (#{tag})")
        else:
            header.update("FILES")

        # Apply display cap for large collections
        if len(files) > MAX_DISPLAY_FILES:
            display_files = files[:MAX_DISPLAY_FILES]
        else:
            display_files = files

        self._files = display_files

        for file_path in display_files:
            list_view.append(FileItem(file_path))

        # Add "show more" item if truncated
        if len(files) > len(display_files):
            list_view.append(ShowMoreFilesItem(len(files), len(display_files)))

        # Highlight first item if available and emit event
        if display_files:
            list_view.index = 0
            self.post_message(self.FileHighlighted(display_files[0]))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle file highlight (cursor moved)."""
        if event.item is not None and isinstance(event.item, FileItem):
            self.post_message(self.FileHighlighted(event.item.file_path))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection (click or Enter on already-highlighted item)."""
        if event.item is not None and isinstance(event.item, ShowMoreFilesItem):
            self._show_all_files()
            return
        if event.item is not None and isinstance(event.item, FileItem):
            self.post_message(self.FileHighlighted(event.item.file_path))
            self.post_message(self.FileSelected(event.item.file_path))

    def _show_all_files(self) -> None:
        """Expand the file list to show all files."""
        self._files_show_all = True
        self._files = self._all_files
        list_view = self.list_view
        list_view.clear()
        for file_path in self._all_files:
            list_view.append(FileItem(file_path))
        if self._all_files:
            list_view.index = 0

    def get_selected_file(self) -> Path | None:
        """Get the currently highlighted file path."""
        list_view = self.list_view
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, FileItem):
                return item.file_path
        return None

    def get_navigation_info(self) -> tuple[str | None, list[Path], int]:
        """Get current navigation info for state saving.

        Returns:
            Tuple of (current_tag, files, selected_index)
        """
        list_view = self.list_view
        index = list_view.index if list_view.index is not None else 0
        return (self._current_tag, self._files.copy(), index)

    def is_navigation_mode(self) -> bool:
        """Check if currently in wiki link navigation mode."""
        return self._navigation_target is not None

    def get_header_text(self) -> str:
        """Get the current header text for state saving."""
        # Reconstruct from stored state rather than reading from widget
        if self._navigation_target:
            return f"FILES (-> {self._navigation_target})"
        elif self._current_tag:
            return f"FILES (#{self._current_tag})"
        else:
            return "FILES"

    def restore_state(
        self,
        files: list[Path],
        tag: str | None,
        selected_index: int,
        header_text: str,
    ) -> None:
        """Restore file list to a previous state.

        Args:
            files: List of files to display
            tag: Tag filter (or None)
            selected_index: Index to highlight
            header_text: Header text to restore
        """
        self._files = files
        self._current_tag = tag
        self._navigation_target = None
        self._match_info = {}
        list_view = self.list_view
        list_view.clear()

        # Restore header
        header = self.query_one("#file-header", Static)
        header.update(header_text)

        for file_path in files:
            list_view.append(FileItem(file_path))

        # Restore selection
        if files and 0 <= selected_index < len(files):
            list_view.index = selected_index
            self.post_message(self.FileHighlighted(files[selected_index]))

    @property
    def search_input(self) -> Input:
        return self.query_one("#search-input", Input)

    def is_search_mode(self) -> bool:
        """Check if currently in search mode."""
        return self._search_mode

    def enter_search_mode(self) -> None:
        """Enter search mode - show input and focus it."""
        self._search_mode = True
        search_input = self.search_input
        search_input.add_class("visible")
        search_input.value = ""
        search_input.focus()

        # Update header
        header = self.query_one("#file-header", Static)
        header.update("SEARCH")

        # Clear list while waiting for input
        self._files = []
        self._match_info = {}
        self.list_view.clear()

    def exit_search_mode(self) -> None:
        """Exit search mode - hide input."""
        self._search_mode = False
        search_input = self.search_input
        search_input.remove_class("visible")
        search_input.value = ""

        # Clear search results
        self._files = []
        self._match_info = {}
        self.list_view.clear()

        # Reset header
        header = self.query_one("#file-header", Static)
        header.update("FILES")

        # Notify app that search mode exited
        self.post_message(self.SearchModeExited())

    def update_search_results(
        self, results: list[tuple[Path, float, list[str]]]
    ) -> None:
        """Update the list with search results.

        Args:
            results: List of (path, mtime, matching_tags) tuples
        """
        self._files = [r[0] for r in results]
        self._match_info = {}
        self._current_tag = None
        self._navigation_target = None

        list_view = self.list_view
        list_view.clear()

        # Update header with result count
        header = self.query_one("#file-header", Static)
        header.update(f"SEARCH ({len(results)} results)")

        for path, mtime, matching_tags in results:
            # Create match info string showing which tags matched
            if matching_tags:
                match_info = ", ".join(f"#{t}" for t in matching_tags[:3])
                if len(matching_tags) > 3:
                    match_info += f" +{len(matching_tags) - 3}"
            else:
                match_info = None
            self._match_info[path] = match_info
            list_view.append(FileItem(path, match_info))

        # Highlight first item if available and emit event
        if self._files:
            list_view.index = 0
            self.post_message(self.FileHighlighted(self._files[0]))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if self._search_mode and event.input.id == "search-input":
            # Import here to avoid circular import
            from ..database import search_files

            query = event.value
            if query.strip():
                results = search_files(query)
                self.update_search_results(results)
            else:
                # Clear results when query is empty
                self._files = []
                self._match_info = {}
                self.list_view.clear()
                header = self.query_one("#file-header", Static)
                header.update("SEARCH")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search input - move focus to results."""
        if self._search_mode and event.input.id == "search-input":
            if self._files:
                self.list_view.focus()

    def on_key(self, event: Key) -> None:
        """Handle key events - Escape exits search mode."""
        if self._search_mode and event.key == "escape":
            self.exit_search_mode()
            event.stop()
