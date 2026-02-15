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


@dataclass
class TagConfig:
    """Tag filtering configuration."""

    mode: Literal["all", "whitelist"] = "all"
    whitelist: list[str] = field(default_factory=list)


@dataclass
class Config:
    """Application configuration."""

    scan_directory: Path = field(default_factory=lambda: Path.home() / "Documents")
    editor: str = "vim"
    tags: TagConfig = field(default_factory=TagConfig)
    export_directory: Path = field(default_factory=lambda: Path.home() / "Downloads")
    data_directory: Path = field(default_factory=get_default_data_dir)

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

        config = cls(
            scan_directory=scan_directory,
            editor=editor,
            tags=tags,
            export_directory=export_directory,
            data_directory=data_directory,
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

        config_path.write_text("\n".join(lines) + "\n")
