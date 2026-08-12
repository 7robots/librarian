"""Navigation action handlers for LibrarianApp."""

from __future__ import annotations

from pathlib import Path

from ..database import resolve_wiki_link
from ..navigation import NavigationState
from ..widgets import FileList, Preview, TagList
from ..widgets.calendar_list import CalendarList


class NavigationActionsMixin:
    """Mixin providing navigation actions (focus, back, wiki links, search, help)."""

    def _get_focus_widget(self, widget_id: str):
        """Get a focusable widget by ID."""
        tag_list = self.query_one("#tag-list", TagList)
        if widget_id == "tools-list-view":
            tools = tag_list.tools_list_view
            # With every tool optional, the menu can be empty; an empty panel is
            # not worth a Tab stop.
            return tools if list(tools.children) else None
        elif widget_id == "directory-tree":
            return tag_list.directory_tree
        elif widget_id == "all-tags-list-view":
            return tag_list.all_tags_list_view
        elif widget_id == "file-list-view":
            return self.query_one("#file-list", FileList).list_view
        elif widget_id == "preview":
            return self.query_one("#preview", Preview).scroll_view
        return None

    def _get_current_focus_index(self) -> int:
        """Get the index of the currently focused widget in FOCUS_ORDER."""
        focused = self.focused
        if focused is None:
            return -1

        tag_list = self.query_one("#tag-list", TagList)
        file_list = self.query_one("#file-list", FileList)
        preview = self.query_one("#preview", Preview)

        focus_map = {
            id(tag_list.directory_tree): 0,
            id(tag_list.all_tags_list_view): 1,
            id(tag_list.tools_list_view): 2,
            id(file_list.list_view): 3,
            id(preview.scroll_view): 4,
        }
        return focus_map.get(id(focused), -1)

    def action_focus_next(self) -> None:
        """Focus the next panel, down the left column and then the right."""
        self._focus_step(1)

    def action_focus_previous(self) -> None:
        """Focus the previous panel."""
        self._focus_step(-1)

    def _focus_step(self, direction: int) -> None:
        """Move focus by one stop, skipping panels that have nothing to focus."""
        index = self._get_current_focus_index()
        for _ in range(len(self.FOCUS_ORDER)):
            index = (index + direction) % len(self.FOCUS_ORDER)
            widget = self._get_focus_widget(self.FOCUS_ORDER[index])
            if widget is not None:
                widget.focus()
                return

    async def on_preview_wiki_link_clicked(
        self, event: Preview.WikiLinkClicked
    ) -> None:
        """Handle wiki link clicks in the preview."""
        resolved = resolve_wiki_link(
            event.target, event.current_file, self.config.scan_directory
        )

        if resolved is None:
            self.notify(f"Link target not found: {event.target}", severity="warning")
            return

        file_list = self.query_one("#file-list", FileList)
        tag, files, index = file_list.get_navigation_info()
        header_text = file_list.get_header_text()
        state = NavigationState(
            tag=tag,
            files=files,
            selected_index=index,
            header_text=header_text,
        )
        self._nav_stack.push(state)

        file_list.update_files([resolved], navigation_target=resolved.name)

        preview = self.query_one("#preview", Preview)
        await preview.show_file(resolved)

        def activate_file_list():
            file_list.list_view.focus()
            if len(file_list._files) > 1:
                file_list.list_view.action_cursor_down()
                file_list.list_view.action_cursor_up()

        self.set_timer(0.1, activate_file_list)

    async def action_go_back(self) -> None:
        """Go back in navigation history or exit search mode."""
        file_list = self.query_one("#file-list", FileList)
        if file_list.is_search_mode():
            file_list.exit_search_mode()
            return

        if self._nav_stack.is_empty():
            return

        state = self._nav_stack.pop()
        if state is None:
            return

        file_list = self.query_one("#file-list", FileList)
        file_list.restore_state(
            files=state.files,
            tag=state.tag,
            selected_index=state.selected_index,
            header_text=state.header_text,
        )

        if state.files and 0 <= state.selected_index < len(state.files):
            preview = self.query_one("#preview", Preview)
            await preview.show_file(state.files[state.selected_index])

        def activate_file_list():
            file_list.list_view.focus()
            if len(state.files) > 1:
                file_list.list_view.action_cursor_down()
                file_list.list_view.action_cursor_up()

        self.set_timer(0.1, activate_file_list)

    def action_search(self) -> None:
        """Enter search mode."""
        file_list = self.query_one("#file-list", FileList)
        if not file_list.is_search_mode():
            file_list.enter_search_mode()

    def on_file_list_search_mode_exited(
        self, event: FileList.SearchModeExited
    ) -> None:
        """Handle search mode exit - restore the previous listing and focus.

        Leaving search clears the Files panel, so repopulate it for whichever
        tool is active instead of leaving the user looking at an empty list.
        """
        self._refresh_file_panel()

        # Back to whichever panel drives the Files list.
        tag_list = self.query_one("#tag-list", TagList)
        if tag_list.active_source == "tags":
            tag_list.all_tags_list_view.focus()
        else:
            tag_list.directory_tree.focus()

    def action_help(self) -> None:
        """Show help information."""
        keys = ["s=Search", "n=New", "e=Edit", "d=Delete", "x=Export", "r=Rename", "m=Move"]
        if self.config.tools.taskpaper:
            keys.append("t=TaskPaper")
        if self.config.tools.calendar:
            keys.append("a=Associate")
        keys.extend(["u=Update", "q=Quit"])
        self.notify(", ".join(keys), timeout=5)
