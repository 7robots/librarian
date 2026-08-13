"""How much of a file the preview renders, and when.

Textual's `Markdown` mounts one widget per block, on the message loop, so
rendering *is* the cost of a preview — measured against a real vault, reading and
preprocessing were 0.0 ms while one 61 KB note took 1.9 s to mount, during which
nothing repaints and no keypress is handled. Scrolling eight long notes cost 3.4
seconds of frozen UI, because every file passed rendered in full and a render
cannot be interrupted once it starts.

These tests pin the three things that fixed it: browse renders are capped, files
scrolled past are not rendered at all, and the rest arrives without being asked
for when it is cheap — or on focus, when it is not.
"""

from __future__ import annotations

import pytest

from librarian.app import PREVIEW_DEBOUNCE, PREVIEW_SETTLE
from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.widgets.preview import (
    AUTO_COMPLETE_LINES,
    BROWSE_LINES,
    Preview,
    head_of,
)

SHORT = "# Short\n\nOne paragraph.\n"
MEDIUM = "# Medium\n\n" + "\n\n".join(f"Paragraph {n}." for n in range(60))  # ~130 lines
HUGE = "# Huge\n\n" + "\n\n".join(f"Paragraph {n}." for n in range(600))  # ~1200 lines


def _lines(text: str) -> int:
    return len(text.splitlines())


# ==================== head_of ====================


def test_head_of_leaves_a_short_file_alone():
    text, truncated = head_of(SHORT, BROWSE_LINES)
    assert text == SHORT
    assert truncated is False


def test_head_of_cuts_by_lines_not_blocks():
    """A block can be a two-hundred-row table, so blocks do not bound the cost."""
    table = "| a | b |\n" * 500
    text, truncated = head_of(table, BROWSE_LINES)
    assert truncated is True
    assert _lines(text) == BROWSE_LINES


def test_the_browse_cap_is_more_than_a_screenful():
    """Small enough to stay fast, large enough that most notes never truncate."""
    assert 40 <= BROWSE_LINES <= 120
    assert AUTO_COMPLETE_LINES > BROWSE_LINES


# ==================== What lands on screen ====================


@pytest.fixture
def preview_app():
    from textual.app import App, ComposeResult

    class Host(App):
        def compose(self) -> ComposeResult:
            yield Preview(id="preview")

    return Host()


async def _show(pilot, preview, tmp_path, body, name="note.md"):
    """Preview a file the way browsing does: with the pane *not* focused."""
    path = tmp_path / name
    path.write_text(body)
    preview.app.set_focus(None)
    await pilot.pause()
    truncated = await preview.show_content(path, body, None, max_lines=BROWSE_LINES)
    await pilot.pause()
    return path, truncated


def _rendered(preview) -> str:
    return preview.markdown_widget.source


async def test_a_short_file_renders_whole(preview_app, tmp_path):
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        _, truncated = await _show(pilot, preview, tmp_path, SHORT)

        assert truncated is False
        assert _rendered(preview) == SHORT


async def test_a_long_file_renders_only_its_head(preview_app, tmp_path):
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        _, truncated = await _show(pilot, preview, tmp_path, HUGE)

        assert truncated is True
        # Within a line of the cap: a trailing blank line is not a line.
        assert BROWSE_LINES - 1 <= _lines(_rendered(preview)) <= BROWSE_LINES
        assert _lines(HUGE) > 1000, "the fixture should be long enough to matter"


async def test_the_header_says_the_preview_is_short(preview_app, tmp_path):
    """Silently showing the first eighty lines would be worse than being slow."""
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        await _show(pilot, preview, tmp_path, HUGE)

        header = str(preview.query_one("#preview-header").render())
        assert f"/{_lines(HUGE)} lines" in header
        assert "tab" in header.lower()


async def test_focusing_the_pane_renders_the_rest(preview_app, tmp_path):
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        await _show(pilot, preview, tmp_path, HUGE)

        preview.scroll_view.focus()
        for _ in range(20):
            await pilot.pause()

        assert _rendered(preview) == HUGE
        header = str(preview.query_one("#preview-header").render())
        assert "lines" not in header, "the truncation note should be gone"


async def test_completing_a_file_the_cursor_has_left_does_nothing(
    preview_app, tmp_path
):
    """The fill-in is scheduled ahead of time; the cursor may move first."""
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        await _show(pilot, preview, tmp_path, HUGE, name="first.md")
        await _show(pilot, preview, tmp_path, SHORT, name="second.md")

        await preview.render_full()
        await pilot.pause()

        assert _rendered(preview) == SHORT


async def test_render_full_is_idempotent(preview_app, tmp_path):
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        await _show(pilot, preview, tmp_path, HUGE)

        await preview.render_full()
        await preview.render_full()
        await pilot.pause()

        assert _rendered(preview) == HUGE


# ==================== The debounce, against a real app ====================


@pytest.fixture
def notes(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    for n in range(6):
        (root / f"note-{n}.md").write_text(f"# Note {n}\n\n#work\n\n" + HUGE)
    return root


@pytest.fixture
def app(notes, tmp_path, tmp_index):
    from librarian.app import LibrarianApp

    return LibrarianApp(
        Config(
            scan_directory=notes,
            editor="vim",
            tags=TagConfig(),
            export_directory=tmp_path / "exports",
            data_directory=tmp_path / "data",
            calendar=CalendarConfig(),
            tools=ToolsConfig(),
        )
    )


def test_the_debounce_outlasts_a_held_arrow_key():
    """macOS repeats at ~33 ms; anything shorter renders every file passed.

    This is the whole scrolling problem: at 50 ms, holding a key rendered every
    note it moved over, in full, uninterruptibly.
    """
    assert PREVIEW_DEBOUNCE >= 0.12
    assert PREVIEW_SETTLE > PREVIEW_DEBOUNCE


async def test_scrolling_past_files_renders_none_of_them(app, notes):
    """Six highlights in quick succession must leave at most one render behind."""
    from librarian.widgets import FileList

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        file_list = app.query_one("#file-list", FileList)
        preview = app.query_one("#preview", Preview)

        rendered: list[str] = []
        original = preview.show_content

        async def counting(*args, **kwargs):
            rendered.append(str(args[0]))
            return await original(*args, **kwargs)

        preview.show_content = counting

        paths = list(file_list._files)
        for path in paths:
            file_list.post_message(FileList.FileHighlighted(path))
            await pilot.pause()  # far quicker than the debounce

        assert rendered == [], "nothing should render while the cursor is moving"


async def test_a_focused_pane_never_truncates(preview_app, tmp_path):
    """Changing files while reading should not hand back a shortened note.

    The focus *event* cannot cover this: it fired when the pane was focused,
    which was before this file was chosen.
    """
    async with preview_app.run_test() as pilot:
        preview = preview_app.query_one("#preview", Preview)
        preview.scroll_view.focus()
        await pilot.pause()

        path = tmp_path / "read.md"
        path.write_text(HUGE)
        truncated = await preview.show_content(
            path, HUGE, None, max_lines=BROWSE_LINES
        )
        await pilot.pause()

        assert truncated is False
        assert _rendered(preview) == HUGE
