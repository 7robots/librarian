# Craft module

Status: **phases 5–6 complete, review pass done 2026-08-28** — phase 7 (acceptance gate) remains

Review pass (fresh agent, 2026-08-28): 9 findings, all triaged fix-now and fixed — key-resolution
lock, deferred first fetch (no `op read` at startup), search-mode guard on the docs handler,
stale-refresh guard after prepend, timer-orphan fix, `craftdocs://` scheme check on `open`,
non-UTF-8 editor tolerance, unwrap regex word boundary, JSON-null tolerance. The one open question
(dangling `siblingId`) was closed live: the API 404s, no daily-note fallback.

A Craft browsing module mirroring the folder browser: a sidebar panel of Craft folders driving the
Files and Preview panels, backed by Craft's REST API (`connect.craft.do`), opt-in via
`[tools] craft`. Editing is prepend-only: new content is composed in the editor and inserted at the
top of an existing note, which fits the one-big-note-per-meeting-series style.

## Rulings

- 2026-08-28: "for editing, I'm partial to the v1.5 approach" (prepend/append-only writes; no
  whole-document replace).
- 2026-08-28: "create a 2 phase implementation plan for the craft module with v1 for phase 1 and
  v1.5 for phase 2. For v1.5, I'll want to do the prepend flow for adding blocks to meeting notes.
  the only preamble to keep in mind will be that some notes (mostly meeting notes) may have a #tag
  beneath the document title."
- 2026-08-28 (from the original request): "I'd want to be able to browse my craft folders, view
  notes, and then load them into default editor to edit."

## Design decisions

- **Surface**: REST API, not the MCP server — static bearer auth, works with Craft.app closed,
  returns markdown directly. `GET /folders`, `GET /documents?folderId=`, `GET /blocks?id=` with
  `Accept: text/markdown`, `POST /blocks` for prepend.
- **Secrets**: config stores the connection URL plainly (`[craft] api_url`, provided directly by
  Jefferson; useless without the key) and a 1Password reference for the key (`api_key_ref` =
  `op://Employee/Craft API Key/credential`), resolved lazily via `op read` on a worker thread at
  first use, as projection's SmartsheetClient does — never at startup, never the value in config.
- **HTTP client**: stdlib `urllib.request` — simple JSON GET/POST with timeouts; no new dependency
  for an opt-in module.
- **UI**: `[tools] craft = false` (default). On: a CRAFT panel joins the sidebar (a Textual `Tree`
  of folders), `active_source` gains `"craft"`, the Files panel lists the selected folder's docs,
  Preview shows fetched markdown. Craft tokens (`<callout>`, `<highlight>`, `<page>`, `<caption>`)
  are stripped before rendering.
- **Failures**: `CraftError` raised, never an empty listing shown for a broken backend — same
  contract as `calendar.py`. TTL cache on folder/doc listings; fetches on workers with
  `exit_on_error=False`.
- **Write safety**: the client hard-requires `pageId` on every insert — the API silently routes an
  unanchored insert into today's daily note.
- **Review pass**: this plan touches secrets handling, so a fresh-agent review runs once, after
  Phase 6 and before the acceptance gate.

## Phases

### Phase 5 — v1: read-only browse, preview, open in Craft
Intent: `craft.py` client (folders, docs, doc-as-markdown) + sidebar panel + preview; `e` on a Craft
note opens it in Craft.app via `craftdocs://open?spaceId=&blockId=`.
- [x] `craft.py`: lazy `op read` credential resolution, list_folders / list_documents /
      fetch_document_markdown, token stripping, TTL cache, `CraftError` with specific causes
- [x] `[tools] craft` + `[craft]` config table (`api_url`, `api_key_ref`), backfilled
- [x] `widgets/craft_tree.py` panel; `active_source = "craft"`; Files/Preview follow it;
      focus order and vim keys treat the panel like the other optional ones
- [x] `e` opens the selected Craft note in Craft.app via `clickableLink` (used verbatim — its
      `documentId` is not the API `id`; no `space_id` config needed)
- Verify: `uv run pytest tests/test_craft.py tests/test_craft_panel.py -q` — 32 passed 2026-08-28,
  plus a live end-to-end client check against the real space
- Status: **complete 2026-08-28**

### Phase 6 — v1.5: prepend flow for meeting notes
Intent: compose a new occurrence in `$EDITOR` (temp `.md`), prepend it to the selected Craft note
via `POST /blocks`.
- [x] Smoke test on a scratch doc: multi-block insert at `position: "start"` **preserves markdown
      order** (verified live 2026-08-28), so no `"before"` workaround is needed
- [x] Tag-line rule: when the doc's first body block is a tag-only line (`#tag` beneath the title),
      insert *after* it (`"after"` + `siblingId`); otherwise `position: "start"`
- [x] `a` on a Craft note: `## <date>` template, editor via suspend, on save prepend;
      empty/unchanged buffer aborts without a write. The key falls through to the calendar's
      associate binding whenever no Craft doc is selected (`check_action`)
- [x] Preview refreshes after a successful prepend (client invalidates the doc's markdown cache);
      API errors notified verbatim
- Verify: `uv run pytest tests/test_craft_prepend.py -q` — 18 passed 2026-08-28, plus a live
  end-to-end prepend on a scratch doc with a tag line (placement and order confirmed, then deleted)
- Status: **complete 2026-08-28**

### Phase 7 — acceptance gate
Run once, at the end, against the real space:
- [ ] Launch `uv run librarian` with `[tools] craft = true`; browse folders; preview a real meeting
      note; `e` opens it in Craft.app; prepend a dated test occurrence to a scratch meeting note
      with a `#tag` beneath its title and confirm in Craft.app it landed below the tag line with
      block order intact; delete the test occurrence in Craft; disable `[tools] craft` and confirm
      the panel is gone and startup is unchanged
- Status: not started
