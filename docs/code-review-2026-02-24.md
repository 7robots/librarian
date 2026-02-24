# Librarian Code Review - 2026-02-24

## Overview

This peer review covers the Librarian codebase, a Textual-based TUI application that indexes markdown and taskpaper files by inline hashtags and provides a browsing experience for navigating files by tag. The review covers architecture, code quality, security, performance, and maintainability.

## Summary

| Category | Rating | Notes |
|----------|--------|-------|
| Architecture | Good | Clean separation of concerns; modular widget system |
| Code Quality | Good | Consistent style, clear naming, well-documented |
| Security | Good | HTML export sanitization, atomic writes, no eval/exec |
| Performance | Good | Background scanning, batched writes, LRU caching |
| Maintainability | Good | CLAUDE.md is thorough; architecture is easy to follow |
| Test Coverage | Needs Improvement | No test suite found |

## Architecture

The codebase follows a clean modular structure:

- **Core modules** (`database.py`, `scanner.py`, `config.py`) handle data and configuration
- **UI modules** (`app.py`, `widgets/`) handle presentation and interaction
- **Integration modules** (`calendar.py`, `calendar_store.py`, `watcher.py`, `export.py`) handle external systems

The widget hierarchy is well-structured with clear message-based communication between components. The `TagList` widget acts as a navigation hub with switchable content panels, which is a good pattern for a multi-mode sidebar.

### Strengths

- Message-based widget communication avoids tight coupling
- Atomic writes (`os.replace()`) for iCloud compatibility
- XDG-standard config location
- Denormalized index schema is simple and fast to query

### Areas for Improvement

- The `app.py` file handles many concerns (keybindings, file operations, calendar integration, navigation). Consider extracting action handlers into mixins or separate modules.
- The `tag_list.py` widget is doing a lot of work managing tools, tags, folders, and calendar views. Could benefit from further decomposition.

## Code Quality

| Aspect | Status | Details |
|--------|--------|---------|
| Type Hints | Present | Dataclasses and function signatures are typed |
| Docstrings | Present | Module and class-level docstrings throughout |
| Error Handling | Good | Try/except around file operations, user-facing notifications |
| Naming | Consistent | Clear, descriptive names for classes, methods, messages |
| CSS Organization | Good | Inline CSS in widgets, percentage-based responsive layout |

## Security Review

### Positives

- HTML export includes sanitization against XSS (dangerous tags and attributes removed)
- Document titles escaped with `html.escape()`
- No use of `eval()`, `exec()`, or `pickle`
- File paths validated before operations (rename, move, delete)
- Atomic file writes prevent corruption

### Recommendations

| Priority | Finding | Recommendation |
|----------|---------|----------------|
| Low | Path traversal in wiki links | Validate resolved paths stay within scan directory |
| Low | Subprocess calls for editor/icalPal | Paths are from config, but consider validation |
| Info | No CSP headers in exported HTML | Add Content-Security-Policy meta tag to exports |

## Performance

### Implemented Optimizations

- Background scanning with immediate UI from cached index
- Batched writes via `batch_writes()` context manager
- LRU cache (10 files) for preview content with mtime invalidation
- Debounced file watcher updates
- Targeted rescan on rename/move (not full directory scan)
- Incremental tag list updates preserving cursor position
- Thread-safe index writes with threading lock

### Potential Improvements

| Priority | Area | Suggestion |
|----------|------|------------|
| Medium | Large directories | Consider pagination or virtual scrolling for tag/file lists |
| Low | Calendar cache | 5-minute TTL is reasonable; consider invalidation on app focus |
| Low | Index loading | For very large indices, consider lazy loading |

## New Features Review

### Calendar Integration

The calendar integration (`calendar.py`, `calendar_store.py`, `widgets/calendar_list.py`) is well-implemented:

- Clean separation between icalPal wrapper, storage, and UI
- Sidecar JSON for event-to-file associations with atomic writes
- 5-minute TTL cache prevents excessive subprocess calls
- `AssociateModal` in `file_info.py` provides a clean UI for linking meetings to files

### Banner Widget

The `Banner` widget (`widgets/banner.py`) replaces the default Textual header with custom ASCII art:

- Per-letter colorization using Rich Text
- Fixed height (5 rows) with responsive width
- Clean implementation as a `Vertical` container

### Colorful Border Styling

The app uses distinct border colors per panel with `:focus-within` pseudo-class:

- Tag list: `$accent` (default) / `cyan` (focused)
- File list: `$warning` (default) / `yellow` (focused)
- Preview: `$success` (default) / `green` (focused)

This provides clear visual feedback for which panel is active.

## Recommendations Summary

| Priority | Recommendation |
|----------|----------------|
| High | Add a test suite (unit tests for database, scanner, config; integration tests with Textual pilot) |
| Medium | Extract action handlers from `app.py` to reduce file size and improve maintainability |
| Medium | Add pagination or virtual scrolling for large file/tag collections |
| Low | Validate wiki link targets stay within scan directory |
| Low | Add type stubs or protocols for widget message interfaces |
| Low | Consider adding logging for debugging (file watcher events, scan results) |

## Conclusion

Librarian is a well-structured TUI application with clean architecture, good security practices, and solid performance optimizations. The recent additions (calendar integration, banner widget, colorful borders, associate modal) are well-integrated and follow existing patterns. The primary gap is the absence of automated tests, which should be addressed to maintain confidence as the codebase grows.
