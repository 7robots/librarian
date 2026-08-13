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
    ├── tag_list.py      # Three-panel sidebar: Folders (top) + All Tags (middle) + Tools (bottom)
    ├── file_list.py     # Files for the selected folder or tag (ListView + search/navigation modes)
    ├── file_info.py     # RenameModal, MoveModal, and AssociateModal for file operations
    ├── calendar_list.py # Calendar meeting list widget
    ├── calendar_modal.py # Modal hosting CalendarList + its own Preview over the right panels
    ├── reminders_modal.py # Modal hosting remtui's RemindersPanel over the right panels
    ├── projects_modal.py # Modal hosting projection's ProjectsPanel over the right panels
    └── preview.py       # Markdown preview pane (VerticalScroll + Markdown)
```

## Key Design Decisions

- **Config location**: `$XDG_CONFIG_HOME/librarian/config.toml`, else `~/.config/librarian/config.toml`.
  remtui and taskpapertui resolve config the same way, so the three sit side by side
- **Install**: `./install.sh` syncs the env and puts a launcher in `~/bin` (`--dir DIR`, `--uninstall`).
  The identical script ships in remtui, projection, and taskpapertui — one install command across the
  four; only the `APP=`/`EXTRAS=` lines at the top differ. It syncs
  `--inexact --extra "$EXTRAS"`: exact is the `uv sync` default and **deleted** hand-installed
  optional panels (projection), while omitting the extra meant a fresh install silently lacked remtui
  and fell back to the terminal handoff. `EXTRAS` is empty in the other three
- **Index storage**: JSON at configurable `data_directory` (default: `~/.local/share/librarian/`). Atomic writes for iCloud compatibility.
- **Tag format**: Inline hashtags matching `#[a-zA-Z][a-zA-Z0-9_-]*`, where the `#` must start a line
  or follow whitespace, and code blocks are skipped. Without the whitespace rule every URL fragment
  and link anchor becomes a tag — that alone accounted for 53 of 55 tags in a real vault. Matches
  Obsidian's rules, so the two tag lists agree
- **Auto-refresh**: watchdog monitors scan directory with debouncing
- **Three-panel sidebar**: Folders, All Tags, and Tools are all visible at once — the folder tree is for browsing, while a tag like `#meetings` acts as a shortcut list to frequently used notes, so neither should hide the other. Startup focus is the folder tree; see `DEFAULT_SOURCE` in `widgets/tag_list.py`
- **Optional tools**: every tool needing a third-party program (TaskPaper, Reminders, Calendar, Projects) is opt-in via `[tools]`. Hiding a tool withholds its UI entry points only — the code stays live, so `.taskpaper` files keep being indexed, previewed, exported, and edited
- **Tools are launchers, not panels**: with Folders and Tags permanently on screen, every tool either hands off to an external program (TaskPaper) or opens a modal over the two right-hand panels (Reminders, Calendar, Projects) — see `LAUNCHER_TOOLS` in `widgets/tag_list.py`
- **Wiki links**: `[[note.md]]` or `[[note|display text]]` syntax, preprocessed to `wikilink:` scheme
- **Export**: HTML export with configurable output directory (sanitized output)
- **Banner**: Compact 3-row header (`widgets/banner.py`) — a robot mark echoing the `md-robot` folder glyph, a letter-spaced title, and the tagline. `Text(no_wrap=True)` keeps a narrow terminal from making it taller
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

The index also carries `scanner_version`. Scanning skips files by mtime, and a change to the tag
rules does not touch mtimes, so `scanner.SCANNER_VERSION` is bumped when extraction changes meaning
and a mismatch forces one full rescan. Bump it in the same commit as any change to `TAG_PATTERN` or
`strip_code()`.

Denormalized structure with tags inline per file. Only files containing at least one hashtag are indexed. Uses atomic writes (temp file + `os.replace()`) for iCloud compatibility.

## UI Layout

The app has five panels — three down the left, two on the right:
- **Left sidebar** (25% width), all three always visible:
  - **Folders** (`1fr`): DirectoryTree of the scan directory
  - **All Tags** (`1fr`): every indexed tag with its file count — equal weight with Folders, since
    browsing the tree and jumping to a tag are equally common and neither should crowd the other
  - **Tools** (`height: auto`, capped at 40%): only the tools enabled in `[tools]`, so it takes just
    the rows its launchers need, collapses to its header when none are enabled — and is skipped in
    the Tab cycle when empty
- **Right top** (33% height): File list — the selected folder's files in folder view, the selected tag's files otherwise
- **Right bottom** (67% height): Markdown preview

Layout uses percentage-based CSS for dynamic terminal resizing.

### Active source
Folders and Tags are both on screen, so "which one is the Files panel showing?" is state in its own
right: `TagList.active_source` (`"folders"` or `"tags"`), set by moving the tree cursor or selecting
a tag. It is not the same idea as the old `active_tool` — tools no longer own the content area.

### Folder view
With `active_source == "folders"`, the Files panel follows the folder tree cursor: moving onto a
folder lists that folder's files. Two deliberate choices:

- **Direct children only** — descendants are not included, matching Notebook Navigator's own
  `includeDescendantNotes = false`. Purely organizational folders therefore show an empty panel.
- **Read from the filesystem, not the index** (`scanner.list_folder_files()`) — the index holds only
  files carrying at least one hashtag, so a folder-organized vault would look nearly empty if
  listed from there.

`LibrarianApp._refresh_file_panel()` dispatches on `active_source`, so an index update (background
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

- `TagList` contains three sibling panels: `#folders-panel` (DirectoryTree), `#tags-panel` (All Tags
  ListView), and `#tools-panel` (Tools ListView)
  - Tracks `active_source` (`"folders"` or `"tags"`) — which panel the Files panel is following
  - Emits `TagSelected` when a tag is selected (sets `active_source = "tags"`)
  - Emits `FolderHighlighted` when the folder tree cursor moves to a folder (sets it to `"folders"`)
  - Emits `FileSelected` when a file is selected in folder browser
  - Emits `ToolLaunched` for every tool — each either runs an external program (TaskPaper) or opens a
    modal (Reminders, Calendar). Neither touches `active_source`, so the Files panel keeps showing
    what it was showing when the modal closes
  - `initialize()` focuses the folder tree and publishes the root folder's files at startup
- `CalendarModal` (in `calendar_modal.py`) frames `CalendarList` plus **its own** `Preview` over the
  two right-hand panels — it covers the main preview, so it cannot borrow it. `q`/`escape` close it;
  `a`, `n`, and `e` forward to the app's actions
- `RemindersModal` (in `reminders_modal.py`) frames remtui's `RemindersPanel` the same way. Both bind
  `q` with `priority=True`: the hosted panel binds `q` to `app.quit`, so without the priority
  binding closing the modal would quit Librarian
- `FileList` emits `FileHighlighted` when cursor moves (updates preview)
- `Preview` receives file paths via `show_file()` async method, scrollable when focused
- `AssociateModal` (in `file_info.py`) presents a list of `#meetings`-tagged files for linking to a calendar event; returns the selected `Path` or `None`
- `Banner` (in `banner.py`) renders a colorful ASCII art header, replacing the default Textual Header widget
- App handles all messages in `on_<widget>_<message>` handlers

## Keyboard Navigation

Tab goes down the left column, then down the right:
1. Folders (top-left)
2. All Tags (middle-left)
3. Tools (bottom-left) — **skipped when no tools are enabled**, since the panel is then empty
4. Files (top-right)
5. Preview (bottom-right)

Custom focus order is defined in `LibrarianApp.FOCUS_ORDER`, with `action_focus_next`/
`action_focus_previous` delegating to `_focus_step()`, which walks past any stop whose lookup
returns `None`.

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
- TagList: Folders `1fr`, All Tags `1fr`, Tools `height: auto` with `max-height: 40%`. `#tools-list-view`
  must be `height: auto` too — a `1fr` child inside an `auto` parent grabs the leftover sidebar space,
  which made a three-item menu render as tall as the folder tree. Auto also lets the panel shrink to
  its header when no tools are enabled, giving the rows back to Folders and Tags
- Each sidebar panel carries its own border color: Folders `$success`, All Tags `$primary`,
  Tools `$accent`
- Banner widget has fixed `height: 3` with `width: 100%`; `ROBOT_ROWS` must stay 3 rows of equal, single-cell width or the text column shifts between lines
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
    projects: bool = False    # show the Projects tool (needs projection)

@dataclass
class Config:
    scan_directory: Path
    editor: str
    taskpaper: str          # Path to taskpapertui executable (empty = use editor)
    reminders: str          # Path to remtui executable (empty = find "remtui" on PATH)
    projects: str           # Path to projection executable (empty = find "projection" on PATH)
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
- **Batched watcher updates**: File watcher batches multiple file changes into single index write.
  The debounce is a `threading.Timer`, so `FileWatcher.stop()` calls `MarkdownEventHandler.cancel()`
  to discard anything still in the window — otherwise a file saved just before quit gets rescanned
  against a torn-down database. `LibrarianApp._handle_file_change()` swallows `NoMatches` for the
  same reason, from the other end
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

- `textual>=8.2.8` - TUI framework
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
- `widgets/calendar_modal.py`: `CalendarModal` — the meeting list plus a dedicated `Preview`, over
  the Files and Preview panels
- `widgets/file_info.py`: `AssociateModal` - modal screen listing `#meetings`-tagged files for event-to-file association
- `actions/calendar_actions.py`: `action_open_calendar()` (gated on `[tools] calendar`) and the
  `_calendar_list()`/`_calendar_preview()` lookups the meeting handlers use, which return `None` when
  the modal is closed

### Failures vs empty days
`fetch_todays_events()` raises `CalendarError` rather than returning `[]` when anything goes wrong,
so a broken icalPal is never displayed as a day with no meetings. The message carries the specific
cause: exit code with the first line of stderr, a timeout, an OSError's `strerror`, or unreadable
output. A configured `icalpal_path` that is missing or not executable is reported instead of quietly
falling back to whatever is on PATH, so a typo says so.

The worker runs with `exit_on_error=False`. Without it, Textual's default takes the **whole app
down** when the worker raises, before the error branch can display anything. The `_export_file`
worker needs the same for the same reason.

There is no `--version` pre-flight: `icalPal --version` writes to stderr and exits 1, so it cannot
tell a working install from a broken one. The fetch itself is the check.

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
1. Select "Calendar" in Tools → a modal opens over the right-hand panels with today's meetings
2. Navigate meetings → the modal's preview shows the associated note or the meeting details
3. Press `a` → pick from `#meetings` tagged files to associate
4. Press `n` → create meeting note template (auto-associated, includes `#meetings` tag)
5. Press `e` → edit associated note
6. Press `q` or `escape` → close, returning to whatever the Files panel was showing

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
projects = false    # Smartsheet projects, via projection
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

### Embedded panel, with a handoff fallback
`action_launch_reminders` prefers the embedded panel and falls back to the executable:

1. **Panel** — with remtui importable, `RemindersModal` (`widgets/reminders_modal.py`) mounts
   remtui's `RemindersPanel` over the Files and Preview panels, leaving the banner, folder tree, and
   Tools menu visible. Install with `uv sync --extra reminders`.
2. **Handoff** — otherwise Librarian suspends and runs the `remtui` executable.

The fallback is not vestigial: remtui needs Python 3.12+ while Librarian supports 3.10, so on older
interpreters the package cannot be installed even when the binary is on PATH. The optional
dependency carries a `python_version >= '3.12'` marker for the same reason, and hatchling needs
`allow-direct-references` because remtui is referenced by git URL.

Three things make the embed work:

- **The hosted panels' dialogs share one contract.** remtui's and projection's edit dialogs use the
  same shape — `[secondary…] [Cancel] [Primary]` right-aligned, `btn-*` ids, a `Footer` derived from
  `BINDINGS`, focus starting in the first field, and the safe option focused in a destructive
  confirm. Their bindings are `priority=True`, without which the focused `Input` swallows `ctrl+e`
  and friends — so the dialog's own shortcuts died exactly where the cursor starts. Tests in
  `test_projects_panel.py` / `test_reminders_panel.py` pin that the contract still holds when the
  dialog is pushed onto *Librarian's* screen stack, including that `s` and `u` stay unreachable and
  that `escape` closes the dialog rather than the panel.
- **The embed drops the panel's wordmark.** Both panels take `show_logo=False`, which Librarian
  passes: its own frame already labels the panel, so the three sidebar rows go to the lists instead.
  The flag is newer than the embed, so each modal checks `inspect.signature` before passing it —
  an older build would otherwise raise inside `compose()`, failing the whole modal rather than
  just the logo. Mutation-verified.
- **remtui exposes a widget, not a Screen.** Textual cannot nest one `App` inside another, and a
  `Screen` cannot be mounted inside a container. remtui's `RemindersPanel` is a plain widget with
  scoped `DEFAULT_CSS`, so hosting it cannot restyle Librarian; its dialogs carry their own
  `dialogs.tcss`.
- **`q` needs a binding here.** The panel carries remtui's `q -> quit`, which resolves to nothing in
  this context, so without `RemindersModal`'s own `q` the panel could not be closed by keyboard.
- **`ModalScreen` isolates Librarian's keys.** Librarian binds single letters on the App, which would
  otherwise stay live beneath another screen; being modal stops `s`, `u`, `x` and friends from firing
  while the panel is open. `n` reaching remtui's add-reminder form rather than Librarian's new-note
  action is the visible proof, and both are pinned by tests.

Tests use remtui's `fake_remctl.py` backend, so they never read or write real Reminders. They skip
when remtui is not installed (`pytest.importorskip`).

## Projects (projection)

Selecting **Projects** opens [projection](https://github.com/7robots/projection) — a Textual TUI over
a Smartsheet of Infrastructure Architecture projects — in a modal over the Files and Preview panels.
Structurally identical to Reminders: `widgets/projects_modal.py` frames `projection.panel.ProjectsPanel`,
`actions/projects_actions.py` prefers the embed and falls back to the executable.

```toml
[tools]
projects = true

projects = ""   # empty = find "projection" on PATH
```

### The dependency is declared, as of 2026-08-13
`uv sync --extra projects` installs it, exactly like remtui. It was deliberately *undeclared* for a
long time because projection's repository was private, and declaring it would have made that command
fail for anyone without access. projection is public now, so the extra is ordinary.

Two things left over from that era are worth knowing. The suspend-and-launch fallback is **not**
vestigial: projection needs Python 3.11+, so the marker on the extra keeps librarian installable
below that, with the panel simply unavailable. And a hand-installed editable checkout — which is how
this machine runs it, pointed at a private fork — survives `./install.sh` because it syncs
`--inexact`; a bare `uv sync` is exact and would replace it with the published version.

### `priority=True` on `q` is load-bearing here
Unlike `CalendarModal`, where the flag is defensive, `ProjectsPanel` binds `q -> app.quit` itself and
holds focus — so the focused widget is checked before the screen, and without priority `q` closes
Librarian outright. Mutation-verified: dropping the flag fails
`test_q_closes_the_panel_and_librarian_survives`.

`SmartsheetClient` loads its token from 1Password lazily, on the first request and on a worker
thread, so constructing it when the modal opens cannot block the UI or trigger a Touch ID prompt at
startup.

Tests live in two files: `test_projects.py` covers what Librarian owns either way (resolving the
executable, the opt-in gate, embed-preferred-over-handoff) and always runs; `test_projects_panel.py`
covers the embed and skips via `importorskip`. The latter uses a local copy of projection's `FakeSync`
rather than importing it, so a change in projection's own suite cannot silently alter what is tested
here.

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
