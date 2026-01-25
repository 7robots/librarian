"""Markdown preview widget."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Markdown, Static


class Preview(Vertical):
    """Widget displaying a markdown file preview."""

    DEFAULT_CSS = """
    Preview {
        width: 1fr;
        height: 1fr;
    }

    Preview > #preview-header {
        background: $primary-background;
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    Preview > VerticalScroll {
        height: 1fr;
    }

    Preview Markdown {
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_file: Path | None = None

    def compose(self) -> ComposeResult:
        yield Static("PREVIEW", id="preview-header")
        with VerticalScroll():
            yield Markdown(id="preview-content")

    @property
    def markdown_widget(self) -> Markdown:
        return self.query_one("#preview-content", Markdown)

    async def show_file(self, file_path: Path | None) -> None:
        """Display the contents of a markdown file."""
        self._current_file = file_path

        header = self.query_one("#preview-header", Static)
        markdown = self.markdown_widget

        if file_path is None:
            header.update("PREVIEW")
            await markdown.update("")
            return

        header.update(f"PREVIEW - {file_path.name}")

        try:
            content = file_path.read_text(encoding="utf-8")
            await markdown.update(content)
        except (OSError, UnicodeDecodeError) as e:
            await markdown.update(f"*Error reading file: {e}*")

    def get_current_file(self) -> Path | None:
        """Get the currently displayed file path."""
        return self._current_file
