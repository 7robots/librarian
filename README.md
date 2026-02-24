# Librarian

A terminal-based tag browser for markdown and taskpaper files. Librarian scans your files for inline hashtags (`#tag`) and provides a TUI for browsing files by tag.

```
┌─────────────────────────────────────────────────────────────┐
│  Librarian - Markdown Tag Browser                           │
├──────────────┬──────────────────────────────────────────────┤
│  ★ TOOLS     │  FILES (#project)                            │
│              │                                              │
│ > Tags       │  > meeting-notes.md                          │
│   Folders    │    project-plan.md                           │
│   TaskPaper  │    ideas.md                                  │
│   Calendar   │                                              │
│   Agents     ├──────────────────────────────────────────────┤
│──────────────│  PREVIEW - meeting-notes.md                  │
│  ALL TAGS    │                                              │
│              │  # Meeting Notes                             │
│   #work      │                                              │
│   #meeting   │  Today we discussed the #project timeline... │
│   #idea      │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

## Features

- **Tag Discovery**: Automatically finds hashtags in markdown and taskpaper files
- **Tools Sidebar**: Top-level navigation hub with Tags, Folders, TaskPaper, Calendar, and Agents
- **Directory Browser**: Browse files by folder structure via the Folders tool
- **TaskPaper Integration**: Dedicated tool that filters to `#taskpaper` tag, creates `.taskpaper` files, and launches TaskPaper TUI for editing
- **Live Preview**: Markdown and taskpaper files rendered as you navigate
- **Search**: Find files by filename or tag with partial matching
- **Auto-Refresh**: File watcher updates index when files change
- **Editor Integration**: Press `e` to edit files in your preferred editor (or TaskPaper TUI for `.taskpaper` files)
- **File Management**: Rename, move, and delete files with keyboard shortcuts
- **Wiki Links**: Navigate between notes using `[[note.md]]` syntax
- **Export**: Export files to HTML with one keypress
- **Calendar Integration**: View today's meetings from macOS Calendar (via icalPal), associate meetings with notes, and create meeting note templates
- **File Creation**: Create new notes (`.md` or `.taskpaper` depending on active tool)
- **Custom Banner**: Colorful ASCII art header with per-letter styling
- **Visual Focus Indicators**: Distinct border colors per panel with focus-within highlighting
- **Dynamic Layout**: Resize terminal window and UI adapts

## Installation

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).

```bash
# Clone the repository
git clone https://github.com/yourusername/librarian.git
cd librarian

# Install dependencies
uv sync
```

## Usage

```bash
uv run librarian
```

On first run, Librarian will:
1. Create config directory at `~/Documents/librarian/`
2. Generate default config at `~/Documents/librarian/config.toml`
3. Create JSON index at `~/Documents/librarian/index.json`
4. Scan `~/Documents` for markdown and taskpaper files with hashtags

## Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `s` | Search files and tags |
| `e` | Edit selected file (uses TaskPaper TUI for `.taskpaper` files if configured) |
| `n` | Create new file (`.taskpaper` when TaskPaper tool active, `.md` otherwise) |
| `d` | Delete selected file (press twice to confirm) |
| `r` | Rename selected file |
| `m` | Move selected file to different directory |
| `t` | Select TaskPaper tool (auto-selects #taskpaper tag) |
| `a` | Associate meeting with file (Calendar tool only) |
| `x` | Export selected file to HTML |
| `u` | Update/rescan all files |
| `Tab` | Cycle focus between panels (clockwise) |
| `Shift+Tab` | Cycle focus backwards (counter-clockwise) |
| `↑/↓` | Navigate lists / scroll preview |
| `Enter` | Select tag / confirm search |
| `Escape` | Navigate back / exit search |
| `?` | Show help |

Tab order follows a clockwise pattern: Tools → Files → Preview → All Tags.

## Configuration

Edit `~/Documents/librarian/config.toml`:

```toml
# Directory to scan for markdown files
scan_directory = "~/Documents"

# Editor command for editing files (e.g., "vim", "code", "nano")
editor = "vim"

# TaskPaper TUI executable for editing .taskpaper files
# Leave empty to use the default editor instead
taskpaper = "taskpapertui"

# Directory for exported HTML files
export_directory = "~/Downloads"

# Tag filtering
[tags]
mode = "all"  # "all" shows all discovered tags, "whitelist" filters to specific tags
whitelist = ["project", "todo", "notes"]  # Used when mode = "whitelist"
```

### TaskPaper Integration

When `taskpaper` is set in the config, pressing `e` on a `.taskpaper` file will launch the specified TaskPaper TUI instead of the default editor. This allows a seamless workflow: select TaskPaper from the Tools menu (or press `t`), browse your `.taskpaper` files, and edit them in a dedicated TaskPaper editor.

### Calendar Integration

Librarian integrates with macOS Calendar via [icalPal](https://github.com/ajrosen/icalPal) to show today's meetings in the TUI.

**Prerequisites:**
```bash
brew tap ajrosen/tap && brew install icalPal
```

**Configuration:**
```toml
[calendar]
enabled = true
calendar_name = ""     # empty = all calendars
icalpal_path = ""      # empty = auto-detect
```

**Workflow:**
1. Select **Calendar** from the Tools menu to see today's meetings
2. Navigate meetings to preview associated notes or meeting details
3. Press `a` to associate a meeting with an existing `#meetings`-tagged file (opens the AssociateModal)
4. Press `n` to create a new meeting note template (auto-associated, includes `#meetings` tag)
5. Press `e` to edit the associated note

## Supported File Types

### Markdown (`.md`)
Standard markdown files with inline hashtags.

### Taskpaper (`.taskpaper`)
Plain-text task management files (compatible with [vim-taskpaper](https://github.com/davidoc/taskpaper.vim) and TaskPaper.app). Taskpaper files are indexed by `#hashtags` like markdown files, and the preview renders taskpaper-specific syntax:

- **Projects** (`Project Name:`) → displayed as headings
- **Tasks** (`- task text`) → displayed as checkboxes
- **Done tasks** (`- task @done`) → displayed as checked with strikethrough
- **@tags** (`@due(2024-01-01)`, `@priority(high)`) → highlighted inline

Taskpaper files can also be exported to HTML with `x`.

## Tag Format

Librarian recognizes hashtags in the format:
- Must start with `#` followed by a letter
- Can contain letters, numbers, underscores, and hyphens
- Examples: `#project`, `#todo-list`, `#meeting_notes`, `#2024goals`

## Search

Press `s` to search across all indexed files:

1. The file list transforms into a search input
2. Type to search - results update as you type
3. Matches against filenames and tag names (case-insensitive, partial matching)
4. Results show the filename and any matching tags
5. Press `Enter` to move focus to the results list
6. Use arrow keys to select a file for preview
7. Press `Escape` to exit search mode

## Wiki Links

Navigate between notes using wiki-style links in your markdown files:

### Syntax
```markdown
Link to a file: [[note.md]]
Link with custom text: [[my-file|Custom Display Text]]
Links with spaces: [[second test.md]]
```

### Usage
1. Write wiki links in your markdown files using the `[[filename]]` syntax
2. In the preview panel, click on a wiki link to navigate to that file
3. Press `Escape` to navigate back to your previous view

The navigation preserves your context, returning you to the exact tag and file position you were viewing before.

## Creating New Files

Press `n` to create a new file:

- **With Tags or Folders tool active**: Creates a `.md` file with a template including the current tag
- **With TaskPaper tool active**: Creates a `.taskpaper` file with an `Inbox:` project and `#taskpaper` tag

The new file opens automatically in the appropriate editor.

## File Management

### Renaming Files

Press `r` to rename the currently selected file:

1. A modal appears with the current filename
2. The filename (without extension) is pre-selected for easy editing
3. Edit the name and press `Enter` or `Ctrl+S` to save
4. Press `Escape` or `Ctrl+C` to cancel

### Moving Files

Press `m` to move the currently selected file to a different directory:

1. A modal appears with the current directory path
2. Edit the path or use Tab for Unix-style path completion:
   - Single match: completes the full path
   - Multiple matches: shows all options and completes the common prefix
3. Press `Enter` or `Ctrl+S` to move the file
4. Press `Escape` or `Ctrl+C` to cancel

## Directory Browser

Select **Folders** from the Tools menu to browse files by directory:

- Shows a tree view of your scan directory
- Only supported files (`.md`, `.taskpaper`) and directories are displayed
- Hidden files/directories (starting with `.`) are filtered out
- Select a file to preview it
- Select **Tags** from the Tools menu to return to tag browsing

## Deleting Files

Press `d` to delete the currently selected file:

1. First press shows a confirmation warning
2. Press `d` again within 3 seconds to confirm deletion
3. The file is removed from disk and the index is updated

## Exporting Files

Press `x` to export the currently selected file to HTML:

- Creates a standalone HTML file with embedded CSS
- Professional GitHub-style markdown rendering
- Output is sanitized to prevent XSS (dangerous tags/attributes removed)

Exported files are saved to your configured `export_directory` (default: `~/Downloads`) with professional styling suitable for sharing or printing.

## Data Storage

All data is stored in `~/Documents/librarian/`:
- `config.toml` - Configuration file
- `index.json` - JSON index with file/tag mappings

This location was chosen to enable iCloud sync on macOS.

## How It Works

1. **Scanning**: Recursively finds `*.md` and `*.taskpaper` files in the scan directory
2. **Indexing**: Extracts hashtags using regex, stores in JSON with file modification times
3. **Watching**: Uses `watchdog` to monitor for file changes with debouncing
4. **Display**: Textual TUI with Tools sidebar, tag/folder browser, file list, and markdown preview

## Development

```bash
# Run the app
uv run librarian

# Run with Python directly
uv run python -m librarian
```

## Dependencies

- [Textual](https://textual.textualize.io/) - TUI framework
- [watchdog](https://python-watchdog.readthedocs.io/) - File system monitoring
- [Rich](https://rich.readthedocs.io/) - Markdown rendering (bundled with Textual)
- [Python Markdown](https://python-markdown.github.io/) - Markdown to HTML conversion

## License

MIT
