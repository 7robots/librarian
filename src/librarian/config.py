"""Configuration loading and defaults for Librarian."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


def get_data_dir() -> Path:
    """Get the librarian data directory."""
    return Path.home() / "Documents" / "librarian"


def get_config_path() -> Path:
    """Get the config file path."""
    return get_data_dir() / "config.toml"


def get_database_path() -> Path:
    """Get the database file path."""
    return get_data_dir() / "index.db"


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

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file or create defaults."""
        config_path = get_config_path()

        # Ensure data directory exists
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        if not config_path.exists():
            # Create default config file
            default_config = cls()
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

        return cls(
            scan_directory=scan_directory,
            editor=editor,
            tags=tags,
        )

    def save(self) -> None:
        """Save configuration to file."""
        config_path = get_config_path()

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
