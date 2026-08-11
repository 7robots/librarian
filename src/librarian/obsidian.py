"""Read folder appearance from an Obsidian vault's Notebook Navigator plugin.

Notebook Navigator stores per-folder icons and colors in its plugin data file at
``<vault>/.obsidian/plugins/notebook-navigator/data.json``. Librarian mirrors
those so the Folders panel matches the vault's appearance in Obsidian.

This module is one appearance source among several -- see ``appearance.py`` for
how sources are layered, and ``icons.py`` for how icon names become glyphs. It
is entirely optional: Librarian works the same without Obsidian, without the
plugin, or with the plugin's data unreadable.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .appearance import lookup_with_inheritance, relative_key

logger = logging.getLogger(__name__)

PLUGIN_DATA_RELATIVE_PATH = Path(".obsidian/plugins/notebook-navigator/data.json")

VAULT_MARKER_DIRECTORY = ".obsidian"


def find_vault_root(start: Path) -> Path | None:
    """Find the Obsidian vault root at or above ``start``.

    A vault root is a directory containing a ``.obsidian`` directory. Walks
    upward so a scan directory pointed at a subfolder of a vault still resolves.
    Returns None when no vault is found.
    """
    try:
        current = start.expanduser().resolve()
    except OSError:
        return None

    for candidate in (current, *current.parents):
        if (candidate / VAULT_MARKER_DIRECTORY).is_dir():
            return candidate

    return None


@dataclass
class NotebookNavigatorAppearance:
    """Folder appearance mirrored from Notebook Navigator's plugin data.

    Returns icon *names* (Lucide names, or ``emoji:`` literals) rather than
    glyphs; turning those into glyphs is ``icons.py``'s job.
    """

    vault_root: Path
    folder_icons: dict[str, str] = field(default_factory=dict)
    folder_colors: dict[str, str] = field(default_factory=dict)
    tag_colors: dict[str, str] = field(default_factory=dict)
    inherit_folder_colors: bool = True
    show_folder_icons: bool = True
    color_icon_only: bool = False

    def icon_name_for(self, path: Path) -> str | None:
        """Get the configured icon name for a folder, or None."""
        if not self.show_folder_icons:
            # The plugin is set to hide folder icons; respect that rather than
            # supplying icons Obsidian itself would not show.
            return None
        key = relative_key(path, self.vault_root)
        if key is None:
            return None
        return self.folder_icons.get(key) or None

    def color_for(self, path: Path) -> str | None:
        """Get the color for a folder, inheriting from ancestors if enabled."""
        key = relative_key(path, self.vault_root)
        if key is None:
            return None
        return lookup_with_inheritance(
            self.folder_colors, key, inherit=self.inherit_folder_colors
        )

    @classmethod
    def load(cls, scan_directory: Path) -> "NotebookNavigatorAppearance | None":
        """Load plugin data for the vault containing ``scan_directory``.

        Returns None when the directory is not in an Obsidian vault, the plugin
        is not installed, or its data file cannot be read.
        """
        vault_root = find_vault_root(scan_directory)
        if vault_root is None:
            logger.debug("Not an Obsidian vault: %s", scan_directory)
            return None

        data_path = vault_root / PLUGIN_DATA_RELATIVE_PATH
        if not data_path.is_file():
            logger.debug("Notebook Navigator data not found: %s", data_path)
            return None

        try:
            with open(data_path, "rb") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read Notebook Navigator data: %s", exc)
            return None

        if not isinstance(data, dict):
            logger.warning("Unexpected Notebook Navigator data shape: %s", data_path)
            return None

        def string_map(key: str) -> dict[str, str]:
            raw = data.get(key)
            if not isinstance(raw, dict):
                return {}
            return {
                str(k): v for k, v in raw.items() if isinstance(v, str) and v.strip()
            }

        appearance = cls(
            vault_root=vault_root,
            folder_icons=string_map("folderIcons"),
            folder_colors=string_map("folderColors"),
            tag_colors=string_map("tagColors"),
            inherit_folder_colors=bool(data.get("inheritFolderColors", True)),
            show_folder_icons=bool(data.get("showFolderIcons", True)),
            color_icon_only=bool(data.get("colorIconOnly", False)),
        )
        logger.info(
            "Loaded Notebook Navigator appearance from %s (%d icons, %d colors)",
            data_path,
            len(appearance.folder_icons),
            len(appearance.folder_colors),
        )
        return appearance
