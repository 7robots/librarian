# Librarian

A terminal-based markdown tag browser. Librarian scans your markdown files for inline hashtags (`#tag`) and provides a TUI for browsing files by tag.

```
┌─────────────────────────────────────────────────────────────┐
│  Librarian - Markdown Tag Browser                           │
├──────────────┬──────────────────────────────────────────────┤
│  FAVORITES   │  FILES (#project)                            │
│              │                                              │
│ > #project   │  > meeting-notes.md                          │
│   #todo      │    project-plan.md                           │
│──────────────│    ideas.md                                  │
│  ALL TAGS    │                                              │
│              ├──────────────────────────────────────────────┤
│   #work      │  PREVIEW - meeting-notes.md                  │
│   #meeting   │                                              │
│   #idea      │  # Meeting Notes                             │
│              │                                              │
│              │  Today we discussed the #project timeline... │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

## Features

- **Tag Discovery**: Automatically finds hashtags in markdown files
- **Favorites Panel**: Pin frequently-used tags to a dedicated section
- **Four-Panel UI**: Browse favorites, all tags, files, and preview content
- **Live Preview**: Markdown rendered as you navigate
- **Auto-Refresh**: File watcher updates index when files change
- **Editor Integration**: Press `e` to edit files in your preferred editor
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
3. Create SQLite index at `~/Documents/librarian/index.db`
4. Scan `~/Documents` for markdown files with hashtags

## Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `e` | Edit selected file in configured editor |
| `r` | Manual refresh/rescan all files |
| `Tab` | Cycle focus between panels |
| `Shift+Tab` | Cycle focus backwards |
| `↑/↓` | Navigate lists |
| `Enter` | Select tag or open file |
| `?` | Show help |

## Configuration

Edit `~/Documents/librarian/config.toml`:

```toml
# Directory to scan for markdown files
scan_directory = "~/Documents"

# Editor command for editing files (e.g., "vim", "code", "nano")
editor = "vim"

# Tag filtering
[tags]
mode = "all"  # "all" shows all discovered tags, "whitelist" filters to specific tags
whitelist = ["project", "todo", "notes"]  # Tags listed here appear in FAVORITES panel
```

### Favorites

Tags listed in the `whitelist` array appear in the **FAVORITES** panel at the top of the left sidebar for quick access. All discovered tags still appear in the **ALL TAGS** panel below.

## Tag Format

Librarian recognizes hashtags in the format:
- Must start with `#` followed by a letter
- Can contain letters, numbers, underscores, and hyphens
- Examples: `#project`, `#todo-list`, `#meeting_notes`, `#2024goals`

## Data Storage

All data is stored in `~/Documents/librarian/`:
- `config.toml` - Configuration file
- `index.db` - SQLite database with file/tag index

This location was chosen to enable iCloud sync on macOS.

## How It Works

1. **Scanning**: Recursively finds `*.md` files in the scan directory
2. **Indexing**: Extracts hashtags using regex, stores in SQLite with file modification times
3. **Watching**: Uses `watchdog` to monitor for file changes with debouncing
4. **Display**: Textual TUI with four panels - favorites, all tags, files, and markdown preview

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

## License

MIT
