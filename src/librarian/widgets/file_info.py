"""File info modal for viewing path, renaming, and moving files."""

import shutil
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, OptionList
from textual.widgets.option_list import Option


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
    if partial_path.endswith("/") or partial_path.endswith("\\"):
        if expanded.is_dir():
            try:
                dirs = sorted([
                    p for p in expanded.iterdir()
                    if p.is_dir() and not p.name.startswith(".")
                ])
                return dirs[:20]  # Limit results
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
        return matches[:20]  # Limit results
    except PermissionError:
        return []


class FileInfoModal(ModalScreen):
    """Modal screen for file information and operations."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    FileInfoModal {
        align: center middle;
    }

    #file-info-container {
        width: 70;
        height: auto;
        max-height: 30;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #file-info-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .info-label {
        margin-top: 1;
        color: $text-muted;
    }

    .info-value {
        margin-bottom: 1;
    }

    #path-display {
        color: $text;
        padding: 0 1;
        background: $surface-darken-1;
        height: auto;
        max-height: 3;
    }

    .input-row {
        height: 3;
        margin-top: 1;
    }

    .input-row Input {
        width: 1fr;
    }

    #move-section {
        height: auto;
    }

    #completion-list {
        height: auto;
        max-height: 8;
        display: none;
        background: $surface-darken-1;
        border: solid $primary-darken-1;
        margin-top: 0;
    }

    #completion-list.visible {
        display: block;
    }

    #completion-hint {
        color: $text-muted;
        text-style: italic;
        height: 1;
        margin-top: 0;
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

    #rename-btn {
        background: $primary;
    }

    #move-btn {
        background: $warning;
    }

    #cancel-btn {
        background: $surface-lighten-1;
    }
    """

    class FileRenamed(Message):
        """Message emitted when a file is renamed."""

        def __init__(self, old_path: Path, new_path: Path) -> None:
            super().__init__()
            self.old_path = old_path
            self.new_path = new_path

    class FileMoved(Message):
        """Message emitted when a file is moved."""

        def __init__(self, old_path: Path, new_path: Path) -> None:
            super().__init__()
            self.old_path = old_path
            self.new_path = new_path

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path
        self._completion_visible = False

    def compose(self) -> ComposeResult:
        with Vertical(id="file-info-container"):
            yield Static("FILE INFO", id="file-info-title")

            yield Label("Path:", classes="info-label")
            yield Static(str(self.file_path), id="path-display", classes="info-value")

            yield Label("Rename (new filename):", classes="info-label")
            with Horizontal(classes="input-row"):
                yield Input(
                    value=self.file_path.name,
                    id="rename-input",
                    placeholder="Enter new filename",
                )

            with Vertical(id="move-section"):
                yield Label("Move to (directory path, Tab to complete):", classes="info-label")
                with Horizontal(classes="input-row"):
                    yield Input(
                        value=str(self.file_path.parent),
                        id="move-input",
                        placeholder="Enter destination directory",
                    )
                yield Static("Tab: complete, ↑↓: select, Enter: confirm", id="completion-hint")
                yield OptionList(id="completion-list")

            with Horizontal(id="button-row"):
                yield Button("Rename", id="rename-btn", variant="primary")
                yield Button("Move", id="move-btn", variant="warning")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus the rename input on mount."""
        self.query_one("#rename-input", Input).focus()

    def action_cancel(self) -> None:
        """Cancel and close the modal."""
        if self._completion_visible:
            self._hide_completions()
        else:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "rename-btn":
            self._do_rename()
        elif event.button.id == "move-btn":
            self._do_move()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in inputs."""
        if event.input.id == "rename-input":
            self._do_rename()
        elif event.input.id == "move-input":
            if self._completion_visible:
                self._select_current_completion()
            else:
                self._do_move()

    def on_key(self, event) -> None:
        """Handle key events for tab completion."""
        move_input = self.query_one("#move-input", Input)
        completion_list = self.query_one("#completion-list", OptionList)

        # Only handle keys when move input is focused or completion list is focused
        if self.focused not in (move_input, completion_list):
            return

        if event.key == "tab":
            event.stop()
            event.prevent_default()
            if self._completion_visible:
                # Tab cycles through completions or selects single match
                if completion_list.option_count == 1:
                    self._select_current_completion()
                else:
                    # Move to next completion
                    if completion_list.highlighted is not None:
                        next_idx = (completion_list.highlighted + 1) % completion_list.option_count
                        completion_list.highlighted = next_idx
                    completion_list.focus()
            else:
                self._show_completions()

        elif event.key == "down" and self._completion_visible:
            event.stop()
            event.prevent_default()
            completion_list.focus()
            if completion_list.highlighted is None and completion_list.option_count > 0:
                completion_list.highlighted = 0

        elif event.key == "up" and self._completion_visible:
            event.stop()
            event.prevent_default()
            completion_list.focus()

        elif event.key == "escape" and self._completion_visible:
            event.stop()
            event.prevent_default()
            self._hide_completions()
            move_input.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle completion selection."""
        if event.option_list.id == "completion-list":
            self._apply_completion(str(event.option.prompt))

    def _show_completions(self) -> None:
        """Show directory completions for current input."""
        move_input = self.query_one("#move-input", Input)
        completion_list = self.query_one("#completion-list", OptionList)

        current_value = move_input.value
        completions = get_directory_completions(current_value)

        completion_list.clear_options()

        if not completions:
            # No completions found
            self.app.notify("No matching directories", severity="warning")
            return

        if len(completions) == 1:
            # Single match - auto-complete
            self._apply_completion(str(completions[0]))
            return

        # Multiple matches - show list
        for path in completions:
            completion_list.add_option(Option(str(path)))

        completion_list.add_class("visible")
        completion_list.highlighted = 0
        self._completion_visible = True

    def _hide_completions(self) -> None:
        """Hide the completion list."""
        completion_list = self.query_one("#completion-list", OptionList)
        completion_list.remove_class("visible")
        completion_list.clear_options()
        self._completion_visible = False

    def _select_current_completion(self) -> None:
        """Select the currently highlighted completion."""
        completion_list = self.query_one("#completion-list", OptionList)
        if completion_list.highlighted is not None:
            option = completion_list.get_option_at_index(completion_list.highlighted)
            self._apply_completion(str(option.prompt))

    def _apply_completion(self, path: str) -> None:
        """Apply a completion to the move input."""
        move_input = self.query_one("#move-input", Input)
        # Add trailing slash to encourage further completion
        if not path.endswith("/"):
            path = path + "/"
        move_input.value = path
        move_input.cursor_position = len(path)
        self._hide_completions()
        move_input.focus()

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
            self.app.notify(f"File already exists at destination", severity="error")
            return

        try:
            shutil.move(str(self.file_path), str(new_path))
            self.post_message(self.FileMoved(self.file_path, new_path))
            self.dismiss(("moved", self.file_path, new_path))
        except OSError as e:
            self.app.notify(f"Move failed: {e}", severity="error")
