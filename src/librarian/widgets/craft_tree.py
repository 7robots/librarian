"""Tree widget for browsing Craft folders."""

from rich.style import Style
from rich.text import Text
from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TOGGLE_STYLE, TreeNode

from ..appearance import CraftAppearance
from ..craft import CraftFolder


class CraftTree(Tree):
    """A tree of Craft folders, populated asynchronously by the app.

    Node data is a `CraftFolder` for real folders, or None for the placeholder
    rows used while loading and on error -- highlight handlers key off that.

    Nothing is fetched until the panel is first focused: the fetch resolves the
    API key via `op read`, and a 1Password authorization prompt at startup --
    for a panel that may not be touched all session -- is the projection
    lesson this repo already learned once.
    """

    class LoadRequested(Message):
        """Posted on first focus, asking the app to fetch the folder tree."""

    def __init__(self, appearance: CraftAppearance | None = None, **kwargs) -> None:
        # Before super().__init__: Tree renders its root label during init,
        # and render_label already needs the attribute.
        self._appearance = appearance
        super().__init__("Craft", **kwargs)
        self.show_root = False
        self._load_requested = False

    @property
    def appearance(self) -> CraftAppearance | None:
        """The layered Craft folder appearance in use, if any."""
        return self._appearance

    @appearance.setter
    def appearance(self, appearance: CraftAppearance | None) -> None:
        self._appearance = appearance
        if self.is_mounted:
            self._invalidate()

    def on_mount(self) -> None:
        self.show_message("(select to load)")

    def on_focus(self) -> None:
        if not self._load_requested:
            self._load_requested = True
            self.post_message(self.LoadRequested())

    def reset_load_request(self) -> None:
        """Allow the next focus to retry -- called after a failed load."""
        self._load_requested = False

    def show_message(self, message: str) -> None:
        """Replace the tree with a single inert row (loading, error)."""
        self.clear()
        self.root.add_leaf(message, data=None)

    def update_folders(self, folders: list[CraftFolder]) -> None:
        """Rebuild the tree from a fresh folder listing."""
        self.clear()
        if not folders:
            self.root.add_leaf("(no folders)", data=None)
            return
        for folder in folders:
            self._add_folder(self.root, folder)
        # The cursor is deliberately left unset: placing it would fire
        # NodeHighlighted the moment folders load, and the Files panel would
        # switch to Craft at startup without the user touching the panel.

    def _add_folder(self, parent, folder: CraftFolder) -> None:
        label = f"{folder.name} ({folder.document_count})"
        if folder.folders:
            node = parent.add(label, data=folder)
            for child in folder.folders:
                self._add_folder(node, child)
        else:
            parent.add_leaf(label, data=folder)

    @staticmethod
    def folder_key(node: TreeNode) -> str | None:
        """The Craft folder path a node represents: names joined with "/".

        This is the key `[craft-folders.icons]` / `[craft-folders.colors]` use,
        and the relative path the same-name local fallback resolves. None for
        placeholder rows, whose data is not a `CraftFolder`.
        """
        parts: list[str] = []
        current: TreeNode | None = node
        while current is not None:
            data = getattr(current, "data", None)
            if isinstance(data, CraftFolder):
                parts.append(data.name)
            current = current.parent
        if not parts:
            return None
        return "/".join(reversed(parts))

    def render_label(
        self, node: TreeNode, base_style: Style, style: Style
    ) -> Text:
        """Render a node label, applying the layered Craft folder appearance.

        Mirrors `MarkdownDirectoryTree.render_label`: the icon takes the place
        of the tree's own expand/collapse glyph and keeps ``TOGGLE_STYLE``, so
        clicking it still expands or collapses. Leaf folders have no toggle
        glyph to replace, so the icon is simply prepended there.
        """
        label = super().render_label(node, base_style, style)

        if self._appearance is None or not self.is_mounted:
            return label
        key = self.folder_key(node)
        if key is None:
            return label  # placeholder row (loading, error, empty)

        icon = self._appearance.folder_icon(key, node.is_expanded)
        color = self._appearance.color_for(key)

        if node.allow_expand:
            prefix_length = len(
                self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE
            )
        else:
            prefix_length = 0
        name = label[prefix_length:]

        icon_style = base_style + TOGGLE_STYLE
        if color:
            icon_style += Style(color=color)
            if not self._appearance.color_icon_only:
                name.stylize(Style(color=color))

        return Text.assemble((icon, icon_style), name)
