# Librarian

**Terminal Notes & Tasks.** Librarian browses a folder of markdown notes from the terminal — folder
tree, file list, live preview — with optional tools for Apple Reminders, today's meetings, and
Smartsheet projects. It reads an existing directory of files and never takes ownership of them, so
it sits happily on top of an Obsidian vault or any plain folder of markdown.

```
 ●    L I B R A R I A N
╢● ●╟  Terminal Notes & Tasks  │  github.com/7robots/librarian
┌───────────────┬─────────────────────────────────────────────┐
│ FOLDERS       │ FILES (techne/)                             │
│               │                                             │
│ ▾ vault       │ > Claude Notes.md                           │
│   anthologia  │   CLI Dev Environment Setup.md              │
│   kybernetes  │   Terminal Tools.md                         │
│   techne      │                                             │
├───────────────┼─────────────────────────────────────────────┤
│ ALL TAGS      │ PREVIEW - Claude Notes.md                   │
│ #arete (66)   │                                             │
│ #meetings (9) │ # Claude Notes                              │
├───────────────┤                                             │
│ ★ TOOLS       │ Working notes on the CLI. #arete            │
│ Reminders     │                                             │
│ Calendar      │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

## Features

- **Folder-first browsing** — the folder tree leads, and the file list follows the cursor
- **Live preview** — markdown (and taskpaper) rendered as you move
- **Folders and tags side by side** — the tree for browsing, the tag list as shortcuts to the notes
  you keep coming back to; the file list follows whichever you touched last
- **Tags** — inline `#hashtags` indexed across the vault
- **Search** — files and tags by partial match
- **Wiki links** — click `[[note.md]]` in the preview to navigate, `Escape` to come back
- **File management** — create, rename, move, delete, and export to HTML
- **Auto-refresh** — a file watcher keeps the index current
- **Folder icons and colors** — per-folder, from your config or mirrored from Obsidian
- **Optional tools** — Apple Reminders, today's meetings, Smartsheet projects, and TaskPaper,
  each opt-in

## Installation

Requires Python 3.10+ and [uv](https://github.com/astral-sh/uv).
Textual 8.2.8 or newer is installed for you from the committed lockfile.

```bash
git clone https://github.com/7robots/librarian.git
cd librarian
./install.sh
librarian
```

`install.sh` syncs the environment and puts a `librarian` launcher in `~/bin` (`--dir DIR` to choose
elsewhere, `--uninstall` to remove it). The launcher runs this checkout, so `git pull && ./install.sh`
is also the update path. The same script with the same defaults ships in
[remtui](https://github.com/7robots/remtui) and
[TaskPaperTUI](https://github.com/7robots/TaskPaperTUI).

To run from the checkout without installing: `uv sync --extra reminders && uv run librarian`.

On first run Librarian writes `~/.config/librarian/config.toml` (honoring `XDG_CONFIG_HOME`), creates
its index under `~/.local/share/librarian/`, and scans `~/Documents` for markdown and taskpaper
files. Point `scan_directory` at your notes and restart.

Out of the box you get Folders and Tags. Everything that needs another program installed is off
until you turn it on — see below.

## Third-party integrations

Librarian bundles none of these. Each is optional, each stays out of the UI until enabled, and
nothing breaks if you never install any of them.

| Integration | Needs | Gives you |
|---|---|---|
| [Nerd Font](https://www.nerdfonts.com/) | a Nerd Font in your terminal | Monochrome folder icons that take on folder colors |
| [Obsidian Notebook Navigator](https://github.com/johansan/notebook-navigator) | the plugin, in a vault | Folder icons and colors mirrored from Obsidian |
| [icalPal](https://github.com/ajrosen/icalPal) | `brew tap ajrosen/tap && brew install icalPal` | Today's meetings, linkable to notes |
| [remtui](https://github.com/7robots/remtui) | remtui + [remctl](https://github.com/viticci/remctl) | Apple Reminders, in a full-screen handoff |
| [projection](https://github.com/7robots/projection) | projection (private repo) + a Smartsheet token | Smartsheet projects, in a panel |
| A TaskPaper TUI | any `.taskpaper` editor on your PATH | A `.taskpaper` view, and `e` opening it in that editor |

### Why they are opt-in

A menu entry for a tool whose program is missing is worse than no entry: you select it, nothing
useful happens, and you cannot tell whether the tool or your setup is broken. So every tool
that leans on another program is off by default, and turning one on is a statement that you
have it installed.

```toml
[tools]
taskpaper = false   # file-based tasks, via taskpapertui
reminders = false   # Apple Reminders, via remtui
calendar = false    # today's meetings, via icalPal
projects = false    # Smartsheet projects, via projection
```

Disabling a tool hides **all** of its entry points — the menu row, its keybinding, and its line in
the help text. It does not remove functionality that stands on its own: `.taskpaper` files are still
indexed, previewed, exported, and editable whatever `[tools] taskpaper` says.

### Folder icons (Nerd Font)

Folders can carry an icon and a color. Icons are named with
[Lucide](https://lucide.dev/icons/) names and rendered either as Nerd Font glyphs or as emoji:

```toml
[icons]
style = "auto"   # auto | nerd | emoji

[folders.icons]
"projects" = "briefcase"
"projects/2026" = "calendar"

[folders.colors]
"projects" = "#8b5cf6"   # colors inherit to subfolders
```

`auto` looks for a terminal that ships Nerd Font symbols (Ghostty and WezTerm embed them) or a Nerd
Font installed in your font directories, and falls back to emoji. Set `nerd` or `emoji` explicitly if
the guess is wrong. Nerd Font glyphs are monochrome, so they take on the folder's color; emoji keep
their own colors.

### Obsidian (Notebook Navigator)

If `scan_directory` is inside an Obsidian vault using the
[Notebook Navigator](https://github.com/johansan/notebook-navigator) plugin, Librarian reads that
plugin's per-folder icons and colors so the two apps look alike. Nothing is copied into Librarian's
config — change an icon in Obsidian and it shows up here on the next launch.

Your own config wins where the two disagree, per folder and per property, so you can override one
folder's color while leaving its icon to the plugin. To ignore the plugin entirely:

```toml
[obsidian]
enabled = false
```

### Calendar (icalPal)

```toml
[tools]
calendar = true

[calendar]
calendar_name = ""     # empty = all calendars
icalpal_path = ""      # empty = find icalPal on PATH
```

Select **Calendar** and today's meetings open as a panel over the Files and Preview panels, with your
folder tree and tag list still visible; `q` closes it. Navigate the meetings to preview a linked note
or the meeting's own details; press `a` to link a meeting to an existing `#meetings` file, or `n` to
create a meeting note from a template. When icalPal cannot run, the panel says why — it will not
quietly show you an empty day.

### Reminders (remtui)

```toml
[tools]
reminders = true

reminders = ""   # or a path; empty finds "remtui" on PATH
```

Select **Reminders** and the reminders list opens as a panel over the Files and Preview panels, with
your folder tree and tag list still visible; `q` closes it. `./install.sh` installs remtui for you,
so there is nothing extra to do; running from a checkout instead needs the extra by hand:

```bash
uv sync --extra reminders
```

Without the package, Librarian falls back to suspending and running the `remtui` executable,
returning to your panels when you quit. (remtui needs Python 3.12+, so on 3.10 or 3.11 only the
fallback is available — the extra resolves to nothing there rather than failing.)

Either way, reminders live in Apple Reminders rather than in files, so nothing here touches your
notes or the index.

### TaskPaper

```toml
[tools]
taskpaper = true

taskpaper = "taskpapertui"   # empty = use `editor` instead
```

Adds a TaskPaper tool that filters to the `#taskpaper` tag and creates `.taskpaper` files, and makes
`e` open them in your taskpaper editor rather than `editor`.

### Projects (projection)

```toml
[tools]
projects = true

projects = ""   # or a path; empty finds "projection" on PATH
```

Select **Projects** and [projection](https://github.com/7robots/projection) opens as a panel over the
Files and Preview panels, the same way Reminders does; `q` closes it.

Unlike remtui, projection is **not** declared as an optional dependency — its repository is private,
so `uv sync --extra ...` would fail for anyone without access. Install it by hand instead:

```bash
uv pip install -e /path/to/projection
```

That install now survives `./install.sh`, which syncs with `--inexact` so it does not delete packages
it did not put there. A bare `uv sync` **is** exact and still removes it, so prefer `./install.sh` (or
`uv sync --inexact`) when updating. Without the package, Librarian falls back to suspending and
running the `projection` executable.

Projects live in Smartsheet rather than in files, so nothing here touches your notes or the index.

## Keybindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `s` | Search files and tags |
| `e` | Edit selected file |
| `n` | Create a new file (kind depends on the active tool) |
| `d` | Delete selected file (twice to confirm) |
| `r` | Rename selected file |
| `m` | Move selected file |
| `x` | Export selected file to HTML |
| `u` | Rescan files |
| `t` | TaskPaper tool (when enabled) |
| `a` | Link a meeting to a note (Calendar tool) |
| `Tab` / `Shift+Tab` | Cycle panels forward / backward |
| `↑/↓` | Navigate lists, scroll the preview |
| `Enter` | Select |
| `Escape` | Back from a wiki link, or out of search |
| `?` | Show help |

Tab goes down the left column and then down the right: folders → tags → tools → files → preview. With
no tools enabled the Tools panel is empty, so Tab skips it.

## Tags

A tag is `#` followed by a letter, then letters, numbers, underscores, or hyphens — and the `#` must
start a line or follow whitespace:

```markdown
#project #meeting-notes #2026goals   ← tags
[LMA](./LMA.md#lma)                  ← not a tag: an anchor
https://example.com/page#section     ← not a tag: a URL fragment
# Heading                            ← not a tag: a heading
`#example`                           ← not a tag: inline code
```

Those rules match Obsidian's, so the tag list agrees with Obsidian's rather than filling up with
every link anchor in the vault. Tags inside fenced code blocks are ignored for the same reason.

Only files with at least one tag are indexed. The folder view reads the filesystem instead, so
untagged notes are still browsable.

```toml
[tags]
mode = "all"                   # or "whitelist"
whitelist = ["project", "todo"]  # used when mode = "whitelist"
```

## Wiki links

`[[note.md]]` links to a file by name, and `[[note|Display text]]` sets the link text. Click one in
the preview to follow it, `Escape` to return to where you were.

## Data storage

| Path | Contents |
|---|---|
| `~/.config/librarian/config.toml` | Configuration |
| `~/.local/share/librarian/index.json` | Tag index (file path → mtime + tags) |
| `~/.local/share/librarian/calendar_associations.json` | Meeting → note links |

Both data files are caches you can delete; `u` rebuilds the index. Writes are atomic, which matters
when the vault is in iCloud Drive. The index records the scanner version that wrote it, so a change
to the tag rules re-reads your files rather than trusting entries whose mtimes never changed.

## Development

```bash
uv run librarian          # run
uv run pytest             # tests
```

See [CLAUDE.md](CLAUDE.md) for architecture and design notes, and
[docs/ROADMAP.md](docs/ROADMAP.md) for planned work.

## Dependencies

- [textual](https://github.com/Textualize/textual) — TUI framework
- [watchdog](https://github.com/gorakhargosh/watchdog) — file watching
- [markdown](https://python-markdown.github.io/) — HTML export

## License

MIT
