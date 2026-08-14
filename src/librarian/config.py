"""Configuration loading and defaults for Librarian."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# Every option `save()` writes, as (table, key, default literal, comment).
# `load()` adds any of these a config file is missing, so an option added to
# Librarian shows up in a config written before it existed -- otherwise the only
# way to discover a new setting is to read the source or delete the file.
#
# Order matters: within a table, keys are appended in the order listed here.
_CONFIG_KEYS: tuple[tuple[str | None, str, str, str], ...] = (
    (None, "taskpaper", '""', "TaskPaper TUI executable for .taskpaper files"),
    (
        None,
        "reminders",
        '""',
        'Reminders TUI executable (remtui); empty = look for "remtui" on PATH',
    ),
    (
        None,
        "projects",
        '""',
        'Projects TUI executable (projection); empty = look for "projection" on PATH',
    ),
    (None, "export_directory", None, "Directory for exported files (PDF/HTML)"),
    (None, "data_directory", None, "Directory for index data (index.json)"),
    ("tools", "taskpaper", "false", "file-based tasks, via taskpapertui"),
    ("tools", "reminders", "false", "Apple Reminders, via remtui"),
    ("tools", "calendar", "false", "today's meetings, via icalPal"),
    ("tools", "projects", "false", "Smartsheet projects, via projection"),
    ("calendar", "calendar_name", '""', "empty = all calendars"),
    ("calendar", "command", '""', "empty = auto-detect: calctl, then icalPal"),
    ("icons", "style", '"auto"', "auto | nerd | emoji"),
    ("obsidian", "enabled", "true", "read folder icons from Notebook Navigator"),
)


def _find_table(lines: list[str], table: str) -> tuple[int, int] | None:
    """Locate `[table]` as (header index, index just past its last key).

    Trailing blank and comment lines are excluded: a comment sitting between two
    tables introduces the *next* one, so inserting after it would read as though
    the new key belonged to that table even though TOML still scopes it here.
    """
    header = f"[{table}]"
    for i, line in enumerate(lines):
        if line.strip() != header:
            continue
        end = i + 1
        for j in range(i + 1, len(lines)):
            if lines[j].lstrip().startswith("["):
                break
            if lines[j].strip() and not lines[j].lstrip().startswith("#"):
                end = j + 1
        return i, end
    return None


def _preamble_end(lines: list[str]) -> int:
    """Where top-level keys end: before the first table, past its comments.

    A bare key appended to the end of a TOML file belongs to whatever table
    precedes it, so top-level keys have to go above the first `[table]` header
    -- and above any comment block introducing it.
    """
    first_table = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )
    end = first_table
    while end > 0 and (
        not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")
    ):
        end -= 1
    return end


def _add_missing_keys(text: str, present: dict) -> str | None:
    """Append options the file lacks. None when nothing is missing.

    Existing content is untouched -- values, ordering, and hand-written comments
    all survive, since rewriting the file wholesale would discard them.
    """
    lines = text.splitlines()
    added = False

    for table, key, default, comment in _CONFIG_KEYS:
        if default is None:
            continue  # path defaults depend on the environment; not backfilled
        scope = present.get(table, {}) if table else present
        if not isinstance(scope, dict) or key in scope:
            continue

        entry = [f"{key} = {default}  # {comment}"]

        if table is None:
            at = _preamble_end(lines)
        else:
            found = _find_table(lines, table)
            if found is None:
                if lines and lines[-1].strip():
                    lines.append("")
                lines.append(f"[{table}]")
                at = len(lines)
            else:
                at = found[1]

        lines[at:at] = entry
        added = True

    if not added:
        return None
    return "\n".join(lines) + "\n"


def get_config_dir() -> Path:
    """Get the librarian config directory.

    ``$XDG_CONFIG_HOME`` when set, else ``~/.config`` -- the same resolution
    remtui and taskpapertui use, so all three keep config in one place.
    """
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "librarian"


def get_config_path() -> Path:
    """Get the config file path."""
    return get_config_dir() / "config.toml"


def get_default_data_dir() -> Path:
    """Get the default data directory for index storage."""
    return Path.home() / ".local" / "share" / "librarian"


def _string_map(raw: object) -> dict[str, str]:
    """Coerce a parsed TOML table to a str->str mapping, dropping bad entries."""
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, str) and v.strip()}


def _toml_key(key: str) -> str:
    """Quote a TOML key. Folder keys contain slashes, dots, and spaces."""
    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_table(name: str, values: dict[str, str], comment: str = "") -> list[str]:
    """Render a TOML table, commented out entirely when it has no entries."""
    if not values:
        return [f"# [{name}]", f"# {comment}" if comment else "# (none set)"]

    lines = [f"[{name}]"]
    if comment:
        lines.insert(0, f"# {comment}")
    for key, value in values.items():
        lines.append(f"{_toml_key(key)} = \"{value}\"")
    return lines


@dataclass
class TagConfig:
    """Tag filtering configuration."""

    mode: Literal["all", "whitelist"] = "all"
    whitelist: list[str] = field(default_factory=list)


@dataclass
class ToolsConfig:
    """Which optional tools appear in the Tools menu.

    Every optional tool depends on a third-party program Librarian does not
    bundle -- taskpapertui, remtui, icalPal, projection -- so all are off by
    default and turned on deliberately. Hiding a tool only removes its UI entry points; the
    code stays in place, so `.taskpaper` files keep being indexed, previewed,
    exported, and edited either way.
    """

    taskpaper: bool = False
    reminders: bool = False
    calendar: bool = False
    projects: bool = False

    def is_enabled(self, tool_name: str) -> bool:
        """Whether a tool should be shown.

        Tools with no field here are not optional and are always enabled.
        """
        return bool(getattr(self, tool_name.lower(), True))


@dataclass
class IconConfig:
    """How folder icon names are rendered as terminal glyphs."""

    # "auto" detects whether the terminal can show Nerd Font glyphs; "nerd"
    # forces them (they take on folder colors); "emoji" works anywhere but
    # keeps the emoji's own colors.
    style: Literal["auto", "nerd", "emoji"] = "auto"


@dataclass
class FoldersConfig:
    """Per-folder icons and colors, keyed by path relative to scan_directory."""

    icons: dict[str, str] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)


@dataclass
class ObsidianConfig:
    """Appearance mirroring for Obsidian vaults (Notebook Navigator plugin)."""

    # Set false to ignore the plugin even when the scan directory is in a vault.
    enabled: bool = True


@dataclass
class CalendarConfig:
    """Calendar integration settings. Whether the tool shows is `[tools] calendar`."""

    calendar_name: str = ""  # empty = all calendars
    # Backend command name or path. Empty means auto-detect, which prefers
    # calctl over icalPal. This used to be `icalpal_path`, a key named after one
    # specific third-party tool; that name is still read (see `load`).
    command: str = ""


@dataclass
class Config:
    """Application configuration."""

    scan_directory: Path = field(default_factory=lambda: Path.home() / "Documents")
    editor: str = "vim"
    taskpaper: str = ""
    reminders: str = ""
    projects: str = ""
    tags: TagConfig = field(default_factory=TagConfig)
    export_directory: Path = field(default_factory=lambda: Path.home() / "Downloads")
    data_directory: Path = field(default_factory=get_default_data_dir)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    icons: IconConfig = field(default_factory=IconConfig)
    folders: FoldersConfig = field(default_factory=FoldersConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)

    def get_index_path(self) -> Path:
        """Get the JSON index file path based on configured data directory."""
        return self.data_directory / "index.json"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file or create defaults."""
        config_path = get_config_path()

        # Ensure config directory exists
        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)

        if not config_path.exists():
            # Create default config file
            default_config = cls()
            default_config.data_directory.mkdir(parents=True, exist_ok=True)
            default_config.save()
            return default_config

        # Load existing config
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        # Backfill options added since this file was written. Without this, a
        # config created before a setting existed never gains it, and the only
        # way to find the new switch is to read the source.
        try:
            text = config_path.read_text(encoding="utf-8")
            updated = _add_missing_keys(text, data)
            if updated is not None:
                config_path.write_text(updated, encoding="utf-8")
        except OSError:
            # A read-only config directory must not stop Librarian starting.
            pass

        # Parse scan_directory
        scan_dir = data.get("scan_directory", "~/Documents")
        scan_directory = Path(scan_dir).expanduser()

        # Parse editor
        editor = data.get("editor", "vim")

        # Parse taskpaper editor path
        taskpaper = data.get("taskpaper", "")

        # Parse reminders TUI path (remtui)
        reminders = data.get("reminders", "")

        # Parse projects TUI path (projection)
        projects = data.get("projects", "")

        # Parse tags config
        tags_data = data.get("tags", {})
        tags = TagConfig(
            mode=tags_data.get("mode", "all"),
            whitelist=tags_data.get("whitelist", []),
        )

        # Parse export_directory
        export_dir = data.get("export_directory", "~/Downloads")
        export_directory = Path(export_dir).expanduser()

        # Parse data_directory (where index.json is stored)
        data_dir = data.get("data_directory", str(get_default_data_dir()))
        data_directory = Path(data_dir).expanduser()

        # Parse calendar config. `command` replaced `icalpal_path`, which is
        # still read so older configs keep working. The fallback triggers on an
        # *empty* command, not just a missing one, because migration adds
        # `command = ""` to a file that may already carry a real icalpal_path --
        # and `save()` only writes `command`, so adopting the old value here is
        # what keeps it from being dropped on the next write.
        cal_data = data.get("calendar", {})
        calendar = CalendarConfig(
            calendar_name=cal_data.get("calendar_name", ""),
            command=cal_data.get("command") or cal_data.get("icalpal_path", ""),
        )

        # Parse tools menu config. The calendar switch used to live at
        # [calendar] enabled, which is still honored so older configs keep
        # working.
        tools_data = data.get("tools", {})
        tools = ToolsConfig(
            taskpaper=bool(tools_data.get("taskpaper", False)),
            reminders=bool(tools_data.get("reminders", False)),
            calendar=bool(
                tools_data.get("calendar", cal_data.get("enabled", False))
            ),
            projects=bool(tools_data.get("projects", False)),
        )

        # Parse icon rendering config
        icons_data = data.get("icons", {})
        icons = IconConfig(style=icons_data.get("style", "auto"))

        # Parse per-folder icons/colors
        folders_data = data.get("folders", {})
        folders = FoldersConfig(
            icons=_string_map(folders_data.get("icons")),
            colors=_string_map(folders_data.get("colors")),
        )

        # Parse obsidian integration config
        obsidian_data = data.get("obsidian", {})
        obsidian = ObsidianConfig(
            enabled=bool(obsidian_data.get("enabled", True)),
        )

        config = cls(
            scan_directory=scan_directory,
            editor=editor,
            taskpaper=taskpaper,
            reminders=reminders,
            projects=projects,
            tags=tags,
            export_directory=export_directory,
            data_directory=data_directory,
            calendar=calendar,
            tools=tools,
            icons=icons,
            folders=folders,
            obsidian=obsidian,
        )

        # Ensure data directory exists
        config.data_directory.mkdir(parents=True, exist_ok=True)

        return config

    def save(self) -> None:
        """Save configuration to file."""
        config_path = get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Build TOML content manually (tomllib is read-only)
        lines = [
            '# Librarian Configuration',
            '',
            '# Directory to scan for markdown files',
            f'scan_directory = "{self.scan_directory}"',
            '',
            '# Editor command for editing files',
            f'editor = "{self.editor}"',
            '',
            '# TaskPaper TUI executable for editing .taskpaper files',
            '# e.g. taskpaper = "taskpapertui"',
            f'taskpaper = "{self.taskpaper}"',
            '',
            '# Reminders TUI executable (remtui); empty = look for "remtui" on PATH',
            f'reminders = "{self.reminders}"',
            '',
            '# Projects TUI executable (projection); empty = look for "projection" on PATH',
            f'projects = "{self.projects}"',
            '',
            '# Directory for exported files (PDF/HTML)',
            f'export_directory = "{self.export_directory}"',
            '',
            '# Directory for index data (index.json)',
            f'# Default: ~/.local/share/librarian',
            f'data_directory = "{self.data_directory}"',
            '',
            '# Tag filtering: "all" or "whitelist"',
            '[tags]',
            f'mode = "{self.tags.mode}"  # or "whitelist"',
        ]

        if self.tags.whitelist:
            whitelist_str = ", ".join(f'"{t}"' for t in self.tags.whitelist)
            lines.append(f'whitelist = [{whitelist_str}]  # only used if mode = "whitelist"')
        else:
            lines.append('whitelist = []  # only used if mode = "whitelist"')

        lines.extend([
            '',
            '# Optional tools shown in the Tools menu. Each needs a third-party',
            '# program (taskpapertui, remtui, icalPal, projection), so all are opt-in.',
            '# Hiding one only hides its UI: .taskpaper files stay indexed.',
            '[tools]',
            f'taskpaper = {str(self.tools.taskpaper).lower()}',
            f'reminders = {str(self.tools.reminders).lower()}',
            f'calendar = {str(self.tools.calendar).lower()}',
            f'projects = {str(self.tools.projects).lower()}',
            '',
            '# Folder icon glyphs: "auto" detects Nerd Font support, or force',
            '# "nerd" (tinted with the folder color) or "emoji" (works anywhere)',
            '[icons]',
            f'style = "{self.icons.style}"',
            '',
            '# Per-folder icons and colors, keyed by path relative to',
            '# scan_directory. Icon names are Lucide names, e.g. "book-open".',
        ])

        lines.extend(
            _toml_table(
                "folders.icons",
                self.folders.icons,
                comment='e.g. "projects" = "briefcase"',
            )
        )
        lines.append('')
        lines.extend(
            _toml_table(
                "folders.colors",
                self.folders.colors,
                comment='e.g. "projects" = "#8b5cf6"',
            )
        )

        lines.extend([
            '',
            '# Mirror folder icons/colors from Obsidian\'s Notebook Navigator',
            '# plugin when the scan directory is inside a vault',
            '[obsidian]',
            f'enabled = {str(self.obsidian.enabled).lower()}',
            '',
            '# Calendar settings (the tool itself is enabled under [tools])',
            '[calendar]',
            f'calendar_name = "{self.calendar.calendar_name}"  # empty = all calendars',
            f'command = "{self.calendar.command}"  '
            '# empty = auto-detect: calctl, then icalPal',
        ])

        config_path.write_text("\n".join(lines) + "\n")
