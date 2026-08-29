"""Layered folder appearance: where a folder's icon and color come from.

Several sources can supply appearance for a folder, and they are consulted in
precedence order, **per key**:

1. Librarian's own config (``[folders.icons]`` / ``[folders.colors]``)
2. Obsidian's Notebook Navigator plugin, when the scan directory is in a vault
3. A plain folder glyph, with no color

Per key matters: config may set only a color for a folder while the plugin
supplies its icon, and both should apply. A source that won outright would make
that impossible.

Nothing here requires Obsidian. With no config and no plugin, every folder gets
the default glyph -- which is what a stock Textual tree shows anyway.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .icons import GlyphStyle, folder_glyph, resolve_icon, resolve_style

logger = logging.getLogger(__name__)


def relative_key(path: Path, root: Path) -> str | None:
    """Return the root-relative POSIX key used to look a folder up.

    Returns None for the root itself (it has no key of its own) and for paths
    outside the root.
    """
    try:
        relative = path.expanduser().resolve().relative_to(root)
    except (OSError, ValueError):
        return None
    key = relative.as_posix()
    return None if key == "." else key


def lookup_with_inheritance(
    values: dict[str, str], key: str, inherit: bool = True
) -> str | None:
    """Look up a key, optionally falling back to the nearest ancestor's value."""
    value = values.get(key)
    if value or not inherit:
        return value

    parts = key.split("/")
    for depth in range(len(parts) - 1, 0, -1):
        value = values.get("/".join(parts[:depth]))
        if value:
            return value

    return None


@runtime_checkable
class AppearanceSource(Protocol):
    """A source of per-folder icon names and colors."""

    def icon_name_for(self, path: Path) -> str | None:
        """Icon name for a folder (a Lucide name or ``emoji:`` literal)."""
        ...

    def color_for(self, path: Path) -> str | None:
        """Hex color for a folder."""
        ...


@dataclass
class ConfigAppearance:
    """Folder appearance from Librarian's own config.

    Keys are paths relative to the scan directory. Colors inherit to
    subfolders, matching how the plugin behaves.
    """

    root: Path
    icons: dict[str, str] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)

    def icon_name_for(self, path: Path) -> str | None:
        key = relative_key(path, self.root)
        if key is None:
            return None
        return self.icons.get(key) or None

    def color_for(self, path: Path) -> str | None:
        key = relative_key(path, self.root)
        if key is None:
            return None
        return lookup_with_inheritance(self.colors, key)

    def is_empty(self) -> bool:
        return not self.icons and not self.colors


@dataclass
class FolderAppearance:
    """Resolves a folder's rendered icon and color across layered sources.

    This is what the folder tree holds. It is always present -- absent sources
    simply mean every folder falls back to the default glyph.
    """

    glyph_style: GlyphStyle
    sources: tuple[AppearanceSource, ...] = ()
    color_icon_only: bool = False

    def icon_name_for(self, path: Path) -> str | None:
        """First icon name any source supplies, in precedence order."""
        for source in self.sources:
            name = source.icon_name_for(path)
            if name:
                return name
        return None

    def color_for(self, path: Path) -> str | None:
        """First color any source supplies, in precedence order."""
        for source in self.sources:
            color = source.color_for(path)
            if color:
                return color
        return None

    def folder_icon(self, path: Path, expanded: bool = False) -> str:
        """Padded glyph for a folder, falling back to a plain folder glyph.

        The fallback tracks expanded state, which a configured icon cannot: an
        icon chosen for a folder is the same open or closed.
        """
        name = self.icon_name_for(path)
        if name:
            return resolve_icon(name, self.glyph_style)
        return folder_glyph(expanded, self.glyph_style)


@dataclass
class CraftAppearance:
    """Appearance for Craft folders, keyed by Craft folder path ("A/B").

    Craft's REST API does not expose folder icons, so these are layered from
    what Librarian can see, consulted per key:

    1. ``[craft-folders.icons]`` / ``[craft-folders.colors]`` from config
    2. The local folder appearance for the *same relative path* -- Craft spaces
       often mirror the vault's top-level folders, so a Craft folder named
       "Projects" picks up whatever the local "Projects" folder shows, config
       and Notebook Navigator alike
    3. The plain folder glyph, with no color

    Keys are folder names joined with "/" from the top of the Craft space,
    matching how config keys are written.
    """

    glyph_style: GlyphStyle
    icons: dict[str, str] = field(default_factory=dict)
    colors: dict[str, str] = field(default_factory=dict)
    local: FolderAppearance | None = None
    local_root: Path | None = None

    @property
    def color_icon_only(self) -> bool:
        return self.local.color_icon_only if self.local is not None else False

    def _local_path(self, key: str) -> Path | None:
        """The scan-directory path a Craft folder path would have locally."""
        if self.local is None or self.local_root is None:
            return None
        return self.local_root / key

    def icon_name_for(self, key: str) -> str | None:
        name = self.icons.get(key)
        if name:
            return name
        path = self._local_path(key)
        if path is not None:
            return self.local.icon_name_for(path)
        return None

    def color_for(self, key: str) -> str | None:
        color = lookup_with_inheritance(self.colors, key)
        if color:
            return color
        path = self._local_path(key)
        if path is not None:
            return self.local.color_for(path)
        return None

    def folder_icon(self, key: str, expanded: bool = False) -> str:
        """Padded glyph for a Craft folder, falling back to the plain glyph."""
        name = self.icon_name_for(key)
        if name:
            return resolve_icon(name, self.glyph_style)
        return folder_glyph(expanded, self.glyph_style)


def build_craft_appearance(
    config, local: FolderAppearance | None = None
) -> CraftAppearance:
    """Assemble the appearance layers for the Craft folder tree.

    Args:
        config: Application config, read for ``craft_folders`` and the paths
            the same-name fallback resolves against
        local: The local folder tree's appearance, reused as the same-path
            fallback source; built from config when not supplied
    """
    if local is None:
        local = build_folder_appearance(config)
    return CraftAppearance(
        glyph_style=local.glyph_style,
        icons=dict(config.craft_folders.icons),
        colors=dict(config.craft_folders.colors),
        local=local,
        local_root=config.scan_directory,
    )


def build_folder_appearance(config, scan_directory: Path | None = None) -> FolderAppearance:
    """Assemble the appearance layers for a scan directory.

    Args:
        config: Application config, read for ``icons`` / ``folders`` / ``obsidian``
        scan_directory: Root to resolve config keys against and to search for an
            Obsidian vault; defaults to the config's scan directory
    """
    # Imported here to keep the Obsidian integration optional and out of this
    # module's import graph.
    from .obsidian import NotebookNavigatorAppearance

    root = scan_directory if scan_directory is not None else config.scan_directory
    glyph_style = resolve_style(config.icons.style)

    sources: list[AppearanceSource] = []

    config_source = ConfigAppearance(
        root=root,
        icons=dict(config.folders.icons),
        colors=dict(config.folders.colors),
    )
    if not config_source.is_empty():
        sources.append(config_source)

    color_icon_only = False
    if config.obsidian.enabled:
        plugin = NotebookNavigatorAppearance.load(root)
        if plugin is not None:
            sources.append(plugin)
            color_icon_only = plugin.color_icon_only

    logger.info(
        "Folder appearance: style=%s, sources=%s",
        glyph_style,
        [type(s).__name__ for s in sources] or "defaults only",
    )

    return FolderAppearance(
        glyph_style=glyph_style,
        sources=tuple(sources),
        color_icon_only=color_icon_only,
    )
