# Craft module

Status: **awaiting approval** — no phase started

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
- **Secrets**: connection URL and `pdk_` key are both secrets. Config stores `op://` references
  (`[craft] connection_url_ref`, `api_key_ref`); resolved lazily via `op read` on a worker thread at
  first use, as projection's SmartsheetClient does — never at startup, never stored in config.
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
- [ ] `craft.py`: lazy `op read` credential resolution, list_folders / list_documents /
      fetch_document_markdown, token stripping, TTL cache, `CraftError` with specific causes
- [ ] `[tools] craft` + `[craft]` config table (refs; `space_id` for the URL scheme), backfilled
- [ ] `widgets/craft_tree.py` panel; `active_source = "craft"`; Files/Preview follow it;
      focus order and vim keys treat the panel like the other optional ones
- [ ] `e` opens the selected Craft note in Craft.app
- Verify: `uv run pytest tests/test_craft.py tests/test_craft_panel.py -q`
- Status: not started

### Phase 6 — v1.5: prepend flow for meeting notes
Intent: compose a new occurrence in `$EDITOR` (temp `.md`), prepend it to the selected Craft note
via `POST /blocks`.
- [ ] One-time smoke test on a scratch doc first: does a multi-block insert at `position: "start"`
      preserve markdown order? If reversed, anchor with `"before"` + first block id instead
- [ ] Tag-line rule: when the doc's first body block is a tag-only line (`#tag` beneath the title),
      insert *after* it (`"after"` + `siblingId`); otherwise `position: "start"`
- [ ] `a` (or similar) on a Craft note: template with date heading, open editor, on save prepend;
      empty/unchanged buffer aborts without a write
- [ ] Refresh the preview after a successful prepend; report API errors verbatim
- Verify: `uv run pytest tests/test_craft_prepend.py -q`
- Status: not started

### Phase 7 — acceptance gate
Run once, at the end, against the real space:
- [ ] Launch `uv run librarian` with `[tools] craft = true`; browse folders; preview a real meeting
      note; `e` opens it in Craft.app; prepend a dated test occurrence to a scratch meeting note
      with a `#tag` beneath its title and confirm in Craft.app it landed below the tag line with
      block order intact; delete the test occurrence in Craft; disable `[tools] craft` and confirm
      the panel is gone and startup is unchanged
- Status: not started
