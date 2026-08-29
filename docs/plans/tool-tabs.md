# Full-width tool tabs

The stacked sidebar (Folders / Craft / Tags / Tools) becomes a full-width tab strip under the
banner — one boxed tab per enabled tool, full names — over a two-panel sidebar (active tree +
tags, 50/50) and the existing Files/Preview column. Signed-off mockup: artifact "Librarian
Tabbed Sidebar" rev 4, also `~/Downloads/sidebar-tabs-mockup.html`.

## Rulings

- 2026-08-28: "creat a mock-up wherein the tools, folder view, and craft are all tabs at the
  top. don't merge the browse tree for folders and craft since they would be different tabs."
- 2026-08-28: "I actually envisioned the tabs running the width of the terminal, as long as the
  header. that way you could list each tool fully: local folders, craft docs, projects,
  reminders, calendar, taskpaper. (but only setting each tool to true in config.toml would
  actually expose the tab at the top of the tui."
- 2026-08-28: "the 2 remaining sidebars on the left should each be 50%." / "can you create a
  nice tab square around each tab?"
- 2026-08-28: "that looks great! let's close on that design." Reminders/projects as modals:
  "could reminders and projects remain as a modal screen in this UI?" → launcher tabs keep the
  existing modals and snap back; the `q`-meaning redesign stays deferred. "yes and proceed with
  implementation."

## Design

- **Two kinds of tab.** Local Folders and Craft Docs are *workspace* tabs: activating one shows
  its tree in the sidebar, points the shared Tags panel at its scope, and sets `active_source`.
  TaskPaper, Reminders, Calendar, Projects are *launcher* tabs: activating one does what the
  Tools menu row does today (select #taskpaper / open the modal), then snaps the strip back to
  the last workspace tab. Modals and their key isolation are untouched.
- **One strip, app-owned.** A `Tabs` widget (not `TabbedContent`) under the Banner; the single
  FileList/Preview stay where they are, so all listing/preview/search/navigation machinery is
  untouched. TagList keeps both trees composed and shows one; the Tools panel is deleted.
- **Gating:** Local Folders tab when `folders` or `tags` is enabled; Craft Docs when `craft`;
  each launcher per its `[tools]` flag. Startup tab: Local Folders when present, else Craft
  Docs. Craft's lazy first fetch fires on first activation (focus-driven, as today).
- **Look:** boxed tabs (round border, active = accent, underline hidden); panel borders one
  neutral with a single accent on focus; headers one style; sidebar 50/50.

## Phases

### Phase 11 — the strip and workspace tabs  ⏳
`ToolTabs` widget + app compose; TagList loses the Tools panel and gains switched tree panels
(50/50 with Tags); tab activation drives `active_source`/tags scope/file panel; startup tab.
Verify: `uv run pytest tests/test_tool_tabs.py tests/test_folders_toggle.py tests/test_tags_toggle.py tests/test_craft_panel.py -q`

### Phase 12 — launcher tabs  ⏳
Launcher tabs invoke the existing tool actions and snap back to the last workspace tab; per-tool
gating; help text updated. ToolLaunched/ToolItem plumbing removed.
Verify: `uv run pytest tests/test_tool_tabs.py tests/test_reminders.py tests/test_projects.py tests/test_calendar_modal.py -q`

### Phase 13 — focus order, vim grid, border normalization  ⏳
FOCUS_ORDER/PANEL_GRID drop the Tools stop and treat the hidden tree as absent; the strip joins
the Tab cycle; borders/headers normalized per the mockup.
Verify: `uv run pytest tests/test_vim_navigation.py tests/test_tool_tabs.py -q`

### Phase 14 — docs  ⏳
CLAUDE.md UI Layout / Widget Communication / Keyboard Navigation sections rewritten; ROADMAP
sidebar item closed.
Verify: docs read true against the code (grep the claims).

### Phase 15 — acceptance gate  ⏳
One scripted pilot flow: launch with all tools on → startup tab Local Folders → switch to Craft
Docs (tags flip to CRAFT TAGS) → activate Calendar (modal opens, strip snaps back) → close →
folder listing intact → full suite green.
Verify: `uv run pytest -q` and `uv run pytest tests/test_tool_tabs.py::TestAcceptance -q`
