"""Navigation action handlers for LibrarianApp."""

from __future__ import annotations

from pathlib import Path

from textual.containers import ScrollableContainer
from textual.widgets import ListView, Tree

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
        elif widget_id == "craft-tree":
            return tag_list.craft_tree
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
            id(tag_list.all_tags_list_view): 2,
            id(tag_list.tools_list_view): 3,
            id(file_list.list_view): 4,
            id(preview.scroll_view): 5,
        }
        # The folder browser and Craft panels are optional, so either tree may
        # not exist at all.
        tree = tag_list.directory_tree
        if tree is not None:
            focus_map[id(tree)] = 0
        craft = tag_list.craft_tree
        if craft is not None:
            focus_map[id(craft)] = 1
        return focus_map.get(id(focused), -1)

    def action_focus_next(self) -> None:
        """Focus the next panel, down the left column and then the right."""
        self._focus_step(1)

    def action_focus_previous(self) -> None:
        """Focus the previous panel."""
        self._focus_step(-1)

    # --- vim panel movement -------------------------------------------------
    #
    # `ctrl+w` arms a prefix; the next h/j/k/l moves focus. Textual has no chord
    # bindings, so the prefix is state plus `check_action()`: the direction keys
    # are declared `priority=True` and reported *disabled* until the prefix is
    # pending, which leaves them falling through to the focused widget the rest
    # of the time. `refresh_bindings()` after every change to the flag is what
    # makes Textual re-ask.

    #: How long a lone `ctrl+w` waits for its direction, as vim's timeoutlen does.
    VIM_PREFIX_TIMEOUT = 2.0

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable the vim bindings unless the config switch and prefix allow."""
        if action == "vim_prefix":
            return self.config.keys.vim
        if action == "vim_focus":
            return self.config.keys.vim and self._vim_pending
        if action in ("vim_cursor", "vim_edge", "vim_expand", "vim_collapse"):
            return self.config.keys.vim
        return super().check_action(action, parameters)

    def action_vim_prefix(self) -> None:
        """Arm `ctrl+w`, so the next h/j/k/l moves between panels."""
        self._vim_pending = True
        self.refresh_bindings()
        if self._vim_prefix_timer is not None:
            self._vim_prefix_timer.stop()
        self._vim_prefix_timer = self.set_timer(
            self.VIM_PREFIX_TIMEOUT, self._clear_vim_prefix
        )

    def _clear_vim_prefix(self) -> None:
        """Disarm the prefix, giving h/j/k/l back to the focused widget."""
        if self._vim_prefix_timer is not None:
            self._vim_prefix_timer.stop()
            self._vim_prefix_timer = None
        if self._vim_pending:
            self._vim_pending = False
            self.refresh_bindings()

    def action_vim_focus(self, direction: str) -> None:
        """Move focus one panel in `direction` (left/right/up/down)."""
        self._clear_vim_prefix()

        position = self._vim_position()
        if position is not None:
            column, row = position
            # Record where we are leaving from before moving, so h/l can come
            # back here -- including when the panel was reached with Tab.
            self._vim_column[column] = self.PANEL_GRID[column][row]

        target = self._vim_target(direction, position)
        if target is None:
            return

        widget = self._get_focus_widget(target)
        if widget is None:
            return
        widget.focus()
        for index, panels in enumerate(self.PANEL_GRID):
            if target in panels:
                self._vim_column[index] = target

    def _vim_position(self) -> tuple[int, int] | None:
        """(column, row) of the focused panel, or None if focus is elsewhere."""
        index = self._get_current_focus_index()
        if index == -1:
            return None
        widget_id = self.FOCUS_ORDER[index]
        for column, panels in enumerate(self.PANEL_GRID):
            if widget_id in panels:
                return column, panels.index(widget_id)
        return None

    def _vim_target(
        self, direction: str, position: tuple[int, int] | None
    ) -> str | None:
        """The panel id `direction` leads to, or None to stay put."""
        wanted = {"left": 0, "right": 1}.get(direction)

        if position is None:
            # Focus is somewhere unrecognised (or nowhere). Land in the column
            # the key points at rather than doing nothing.
            return self._vim_remembered(wanted if wanted is not None else 0)

        column, row = position
        if wanted is None:
            return self._vim_vertical(column, row, -1 if direction == "up" else 1)
        if wanted == column:
            return None  # already the leftmost/rightmost column, as in vim
        return self._vim_remembered(wanted)

    def _vim_vertical(self, column: int, row: int, step: int) -> str | None:
        """The next focusable panel up or down this column.

        No wraparound -- `ctrl+w j` at the bottom of a column stays there, which
        is what vim does. Tab still wraps; the two are different gestures.
        """
        panels = self.PANEL_GRID[column]
        row += step
        while 0 <= row < len(panels):
            if self._get_focus_widget(panels[row]) is not None:
                return panels[row]
            row += step  # e.g. an empty Tools panel, which is not a stop
        return None

    def _vim_remembered(self, column: int) -> str | None:
        """The panel last focused in `column`, or its first focusable one."""
        remembered = self._vim_column[column]
        if self._get_focus_widget(remembered) is not None:
            return remembered
        # The remembered panel can vanish -- Tools empties when its last tool is
        # disabled -- so fall back rather than refusing to move.
        for widget_id in self.PANEL_GRID[column]:
            if self._get_focus_widget(widget_id) is not None:
                return widget_id
        return None

    # --- vim movement inside a panel ----------------------------------------
    #
    # One dispatcher on `self.focused` rather than bindings on four widgets: the
    # panels are a Tree, three ListViews and a VerticalScroll, none of which
    # binds a vim key of its own, and keeping the keys here means the config
    # switch turns all of them off in one place.

    def action_vim_cursor(self, direction: str) -> None:
        """Move the focused panel's cursor, or scroll the preview."""
        widget = self.focused
        if widget is None:
            return
        down = direction == "down"
        if isinstance(widget, (Tree, ListView)):
            widget.action_cursor_down() if down else widget.action_cursor_up()
        elif isinstance(widget, ScrollableContainer):
            widget.scroll_down(animate=False) if down else widget.scroll_up(
                animate=False
            )

    def action_vim_edge(self, edge: str) -> None:
        """`g`/`G`: jump to the top or bottom of the focused panel."""
        widget = self.focused
        bottom = edge == "bottom"
        if isinstance(widget, Tree):
            # Tree binds no home/end action, and scrolling alone would leave the
            # cursor behind -- which is the thing being moved.
            widget.cursor_line = widget.last_line if bottom else 0
        elif isinstance(widget, ListView):
            count = len(widget.children)
            if count:
                widget.index = count - 1 if bottom else 0
        elif isinstance(widget, ScrollableContainer):
            widget.scroll_end(animate=False) if bottom else widget.scroll_home(
                animate=False
            )

    def action_vim_expand(self) -> None:
        """`l` in a tree: expand, or step into an open folder.

        Acts on the focused tree -- there are two now (Folders and Craft), and
        `_vim_tree_node` already guarantees `self.focused` is a Tree.
        """
        node = self._vim_tree_node()
        if node is None:
            return
        if node.allow_expand and not node.is_expanded:
            node.expand()
        elif node.children:
            self.focused.move_cursor(node.children[0])

    def action_vim_collapse(self) -> None:
        """`h` in a tree: collapse, or step out to the parent."""
        node = self._vim_tree_node()
        if node is None:
            return
        if node.is_expanded:
            node.collapse()
        elif node.parent is not None:
            self.focused.move_cursor(node.parent)

    def _vim_tree_node(self):
        """The folder tree's cursor node, or None when the tree is not focused."""
        focused = self.focused
        if not isinstance(focused, Tree):
            return None
        return focused.cursor_node

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
        if tag_list.active_source == "craft" and tag_list.craft_tree is not None:
            tag_list.craft_tree.focus()
            return
        tree = tag_list.directory_tree
        if tag_list.active_source == "tags" or tree is None:
            tag_list.all_tags_list_view.focus()
        else:
            tree.focus()

    def action_help(self) -> None:
        """Show help information."""
        keys = ["s=Search", "n=New", "e=Edit", "d=Delete", "x=Export", "r=Rename", "m=Move"]
        if self.config.tools.taskpaper:
            keys.append("t=TaskPaper")
        if self.config.tools.calendar:
            keys.append("a=Associate")
        keys.extend(["u=Update", "q=Quit"])
        if self.config.keys.vim:
            keys.append("j/k=Move, ctrl+w+hjkl=Panel")
        self.notify(", ".join(keys), timeout=5)
