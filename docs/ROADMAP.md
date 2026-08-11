# Roadmap

Planned and deferred work for Librarian. Single source of truth — keep roadmap content here
rather than scattering it across READMEs or issue comments.

## Planned

### Work without Notebook Navigator
Librarian must stay first-class for users who don't run Obsidian, don't use the Notebook Navigator
plugin, or whose terminal has no Nerd Font. The mirroring code already degrades to the stock
Textual tree when a vault or plugin is absent, so this is mostly about proving and widening that
path rather than building it: a plain (non-vault) scan directory, a vault without the plugin,
an unreadable or partial `data.json`, and `icon_style = "emoji"` for terminals lacking a Nerd
Font. Consider detecting Nerd Font availability instead of defaulting to `nerd` blind.

### Replace TaskPaper with a remtui re-implementation
Swap the TaskPaper tool for an Apple Reminders tool, re-implementing
[remtui](https://github.com/7robots/remtui) (Textual TUI over the `remctl` CLI) inside Librarian
rather than shelling out to an external editor the way TaskPaper does. Touches the Tools menu,
the `t` binding, `n` (new-file behavior per active tool), the `taskpaper` config key, and the
`.taskpaper` handling in the scanner and file list.

Worth splitting into two decisions before writing code: *adding* a Reminders tool, versus
*removing* TaskPaper support. TaskPaper currently runs through 9 modules, including
`taskpaper.py` (taskpaper→markdown for preview and export) and `.taskpaper` handling in the
scanner, watcher, database, preview, and export. Reminders live in Apple Reminders via `remctl`
rather than in files, so the new tool cannot reuse the index, file list, or preview the way
TaskPaper does.

## Deferred

### Tag colors from Notebook Navigator
`obsidian.py` already loads the plugin's `tagColors` map but nothing consumes it. Low value while
the vault has only a couple of tags; revisit if tag use grows.
