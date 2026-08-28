"""Tree widget for browsing Craft folders."""

from textual.widgets import Tree

from ..craft import CraftFolder


class CraftTree(Tree):
    """A tree of Craft folders, populated asynchronously by the app.

    Node data is a `CraftFolder` for real folders, or None for the placeholder
    rows used while loading and on error -- highlight handlers key off that.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("Craft", **kwargs)
        self.show_root = False

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
