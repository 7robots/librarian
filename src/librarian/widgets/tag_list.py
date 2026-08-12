"""Tag list widget with Tools sidebar for Librarian."""

from pathlib import Path
from typing import Iterable

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DirectoryTree, Label, ListItem, ListView, Static, Tree
from textual.widgets._directory_tree import DirEntry
from textual.widgets._tree import TOGGLE_STYLE, TreeNode

from ..appearance import FolderAppearance

# Maximum tags to display before showing "Show more" item
MAX_DISPLAY_TAGS = 200

# Every tool Librarian knows about, in display order. Folders and Tags are no
# longer here: they have permanent panels of their own, so everything in the
# Tools menu now launches something.
ALL_TOOLS = ("TaskPaper", "Reminders", "Calendar")

# Tools hidden unless enabled in config. The code behind them stays live; only
# the menu entry is withheld.
OPTIONAL_TOOLS = ALL_TOOLS

# What the menu shows when nothing is configured: nothing, since every tool
# needs a third-party program.
DEFAULT_TOOLS: tuple[str, ...] = ()

# Every tool now launches something rather than switching a panel.
LAUNCHER_TOOLS = ("taskpaper", "reminders", "calendar")

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


class ToolItem(ListItem):
    """A list item representing a tool in the Tools menu."""

    def __init__(self, tool_name: str) -> None:
        super().__init__()
        self.tool_name = tool_name

    def compose(self) -> ComposeResult:
        yield Label(self.tool_name)


class TagList(Vertical):
    """Widget displaying Tools menu at top and switchable content panel below."""

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

    TagList #tools-header {
        color: $warning;
    }

    /* Folders gets the most room; Tools is a short list of launchers, so it
       takes only the rows it needs. */
    TagList #folders-panel {
        height: 2fr;
        border: solid $success;
    }

    TagList #folders-panel:focus-within {
        border: solid green;
    }

    TagList #tags-panel {
        height: 1fr;
        border: solid $primary;
    }

    TagList #tags-panel:focus-within {
        border: solid $primary-lighten-2;
    }

    TagList #tools-panel {
        height: auto;
        max-height: 40%;
        border: solid $accent;
    }

    TagList #tools-panel:focus-within {
        border: solid cyan;
    }

    TagList #tools-list-view {
        height: 1fr;
    }

    TagList #tools-list-view ListItem {
        padding: 0 1;
    }

    TagList #tools-list-view ListItem:hover {
        background: $boost;
    }

    TagList #tools-list-view ListItem.--highlight {
        background: $accent;
    }

    TagList #all-tags-header {
        color: $primary-lighten-2;
    }

    TagList #folders-header {
        color: $success;
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

    class ToolLaunched(Message):
        """Message emitted when a tool is selected from the Tools menu."""

        def __init__(self, tool_name: str) -> None:
            super().__init__()
            self.tool_name = tool_name

    def __init__(
        self,
        scan_directory: Path | None = None,
        appearance: FolderAppearance | None = None,
        tools: tuple[str, ...] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tools = tuple(tools) if tools is not None else DEFAULT_TOOLS
        self._all_tags: list[tuple[str, int]] = []
        self._scan_directory = scan_directory or Path.home()
        self._appearance = appearance
        # Which panel drives the Files list: "folders" or "tags". Both are
        # always visible, so the last one touched wins.
        self.active_source: str = DEFAULT_SOURCE
        self._tags_show_all: bool = False

    def compose(self) -> ComposeResult:
        # Three permanent panels. Folders and Tags are both visible because they
        # do different jobs -- the tree is for browsing, a tag like #meetings is
        # a shortcut list -- and switching between them lost sight of the other.
        with Vertical(id="folders-panel"):
            yield Static("FOLDERS", classes="tag-header", id="folders-header")
            yield MarkdownDirectoryTree(
                str(self._scan_directory),
                appearance=self._appearance,
                id="directory-tree",
            )
        with Vertical(id="tags-panel"):
            yield Static("ALL TAGS", classes="tag-header", id="all-tags-header")
            yield ListView(id="all-tags-list-view")
        with Vertical(id="tools-panel"):
            yield Static("\u2605 TOOLS", classes="tag-header", id="tools-header")
            yield ListView(
                *(ToolItem(name) for name in self.tools),
                id="tools-list-view",
            )

    @property
    def tools_list_view(self) -> ListView:
        return self.query_one("#tools-list-view", ListView)

    @property
    def all_tags_list_view(self) -> ListView:
        return self.query_one("#all-tags-list-view", ListView)

    @property
    def directory_tree(self) -> MarkdownDirectoryTree:
        return self.query_one("#directory-tree", MarkdownDirectoryTree)

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
            tree.appearance = self._appearance
            tree.path = path
        except Exception:
            pass  # Tree not yet mounted

    def update_tags(self, tags: list[tuple[str, int]]) -> None:
        """Update the list of tags with incremental updates."""
        selected_tag = self.get_selected_tag()

        self._all_tags = tags

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
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name == tag_name:
                all_list.index = i
                return

    def initialize(self) -> None:
        """Focus the folder tree and announce its starting folder.

        Called once at startup. Folders leads, so browsing begins there.
        """
        tree = self.directory_tree
        if tree.cursor_line < 0:
            tree.cursor_line = 0
        tree.focus()

        folder = self.get_selected_folder()
        if folder is not None:
            self.post_message(self.FolderHighlighted(folder))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection from tools menu or tag list."""
        item = event.item

        # Handle tools menu selection
        if isinstance(item, ToolItem):
            tool = item.tool_name.lower()
            # Every tool launches something; the sidebar panels stay put.
            if tool in LAUNCHER_TOOLS:
                self.post_message(self.ToolLaunched(tool))
            return

        # Handle "Show more" item
        if isinstance(item, ShowMoreItem):
            self._tags_show_all = True
            self.update_tags(self._all_tags)
            return

        # Handle tag list selection
        if isinstance(item, TagItem):
            self.active_source = "tags"
            self.post_message(self.TagSelected(item.tag_name))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from directory tree."""
        if event.path.suffix.lower() in (".md", ".taskpaper"):
            self.post_message(self.FileSelected(event.path))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Announce the folder under the cursor so the Files panel can follow."""
        folder = self._folder_for_node(event.node)
        if folder is not None:
            self.active_source = "folders"
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

        node = tree.cursor_node
        folder = self._folder_for_node(node) if node is not None else None
        if folder is not None:
            return folder

        return self._folder_for_node(tree.root)

    def get_selected_tag(self) -> str | None:
        """Get the currently selected tag name."""
        all_list = self.all_tags_list_view
        if all_list.highlighted_child is not None:
            item = all_list.highlighted_child
            if isinstance(item, TagItem):
                return item.tag_name

        return None
