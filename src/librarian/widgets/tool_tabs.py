"""The full-width tool tab strip under the banner.

One boxed tab per enabled tool, full names. Two kinds of tab, distinguished by
`is_workspace_tab`:

- **Workspace tabs** (Local Folders, Craft Docs) own the content below: the
  sidebar shows their tree, the Tags panel follows their scope, and
  `active_source` tracks them.
- **Launcher tabs** (TaskPaper, Reminders, Calendar, Projects) act like the old
  Tools menu rows: activating one launches the tool -- a modal, or the
  #taskpaper tag selection -- and the strip snaps back to the last workspace
  tab, so the content underneath never changes hands.

Only tools set true in ``[tools]`` expose a tab; the strip is built from the
flags once, at compose time, the same way the old Tools menu was.
"""

from textual.widgets import Tab, Tabs

# Workspace tabs, in strip order. Local Folders leads for the same reason the
# folder tree led the old sidebar: content is organized by folder.
WORKSPACE_TAB_LOCAL = "tab-local"
WORKSPACE_TAB_CRAFT = "tab-craft"

# Launcher tabs, in the Tools catalog order (tag_list.ALL_TOOLS).
LAUNCHER_TAB_IDS: dict[str, str] = {
    "taskpaper": "tab-taskpaper",
    "reminders": "tab-reminders",
    "calendar": "tab-calendar",
    "projects": "tab-projects",
}
LAUNCHER_LABELS: dict[str, str] = {
    "taskpaper": "TaskPaper",
    "reminders": "Reminders",
    "calendar": "Calendar",
    "projects": "Projects",
}


def launcher_tool_for(tab_id: str | None) -> str | None:
    """The tool a launcher tab id names, or None for workspace/unknown ids."""
    for tool, known_id in LAUNCHER_TAB_IDS.items():
        if tab_id == known_id:
            return tool
    return None


def is_workspace_tab(tab_id: str | None) -> bool:
    return tab_id in (WORKSPACE_TAB_LOCAL, WORKSPACE_TAB_CRAFT)


class ToolTabs(Tabs):
    """Boxed, full-width tabs: each tab in its own frame, the active one in
    the accent color. The stock underline is redundant with the boxes."""

    DEFAULT_CSS = """
    ToolTabs {
        height: 3;
    }

    ToolTabs Tab {
        height: 3;
        padding: 0 2;
        margin: 0 1 0 0;
        border: round $panel-lighten-2;
        color: $foreground 50%;
    }

    ToolTabs Tab.-active {
        border: round $accent;
        color: $foreground;
    }

    ToolTabs Underline {
        display: none;
    }
    """

    def __init__(
        self,
        show_local: bool,
        show_craft: bool,
        launchers: tuple[str, ...] = (),
        **kwargs,
    ) -> None:
        """Build the strip from the config flags.

        Args:
            show_local: Show the Local Folders workspace tab (folders or tags
                panel enabled).
            show_craft: Show the Craft Docs workspace tab.
            launchers: Enabled launcher tools, lowercase, in display order.
        """
        tabs: list[Tab] = []
        if show_local:
            tabs.append(Tab("Local Folders", id=WORKSPACE_TAB_LOCAL))
        if show_craft:
            tabs.append(Tab("Craft Docs", id=WORKSPACE_TAB_CRAFT))
        for tool in launchers:
            tab_id = LAUNCHER_TAB_IDS.get(tool.lower())
            if tab_id is not None:
                tabs.append(Tab(LAUNCHER_LABELS[tool.lower()], id=tab_id))
        super().__init__(*tabs, **kwargs)
