"""Read appearance settings from an Obsidian vault's Notebook Navigator plugin.

Notebook Navigator stores per-folder icons and colors in its plugin data file at
``<vault>/.obsidian/plugins/notebook-navigator/data.json``. Librarian mirrors
those so the Folders panel matches the vault's appearance in Obsidian.

Icons are Lucide icon names (``"library"``) or literal emoji prefixed with
``emoji:`` (``"emoji:\U0001f916"``). Lucide itself has no terminal-renderable
form -- Obsidian draws it as inline SVG -- so names are mapped to glyphs in one
of two styles:

``nerd``
    Material Design Icons from Nerd Fonts. Monochrome, so they take on the
    folder's color, and closest in spirit to the Lucide originals. Requires a
    Nerd Font; Ghostty embeds one, so no install is needed there.
``emoji``
    Plain emoji, for terminals without a Nerd Font. Emoji carry their own
    colors and ignore the folder color.

Literal ``emoji:`` icons are passed through unchanged in both styles, since
that is what Obsidian shows for them.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rich.cells import cell_len

logger = logging.getLogger(__name__)

IconStyle = Literal["nerd", "emoji"]

ICON_STYLES: tuple[IconStyle, ...] = ("nerd", "emoji")
DEFAULT_ICON_STYLE: IconStyle = "nerd"

PLUGIN_DATA_RELATIVE_PATH = Path(".obsidian/plugins/notebook-navigator/data.json")

# Width in cells an icon glyph is padded to, so folder names line up regardless
# of whether the glyph is single- or double-width. One separating space is added
# on top of this, making every rendered icon ICON_CELL_WIDTH + 1 cells wide.
ICON_CELL_WIDTH = 2

# Lucide icon name -> Nerd Font glyph, using the Material Design Icons set.
# Codepoints were resolved from the Nerd Fonts glyphnames.json (v3.5.0); the
# trailing comment records the source glyph name so they can be re-checked.
# All are in the long-standing Material Design range, so they are present in
# older Nerd Fonts releases too (Ghostty embeds 3.4.0).
NERD_GLYPHS: dict[str, str] = {
    "album": "\U000f0025",  # md-album
    "archive": "\U000f003c",  # md-archive
    "atom": "\U000f0768",  # md-atom
    "banknote": "\U000f0114",  # md-cash
    "book": "\U000f00ba",  # md-book
    "book-open": "\U000f00bd",  # md-book_open
    "bookmark": "\U000f00c0",  # md-bookmark
    "bot": "\U000f06a9",  # md-robot
    "brain": "\U000f09d1",  # md-brain
    "briefcase": "\U000f00d6",  # md-briefcase
    "bug": "\U000f00e4",  # md-bug
    "calendar": "\U000f00ed",  # md-calendar
    "camera": "\U000f0100",  # md-camera
    "check-circle": "\U000f05e0",  # md-check_circle
    "clipboard-list": "\U000f10d4",  # md-clipboard_list
    "clock": "\U000f0954",  # md-clock
    "cloud": "\U000f015f",  # md-cloud
    "code": "\U000f0174",  # md-code_tags
    "compass": "\U000f018b",  # md-compass
    "computer": "\U000f0322",  # md-laptop
    "database": "\U000f01bc",  # md-database
    "file-text": "\U000f0219",  # md-file_document
    "film": "\U000f022f",  # md-film
    "flask-conical": "\U000f0093",  # md-flask
    "folder": "\U000f024b",  # md-folder
    "gamepad-2": "\U000f0296",  # md-gamepad
    "globe": "\U000f01e7",  # md-earth
    "graduation-cap": "\U000f0474",  # md-school
    "heart": "\U000f02d1",  # md-heart
    "home": "\U000f02dc",  # md-home
    "image": "\U000f02e9",  # md-image
    "inbox": "\U000f0687",  # md-inbox
    "landmark": "\U000f0070",  # md-bank
    "leaf": "\U000f032a",  # md-leaf
    "library": "\U000f0331",  # md-library
    "lightbulb": "\U000f0335",  # md-lightbulb
    "link": "\U000f0337",  # md-link
    "lock": "\U000f033e",  # md-lock
    "map": "\U000f034d",  # md-map
    "message-square": "\U000f0361",  # md-message
    "music": "\U000f075a",  # md-music
    "notebook": "\U000f082e",  # md-notebook
    "package": "\U000f03d6",  # md-package_variant
    "palette": "\U000f03d8",  # md-palette
    "pen-tool": "\U000f03ea",  # md-pen
    "pencil": "\U000f03eb",  # md-pencil
    "phone": "\U000f03f2",  # md-phone
    "pin": "\U000f0403",  # md-pin
    "rocket": "\U000f0463",  # md-rocket
    "school": "\U000f0474",  # md-school
    "search": "\U000f0349",  # md-magnify
    "settings": "\U000f0493",  # md-cog
    "shield": "\U000f0498",  # md-shield
    "sparkles": "\U000f1545",  # md-shimmer
    "star": "\U000f04ce",  # md-star
    "sun": "\U000f05a8",  # md-white_balance_sunny
    "tag": "\U000f04f9",  # md-tag
    "target": "\U000f04fe",  # md-target
    "terminal": "\U000f018d",  # md-console
    "trees": "\U000f0405",  # md-pine_tree
    "triangle-right": "\U000f145d",  # md-set_square
    "trophy": "\U000f0538",  # md-trophy
    "users": "\U000f0849",  # md-account_group
    "wallet": "\U000f0584",  # md-wallet
    "wrench": "\U000f05b7",  # md-wrench
    "zap": "\U000f0241",  # md-flash
}

# Lucide icon name -> emoji, for terminals without a Nerd Font.
EMOJI_GLYPHS: dict[str, str] = {
    "album": "\U0001f4bd",  # 💽
    "archive": "\U0001f5c4",  # 🗄
    "atom": "⚛",  # ⚛
    "banknote": "\U0001f4b5",  # 💵
    "book": "\U0001f4d5",  # 📕
    "book-open": "\U0001f4d6",  # 📖
    "bookmark": "\U0001f516",  # 🔖
    "bot": "\U0001f916",  # 🤖
    "briefcase": "\U0001f4bc",  # 💼
    "brain": "\U0001f9e0",  # 🧠
    "bug": "\U0001f41b",  # 🐛
    "calendar": "\U0001f4c5",  # 📅
    "camera": "\U0001f4f7",  # 📷
    "check-circle": "✅",  # ✅
    "clipboard-list": "\U0001f4cb",  # 📋
    "clock": "\U0001f552",  # 🕒
    "cloud": "☁",  # ☁
    "code": "⌨",  # ⌨
    "compass": "\U0001f9ed",  # 🧭
    "computer": "\U0001f4bb",  # 💻
    "database": "\U0001f5c3",  # 🗃
    "file-text": "\U0001f4c4",  # 📄
    "film": "\U0001f3ac",  # 🎬
    "flask-conical": "\U0001f9ea",  # 🧪
    "folder": "\U0001f4c1",  # 📁
    "gamepad-2": "\U0001f3ae",  # 🎮
    "globe": "\U0001f30d",  # 🌍
    "graduation-cap": "\U0001f393",  # 🎓
    "heart": "❤",  # ❤
    "home": "\U0001f3e0",  # 🏠
    "image": "\U0001f5bc",  # 🖼
    "inbox": "\U0001f4e5",  # 📥
    "landmark": "\U0001f3db",  # 🏛
    "leaf": "\U0001f342",  # 🍂
    "library": "\U0001f4da",  # 📚
    "lightbulb": "\U0001f4a1",  # 💡
    "link": "\U0001f517",  # 🔗
    "lock": "\U0001f512",  # 🔒
    "map": "\U0001f5fa",  # 🗺
    "message-square": "\U0001f4ac",  # 💬
    "music": "\U0001f3b5",  # 🎵
    "notebook": "\U0001f4d3",  # 📓
    "package": "\U0001f4e6",  # 📦
    "palette": "\U0001f3a8",  # 🎨
    "pen-tool": "✒",  # ✒
    "pencil": "✏",  # ✏
    "phone": "\U0001f4de",  # 📞
    "pin": "\U0001f4cc",  # 📌
    "rocket": "\U0001f680",  # 🚀
    "school": "\U0001f393",  # 🎓
    "search": "\U0001f50d",  # 🔍
    "settings": "⚙",  # ⚙
    "shield": "\U0001f6e1",  # 🛡
    "sparkles": "✨",  # ✨
    "star": "⭐",  # ⭐
    "sun": "☀",  # ☀
    "tag": "\U0001f3f7",  # 🏷
    "target": "\U0001f3af",  # 🎯
    "terminal": "▸",  # ▸
    "trees": "\U0001f332",  # 🌲
    "triangle-right": "▶",  # ▶
    "trophy": "\U0001f3c6",  # 🏆
    "users": "\U0001f465",  # 👥
    "wallet": "\U0001f45c",  # 👛
    "wrench": "\U0001f527",  # 🔧
    "zap": "⚡",  # ⚡
}

GLYPH_TABLES: dict[str, dict[str, str]] = {
    "nerd": NERD_GLYPHS,
    "emoji": EMOJI_GLYPHS,
}

# Glyph used when a folder's icon name is not in the table for its style.
FALLBACK_GLYPHS: dict[str, str] = {
    "nerd": "\U000f024b",  # md-folder
    "emoji": "\U0001f4c1",  # 📁
}

# Glyphs for folders with no icon configured in Notebook Navigator. These keep
# the tree's collapsed/expanded distinction that a custom icon cannot show.
CLOSED_FOLDER_GLYPHS: dict[str, str] = {
    "nerd": "\U000f024b",  # md-folder
    "emoji": "\U0001f4c1",  # 📁
}
OPEN_FOLDER_GLYPHS: dict[str, str] = {
    "nerd": "\U000f0770",  # md-folder_open
    "emoji": "\U0001f4c2",  # 📂
}


def normalize_style(style: str | None) -> IconStyle:
    """Coerce a configured style name to a supported one."""
    if style in ICON_STYLES:
        return style  # type: ignore[return-value]
    if style:
        logger.warning(
            "Unknown icon_style %r, falling back to %r", style, DEFAULT_ICON_STYLE
        )
    return DEFAULT_ICON_STYLE


def folder_glyph(expanded: bool, style: IconStyle = DEFAULT_ICON_STYLE) -> str:
    """Get the padded glyph for a folder with no icon configured."""
    table = OPEN_FOLDER_GLYPHS if expanded else CLOSED_FOLDER_GLYPHS
    return pad_glyph(table[normalize_style(style)])


def pad_glyph(glyph: str) -> str:
    """Pad a glyph to a fixed cell width plus one separating space."""
    if not glyph:
        return ""
    padding = max(0, ICON_CELL_WIDTH - cell_len(glyph))
    return glyph + " " * padding + " "


def resolve_icon(icon_name: str, style: IconStyle = DEFAULT_ICON_STYLE) -> str:
    """Convert a Notebook Navigator icon name to a padded terminal glyph.

    Returns an empty string when ``icon_name`` is empty. Glyphs are padded to
    ``ICON_CELL_WIDTH`` cells plus a separating space, so folder names align in
    a column whatever the glyph's width -- necessary because a single tree can
    mix one-cell Nerd Font glyphs with two-cell emoji.
    """
    if not icon_name:
        return ""

    style = normalize_style(style)

    if icon_name.startswith("emoji:"):
        # An emoji chosen in Obsidian stays an emoji, whatever the style.
        glyph = icon_name[len("emoji:") :]
    else:
        glyph = GLYPH_TABLES[style].get(icon_name, FALLBACK_GLYPHS[style])

    return pad_glyph(glyph)


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
        if (candidate / ".obsidian").is_dir():
            return candidate

    return None


@dataclass
class NotebookNavigatorAppearance:
    """Folder and tag appearance mirrored from Notebook Navigator."""

    vault_root: Path
    folder_icons: dict[str, str] = field(default_factory=dict)
    folder_colors: dict[str, str] = field(default_factory=dict)
    tag_colors: dict[str, str] = field(default_factory=dict)
    inherit_folder_colors: bool = True
    show_folder_icons: bool = True
    color_icon_only: bool = False
    icon_style: IconStyle = DEFAULT_ICON_STYLE

    def _key_for(self, path: Path) -> str | None:
        """Return the vault-relative key Notebook Navigator uses for a path."""
        try:
            relative = path.expanduser().resolve().relative_to(self.vault_root)
        except (OSError, ValueError):
            return None
        key = relative.as_posix()
        return None if key == "." else key

    def icon_for(self, path: Path) -> str:
        """Get the padded glyph for a folder, or empty string if none is set."""
        if not self.show_folder_icons:
            return ""
        key = self._key_for(path)
        if key is None:
            return ""
        return resolve_icon(self.folder_icons.get(key, ""), self.icon_style)

    def default_folder_icon(self, expanded: bool) -> str:
        """Get the padded glyph for a folder with no icon configured."""
        return folder_glyph(expanded, self.icon_style)

    def color_for(self, path: Path) -> str | None:
        """Get the hex color for a folder, inheriting from ancestors if enabled."""
        key = self._key_for(path)
        if key is None:
            return None

        color = self.folder_colors.get(key)
        if color or not self.inherit_folder_colors:
            return color

        # Walk up toward the vault root, nearest ancestor wins.
        parts = key.split("/")
        for depth in range(len(parts) - 1, 0, -1):
            ancestor = "/".join(parts[:depth])
            color = self.folder_colors.get(ancestor)
            if color:
                return color

        return None

    @classmethod
    def load(
        cls,
        scan_directory: Path,
        icon_style: IconStyle | str = DEFAULT_ICON_STYLE,
    ) -> "NotebookNavigatorAppearance | None":
        """Load appearance settings for the vault containing ``scan_directory``.

        Returns None when the directory is not in an Obsidian vault, the plugin
        is not installed, or its data file cannot be read.
        """
        vault_root = find_vault_root(scan_directory)
        if vault_root is None:
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
            icon_style=normalize_style(icon_style),
        )
        logger.info(
            "Loaded Notebook Navigator appearance from %s (%d icons, %d colors, %s style)",
            data_path,
            len(appearance.folder_icons),
            len(appearance.folder_colors),
            appearance.icon_style,
        )
        return appearance
