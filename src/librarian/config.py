"""Configuration loading and defaults for Librarian."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def get_config_dir() -> Path:
    """Get the librarian config directory (XDG-style)."""
    return Path.home() / ".config" / "librarian"


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
    """Calendar integration configuration."""

    enabled: bool = True
    calendar_name: str = ""  # empty = all calendars
    icalpal_path: str = ""   # empty = auto-detect


@dataclass
class Config:
    """Application configuration."""

    scan_directory: Path = field(default_factory=lambda: Path.home() / "Documents")
    editor: str = "vim"
    taskpaper: str = ""
    tags: TagConfig = field(default_factory=TagConfig)
    export_directory: Path = field(default_factory=lambda: Path.home() / "Downloads")
    data_directory: Path = field(default_factory=get_default_data_dir)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
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

        # Parse scan_directory
        scan_dir = data.get("scan_directory", "~/Documents")
        scan_directory = Path(scan_dir).expanduser()

        # Parse editor
        editor = data.get("editor", "vim")

        # Parse taskpaper editor path
        taskpaper = data.get("taskpaper", "")

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

        # Parse calendar config
        cal_data = data.get("calendar", {})
        calendar = CalendarConfig(
            enabled=cal_data.get("enabled", True),
            calendar_name=cal_data.get("calendar_name", ""),
            icalpal_path=cal_data.get("icalpal_path", ""),
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
            tags=tags,
            export_directory=export_directory,
            data_directory=data_directory,
            calendar=calendar,
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
            '# Calendar integration (requires icalPal)',
            '[calendar]',
            f'enabled = {str(self.calendar.enabled).lower()}',
            f'calendar_name = "{self.calendar.calendar_name}"  # empty = all calendars',
            f'icalpal_path = "{self.calendar.icalpal_path}"  # empty = auto-detect',
        ])

        config_path.write_text("\n".join(lines) + "\n")
