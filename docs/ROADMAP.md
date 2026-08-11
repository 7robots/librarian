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

### Change the opening tool
Tags currently opens by default, which reflects Librarian's original tag-centric design. With
content organized by folder, the default should lead with folders instead. Set in
`TagList.active_tool` / the initial `_switch_panel()` call.

### Swap the Tools and Folders panels
The left sidebar currently stacks Tools on top and the content panel (Tags/Folders/Calendar)
below, split 50/50. Swap them so the content panel is on top and Tools below.

### Rework the file browser in folder view
When the Folders tool is active, the Files panel should reflect the selected *folder* rather than
the selected tag — i.e. list that folder's files, updating as the tree cursor moves, instead of
staying bound to tag selection. Today folder-tree selection only fires `FileSelected` for
individual files and leaves the Files panel showing the last tag's results.

### Remove the Agents tool
Drop the "Agents" entry from the Tools menu and its placeholder panel.

### Replace TaskPaper with a remtui re-implementation
Swap the TaskPaper tool for an Apple Reminders tool, re-implementing
[remtui](https://github.com/7robots/remtui) (Textual TUI over the `remctl` CLI) inside Librarian
rather than shelling out to an external editor the way TaskPaper does. Touches the Tools menu,
the `t` binding, `n` (new-file behavior per active tool), the `taskpaper` config key, and the
`.taskpaper` handling in the scanner and file list.

## Deferred

### Tag colors from Notebook Navigator
`obsidian.py` already loads the plugin's `tagColors` map but nothing consumes it. Low value while
the vault has only a couple of tags; revisit if tag use grows.
