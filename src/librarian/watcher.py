"""File system watcher for auto-refresh of markdown index."""

import logging
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .config import Config
from .database import batch_writes
from .scanner import rescan_file
from .widgets.preview import invalidate_file_cache


class MarkdownEventHandler(FileSystemEventHandler):
    """Handler for markdown file changes with debouncing."""

    def __init__(
        self,
        config: Config,
        on_change: Callable[[], None],
        debounce_seconds: float = 0.5,
    ):
        super().__init__()
        self.config = config
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._pending_paths: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def _is_supported_file(self, path: str) -> bool:
        """Check if the path is a supported file type."""
        return path.endswith(".md") or path.endswith(".taskpaper")

    def _schedule_update(self, path: str) -> None:
        """Schedule a debounced update for the given path."""
        logger.debug("File change detected: %s", path)
        with self._lock:
            self._pending_paths[path] = time.time()

            # Cancel existing timer
            if self._timer:
                self._timer.cancel()

            # Schedule new timer
            self._timer = threading.Timer(
                self.debounce_seconds,
                self._process_pending,
            )
            self._timer.daemon = True
            self._timer.start()

    def _process_pending(self) -> None:
        """Process all pending file changes."""
        with self._lock:
            paths = list(self._pending_paths.keys())
            self._pending_paths.clear()
            self._timer = None

        if not paths:
            return

        logger.info("Processing %d file change(s)", len(paths))
        # Process all changed files in a single batch to minimize disk I/O
        with batch_writes():
            for path_str in paths:
                path = Path(path_str)
                # Invalidate preview cache for this file
                invalidate_file_cache(path)
                rescan_file(path, self.config)

        # Notify of changes
        self.on_change()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_update(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_update(event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_update(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename."""
        if not event.is_directory:
            # Handle source path (old location)
            if self._is_supported_file(event.src_path):
                self._schedule_update(event.src_path)
            # Handle destination path (new location)
            if hasattr(event, "dest_path") and self._is_supported_file(event.dest_path):
                self._schedule_update(event.dest_path)


class FileWatcher:
    """Watches a directory for markdown file changes."""

    def __init__(
        self,
        config: Config,
        on_change: Callable[[], None],
    ):
        self.config = config
        self.on_change = on_change
        self._observer: Observer | None = None
        self._handler: MarkdownEventHandler | None = None

    def start(self) -> None:
        """Start watching the configured directory."""
        if self._observer is not None:
            return  # Already running

        self._handler = MarkdownEventHandler(
            self.config,
            self.on_change,
        )

        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.config.scan_directory),
            recursive=True,
        )
        self._observer.daemon = True
        self._observer.start()
        logger.info("File watcher started: %s", self.config.scan_directory)

    def stop(self) -> None:
        """Stop watching."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=1.0)
            self._observer = None
            self._handler = None

    def __enter__(self) -> "FileWatcher":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()
