# CLAUDE.md - Development Guide for Librarian

## Project Overview

Librarian is a Textual-based TUI application that indexes markdown files by inline hashtags and provides a browsing experience for navigating files by tag.

## Architecture

```
src/librarian/
├── __init__.py          # Package version
├── __main__.py          # Entry point, initializes app
├── app.py               # Main Textual App with layout and keybindings
├── config.py            # TOML config loading from ~/.config/librarian/
├── database.py          # JSON index operations (in-memory + file persistence)
├── scanner.py           # File scanning & hashtag extraction
├── watcher.py           # File system watcher using watchdog
├── wikilink.py          # Wiki link preprocessing and parsing
├── navigation.py        # Navigation state management for wiki links
├── export.py            # Export to HTML functionality (with sanitization)
└── widgets/
    ├── __init__.py
    ├── tag_list.py      # Tools sidebar (top) + switchable content panel (Tags/Folders/placeholders)
    ├── file_list.py     # Files with selected tag (ListView + navigation mode)
    ├── file_info.py     # RenameModal and MoveModal for file operations
    └── preview.py       # Markdown preview pane (VerticalScroll + Markdown)
```

## Key Design Decisions

- **Config location**: `~/.config/librarian/config.toml` (XDG standard)
- **Index storage**: JSON at configurable `data_directory` (default: `~/.local/share/librarian/`). Atomic writes for iCloud compatibility.
- **Tag format**: Inline hashtags matching `#[a-zA-Z][a-zA-Z0-9_-]*`
- **Auto-refresh**: watchdog monitors scan directory with debouncing
- **Tools sidebar**: Top-level navigation hub with Tools menu (Tags, Folders, TaskPaper, Calendar, Agents) and switchable content panel
- **Wiki links**: `[[note.md]]` or `[[note|display text]]` syntax, preprocessed to `wikilink:` scheme
- **Export**: HTML export with configurable output directory (sanitized output)

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
- **Left sidebar** (25% width): Tools menu (30% height) and switchable content panel (70% height)
  - Tools menu: Tags, Folders, TaskPaper, Calendar, Agents
  - Content panel switches between: All Tags (ListView), Folders (DirectoryTree), or placeholder text
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
from librarian.config import Config
from librarian.database import init_database, get_all_tags, get_all_files
config = Config.load()
init_database(config.get_index_path())
print(f'Tags: {len(get_all_tags())}')
print(f'Files: {len(get_all_files())}')
"
```

### Viewing raw index
```bash
cat \$(uv run python -c "from librarian.config import Config; print(Config.load().get_index_path())")
```

## Widget Communication

- `TagList` contains Tools ListView, All Tags ListView, DirectoryTree, and placeholder Static
  - Tracks `active_tool` property (`"tags"`, `"folders"`, `"taskpaper"`, `"calendar"`, `"agents"`)
  - Emits `TagSelected` when a tag is selected
  - Emits `FileSelected` when a file is selected in folder browser
  - Emits `ToolLaunched` when a tool (e.g. TaskPaper) is selected from Tools menu
- `FileList` emits `FileHighlighted` when cursor moves (updates preview)
- `Preview` receives file paths via `show_file()` async method, scrollable when focused
- App handles all messages in `on_<widget>_<message>` handlers

## Keyboard Navigation

Tab cycles through panels in clockwise order:
1. Tools (top-left)
2. Files (top-right)
3. Preview (bottom-right)
4. All Tags (bottom-left)

Custom focus order is defined in `LibrarianApp.FOCUS_ORDER` with overridden `action_focus_next`/`action_focus_previous` methods.

Key bindings:
- `s` - Search files and tags
- `e` - Edit selected file (uses taskpaper TUI for `.taskpaper` files if configured)
- `r` - Rename file
- `d` - Delete selected file (press twice to confirm)
- `m` - Move file to different directory (Tab for completion)
- `t` - Select TaskPaper tool (auto-selects #taskpaper tag)
- `u` - Update/rescan files
- `n` - Create new file (`.taskpaper` when TaskPaper tool active, `.md` otherwise)
- `x` - Export current file to HTML
- `Escape` - Navigate back from wiki link or exit search
- `?` - Show help

## CSS Layout Notes

- Main container uses percentage-based widths/heights for dynamic resizing
- Widgets inherit from `Vertical` container (not `Static`)
- ListViews use `height: 1fr` to fill available space within their sections
- Headers use fixed `height: 1`
- TagList: Tools list at 30% height, content panel at 70% height
- Content panel sections toggled via CSS `hidden` class

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
    taskpaper: str          # Path to taskpapertui executable (empty = use editor)
    tags: TagConfig
    export_directory: Path  # Default: ~/Downloads
    data_directory: Path    # Default: ~/.local/share/librarian
```

## Performance Features

- **Background scanning**: Initial scan runs in background worker, UI loads immediately with cached index
- **Batched writes**: `batch_writes()` context manager defers JSON saves until batch completes
- **Batched watcher updates**: File watcher batches multiple file changes into single index write
- **Targeted rescan**: Rename/move operations update only affected files, not full directory scan
- **Thread-safe writes**: Index writes protected by threading lock to prevent corruption
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
- `markdown>=3.5.0` - Markdown to HTML conversion for export

## Wiki Link Navigation

Librarian supports wiki-style links for navigating between markdown files:

### Syntax
- `[[filename.md]]` - Link to a file by name, displays the filename
- `[[filename|Display Text]]` - Link with custom display text
- Filenames can have spaces: `[[my notes.md]]`

### Implementation
1. **Preprocessing**: `wikilink.py` converts wiki links to markdown links with custom `wikilink:` scheme
   - `[[note.md]]` becomes `[note.md](wikilink:note.md)`
   - `[[note|Text]]` becomes `[Text](wikilink:note)`
   - URL-encodes targets to handle spaces and special characters

2. **Link Resolution**: `database.py` provides `resolve_wiki_link()` to find files
   - Searches by exact filename match in the index
   - Returns `Path | None`

3. **Click Handling**: `preview.py` intercepts link clicks in markdown preview
   - Detects `wikilink:` scheme URLs
   - Extracts and resolves target filename
   - Posts message to app to navigate to the file

4. **Navigation Stack**: `navigation.py` manages back navigation
   - `NavigationState` stores file list state (tag, files, selected index, header)
   - `NavigationStack` provides push/pop operations
   - App stores stack instance and handles Escape key to go back

5. **Navigation Mode**: `file_list.py` supports two modes
   - Normal mode: Shows files for selected tag
   - Navigation mode: Shows single file from wiki link
   - Header text indicates mode ("FILES" vs "BACK: filename")

### User Experience
- Click a wiki link in the preview panel to navigate to that file
- Press `Escape` to return to the previous view (tag/file list)
- Navigation preserves the entire state: selected tag, file list, cursor position

## Search

Press `s` to search files by filename or tag. The search performs partial matching (case-insensitive) against both file names and tag names.

### Behavior
- Press `s` to enter search mode - the file list becomes a search input
- Type to search - results update as you type
- Results show filename and matching tags (if any)
- If multiple results, use arrow keys to select
- If single result, it previews automatically
- Press `Enter` to move focus from search input to results
- Press `Escape` to exit search mode

### Implementation
- `database.py`: `search_files(query)` returns `list[tuple[Path, float, list[str]]]` with matching files
- `file_list.py`: `enter_search_mode()`, `exit_search_mode()`, `update_search_results()` methods
- Search is performed on the in-memory index, not file contents

## File Creation

Press `n` to create a new file in the scan directory. The file type depends on the active tool:

### Markdown (default)
- Creates `.md` file with template including current tag
- Opens in the configured editor

### TaskPaper (when TaskPaper tool is active)
- Creates `.taskpaper` file with `Inbox:` project template and `#taskpaper` tag
- Opens in configured taskpaper editor (or falls back to default editor)

## Export to HTML

Press `x` to export the currently selected file to HTML.

### Security
Export includes HTML sanitization to prevent XSS:
- Document titles are escaped with `html.escape()`
- Dangerous tags removed: `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, etc.
- Dangerous attributes removed: `onclick`, `onerror`, `javascript:` URLs, etc.

### Export Styling
The `export.py` module includes clean, professional CSS:
- System fonts with good fallbacks
- GitHub-style markdown rendering
- Syntax highlighting support
- Responsive layout (800px max width)

### Configuration
Set export destination in config.toml (`~/.config/librarian/config.toml`):
```toml
export_directory = "~/Downloads"  # or any other directory
```

### User Experience
- Press `x` on any file in the file list
- App shows notification with export path
- Files are named `{original-stem}.html`
- Existing files are overwritten
