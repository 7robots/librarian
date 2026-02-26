"""Tag list widget with Tools sidebar for Librarian."""

from pathlib import Path
from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DirectoryTree, Label, ListItem, ListView, Static

from .calendar_list import CalendarList

# Maximum tags to display before showing "Show more" item
MAX_DISPLAY_TAGS = 200


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

    TagList #tools-panel {
        height: 1fr;
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

    TagList #content-panel {
        height: 1fr;
        border: solid $primary;
    }

    TagList #content-panel:focus-within {
        border: solid $primary-lighten-2;
    }

    TagList .content-section {
        height: 1fr;
    }

    TagList .content-section.hidden {
        display: none;
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

    TagList #placeholder-section {
        padding: 1 2;
        color: $text-muted;
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

    class ToolLaunched(Message):
        """Message emitted when a tool is selected from the Tools menu."""

        def __init__(self, tool_name: str) -> None:
            super().__init__()
            self.tool_name = tool_name

    class CalendarRefreshRequested(Message):
        """Message emitted when the calendar panel is shown and needs data."""

        pass

    def __init__(self, scan_directory: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._all_tags: list[tuple[str, int]] = []
        self._scan_directory = scan_directory or Path.home()
        self.active_tool: str = "tags"
        self._tags_show_all: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="tools-panel"):
            yield Static("\u2605 TOOLS", classes="tag-header", id="tools-header")
            yield ListView(
                ToolItem("Tags"),
                ToolItem("Folders"),
                ToolItem("TaskPaper"),
                ToolItem("Calendar"),
                ToolItem("Agents"),
                id="tools-list-view",
            )
        with Vertical(id="content-panel"):
            with Vertical(id="tags-section", classes="content-section"):
                yield Static("ALL TAGS", classes="tag-header", id="all-tags-header")
                yield ListView(id="all-tags-list-view")
            with Vertical(id="folders-section", classes="content-section hidden"):
                yield Static("FOLDERS", classes="tag-header", id="folders-header")
                yield MarkdownDirectoryTree(str(self._scan_directory), id="directory-tree")
            with Vertical(id="calendar-section", classes="content-section hidden"):
                yield CalendarList(id="calendar-list")
            yield Static(
                "Coming soon...",
                id="placeholder-section",
                classes="content-section hidden",
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

    def set_scan_directory(self, path: Path) -> None:
        """Set the root directory for the directory browser."""
        self._scan_directory = path
        try:
            tree = self.directory_tree
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

    @property
    def calendar_list(self) -> CalendarList:
        return self.query_one("#calendar-list", CalendarList)

    def _switch_panel(self, panel_name: str) -> None:
        """Hide all content sections, then show the requested one."""
        self.active_tool = panel_name
        tags_section = self.query_one("#tags-section")
        folders_section = self.query_one("#folders-section")
        calendar_section = self.query_one("#calendar-section")
        placeholder = self.query_one("#placeholder-section")

        for section in (tags_section, folders_section, calendar_section, placeholder):
            section.add_class("hidden")

        if panel_name == "tags":
            tags_section.remove_class("hidden")
            self.all_tags_list_view.focus()
        elif panel_name == "folders":
            folders_section.remove_class("hidden")
            self.directory_tree.focus()
        elif panel_name == "calendar":
            calendar_section.remove_class("hidden")
            self.calendar_list.list_view.focus()
            self.post_message(self.CalendarRefreshRequested())
        elif panel_name == "agents":
            placeholder.remove_class("hidden")
            placeholder.update("Agents \u2014 coming soon...")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection from tools menu or tag list."""
        item = event.item

        # Handle tools menu selection
        if isinstance(item, ToolItem):
            tool = item.tool_name.lower()
            if tool == "tags":
                self._switch_panel("tags")
            elif tool == "folders":
                self._switch_panel("folders")
            elif tool == "calendar":
                self._switch_panel("calendar")
            elif tool == "agents":
                self._switch_panel("agents")
            elif tool == "taskpaper":
                self.active_tool = "taskpaper"
                self.post_message(self.ToolLaunched("taskpaper"))
            return

        # Handle "Show more" item
        if isinstance(item, ShowMoreItem):
            self._tags_show_all = True
            self.update_tags(self._all_tags)
            return

        # Handle tag list selection
        if isinstance(item, TagItem):
            self.post_message(self.TagSelected(item.tag_name))

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from directory tree."""
        if event.path.suffix.lower() in (".md", ".taskpaper"):
            self.post_message(self.FileSelected(event.path))

    def get_selected_tag(self) -> str | None:
        """Get the currently selected tag name."""
        all_list = self.all_tags_list_view
        if all_list.highlighted_child is not None:
            item = all_list.highlighted_child
            if isinstance(item, TagItem):
                return item.tag_name

        return None
