"""Tests for the file watcher's debounce and shutdown behaviour.

The watcher runs off the Textual event loop -- watchdog's observer thread feeds a
`threading.Timer` that does the rescan -- so shutdown ordering matters. A timer
left armed past `stop()` rescans into a database that is already gone.
"""

from __future__ import annotations

import threading
import time

import pytest

from librarian.config import CalendarConfig, Config, TagConfig, ToolsConfig
from librarian.watcher import FileWatcher, MarkdownEventHandler


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "notes"
    root.mkdir()
    return Config(
        scan_directory=root,
        editor="vim",
        tags=TagConfig(),
        export_directory=tmp_path / "exports",
        data_directory=tmp_path / "data",
        calendar=CalendarConfig(),
        tools=ToolsConfig(),
    )


class FakeEvent:
    """Stands in for a watchdog filesystem event."""

    is_directory = False

    def __init__(self, path):
        self.src_path = str(path)


class TestCancel:
    def test_cancel_drops_a_pending_rescan(self, config, monkeypatch):
        """The bug: a file saved just before quit was rescanned after teardown."""
        rescanned: list = []
        monkeypatch.setattr(
            "librarian.watcher.rescan_file",
            lambda path, config: rescanned.append(path),
        )

        note = config.scan_directory / "note.md"
        note.write_text("# note\n\n#tag\n")

        handler = MarkdownEventHandler(config, on_change=lambda: None, debounce_seconds=0.05)
        handler.on_modified(FakeEvent(note))

        handler.cancel()
        time.sleep(0.2)

        assert rescanned == [], "a cancelled watcher must not touch the database"

    def test_cancel_is_safe_with_nothing_pending(self, config):
        handler = MarkdownEventHandler(config, on_change=lambda: None)
        handler.cancel()
        handler.cancel()

    def test_without_cancel_the_timer_would_fire(self, config, monkeypatch):
        """Proves the test above is testing something.

        Same setup, no cancel: the rescan lands. If this ever stops holding, the
        cancel test has gone hollow.
        """
        rescanned: list = []
        monkeypatch.setattr(
            "librarian.watcher.rescan_file",
            lambda path, config: rescanned.append(path),
        )

        note = config.scan_directory / "note.md"
        note.write_text("# note\n\n#tag\n")

        handler = MarkdownEventHandler(config, on_change=lambda: None, debounce_seconds=0.05)
        handler.on_modified(FakeEvent(note))
        time.sleep(0.3)

        assert rescanned == [note]


class TestStop:
    def test_stop_cancels_the_handlers_pending_work(self, config, monkeypatch):
        cancelled = threading.Event()
        monkeypatch.setattr(
            MarkdownEventHandler, "cancel", lambda self: cancelled.set()
        )

        watcher = FileWatcher(config, on_change=lambda: None)
        watcher.start()
        watcher.stop()

        assert cancelled.is_set()

    def test_stop_is_idempotent(self, config):
        watcher = FileWatcher(config, on_change=lambda: None)
        watcher.start()
        watcher.stop()
        watcher.stop()

    def test_stop_without_start_is_safe(self, config):
        FileWatcher(config, on_change=lambda: None).stop()

    def test_context_manager_stops_on_exit(self, config):
        with FileWatcher(config, on_change=lambda: None) as watcher:
            assert watcher._observer is not None
        assert watcher._observer is None
        assert watcher._handler is None
