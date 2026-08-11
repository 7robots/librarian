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
├── calendar.py          # icalPal wrapper for fetching calendar events
├── calendar_store.py    # Event-to-file association storage (sidecar JSON)
├── icons.py             # Icon-name -> terminal glyph tables (Nerd Font / emoji) + style detection
├── appearance.py        # Layered folder appearance: config > Notebook Navigator > defaults
├── obsidian.py          # Reads folder icons/colors from Obsidian's Notebook Navigator plugin
└── widgets/
    ├── __init__.py
    ├── banner.py        # Custom ASCII art banner replacing default Textual Header
    ├── tag_list.py      # Switchable content panel (Tags/Folders/Calendar, top) + Tools menu (bottom)
    ├── file_list.py     # Files for the selected folder or tag (ListView + search/navigation modes)
    ├── file_info.py     # RenameModal, MoveModal, and AssociateModal for file operations
    ├── calendar_list.py # Calendar meeting list widget
    └── preview.py       # Markdown preview pane (VerticalScroll + Markdown)
```

## Key Design Decisions

- **Config location**: `~/.config/librarian/config.toml` (XDG standard)
- **Index storage**: JSON at configurable `data_directory` (default: `~/.local/share/librarian/`). Atomic writes for iCloud compatibility.
- **Tag format**: Inline hashtags matching `#[a-zA-Z][a-zA-Z0-9_-]*`
- **Auto-refresh**: watchdog monitors scan directory with debouncing
- **Folder-first sidebar**: Content panel (Folders/Tags/Calendar) on top, Tools menu below. Opens on Folders — see `DEFAULT_TOOL` in `widgets/tag_list.py`
- **Optional tools**: every tool needing a third-party program (TaskPaper, Reminders, Calendar) is opt-in via `[tools]`. Hiding a tool withholds its UI entry points only — the code stays live, so `.taskpaper` files keep being indexed, previewed, exported, and edited
- **Launcher tools**: TaskPaper and Reminders hand off to an external program rather than switching the content panel — see `LAUNCHER_TOOLS` in `widgets/tag_list.py`
- **Wiki links**: `[[note.md]]` or `[[note|display text]]` syntax, preprocessed to `wikilink:` scheme
- **Export**: HTML export with configurable output directory (sanitized output)
- **Banner**: Custom ASCII art header (`widgets/banner.py`) with per-letter colorization, replacing the default Textual Header
- **Border styling**: Each panel has a distinct border color (`$accent`/cyan for tags, `$warning`/yellow for files, `$success`/green for preview) with `:focus-within` pseudo-class for active panel indication

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
- **Left sidebar** (25% width): switchable content panel (50% height) on top, Tools menu (50% height) below
  - Content panel switches between: Folders (DirectoryTree), All Tags (ListView), Calendar (CalendarList)
  - Tools menu: Tags and Folders always; TaskPaper, Reminders, and Calendar when enabled in config
- **Right top** (33% height): File list — the selected folder's files in folder view, the selected tag's files otherwise
- **Right bottom** (67% height): Markdown preview

Layout uses percentage-based CSS for dynamic terminal resizing.

### Folder view
With the Folders tool active, the Files panel follows the folder tree cursor: moving onto a folder
lists that folder's files. Two deliberate choices:

- **Direct children only** — descendants are not included, matching Notebook Navigator's own
  `includeDescendantNotes = false`. Purely organizational folders therefore show an empty panel.
- **Read from the filesystem, not the index** (`scanner.list_folder_files()`) — the index holds only
  files carrying at least one hashtag, so a folder-organized vault would look nearly empty if
  listed from there.

`LibrarianApp._refresh_file_panel()` dispatches on `active_tool`, so an index update (background
scan or file watcher) refreshes the folder listing rather than replacing it with a tag's files.

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

- `TagList` contains the content panel (DirectoryTree, All Tags ListView, CalendarList) and the Tools ListView
  - Tracks `active_tool` property (`"folders"`, `"tags"`, `"taskpaper"`, `"calendar"`)
  - Emits `TagSelected` when a tag is selected
  - Emits `FolderHighlighted` when the folder tree cursor moves to a folder
  - Emits `FileSelected` when a file is selected in folder browser
  - Emits `ToolLaunched` for launcher tools (TaskPaper, Reminders), which run an external program
    instead of switching the content panel — `active_tool` and the visible panel are left alone
  - `_switch_panel()` republishes the active selection so the Files panel follows the tool
  - `initialize_default_tool()` syncs the menu highlight and content panel at startup without taking focus
- `FileList` emits `FileHighlighted` when cursor moves (updates preview)
- `Preview` receives file paths via `show_file()` async method, scrollable when focused
- `AssociateModal` (in `file_info.py`) presents a list of `#meetings`-tagged files for linking to a calendar event; returns the selected `Path` or `None`
- `Banner` (in `banner.py`) renders a colorful ASCII art header, replacing the default Textual Header widget
- App handles all messages in `on_<widget>_<message>` handlers

## Keyboard Navigation

Tab cycles through panels in clockwise order:
1. Content panel (top-left) — resolves to the active tool's view (Folders/Tags/Calendar)
2. Files (top-right)
3. Preview (bottom-right)
4. Tools (bottom-left)

Custom focus order is defined in `LibrarianApp.FOCUS_ORDER` with overridden `action_focus_next`/`action_focus_previous` methods.

Key bindings:
- `s` - Search files and tags
- `e` - Edit selected file (uses taskpaper TUI for `.taskpaper` files if configured)
- `r` - Rename file
- `d` - Delete selected file (press twice to confirm)
- `m` - Move file to different directory (Tab for completion)
- `t` - Select TaskPaper tool (auto-selects #taskpaper tag)
- `a` - Associate meeting with file (calendar tool only)
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
- TagList: content panel and Tools list each at `height: 1fr` (50/50)
- Content panel sections toggled via CSS `hidden` class
- Banner widget has fixed `height: 5` with `width: 100%`
- Per-panel border colors with `:focus-within` for active indication:
  - `#tag-list`: `$accent` / `cyan` when focused
  - `#file-list`: `$warning` / `yellow` when focused
  - `#preview`: `$success` / `green` when focused

## Config Structure

```python
@dataclass
class TagConfig:
    mode: Literal["all", "whitelist"] = "all"
    whitelist: list[str] = field(default_factory=list)  # Used for Favorites

@dataclass
class CalendarConfig:
    calendar_name: str = ""  # empty = all calendars
    icalpal_path: str = ""   # empty = auto-detect
    # Whether the tool is shown lives in [tools] calendar

@dataclass
class IconConfig:
    style: Literal["auto", "nerd", "emoji"] = "auto"

@dataclass
class FoldersConfig:
    icons: dict[str, str]   # relative folder path -> Lucide icon name
    colors: dict[str, str]  # relative folder path -> hex color

@dataclass
class ObsidianConfig:
    enabled: bool = True

@dataclass
class Config:
@dataclass
class ToolsConfig:
    taskpaper: bool = False   # show the TaskPaper tool (needs taskpapertui)
    reminders: bool = False   # show the Reminders tool (needs remtui)
    calendar: bool = False    # show the Calendar tool (needs icalPal)

@dataclass
class Config:
    scan_directory: Path
    editor: str
    taskpaper: str          # Path to taskpapertui executable (empty = use editor)
    reminders: str          # Path to remtui executable (empty = find "remtui" on PATH)
    tags: TagConfig
    export_directory: Path  # Default: ~/Downloads
    data_directory: Path    # Default: ~/.local/share/librarian
    calendar: CalendarConfig
    tools: ToolsConfig
    icons: IconConfig
    folders: FoldersConfig
    obsidian: ObsidianConfig
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

## Calendar Integration

Librarian integrates with macOS Calendar via icalPal to show today's meetings.

### Prerequisites
- icalPal: `brew tap ajrosen/tap && brew install icalPal`

### Configuration
```toml
[tools]
calendar = true        # the tool is opt-in; icalPal is not bundled

[calendar]
calendar_name = ""     # empty = all calendars
icalpal_path = ""      # empty = auto-detect
```

### Architecture
- `calendar.py`: Wraps icalPal subprocess, parses JSON output, 5-minute TTL cache
- `calendar_store.py`: Sidecar JSON at `{data_directory}/calendar_associations.json` for event-to-file mapping
- `widgets/calendar_list.py`: `CalendarList` widget with `MeetingItem` list items
- `widgets/file_info.py`: `AssociateModal` - modal screen listing `#meetings`-tagged files for event-to-file association

### Reading icalPal output
Two field choices in `_parse_event()` are load-bearing and easy to "fix" back into bugs:

- **Use `sctime`/`ectime`, not `start_date`/`end_date`.** For a recurring event, `start_date` holds
  the *series* original start, not today's occurrence — which sorts the meeting away from its real
  slot in the list. `sctime` carries the occurrence and a UTC offset
  (`"2026-08-11 10:00:00 -0400"`).
- **Integer timestamps use Apple's epoch, not Unix.** icalPal counts from 2001-01-01, so
  `datetime.fromtimestamp()` lands 31 years in the past. `APPLE_EPOCH_OFFSET` corrects it. The
  time-of-day still looks right, which is what makes this one easy to miss.

Everything `_parse_datetime()` returns is timezone-aware, because `sctime` is aware and the integer
fallback is not — sorting a mix of aware and naive datetimes raises `TypeError`.

`recurring` comes from `has_recurrences`; icalPal has no `recurring` key. Null is treated as absent
rather than false, since icalPal writes explicit nulls for fields that don't apply.

### User Experience
1. Select "Calendar" in Tools → shows today's meetings
2. Navigate meetings → preview shows associated note or meeting info
3. Press `a` → pick from `#meetings` tagged files to associate
4. Press `n` → create meeting note template (auto-associated, includes `#meetings` tag)
5. Press `e` → edit associated note

### Association Storage
```json
{"associations": {"event-uid": {"file": "/path/to/note.md"}}}
```
Uses atomic writes (temp file + `os.replace()`).

## File Creation

Press `n` to create a new file in the scan directory. The file type depends on the active tool:

### Markdown (default)
- Creates `.md` file with template including current tag
- Opens in the configured editor

### TaskPaper (when TaskPaper tool is active)
- Creates `.taskpaper` file with `Inbox:` project template and `#taskpaper` tag
- Opens in configured taskpaper editor (or falls back to default editor)

### Calendar (when Calendar tool is active)
- Creates `.md` meeting note with title, time, location, attendees from selected event
- Includes `#meetings` tag
- Auto-associates with the selected calendar event

## Folder Appearance

Folder icons and colors come from layered sources, consulted in precedence order **per key**:

1. Librarian's own config — `[folders.icons]` / `[folders.colors]`
2. Obsidian's Notebook Navigator plugin, when the scan directory is inside a vault
3. A plain folder glyph, with no color

Per key matters: config can set only a *color* for a folder while the plugin supplies its *icon*, and
both apply. A source winning outright would make that impossible.

Nothing here requires Obsidian. `appearance.py` owns the layering, `icons.py` the glyphs, and
`obsidian.py` is one optional source — with no config and no plugin, every folder gets the default
glyph, which is what a stock Textual tree shows anyway.

### Config

```toml
[icons]
style = "auto"          # auto | nerd | emoji

[folders.icons]         # keys are paths relative to scan_directory
"projects" = "briefcase"
"projects/2026" = "calendar"

[folders.colors]
"projects" = "#8b5cf6"  # colors inherit to subfolders

[obsidian]
enabled = true          # false ignores the plugin even inside a vault
```

Icon names are [Lucide](https://lucide.dev/icons/) names — the same vocabulary Notebook Navigator
uses. `Config.save()` writes these tables by hand (`tomllib` is read-only) with every key quoted,
since folder paths contain slashes, dots, and spaces; empty tables are written commented out.

Note that config keys are relative to `scan_directory`, so changing that setting leaves them stale.

### Icon styles
Lucide has no terminal-renderable form — Obsidian draws it as inline SVG, and Nerd Fonts does not
carry the set ([nerd-fonts#1389](https://github.com/ryanoasis/nerd-fonts/issues/1389)). So names map
to glyphs in one of two styles:

| Style | Table | Notes |
|---|---|---|
| `nerd` | `NERD_GLYPHS` | Material Design Icons from Nerd Fonts. Monochrome, so they take the folder color. |
| `emoji` | `EMOJI_GLYPHS` | For terminals without a Nerd Font. Emoji carry their own colors and ignore the folder color. |

`auto` (the default) picks between them in `icons.detect_glyph_style()`, which needs two signals
because neither suffices alone: a terminal allowlist (`NERD_FONT_TERMINALS` — Ghostty and WezTerm
embed the font in their own binary, so a font scan misses them) and a scan of the macOS font
directories for a filename containing `nerd` (which catches anyone who installed one in an
unrecognized terminal). Emoji is the fallback, since emoji render nearly everywhere. It is a
heuristic — set `style` explicitly to override it.

Names prefixed `emoji:` (e.g. `emoji:🤖`) are literal emoji and pass through unchanged in both
styles, since that is what Obsidian shows for them.

`NERD_GLYPHS` codepoints were resolved from the Nerd Fonts `glyphnames.json`, not written by hand;
each entry's comment records its `md-*` source name. To re-verify or extend the table:

```bash
curl -sL -o glyphnames.json https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/glyphnames.json
# then look up e.g. md-library -> {"char": "󰌱", "code": "f0331"}
```

A test asserts every glyph sits inside the Material Design range (U+F0001–U+F1AF0) and is
single-cell, which catches a mistyped codepoint before it renders as tofu. The table currently
covers 66 of Lucide's 2,025 names; anything else falls back to a plain folder glyph.

### Notebook Navigator source
Read at startup from `<vault>/.obsidian/plugins/notebook-navigator/data.json`. Nothing is copied into
Librarian's config, so changing an icon in Obsidian shows up on the next launch. These keys are used:

| Key | Use |
|---|---|
| `folderIcons` | Vault-relative folder path → Lucide icon name or `emoji:<char>` |
| `folderColors` | Vault-relative folder path → hex color |
| `inheritFolderColors` | When true, subfolders inherit the nearest ancestor's color |
| `showFolderIcons` | When false, this source supplies no icons (colors still apply) |
| `colorIconOnly` | When true, the color tints only the icon, not the folder name |
| `tagColors` | Loaded but not yet applied to the tag list |

`find_vault_root()` walks up from the scan directory looking for a `.obsidian` directory, so pointing
Librarian at a subfolder of a vault still resolves the right keys. The source returns icon *names*,
never glyphs — turning names into glyphs is `icons.py`'s job.

### Rendering
- `MarkdownDirectoryTree.render_label()` replaces the tree's expand/collapse glyph with the folder's
  icon, so each row shows a single icon. The icon keeps `TOGGLE_STYLE` (from `textual.widgets._tree`),
  which is the meta `Tree._on_click` looks for — so clicking the icon still expands/collapses.
- Folders with no configured icon get `md-folder`/`md-folder_open` (or `📁`/`📂`), which continue to
  flip on expand; a configured icon is the same open or closed.
- Glyphs are padded to a fixed cell width plus a separating space (`pad_glyph()`) so folder names
  align in a column — needed because one tree can mix one-cell Nerd Font glyphs with two-cell emoji.
- Files are left unstyled — folders only.
- Setting `tree.appearance = None` restores the stock Textual tree.

## Optional Tools

Every tool that depends on a program Librarian does not bundle is opt-in:

```toml
[tools]
taskpaper = false   # file-based tasks, via taskpapertui
reminders = false   # Apple Reminders, via remtui
calendar = false    # today's meetings, via icalPal
```

All default to false, so a fresh install shows only Tags and Folders and never advertises a tool
whose backing program is missing. Which task tool to use — if any — is the user's choice.

The calendar switch used to be `[calendar] enabled`. That key is still honored when `[tools] calendar`
is absent, so older configs keep working; `[tools]` wins when both are present. `[calendar]` keeps its
real settings (`calendar_name`, `icalpal_path`).

`ToolsConfig.is_enabled(name)` answers by attribute lookup, so a tool with no field is treated as
non-optional and always shown; `LibrarianApp.visible_tools()` filters `ALL_TOOLS` through it, and
`TagList` renders the list it is handed rather than reading the catalog. Enabling a tool inserts it
in catalog order rather than appending, which a test pins.

Hiding a tool withholds **all** its UI entry points — the menu row, the `t` binding,
`action_launch_reminders`, the calendar fetch, and the corresponding entries in the help text — on
the principle that a shortcut into a hidden feature is worse than no shortcut. Each guard names its
config key in the message it shows, so the switch stays discoverable.

What hiding does *not* touch: `.taskpaper` files are still indexed by the scanner, converted for
preview and export by `taskpaper.py`, and opened with the `taskpaper` editor by `e`. Note the
`taskpaper` config key (a path to an editor) and `[tools] taskpaper` (a bool) are deliberately
separate — one says which editor to use, the other whether the tool appears. They cannot be merged
into a single `[taskpaper]` table, since TOML forbids a bare key and a table sharing a name.

## Reminders (remtui)

Selecting **Reminders** from the Tools menu suspends Librarian and hands the terminal to
[remtui](https://github.com/7robots/remtui), a Textual TUI for Apple Reminders over the `remctl`
CLI. Quitting remtui returns to Librarian's panels.

```toml
reminders = ""   # empty = find "remtui" on PATH
```

`actions/reminders_actions.py` resolves the executable (absolute path used as-is, otherwise looked up
on PATH) and runs it inside `with self.suspend():` — the same pattern `action_edit` uses for editors.
A missing executable notifies rather than launching.

### Why an external program rather than an embedded panel
Textual has no supported way to run one `App` inside another; the App is the root. Embedding remtui
would mean refactoring its `RemTuiApp` into a `Screen` that Librarian pushes, which additionally
requires:

- Upgrading Librarian to `textual>=8.2.8` (remtui's floor; Librarian is on 7.x). The folder tree
  reaches into private Textual APIs (`_tree.TOGGLE_STYLE`, `_directory_tree.DirEntry`,
  `_invalidate()`), which is exactly what breaks across a major version.
- Scoping remtui's app-level theme and `CSS_PATH`, which would otherwise restyle Librarian.

Suspend-and-launch was chosen first because it always runs the real remtui, cannot drift out of sync
with it, and needs no version coupling. Note that reminders live in Apple Reminders, not in files, so
nothing in this path touches the index, file list, or preview.

If the embedded version is ever built, remtui ships `fake_remctl.py` — a fake CLI used by its own
tests — which Librarian could reuse to test the integration without touching real Reminders data.

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
