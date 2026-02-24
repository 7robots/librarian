"""Modals for file rename, move, and association operations."""

import os
import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static


class RenameModal(ModalScreen):
    """Modal screen for renaming a file."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Save", show=False),
    ]

    CSS = """
    RenameModal {
        align: center middle;
    }

    #rename-container {
        width: 60;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #rename-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .info-label {
        margin-top: 1;
        color: $text-muted;
    }

    #current-name {
        color: $text;
        padding: 0 1;
        background: $surface-darken-1;
    }

    .input-row {
        height: 3;
        margin-top: 1;
    }

    .input-row Input {
        width: 1fr;
    }

    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    class FileRenamed(Message):
        """Message emitted when a file is renamed."""

        def __init__(self, old_path: Path, new_path: Path) -> None:
            super().__init__()
            self.old_path = old_path
            self.new_path = new_path

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        with Vertical(id="rename-container"):
            yield Static("RENAME FILE", id="rename-title")

            yield Label("Current name:", classes="info-label")
            yield Static(self.file_path.name, id="current-name")

            yield Label("New name:", classes="info-label")
            with Horizontal(classes="input-row"):
                yield Input(
                    value=self.file_path.name,
                    id="rename-input",
                    placeholder="Enter new filename",
                )

            with Horizontal(id="button-row"):
                yield Button("Save (^S)", id="save-btn", variant="primary")
                yield Button("Cancel (^C)", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus and select the input on mount."""
        input_widget = self.query_one("#rename-input", Input)
        input_widget.focus()
        # Select the filename without extension for easy editing
        name = self.file_path.name
        if "." in name and not name.startswith("."):
            stem_end = name.rfind(".")
            input_widget.selection = (0, stem_end)

    def action_cancel(self) -> None:
        """Cancel and close the modal."""
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._do_rename()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._do_rename()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "ctrl+c":
            event.stop()
            event.prevent_default()
            self.action_cancel()

    def action_save(self) -> None:
        """Save action triggered by Ctrl+S."""
        self._do_rename()

    def _do_rename(self) -> None:
        """Rename the file."""
        rename_input = self.query_one("#rename-input", Input)
        new_name = rename_input.value.strip()

        if not new_name:
            self.app.notify("Filename cannot be empty", severity="error")
            return

        if new_name == self.file_path.name:
            self.dismiss(None)
            return

        new_path = self.file_path.parent / new_name

        if new_path.exists():
            self.app.notify(f"File already exists: {new_name}", severity="error")
            return

        try:
            self.file_path.rename(new_path)
            self.post_message(self.FileRenamed(self.file_path, new_path))
            self.dismiss(("renamed", self.file_path, new_path))
        except OSError as e:
            self.app.notify(f"Rename failed: {e}", severity="error")


def get_directory_completions(partial_path: str) -> list[Path]:
    """Get directory completions for a partial path.

    Args:
        partial_path: The partial path to complete

    Returns:
        List of matching directory paths
    """
    if not partial_path:
        return []

    # Expand ~ to home directory
    expanded = Path(partial_path).expanduser()

    # If the path ends with /, list contents of that directory
    if partial_path.endswith("/") or partial_path.endswith(os.sep):
        if expanded.is_dir():
            try:
                dirs = sorted([
                    p for p in expanded.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                ])
                return dirs
            except PermissionError:
                return []
        return []

    # Otherwise, find matching entries in the parent directory
    parent = expanded.parent
    prefix = expanded.name.lower()

    if not parent.exists():
        return []

    try:
        matches = sorted([
            p for p in parent.iterdir()
            if p.is_dir()
            and p.name.lower().startswith(prefix)
            and not p.name.startswith(".")
        ])
        return matches
    except PermissionError:
        return []


def get_common_prefix(paths: list[Path]) -> str:
    """Get the longest common prefix of a list of paths.

    Args:
        paths: List of paths to find common prefix for

    Returns:
        The longest common prefix string
    """
    if not paths:
        return ""
    if len(paths) == 1:
        return str(paths[0])

    # Get the path strings
    strings = [str(p) for p in paths]

    # Find the shortest string
    min_len = min(len(s) for s in strings)

    # Find the longest common prefix
    prefix = ""
    for i in range(min_len):
        char = strings[0][i]
        if all(s[i] == char for s in strings):
            prefix += char
        else:
            break

    return prefix


class MoveModal(ModalScreen):
    """Modal screen for moving a file to a different directory."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
        Binding("ctrl+s", "save", "Save", show=False),
    ]

    CSS = """
    MoveModal {
        align: center middle;
    }

    #move-container {
        width: 70;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #move-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .info-label {
        margin-top: 1;
        color: $text-muted;
    }

    #current-path {
        color: $text;
        padding: 0 1;
        background: $surface-darken-1;
        height: auto;
        max-height: 2;
    }

    .input-row {
        height: 3;
        margin-top: 1;
    }

    .input-row Input {
        width: 1fr;
    }

    #completion-display {
        height: auto;
        max-height: 10;
        margin-top: 1;
        padding: 0 1;
        background: $surface-darken-1;
        display: none;
    }

    #completion-display.visible {
        display: block;
    }

    #tab-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }

    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    class FileMoved(Message):
        """Message emitted when a file is moved."""

        def __init__(self, old_path: Path, new_path: Path) -> None:
            super().__init__()
            self.old_path = old_path
            self.new_path = new_path

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path
        self._last_completions: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="move-container"):
            yield Static("MOVE FILE", id="move-title")

            yield Label("File:", classes="info-label")
            yield Static(self.file_path.name, id="current-path")

            yield Label("Move to directory:", classes="info-label")
            with Horizontal(classes="input-row"):
                yield Input(
                    value=str(self.file_path.parent),
                    id="move-input",
                    placeholder="Enter destination directory",
                )

            yield Static("", id="completion-display")
            yield Static("Press Tab to complete path", id="tab-hint")

            with Horizontal(id="button-row"):
                yield Button("Save (^S)", id="save-btn", variant="primary")
                yield Button("Cancel (^C)", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        input_widget = self.query_one("#move-input", Input)
        input_widget.focus()
        # Position cursor at the end
        input_widget.cursor_position = len(input_widget.value)

    def action_cancel(self) -> None:
        """Cancel and close the modal."""
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._do_move()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._do_move()

    def action_save(self) -> None:
        """Save action triggered by 's' key."""
        self._do_move()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self._do_tab_completion()
        elif event.key == "ctrl+c":
            event.stop()
            event.prevent_default()
            self.action_cancel()

    def _do_tab_completion(self) -> None:
        """Perform Unix-style tab completion."""
        move_input = self.query_one("#move-input", Input)
        completion_display = self.query_one("#completion-display", Static)

        current_value = move_input.value
        completions = get_directory_completions(current_value)

        if not completions:
            # No matches - hide display and notify
            completion_display.remove_class("visible")
            completion_display.update("")
            self._last_completions = []
            self.app.notify("No matching directories", severity="warning")
            return

        if len(completions) == 1:
            # Single match - complete it fully with trailing slash
            completed = str(completions[0]) + "/"
            move_input.value = completed
            move_input.cursor_position = len(completed)
            completion_display.remove_class("visible")
            completion_display.update("")
            self._last_completions = []
        else:
            # Multiple matches - show them and do partial completion
            # Find longest common prefix
            common = get_common_prefix(completions)

            # If we can extend the current input, do it
            if len(common) > len(current_value.rstrip("/")):
                move_input.value = common
                move_input.cursor_position = len(common)

            # Display all matches (just the directory names)
            match_names = [p.name + "/" for p in completions]

            # Format in columns if there are many
            if len(match_names) <= 10:
                display_text = "  ".join(match_names)
            else:
                # Show first 10 and indicate more
                display_text = "  ".join(match_names[:10]) + f"\n  ... and {len(match_names) - 10} more"

            completion_display.update(display_text)
            completion_display.add_class("visible")
            self._last_completions = completions

    def _do_move(self) -> None:
        """Move the file to a new directory."""
        move_input = self.query_one("#move-input", Input)
        dest_dir_str = move_input.value.strip()

        # Remove trailing slash for validation
        if dest_dir_str.endswith("/"):
            dest_dir_str = dest_dir_str.rstrip("/")

        if not dest_dir_str:
            self.app.notify("Directory cannot be empty", severity="error")
            return

        # Expand ~ to home directory
        dest_dir = Path(dest_dir_str).expanduser()

        if not dest_dir.is_absolute():
            self.app.notify("Please enter an absolute path", severity="error")
            return

        if str(dest_dir) == str(self.file_path.parent):
            self.dismiss(None)
            return

        if not dest_dir.exists():
            self.app.notify(f"Directory does not exist: {dest_dir}", severity="error")
            return

        if not dest_dir.is_dir():
            self.app.notify(f"Not a directory: {dest_dir}", severity="error")
            return

        new_path = dest_dir / self.file_path.name

        if new_path.exists():
            self.app.notify("File already exists at destination", severity="error")
            return

        try:
            shutil.move(str(self.file_path), str(new_path))
            self.post_message(self.FileMoved(self.file_path, new_path))
            self.dismiss(("moved", self.file_path, new_path))
        except OSError as e:
            self.app.notify(f"Move failed: {e}", severity="error")


class _AssociateFileItem(ListItem):
    """A list item for a file in the associate modal."""

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        yield Label(self.file_path.name)


class AssociateModal(ModalScreen):
    """Modal screen for associating a meeting with a file."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    AssociateModal {
        align: center middle;
    }

    #associate-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #associate-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #meeting-name {
        color: $text;
        padding: 0 1;
        background: $surface-darken-1;
        margin-bottom: 1;
    }

    #associate-file-list {
        height: auto;
        max-height: 15;
    }

    #associate-file-list ListItem {
        padding: 0 1;
    }

    #associate-file-list ListItem:hover {
        background: $boost;
    }

    #associate-file-list ListItem.--highlight {
        background: $accent;
    }

    #associate-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }

    #associate-button-row {
        margin-top: 1;
        height: 3;
        align: center middle;
    }

    #associate-button-row Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    def __init__(self, event_title: str, file_paths: list[Path]) -> None:
        super().__init__()
        self.event_title = event_title
        self.file_paths = file_paths

    def compose(self) -> ComposeResult:
        with Vertical(id="associate-container"):
            yield Static("ASSOCIATE MEETING", id="associate-title")
            yield Static(self.event_title, id="meeting-name")
            yield Label("Select a file:", classes="info-label")
            yield ListView(
                *[_AssociateFileItem(fp) for fp in self.file_paths],
                id="associate-file-list",
            )
            yield Static("Enter to confirm, Escape to cancel", id="associate-hint")
            with Horizontal(id="associate-button-row"):
                yield Button("Associate", id="associate-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus the file list on mount."""
        list_view = self.query_one("#associate-file-list", ListView)
        list_view.focus()
        if self.file_paths:
            list_view.index = 0

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "associate-btn":
            self._do_associate()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle Enter/click on a file item."""
        self._do_associate()

    def _do_associate(self) -> None:
        list_view = self.query_one("#associate-file-list", ListView)
        if list_view.highlighted_child is not None:
            item = list_view.highlighted_child
            if isinstance(item, _AssociateFileItem):
                self.dismiss(item.file_path)
                return
        self.app.notify("No file selected", severity="warning")


# Keep FileInfoModal as an alias for backwards compatibility during transition
FileInfoModal = RenameModal
