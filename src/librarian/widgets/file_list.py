"""File list widget for displaying files with a selected tag."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static


class FileItem(ListItem):
    """A list item representing a file."""

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        yield Label(self.file_path.name)


class FileList(Vertical):
    """Widget displaying a list of files."""

    DEFAULT_CSS = """
    FileList {
        width: 1fr;
        height: 1fr;
    }

    FileList > #file-header {
        background: $primary-background;
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: 1;
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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._files: list[Path] = []
        self._current_tag: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("FILES", id="file-header")
        yield ListView(id="file-list-view")

    @property
    def list_view(self) -> ListView:
        return self.query_one("#file-list-view", ListView)

    def update_files(self, files: list[Path], tag: str | None = None) -> None:
        """Update the list of files."""
        self._files = files
        self._current_tag = tag
        list_view = self.list_view
        list_view.clear()

        # Update header
        header = self.query_one("#file-header", Static)
        if tag:
            header.update(f"FILES (#{tag})")
        else:
            header.update("FILES")

        for file_path in files:
            list_view.append(FileItem(file_path))

        # Highlight first item if available and emit event
        if files:
            list_view.index = 0
            self.post_message(self.FileHighlighted(files[0]))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle file selection (Enter pressed)."""
        if isinstance(event.item, FileItem):
            self.post_message(self.FileSelected(event.item.file_path))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle file highlight (cursor moved)."""
        if event.item is not None and isinstance(event.item, FileItem):
            self.post_message(self.FileHighlighted(event.item.file_path))

    def get_selected_file(self) -> Path | None:
        """Get the currently highlighted file path."""
        list_view = self.list_view
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, FileItem):
                return item.file_path
        return None
