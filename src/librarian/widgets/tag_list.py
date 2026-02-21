"""Tag list widget for browsing discovered tags."""

from pathlib import Path
from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DirectoryTree, Label, ListItem, ListView, Static


class MarkdownDirectoryTree(DirectoryTree):
    """A DirectoryTree that only shows directories and markdown files."""

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


class TagItem(ListItem):
    """A list item representing a tag."""

    def __init__(self, tag_name: str, count: int) -> None:
        super().__init__()
        self.tag_name = tag_name
        self.count = count

    def compose(self) -> ComposeResult:
        yield Label(f"#{self.tag_name} ({self.count})")


class TagList(Vertical):
    """Widget displaying favorite tags and all tags in two panels."""

    DEFAULT_CSS = """
    TagList {
        width: 1fr;
        height: 1fr;
    }

    TagList > .tag-section {
        height: 1fr;
        border-bottom: solid $primary;
    }

    TagList > .tag-section:last-child {
        border-bottom: none;
    }

    TagList .tag-header {
        background: $primary-background;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    TagList #favorites-header {
        color: $warning;
    }

    TagList #all-tags-header {
        color: $primary-lighten-2;
    }

    TagList #browse-header {
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

    TagList #favorites-section {
        background: $primary-background-darken-1;
    }

    TagList #all-tags-section.hidden {
        display: none;
    }

    TagList #browse-section {
        display: none;
    }

    TagList #browse-section.visible {
        display: block;
    }
    """

    class TagSelected(Message):
        """Message emitted when a tag is selected."""

        def __init__(self, tag_name: str) -> None:
            super().__init__()
            self.tag_name = tag_name

    class FileSelected(Message):
        """Message emitted when a file is selected in browse mode."""

        def __init__(self, file_path: Path) -> None:
            super().__init__()
            self.file_path = file_path

    def __init__(self, scan_directory: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._all_tags: list[tuple[str, int]] = []
        self._favorites: list[str] = []
        self._scan_directory = scan_directory or Path.home()
        self._browse_mode = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="tag-section", id="favorites-section"):
            yield Static("\u2605 FAVORITES", classes="tag-header", id="favorites-header")
            yield ListView(id="favorites-list-view")
        with Vertical(classes="tag-section", id="all-tags-section"):
            yield Static("ALL TAGS", classes="tag-header", id="all-tags-header")
            yield ListView(id="all-tags-list-view")
        with Vertical(classes="tag-section", id="browse-section"):
            yield Static("BROWSE (b)", classes="tag-header", id="browse-header")
            yield MarkdownDirectoryTree(str(self._scan_directory), id="directory-tree")

    @property
    def favorites_list_view(self) -> ListView:
        return self.query_one("#favorites-list-view", ListView)

    @property
    def all_tags_list_view(self) -> ListView:
        return self.query_one("#all-tags-list-view", ListView)

    @property
    def directory_tree(self) -> MarkdownDirectoryTree:
        return self.query_one("#directory-tree", MarkdownDirectoryTree)

    @property
    def is_browse_mode(self) -> bool:
        return self._browse_mode

    def toggle_browse_mode(self) -> None:
        """Toggle between All Tags view and Browse view."""
        self._browse_mode = not self._browse_mode

        all_tags_section = self.query_one("#all-tags-section")
        browse_section = self.query_one("#browse-section")

        if self._browse_mode:
            all_tags_section.add_class("hidden")
            browse_section.add_class("visible")
            self.directory_tree.focus()
        else:
            all_tags_section.remove_class("hidden")
            browse_section.remove_class("visible")
            self.all_tags_list_view.focus()

    def set_scan_directory(self, path: Path) -> None:
        """Set the root directory for the directory browser."""
        self._scan_directory = path
        # Update the directory tree if it exists
        try:
            tree = self.directory_tree
            tree.path = path
        except Exception:
            pass  # Tree not yet mounted

    def set_favorites(self, favorites: list[str]) -> None:
        """Set the list of favorite tag names."""
        self._favorites = [f.lower() for f in favorites]

    def update_tags(self, tags: list[tuple[str, int]]) -> None:
        """Update the list of tags with incremental updates."""
        # Save currently selected tag to restore after update
        selected_tag = self.get_selected_tag()

        self._all_tags = tags

        # Build favorites list from tags that match whitelist
        favorites_lower = set(self._favorites)
        favorite_tags = [(name, count) for name, count in tags if name.lower() in favorites_lower]

        # Update favorites list incrementally
        fav_list = self.favorites_list_view
        self._update_list_view(fav_list, favorite_tags)

        # Update all tags list incrementally
        all_list = self.all_tags_list_view
        self._update_list_view(all_list, tags)

        # Restore selection if the tag still exists
        if selected_tag:
            self._restore_selection(selected_tag)
        elif favorite_tags:
            fav_list.index = 0
        elif tags:
            all_list.index = 0

    def _update_list_view(
        self, list_view: ListView, new_tags: list[tuple[str, int]]
    ) -> None:
        """Update a ListView incrementally, only changing what's different."""
        new_tags_dict = {name: count for name, count in new_tags}
        existing_items = list(list_view.children)
        existing_tags = {
            item.tag_name: item for item in existing_items if isinstance(item, TagItem)
        }

        # Check if we can do an incremental update (same tags, possibly different counts)
        # If the set of tags changed, do a full rebuild for simplicity
        if set(new_tags_dict.keys()) != set(existing_tags.keys()):
            # Full rebuild needed - tags added or removed
            list_view.clear()
            for tag_name, count in new_tags:
                list_view.append(TagItem(tag_name, count))
            return

        # Incremental update - only update counts that changed
        for tag_name, new_count in new_tags_dict.items():
            item = existing_tags.get(tag_name)
            if item and item.count != new_count:
                # Update the count by replacing the label
                item.count = new_count
                label = item.query_one(Label)
                label.update(f"#{tag_name} ({new_count})")

    def _restore_selection(self, tag_name: str) -> None:
        """Restore selection to a specific tag if it exists."""
        # Try favorites first
        fav_list = self.favorites_list_view
        for i, item in enumerate(fav_list.children):
            if isinstance(item, TagItem) and item.tag_name == tag_name:
                fav_list.index = i
                return

        # Try all tags
        all_list = self.all_tags_list_view
        for i, item in enumerate(all_list.children):
            if isinstance(item, TagItem) and item.tag_name == tag_name:
                all_list.index = i
                return

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle tag selection from either list."""
        if isinstance(event.item, TagItem):
            self.post_message(self.TagSelected(event.item.tag_name))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from directory tree."""
        # Only handle supported files
        if event.path.suffix.lower() in (".md", ".taskpaper"):
            self.post_message(self.FileSelected(event.path))

    def get_selected_tag(self) -> str | None:
        """Get the currently selected tag name from either list."""
        # Check favorites list first
        fav_list = self.favorites_list_view
        if fav_list.has_focus and fav_list.highlighted_child is not None:
            item = fav_list.highlighted_child
            if isinstance(item, TagItem):
                return item.tag_name

        # Check all tags list
        all_list = self.all_tags_list_view
        if all_list.highlighted_child is not None:
            item = all_list.highlighted_child
            if isinstance(item, TagItem):
                return item.tag_name

        return None
