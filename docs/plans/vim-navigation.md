# Vim navigation keys

Status: **complete 2026-08-17** — all four phases landed and verified
Opened: 2026-08-17

## Goal

Optional vim-style keys across Librarian's five panels, off by default, on for
this machine. Two layers, deliberately separated so neither steals the other's
keys:

| Layer | Keys | Meaning |
|---|---|---|
| Between panels | `ctrl+w` then `h` `j` `k` `l` | move focus, vim-window style |
| Within a panel | `j` `k` `g` `G`, plus `h`/`l` on the folder tree | move the cursor / scroll / collapse-expand |

Binding bare `hjkl` to *panel* movement was rejected: nothing in Textual 8.2.8
binds `j`/`k` today (checked — `ListView`, `Tree`, `VerticalScroll` bind only
arrows), so spending them on panel switching would permanently foreclose the
meaning a vim user reaches for first.

## Verified before planning

- No `h`/`j`/`k`/`l`/`g`/`ctrl+w` binding exists anywhere in `src/librarian/`.
- `Input._on_key` calls `event.stop()` on printable keys, so search mode keeps
  working — provided the new bindings are **not** `priority=True`... except the
  prefixed ones, which must be (see below).
- The prefix mechanism works and is spiked: app-level `priority=True` bindings
  for `hjkl` gated by `check_action()` returning `False` until `ctrl+w` is
  pressed. With the prefix inactive the key falls through to the focused widget
  (spike: bare `j` moved a ListView cursor 0→1); with it active the app
  intercepts and the widget cursor does not move. `refresh_bindings()` after
  each flag change.
- Modals (`CalendarModal`, `RemindersModal`, `ProjectsModal`) are `ModalScreen`s,
  which block app bindings entirely — vim keys stop at the modal boundary, which
  is correct, since the guests carry their own.

## Panel geometry

`FOCUS_ORDER` is a flat list; direction needs a grid:

```
left  = directory-tree, all-tags-list-view, tools-list-view   # tools may be absent
right = file-list-view, preview
```

- `j`/`k` step within the column, skipping any stop whose `_get_focus_widget()`
  returns `None` — the same rule that already keeps an empty Tools panel out of
  the Tab cycle.
- **No wraparound.** `ctrl+w j` at the bottom of a column stays put, matching vim.
  (Tab keeps wrapping; it is unchanged.)
- `h`/`l` switch column and land on the panel last focused in that column,
  defaulting to `directory-tree` / `file-list-view`. The rows do not line up
  (left is `1fr/1fr/auto`, right `33%/67%`), so there is no honest "the panel
  level with this one"; last-focused is the rule that never surprises.
- The prefix clears when consumed, and on a 2-second timer otherwise.

## Phases

### Phase 1 — the config switch  ✅ `a2a2c39`

`[keys] vim = false`, a new `KeysConfig` dataclass on `Config`.

- `config.py`: `KeysConfig(vim: bool = False)`, field on `Config`, parsed in
  `load()`, written by `save()`, and one `_CONFIG_KEYS` entry
  `("keys", "vim", "false", ...)` so existing config files gain the key on next
  launch.
- Tests: default is off in `test_config.py`; backfill appends `[keys] vim` to a
  file written before the setting existed, in `test_config_migration.py`.

Verify: `uv run pytest tests/test_config.py tests/test_config_migration.py -q`

### Phase 2 — panel movement (`ctrl+w` + `hjkl`)  ✅ `2278c7b`

- `app.py`: `PANEL_GRID` next to `FOCUS_ORDER`; four `priority=True` bindings
  plus `ctrl+w`, all `show=False`.
- `actions/navigation_actions.py`: `action_vim_prefix()`, `action_vim_focus(dir)`,
  `_vim_target(dir)` reusing `_get_focus_widget()`, and `check_action()` gating
  every one of them on `self.config.keys.vim` — so with the switch off the
  bindings are inert and `ctrl+w` still means delete-word-left in an `Input`.
- Tests: new `tests/test_vim_navigation.py` — each direction from each panel;
  Tools skipped when empty and stepped onto when enabled; no wraparound at the
  ends; `h`/`l` remember the column; prefix expires; **and everything above is a
  no-op with `vim = false`**.

Verify: `uv run pytest tests/test_vim_navigation.py -q`

### Phase 3 — in-panel keys  ✅ `64366aa`

One app-level action rather than bindings on four widgets: `j`/`k`/`g`/`G` and
`h`/`l` dispatch on `self.focused` (`action_cursor_down`/`_up` on Tree and
ListView, `scroll_down`/`scroll_up`/`scroll_home`/`scroll_end` on the preview's
`VerticalScroll`, collapse/expand for `h`/`l` on the tree only). Non-priority, so
a focused `Input` keeps swallowing them; `check_action`-gated like Phase 2.

Tests appended to `tests/test_vim_navigation.py`: cursor moves in each of the
five panels; `s` then typing `hjkl` searches for the text rather than moving;
all inert with `vim = false`.

Verify: `uv run pytest tests/test_vim_navigation.py -q`

### Phase 4 — docs, help text, and turn it on here  ✅

- `action_help()` appends the vim keys only when enabled.
- `CLAUDE.md`: a "Vim navigation" section — the two layers, why they are split,
  why the prefix needs `check_action` rather than a chord binding.
- Set `[keys] vim = true` in `~/.config/librarian/config.toml`.

Verify: `uv run pytest -q` (full suite, once) and launch `uv run librarian` to
confirm the keys move focus for real.

## Out of scope

- Vim keys inside the Calendar/Reminders/Projects modals — those belong to the
  guest panels.
- `ctrl+w` variants beyond `hjkl` (`w`, `W`, `t`, `b`, splits, resizing).
- Any change to Tab/shift+Tab.

## Outcome

All four phases landed. What changed against the plan:

- **`priority=True` is defensive, not load-bearing.** The plan assumed it was what made the prefix
  win. Mutation testing says otherwise: dropping it alone passes, and so does listing the in-panel
  bindings first alone — only removing both fails (ten tests). It stays so that reordering `BINDINGS`
  cannot quietly break the prefix, and both the code comment and CLAUDE.md say that rather than
  overstating it.
- **`h`/`l` on the tree do expand-or-step-in and collapse-or-step-out**, not plain expand/collapse —
  the tree idiom, and no more code.
- The vault fixture grew to three root files: with one, `j` and `G` on a list passed whether or not
  they did anything.

Verified: `uv run pytest -q` → 479 passed. Plus an end-to-end run against the real
`~/.config/librarian/config.toml` and vault, driving `ctrl+w`+`hjkl` through all five panels.
`[keys] vim = true` is set on this machine.
