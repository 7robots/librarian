"""Tag list widget for browsing discovered tags."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Label, ListItem, ListView, Static


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
        color: $text;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }

    TagList ListView {
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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._all_tags: list[tuple[str, int]] = []
        self._favorites: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="tag-section"):
            yield Static("FAVORITES", classes="tag-header")
            yield ListView(id="favorites-list-view")
        with Vertical(classes="tag-section"):
            yield Static("ALL TAGS", classes="tag-header")
            yield ListView(id="all-tags-list-view")

    @property
    def favorites_list_view(self) -> ListView:
        return self.query_one("#favorites-list-view", ListView)

    @property
    def all_tags_list_view(self) -> ListView:
        return self.query_one("#all-tags-list-view", ListView)

    def set_favorites(self, favorites: list[str]) -> None:
        """Set the list of favorite tag names."""
        self._favorites = [f.lower() for f in favorites]

    def update_tags(self, tags: list[tuple[str, int]]) -> None:
        """Update the list of tags."""
        self._all_tags = tags

        # Build favorites list from tags that match whitelist
        favorites_lower = set(self._favorites)
        favorite_tags = [(name, count) for name, count in tags if name.lower() in favorites_lower]

        # Update favorites list
        fav_list = self.favorites_list_view
        fav_list.clear()
        for tag_name, count in favorite_tags:
            fav_list.append(TagItem(tag_name, count))

        # Update all tags list
        all_list = self.all_tags_list_view
        all_list.clear()
        for tag_name, count in tags:
            all_list.append(TagItem(tag_name, count))

        # Highlight first item in favorites if available, otherwise all tags
        if favorite_tags:
            fav_list.index = 0
        elif tags:
            all_list.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle tag selection from either list."""
        if isinstance(event.item, TagItem):
            self.post_message(self.TagSelected(event.item.tag_name))

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
