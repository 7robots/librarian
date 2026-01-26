"""Markdown preview widget."""

from collections import OrderedDict
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Markdown, Static

from ..wikilink import extract_wiki_target, is_wiki_link, preprocess_wiki_links


class FileCache:
    """LRU cache for file contents with mtime-based invalidation."""

    def __init__(self, max_size: int = 10) -> None:
        self._cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._max_size = max_size

    def get(self, path: Path) -> str | None:
        """Get cached content if valid, or None if not cached/stale."""
        key = str(path)
        if key not in self._cache:
            return None

        cached_mtime, content = self._cache[key]

        # Check if file has been modified
        try:
            current_mtime = path.stat().st_mtime
            if current_mtime != cached_mtime:
                # File changed, invalidate cache
                del self._cache[key]
                return None
        except OSError:
            # File no longer accessible
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return content

    def put(self, path: Path, mtime: float, content: str) -> None:
        """Cache file content."""
        key = str(path)

        # Remove oldest entry if at capacity
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._cache.popitem(last=False)

        self._cache[key] = (mtime, content)
        self._cache.move_to_end(key)

    def invalidate(self, path: Path) -> None:
        """Invalidate cache entry for a specific file."""
        key = str(path)
        if key in self._cache:
            del self._cache[key]


# Shared cache instance
_file_cache = FileCache(max_size=10)


def invalidate_file_cache(path: Path) -> None:
    """Invalidate cache for a file (call when file changes)."""
    _file_cache.invalidate(path)


class Preview(Vertical):
    """Widget displaying a markdown file preview."""

    class WikiLinkClicked(Message):
        """Message emitted when a wiki link is clicked."""

        def __init__(self, target: str, current_file: Path | None) -> None:
            super().__init__()
            self.target = target
            self.current_file = current_file

    DEFAULT_CSS = """
    Preview {
        width: 1fr;
        height: 1fr;
    }

    Preview > #preview-header {
        background: $primary-background;
        color: $success;
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

    Preview VerticalScroll:focus {
        border: solid $accent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_file: Path | None = None

    def compose(self) -> ComposeResult:
        yield Static("PREVIEW", id="preview-header")
        with VerticalScroll(id="preview-scroll"):
            yield Markdown(id="preview-content", open_links=False)

    @property
    def scroll_view(self) -> VerticalScroll:
        return self.query_one("#preview-scroll", VerticalScroll)

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

        # Try to get from cache first
        content = _file_cache.get(file_path)
        if content is not None:
            # Preprocess wiki links before rendering
            processed_content = preprocess_wiki_links(content)
            await markdown.update(processed_content)
            return

        # Read from disk and cache
        try:
            mtime = file_path.stat().st_mtime
            content = file_path.read_text(encoding="utf-8")
            _file_cache.put(file_path, mtime, content)
            # Preprocess wiki links before rendering
            processed_content = preprocess_wiki_links(content)
            await markdown.update(processed_content)
        except (OSError, UnicodeDecodeError) as e:
            await markdown.update(f"*Error reading file: {e}*")

    def get_current_file(self) -> Path | None:
        """Get the currently displayed file path."""
        return self._current_file

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Handle link clicks in the markdown preview."""
        href = event.href

        if is_wiki_link(href):
            # Extract target and emit WikiLinkClicked message
            target = extract_wiki_target(href)
            self.post_message(self.WikiLinkClicked(target, self._current_file))
            event.prevent_default()
        # For non-wiki links, let default behavior handle (or ignore since open_links=False)
