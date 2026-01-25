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
├── database.py          # SQLite index operations
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
- **Index storage**: SQLite at `~/Documents/librarian/index.db`
- **Tag format**: Inline hashtags matching `#[a-zA-Z][a-zA-Z0-9_-]*`
- **Auto-refresh**: watchdog monitors scan directory with debouncing
- **Favorites**: Tags in config whitelist appear in dedicated Favorites panel

## Database Schema

```sql
files(id, path, mtime)
tags(id, name)
file_tags(file_id, tag_id)
```

Only files containing at least one hashtag are indexed.

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

### Checking database state
```bash
uv run python -c "
from librarian.database import get_all_tags, get_all_files
print(f'Tags: {len(get_all_tags())}')
print(f'Files: {len(get_all_files())}')
"
```

## Widget Communication

- `TagList` contains two ListViews (favorites + all tags), emits `TagSelected` message
- `FileList` emits `FileHighlighted` when cursor moves, `FileSelected` on Enter
- `Preview` receives file paths via `show_file()` async method
- App handles all messages in `on_<widget>_<message>` handlers

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

## Dependencies

- `textual>=0.47.0` - TUI framework
- `watchdog>=4.0.0` - File system monitoring
- `rich` - Markdown rendering (included with textual)
