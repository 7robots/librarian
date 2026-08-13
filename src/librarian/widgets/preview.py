"""Markdown preview widget."""

from collections import OrderedDict
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Markdown, Static

from ..taskpaper import taskpaper_to_markdown
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

# How much of a document is rendered while the file cursor is still moving.
#
# Textual's `Markdown` mounts one widget per block, on the message loop, and that
# is the entire cost of a preview: measured against the real vault, reading and
# preprocessing are 0.0 ms while mounting is ~0.3 ms per widget. A long note is
# thousands of widgets — one 61 KB note measured 1.9 s, during which nothing
# repaints and no key is handled. Eighty lines holds the worst note in that vault
# to ~60 ms and is more than a screenful; the rest arrives once the cursor stops.
BROWSE_LINES = 80

# A note this long or shorter is completed automatically a moment after the
# cursor stops. Beyond it, the rest waits until the preview is focused: the
# vault this was measured against has 30 notes over 400 lines, and the longest
# takes 1.7 s to render in full — a freeze nobody asked for by merely pausing.
AUTO_COMPLETE_LINES = 150


def head_of(content: str, max_lines: int) -> tuple[str, bool]:
    """The first `max_lines` lines, and whether anything was left out.

    Lines rather than markdown blocks, deliberately: a block can be a
    two-hundred-row table, and capping by blocks left the worst note at 87 ms
    with a cap of ten. Cutting mid-block can produce a partial table, which
    renders as plain text for the moment before the full document replaces it.
    """
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content, False
    return "\n".join(lines[:max_lines]), True


def invalidate_file_cache(path: Path) -> None:
    """Invalidate cache for a file (call when file changes)."""
    _file_cache.invalidate(path)


def load_file_content(file_path: Path) -> tuple[str | None, str | None]:
    """Load file content for preview (can be called from worker thread).

    Handles cache lookup, file reading, and wiki link preprocessing.

    Args:
        file_path: Path to the markdown file to load

    Returns:
        Tuple of (processed_content, error_message).
        If successful, error_message is None.
        If failed, processed_content is None and error_message contains the error.
    """
    is_taskpaper = file_path.suffix.lower() == ".taskpaper"

    # Try to get from cache first (includes mtime check via stat)
    content = _file_cache.get(file_path)
    if content is not None:
        if is_taskpaper:
            processed_content = taskpaper_to_markdown(content)
        else:
            processed_content = preprocess_wiki_links(content)
        return (processed_content, None)

    # Read from disk and cache
    try:
        mtime = file_path.stat().st_mtime
        content = file_path.read_text(encoding="utf-8")
        _file_cache.put(file_path, mtime, content)
        if is_taskpaper:
            processed_content = taskpaper_to_markdown(content)
        else:
            processed_content = preprocess_wiki_links(content)
        return (processed_content, None)
    except (OSError, UnicodeDecodeError) as e:
        return (None, f"*Error reading file: {e}*")


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
        # Set while only the head of a file is on screen: the full text, waiting
        # for the cursor to settle or for this pane to be focused.
        self._unrendered: tuple[Path, str] | None = None

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
        """Display the contents of a markdown file.

        This method does file I/O synchronously. For non-blocking loads,
        use load_file_content() in a worker thread, then call show_content().
        """
        self._current_file = file_path

        header = self.query_one("#preview-header", Static)
        markdown = self.markdown_widget

        if file_path is None:
            header.update("PREVIEW")
            await markdown.update("")
            return

        header.update(f"PREVIEW - {file_path.name}")

        # Load content (blocking I/O)
        content, error = load_file_content(file_path)
        if error:
            await markdown.update(error)
        else:
            await markdown.update(content)

    async def show_content(
        self,
        file_path: Path,
        content: str | None,
        error: str | None,
        *,
        max_lines: int | None = None,
    ) -> bool:
        """Display pre-loaded content (no I/O, safe for main thread).

        Args:
            file_path: The file being displayed (for header and tracking)
            content: Pre-processed markdown content, or None if error
            error: Error message to display, or None if successful
            max_lines: Render only this many lines. The caller re-renders in
                full once the cursor settles; see `BROWSE_LINES`.

        Returns:
            True when the render was cut short, so the caller knows there is a
            fuller version worth showing.
        """
        self._current_file = file_path

        header = self.query_one("#preview-header", Static)
        markdown = self.markdown_widget

        header.update(f"PREVIEW - {file_path.name}")

        if error:
            await markdown.update(error)
            return False

        full = content or ""
        text = full
        truncated = False
        # Someone with the pane focused is reading it, not scrolling past it, so
        # there is nothing to save by truncating — and the focus *event* cannot
        # help here, having already fired before this file was chosen.
        if max_lines is not None and not self.scroll_view.has_focus:
            text, truncated = head_of(full, max_lines)

        self._unrendered = (file_path, full) if truncated else None
        if truncated:
            shown = len(text.splitlines())
            total = len(full.splitlines())
            header.update(
                f"PREVIEW - {file_path.name}  ({shown}/{total} lines — tab to read on)"
            )

        await markdown.update(text)
        return truncated

    async def render_full(self) -> None:
        """Replace a truncated preview with the whole file.

        Idempotent and self-cancelling: nothing happens if the full text is
        already on screen, or if the cursor has moved to another file since.
        """
        pending = self._unrendered
        if pending is None:
            return
        file_path, content = pending
        if file_path != self._current_file:
            self._unrendered = None
            return

        self._unrendered = None
        self.query_one("#preview-header", Static).update(
            f"PREVIEW - {file_path.name}"
        )
        await self.markdown_widget.update(content)

    def on_descendant_focus(self, event) -> None:
        """Focusing the pane means reading it, which is worth the full render.

        The alternative is a note that is silently short — and scrolling into a
        document that stops at line 80 with no explanation is worse than waiting
        for it. The header says so until this fires.
        """
        if self._unrendered is not None:
            self.run_worker(self.render_full(), name="preview-full", group="preview-full")

    async def show_markdown(self, title: str, content: str) -> None:
        """Display markdown that does not come from a file.

        Used for things the index knows nothing about, such as a calendar
        meeting. There is no current file afterwards, so wiki links in the
        content cannot be resolved relative to one.
        """
        self._current_file = None

        self.query_one("#preview-header", Static).update(f"PREVIEW - {title}")
        await self.markdown_widget.update(content)

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
            event.stop()
        # For non-wiki links, let default behavior handle (or ignore since open_links=False)
