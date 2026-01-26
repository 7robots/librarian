# CLAUDE.md - Development Guide for Librarian

## Project Overview

Librarian is a Textual-based TUI application that indexes markdown files by inline hashtags and provides a browsing experience for navigating files by tag.

## Architecture

```
src/librarian/
├── __init__.py          # Package version
├── __main__.py          # Entry point, initializes app
├── app.py               # Main Textual App with layout and keybindings
├── config.py            # TOML config loading from ~/Documents/librarian/
├── database.py          # JSON index operations (in-memory + file persistence)
├── scanner.py           # File scanning & hashtag extraction
├── watcher.py           # File system watcher using watchdog
└── widgets/
    ├── __init__.py
    ├── tag_list.py      # Split panel: Favorites + All Tags (two ListViews)
    ├── file_list.py     # Files with selected tag (ListView)
    └── preview.py       # Markdown preview pane (VerticalScroll + Markdown)
```

## Key Design Decisions

- **Config/Data location**: `~/Documents/librarian/` (iCloud syncable)
- **Config format**: TOML at `~/Documents/librarian/config.toml`
- **Index storage**: JSON at `~/Documents/librarian/index.json` (iCloud-friendly atomic writes)
- **Tag format**: Inline hashtags matching `#[a-zA-Z][a-zA-Z0-9_-]*`
- **Auto-refresh**: watchdog monitors scan directory with debouncing
- **Favorites**: Tags in config whitelist appear in dedicated Favorites panel

## Index Schema

```json
{
  "files": {
    "/absolute/path/to/file.md": {
      "mtime": 1234567890.123,
      "tags": ["tag1", "tag2"]
    }
  }
}
```

Denormalized structure with tags inline per file. Only files containing at least one hashtag are indexed. Uses atomic writes (temp file + `os.replace()`) for iCloud compatibility.

## UI Layout

The app has four panels:
- **Left sidebar** (25% width): Split into Favorites (top) and All Tags (bottom)
- **Right top** (33% height): File list for selected tag
- **Right bottom** (67% height): Markdown preview

Layout uses percentage-based CSS for dynamic terminal resizing.

## Common Development Tasks

### Running the app
```bash
uv run librarian
```

### Testing imports
```bash
uv run python -c "from librarian.app import LibrarianApp; print('OK')"
```

### Testing with Textual pilot
```python
async with app.run_test(size=(80, 24)) as pilot:
    await pilot.press('enter')
    await pilot.pause()
```

### Checking index state
```bash
uv run python -c "
from librarian.database import init_database, get_all_tags, get_all_files
init_database()
print(f'Tags: {len(get_all_tags())}')
print(f'Files: {len(get_all_files())}')
"
```

### Viewing raw index
```bash
cat ~/Documents/librarian/index.json
```

## Widget Communication

- `TagList` contains two ListViews (favorites + all tags), emits `TagSelected` message
- `FileList` emits `FileHighlighted` when cursor moves (updates preview)
- `Preview` receives file paths via `show_file()` async method, scrollable when focused
- App handles all messages in `on_<widget>_<message>` handlers

## Keyboard Navigation

Tab cycles through panels in clockwise order:
1. Favorites (top-left)
2. Files (top-right)
3. Preview (bottom-right)
4. All Tags (bottom-left)

Custom focus order is defined in `LibrarianApp.FOCUS_ORDER` with overridden `action_focus_next`/`action_focus_previous` methods.

Key bindings:
- `e` - Edit selected file (only way to open editor)
- `p` - Show full path of selected file
- `r` - Refresh/rescan files
- `?` - Show help

## CSS Layout Notes

- Main container uses percentage-based widths/heights for dynamic resizing
- Widgets inherit from `Vertical` container (not `Static`)
- ListViews use `height: 1fr` to fill available space within their sections
- Headers use fixed `height: 1`
- TagList splits into two `.tag-section` containers, each with `height: 1fr`

## Config Structure

```python
@dataclass
class TagConfig:
    mode: Literal["all", "whitelist"] = "all"
    whitelist: list[str] = field(default_factory=list)  # Used for Favorites

@dataclass
class Config:
    scan_directory: Path
    editor: str
    tags: TagConfig
```

## Performance Features

- **Background scanning**: Initial scan runs in background worker, UI loads immediately with cached index
- **Batched writes**: `batch_writes()` context manager defers JSON saves until batch completes
- **Incremental UI updates**: Tag list updates only changed items, preserves cursor position
- **File content cache**: LRU cache (10 files) for preview with mtime-based invalidation

### Using batch writes
```python
from librarian.database import batch_writes, add_file

with batch_writes():
    for path in files:
        add_file(path, mtime, tags)  # No disk I/O until context exits
# Single write happens here
```

## Dependencies

- `textual>=0.47.0` - TUI framework
- `watchdog>=4.0.0` - File system monitoring
- `rich` - Markdown rendering (included with textual)
