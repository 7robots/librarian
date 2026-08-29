"""Tag list widget with Tools sidebar for Librarian."""

from pathlib import Path
from typing import Iterable

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import DirectoryTree, Label, ListItem, ListView, Static, Tree
from textual.widgets._directory_tree import DirEntry
from textual.widgets._tree import TOGGLE_STYLE, TreeNode

from ..appearance import CraftAppearance, FolderAppearance
from ..craft import CraftFolder
from .craft_tree import CraftTree

# Maximum tags to display before showing "Show more" item
MAX_DISPLAY_TAGS = 200

# Every launcher tool Librarian knows about, in display order. Folders and Tags
# are not here: they are workspace panels. Each of these gets a launcher tab in
# the strip when enabled in [tools].
ALL_TOOLS = ("TaskPaper", "Reminders", "Calendar", "Projects")

# Which panel drives the Files list at startup. Folders leads because content is
# organized by folder; tags are a shortcut list alongside it.
DEFAULT_SOURCE = "folders"


class MarkdownDirectoryTree(DirectoryTree):
    """A DirectoryTree that only shows directories and markdown files.

    Folder icons and colors come from a `FolderAppearance`, which layers
    Librarian's config over Obsidian's Notebook Navigator settings (when the
    scan directory is in a vault) over plain defaults.
    """

    def __init__(
        self,
        path: str | Path,
        appearance: FolderAppearance | None = None,
        **kwargs,
    ) -> None:
        super().__init__(path, **kwargs)
        self._appearance = appearance

    @property
    def appearance(self) -> FolderAppearance | None:
        """The layered folder appearance in use, if any."""
        return self._appearance

    @appearance.setter
    def appearance(self, appearance: FolderAppearance | None) -> None:
        self._appearance = appearance
        if self.is_mounted:
            self._invalidate()

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter to only show directories and markdown files."""
        for path in paths:
            # Always show directories
            if path.is_dir():
                # Skip hidden directories
                if not path.name.startswith("."):
                    yield path
            # Only show supported files
            elif path.suffix.lower() in (".md", ".taskpaper"):
                yield path

    def render_label(
        self, node: TreeNode[DirEntry], base_style: Style, style: Style
    ) -> Text:
        """Render a node label, applying Notebook Navigator icons and colors.

        The folder's icon takes the place of the tree's own expand/collapse
        glyph rather than sitting beside it, so each row shows one icon. The
        icon keeps ``TOGGLE_STYLE``, which is what makes a click on it expand or
        collapse the folder.
        """
        label = super().render_label(node, base_style, style)

        if self._appearance is None or node.data is None or not self.is_mounted:
            return label

        if not node.allow_expand:
            # Notebook Navigator only styles folders, so leave files alone.
            return label

        path = node.data.path
        icon = self._appearance.folder_icon(path, node.is_expanded)
        color = self._appearance.color_for(path)

        # Drop super()'s toggle glyph and keep the name, which already carries
        # the tree's component styles.
        prefix_length = len(
            self.ICON_NODE_EXPANDED if node.is_expanded else self.ICON_NODE
        )
        name = label[prefix_length:]

        icon_style = base_style + TOGGLE_STYLE
        if color:
            icon_style += Style(color=color)
            if not self._appearance.color_icon_only:
                name.stylize(Style(color=color))

        return Text.assemble((icon, icon_style), name)


class TagItem(ListItem):
    """A list item representing a tag."""

    def __init__(self, tag_name: str, count: int) -> None:
        super().__init__()
        self.tag_name = tag_name
        self.count = count

    def compose(self) -> ComposeResult:
        yield Label(f"#{self.tag_name} ({self.count})")


class ShowMoreItem(ListItem):
    """A list item that triggers loading the full collection."""

    DEFAULT_CSS = """
    ShowMoreItem {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, total_count: int, displayed_count: int) -> None:
        super().__init__()
        self.total_count = total_count
        self.remaining = total_count - displayed_count

    def compose(self) -> ComposeResult:
        yield Label(f"... show {self.remaining} more ({self.total_count} total)")


class TagList(Vertical):
    """The sidebar: the active workspace's tree over the scoped Tags panel.

    Both trees (Folders and Craft) are composed when enabled, but only the
    active workspace's tree is shown -- `show_workspace()` flips them. The
    Tags panel is shared, following the workspace's scope, and splits the
    sidebar 50/50 with the visible tree.
    """

    DEFAULT_CSS = """
    TagList {
        width: 1fr;
        height: 1fr;
    }

    TagList .tag-header {
        background: $primary-background;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    /* The visible tree and the Tags panel split the sidebar 50/50. One
       neutral border everywhere; the focused panel takes the accent. */
    TagList #folders-panel {
        height: 1fr;
        border: solid $panel-lighten-2;
    }

    TagList #folders-panel:focus-within {
        border: solid $accent;
    }

    TagList #craft-panel {
        height: 1fr;
        border: solid $panel-lighten-2;
    }

    TagList #craft-panel:focus-within {
        border: solid $accent;
    }

    TagList #tags-panel {
        height: 1fr;
        border: solid $panel-lighten-2;
    }

    TagList #tags-panel:focus-within {
        border: solid $accent;
    }

    TagList ListView {
        height: 1fr;
    }

    TagList DirectoryTree {
        height: 1fr;
    }

    TagList ListItem {
        padding: 0 1;
    }

    TagList ListItem:hover {
        background: $boost;
    }

    TagList ListItem.--highlight {
        background: $accent;
    }
    """

    class TagSelected(Message):
        """Message emitted when a tag is selected."""

        def __init__(self, tag_name: str) -> None:
            super().__init__()
            self.tag_name = tag_name

    class FileSelected(Message):
        """Message emitted when a file is selected in the folder browser."""

        def __init__(self, file_path: Path) -> None:
            super().__init__()
            self.file_path = file_path

    class FolderHighlighted(Message):
        """Message emitted when the folder browser cursor moves to a folder."""

        def __init__(self, folder_path: Path) -> None:
            super().__init__()
            self.folder_path = folder_path

    class CraftFolderHighlighted(Message):
        """Message emitted when the Craft tree cursor moves to a folder."""

        def __init__(self, folder: CraftFolder) -> None:
            super().__init__()
            self.folder = folder

    class CraftTagSelected(Message):
        """Message emitted when a tag is selected while Craft-scoped."""

        def __init__(self, tag_name: str) -> None:
            super().__init__()
            self.tag_name = tag_name

    def __init__(
        self,
        scan_directory: Path | None = None,
        appearance: FolderAppearance | None = None,
        show_folders: bool = True,
        show_tags: bool = True,
        show_craft: bool = False,
        craft_appearance: CraftAppearance | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._craft_appearance = craft_appearance
        self.show_folders = show_folders
        self.show_tags = show_tags
        self.show_craft = show_craft
        self._all_tags: list[tuple[str, int]] = []
        self._scan_directory = scan_directory or Path.home()
        self._appearance = appearance
        # Which panel drives the Files list: "folders", "tags", or "craft".
        # The last one touched wins; at startup the first panel that exists
        # leads, in that order.
        if show_folders:
            self.active_source: str = DEFAULT_SOURCE
        elif show_tags:
            self.active_source = "tags"
        else:
            self.active_source = "craft"
        # Which workspace's tree the sidebar shows; set for real on mount.
        self._workspace = "folders" if (show_folders or show_tags) else "craft"
        self._tags_show_all: bool = False
        # Which source the Tags panel reflects: "local" (the index) or
        # "craft". Follows whichever tree was last highlighted, so the panel
        # always shows the tags of what is being browsed.
        self.tags_scope: str = "local"
        self._craft_tags: list[tuple[str, int]] = []

    def compose(self) -> ComposeResult:
        # Both trees are composed when enabled; show_workspace() flips which
        # one is visible. The Tags panel is shared beneath, its scope following
        # the active workspace.
        if self.show_folders:
            with Vertical(id="folders-panel"):
                yield Static("FOLDERS", classes="tag-header", id="folders-header")
                yield MarkdownDirectoryTree(
                    str(self._scan_directory),
                    appearance=self._appearance,
                    id="directory-tree",
                )
        if self.show_craft:
            with Vertical(id="craft-panel"):
                yield Static("CRAFT", classes="tag-header", id="craft-header")
                yield CraftTree(appearance=self._craft_appearance, id="craft-tree")
        if self.show_tags:
            with Vertical(id="tags-panel"):
                yield Static("ALL TAGS", classes="tag-header", id="all-tags-header")
                yield ListView(id="all-tags-list-view")

    def on_mount(self) -> None:
        """Start with one workspace visible: local when present, else Craft.

        The local workspace exists when either of its panels does -- a
        folders-off, tags-on config still browses locally, just without the
        tree.
        """
        self.show_workspace(
            "folders" if (self.show_folders or self.show_tags) else "craft"
        )

    def show_workspace(self, workspace: str) -> None:
        """Show one workspace's tree in the sidebar ("folders" or "craft").

        The other tree is hidden, not removed -- its cursor, expansion state,
        and loaded Craft folders all survive the flip. Panels that are not
        composed at all (turned off in [tools]) are left alone.
        """
        self._workspace = workspace
        for panel_id, wanted in (
            ("#folders-panel", workspace == "folders"),
            ("#craft-panel", workspace == "craft"),
        ):
            try:
                self.query_one(panel_id).display = wanted
            except NoMatches:
                continue

    @property
    def workspace(self) -> str:
        """The workspace whose tree is currently shown."""
        return self._workspace

    @property
    def all_tags_list_view(self) -> ListView | None:
        """The tags list, or None when the tags panel is turned off."""
        try:
            return self.query_one("#all-tags-list-view", ListView)
        except NoMatches:
            return None

    @property
    def directory_tree(self) -> MarkdownDirectoryTree | None:
        """The folder tree, or None when the folder browser is turned off."""
        try:
            return self.query_one("#directory-tree", MarkdownDirectoryTree)
        except NoMatches:
            return None

    @property
    def craft_tree(self) -> CraftTree | None:
        """The Craft folder tree, or None when the Craft module is off."""
        try:
            return self.query_one("#craft-tree", CraftTree)
        except NoMatches:
            return None

    def set_scan_directory(
        self, path: Path, appearance: FolderAppearance | None = None
    ) -> None:
        """Set the root directory for the directory browser.

        Appearance depends on the scan directory (config keys are relative to
        it, and vault detection starts from it), so callers changing the
        directory should pass a freshly built appearance.
        """
        self._scan_directory = path
        if appearance is not None:
            self._appearance = appearance
        try:
            tree = self.directory_tree
            if tree is not None:
                tree.appearance = self._appearance
                tree.path = path
        except Exception:
            pass  # Tree not yet mounted

    def set_tags_scope(self, scope: str) -> None:
        """Point the Tags panel at a source's tags ("local" or "craft").

        Each scope's listing is kept, so flipping back is a repopulation from
        memory, not a refetch.
        """
        if scope == self.tags_scope or not self.show_tags:
            return
        self.tags_scope = scope
        self.query_one("#all-tags-header", Static).update(
            "CRAFT TAGS" if scope == "craft" else "ALL TAGS"
        )
        self._repopulate_scope()

    def update_craft_tags(self, tags: list[tuple[str, int]]) -> None:
        """Update the Craft tag listing (shown only while Craft-scoped)."""
        self._craft_tags = tags
        if self.tags_scope == "craft":
            self._repopulate_scope()

    def _repopulate_scope(self) -> None:
        """Rebuild the tags list from the current scope's stored tags."""
        list_view = self.all_tags_list_view
        if list_view is None:
            return
        tags = self._craft_tags if self.tags_scope == "craft" else self._all_tags
        list_view.clear()
        for tag_name, count in tags:
            list_view.append(TagItem(tag_name, count))
        if tags:
            list_view.index = 0

    def update_tags(self, tags: list[tuple[str, int]]) -> None:
        """Update the list of tags with incremental updates."""
        if self.all_tags_list_view is None:
            return  # Tags panel turned off

        self._all_tags = tags
        if self.tags_scope != "local":
            return  # stored; shown again when the scope flips back

        selected_tag = self.get_selected_tag()

        # Apply display cap for large collections unless user expanded
        if not self._tags_show_all and len(tags) > MAX_DISPLAY_TAGS:
            display_tags = tags[:MAX_DISPLAY_TAGS]
        else:
            display_tags = tags

        all_list = self.all_tags_list_view
        self._update_list_view(all_list, display_tags, total_count=len(tags))

        if selected_tag:
            self._restore_selection(selected_tag)
        elif tags:
            all_list.index = 0

    def _update_list_view(
        self, list_view: ListView, new_tags: list[tuple[str, int]], total_count: int = 0
    ) -> None:
        """Update a ListView incrementally, only changing what's different."""
        new_tags_dict = {name: count for name, count in new_tags}
        existing_items = list(list_view.children)
        existing_tags = {
            item.tag_name: item for item in existing_items if isinstance(item, TagItem)
        }

        if set(new_tags_dict.keys()) != set(existing_tags.keys()):
            list_view.clear()
            for tag_name, count in new_tags:
                list_view.append(TagItem(tag_name, count))
            # Add "show more" item if truncated
            if total_count > len(new_tags):
                list_view.append(ShowMoreItem(total_count, len(new_tags)))
            return

        for tag_name, new_count in new_tags_dict.items():
            item = existing_tags.get(tag_name)
            if item and item.count != new_count:
                item.count = new_count
                label = item.query_one(Label)
                label.update(f"#{tag_name} ({new_count})")

    def _restore_selection(self, tag_name: str) -> None:
        """Restore selection to a specific tag if it exists."""
        all_list = self.all_tags_list_view
        if all_list is None:
            return
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name == tag_name:
                all_list.index = i
                return

    def initialize(self) -> None:
        """Focus the first panel that exists and announce its starting item.

        Called once at startup. Folders leads when present, then Tags, then
        Craft. Focusing the Craft tree triggers its first fetch (and so the
        `op read`) -- acceptable only here, where Craft is the sole browsing
        panel and loading it *is* the point of launching.
        """
        tree = self.directory_tree
        if tree is not None:
            if tree.cursor_line < 0:
                tree.cursor_line = 0
            tree.focus()

            folder = self.get_selected_folder()
            if folder is not None:
                self.post_message(self.FolderHighlighted(folder))
            return

        tags = self.all_tags_list_view
        if tags is not None:
            tags.focus()
            tag = self.get_selected_tag()
            if tag is not None:
                self.post_message(self.TagSelected(tag))
            return

        craft = self.craft_tree
        if craft is not None:
            craft.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection from the tag list."""
        item = event.item

        # Handle "Show more" item
        if isinstance(item, ShowMoreItem):
            self._tags_show_all = True
            self.update_tags(self._all_tags)
            return

        # Handle tag list selection -- which source's tag it is depends on
        # the panel's scope.
        if isinstance(item, TagItem):
            if self.tags_scope == "craft":
                self.active_source = "craft-tags"
                self.post_message(self.CraftTagSelected(item.tag_name))
            else:
                self.active_source = "tags"
                self.post_message(self.TagSelected(item.tag_name))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from directory tree."""
        if event.path.suffix.lower() in (".md", ".taskpaper"):
            self.post_message(self.FileSelected(event.path))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Announce the folder under the cursor so the Files panel can follow.

        Both trees land here; which one it was is told by the node's data --
        a filesystem path for the directory tree, a `CraftFolder` for Craft.
        """
        data = getattr(event.node, "data", None)
        if isinstance(data, CraftFolder):
            self.active_source = "craft"
            self.set_tags_scope("craft")
            self.post_message(self.CraftFolderHighlighted(data))
            return

        folder = self._folder_for_node(event.node)
        if folder is not None:
            self.active_source = "folders"
            self.set_tags_scope("local")
            self.post_message(self.FolderHighlighted(folder))

    @staticmethod
    def _folder_for_node(node) -> Path | None:
        """Get the directory a tree node represents, or None if it is a file."""
        entry = getattr(node, "data", None)
        path = getattr(entry, "path", None)
        if path is None:
            return None
        try:
            return path if path.is_dir() else None
        except OSError:
            return None

    def get_selected_folder(self) -> Path | None:
        """Get the folder under the directory tree cursor, falling back to root."""
        try:
            tree = self.directory_tree
        except Exception:
            return None  # Tree not yet mounted
        if tree is None:
            return None  # Folder browser turned off

        node = tree.cursor_node
        folder = self._folder_for_node(node) if node is not None else None
        if folder is not None:
            return folder

        return self._folder_for_node(tree.root)

    def get_selected_tag(self) -> str | None:
        """Get the currently selected tag name."""
        all_list = self.all_tags_list_view
        if all_list is None:
            return None
        if all_list.highlighted_child is not None:
            item = all_list.highlighted_child
            if isinstance(item, TagItem):
                return item.tag_name

        return None
