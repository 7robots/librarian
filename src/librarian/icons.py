"""Terminal glyphs for folder icons, and the style that selects between them.

Folder icons are named with `Lucide <https://lucide.dev/icons/>`_ names -- the
vocabulary Obsidian's Notebook Navigator uses, and what Librarian's own config
accepts. Lucide has no terminal-renderable form (Obsidian draws it as inline
SVG, and Nerd Fonts does not carry the set), so each name maps to a glyph in one
of two styles:

``nerd``
    Material Design Icons from Nerd Fonts. Monochrome, so they take on the
    folder's color, and closest in spirit to the Lucide originals. Needs a Nerd
    Font in the terminal.
``emoji``
    Plain emoji, for terminals without a Nerd Font. Emoji carry their own colors
    and ignore the folder color.

``auto`` picks between them by looking at the terminal -- see
:func:`detect_glyph_style`. Names prefixed with ``emoji:`` are literal emoji and
pass through unchanged in both styles.

This module knows nothing about Obsidian; it is the glyph layer that every
appearance source draws on.
"""

import logging
import os
from pathlib import Path
from typing import Literal

from rich.cells import cell_len

logger = logging.getLogger(__name__)

# Styles that name a glyph table.
GlyphStyle = Literal["nerd", "emoji"]
GLYPH_STYLES: tuple[GlyphStyle, ...] = ("nerd", "emoji")

# Styles accepted in config, including the one that detects at runtime.
IconStyle = Literal["auto", "nerd", "emoji"]
ICON_STYLES: tuple[IconStyle, ...] = ("auto", "nerd", "emoji")
DEFAULT_ICON_STYLE: IconStyle = "auto"

# Style used when a configured value is unusable.
FALLBACK_GLYPH_STYLE: GlyphStyle = "emoji"

# Width in cells an icon glyph is padded to, so folder names line up regardless
# of whether the glyph is single- or double-width. One separating space is added
# on top of this, making every rendered icon ICON_CELL_WIDTH + 1 cells wide.
ICON_CELL_WIDTH = 2

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


# Terminals that ship Nerd Font symbols themselves, so no font install is
# needed. Matched against TERM_PROGRAM, lowercased.
NERD_FONT_TERMINALS = frozenset({"ghostty", "wezterm"})

# Where macOS keeps user- and system-installed fonts.
FONT_DIRECTORIES = (
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
)

FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".dfont"})

# Nerd Font releases put this in the filename, patched fonts included.
NERD_FONT_FILENAME_MARKER = "nerd"


def has_nerd_font_terminal() -> bool:
    """Check whether the terminal is one that bundles Nerd Font symbols."""
    return os.environ.get("TERM_PROGRAM", "").strip().lower() in NERD_FONT_TERMINALS


def has_nerd_font_installed() -> bool:
    """Check whether a Nerd Font is installed in a standard font directory."""
    for directory in FONT_DIRECTORIES:
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if (
                entry.suffix.lower() in FONT_SUFFIXES
                and NERD_FONT_FILENAME_MARKER in entry.name.lower()
            ):
                return True
    return False


def detect_glyph_style() -> GlyphStyle:
    """Guess whether the terminal can render Nerd Font glyphs.

    Both signals are needed: terminals like Ghostty embed the font in their own
    binary, so a font-directory scan misses them, while an installed Nerd Font
    is invisible to a terminal allowlist. Emoji is the safe answer when neither
    signal fires, since emoji render nearly everywhere.

    This is a heuristic. Set ``style`` explicitly in ``[icons]`` to override it.
    """
    if has_nerd_font_terminal():
        return "nerd"
    if has_nerd_font_installed():
        return "nerd"
    return FALLBACK_GLYPH_STYLE


def resolve_style(style: str | None) -> GlyphStyle:
    """Turn a configured ``icon_style`` into the style to actually render with.

    Call once at startup rather than per glyph -- detection touches the
    filesystem.
    """
    if style in GLYPH_STYLES:
        return style  # type: ignore[return-value]
    if style is None or style == "auto":
        return detect_glyph_style()

    logger.warning(
        "Unknown icon style %r, detecting instead of guessing a table", style
    )
    return detect_glyph_style()


def _glyph_table(style: str) -> dict[str, str]:
    """Get the glyph table for a resolved style, defensively."""
    return GLYPH_TABLES.get(style, GLYPH_TABLES[FALLBACK_GLYPH_STYLE])


def pad_glyph(glyph: str) -> str:
    """Pad a glyph to a fixed cell width plus one separating space."""
    if not glyph:
        return ""
    padding = max(0, ICON_CELL_WIDTH - cell_len(glyph))
    return glyph + " " * padding + " "


def resolve_icon(icon_name: str, style: GlyphStyle) -> str:
    """Convert an icon name to a padded terminal glyph.

    Returns an empty string when ``icon_name`` is empty. Glyphs are padded to
    ``ICON_CELL_WIDTH`` cells plus a separating space, so folder names align in
    a column whatever the glyph's width -- necessary because a single tree can
    mix one-cell Nerd Font glyphs with two-cell emoji.
    """
    if not icon_name:
        return ""

    if icon_name.startswith("emoji:"):
        # An emoji chosen deliberately stays an emoji, whatever the style.
        glyph = icon_name[len("emoji:") :]
    else:
        table = _glyph_table(style)
        glyph = table.get(
            icon_name, FALLBACK_GLYPHS.get(style, FALLBACK_GLYPHS[FALLBACK_GLYPH_STYLE])
        )

    return pad_glyph(glyph)


def folder_glyph(expanded: bool, style: GlyphStyle) -> str:
    """Get the padded glyph for a folder with no icon configured."""
    table = OPEN_FOLDER_GLYPHS if expanded else CLOSED_FOLDER_GLYPHS
    return pad_glyph(table.get(style, table[FALLBACK_GLYPH_STYLE]))
