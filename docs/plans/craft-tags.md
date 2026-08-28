# Craft tags: a source-scoped Tags panel

Status: **phases 8–9 complete 2026-08-28** — phase 10 (acceptance gate) remains

The Tags panel follows the active browsing source: local index tags while browsing Folders, Craft
tags while browsing the Craft tree. Selecting a Craft tag lists its documents in the Files panel.
Feasibility and API shapes were verified live 2026-08-28 (see `docs/ROADMAP.md` "Craft tags
browser", which this plan implements).

## Rulings

- 2026-08-28: "go ahead and do the source-scoped tags panel"
- 2026-08-28 (design agreed in conversation): source-scoped beats a fixed priority order — "perhaps
  there should be a preference order for the tags browser with craft taking higher priority over
  folders. if you have a better idea, let me know!" → scoped panel accepted.

## Design decisions

- **Discovery**: one space-wide `GET /documents/search?regexps=(^|\s)#[a-zA-Z][a-zA-Z0-9_-]+` with
  `fetchBlocks=true`; tags extracted from the returned blocks' raw markdown (snippets bold matches,
  so extraction uses blocks, not snippets). Counts = unique documents per tag. Verified: the
  documented top-20 cap does not apply (83 matches returned).
- **Per-tag listing**: `GET /documents/search?regexps=(^|\s)#<tag>\b` — results arrive
  newest-modified first and carry no title, so titles resolve per doc via
  `GET /blocks?id=&maxDepth=0` (root markdown = title), cached.
- **Open-in-Craft from a tag listing**: search results carry no `clickableLink`; links are built
  from `GET /connection`'s `urlTemplates.app` (`blockId={blockId}`, and the API doc id *is* the
  root block id). Whether such links open correctly is a gate item — listings' native links use a
  different `documentId`.
- **Tag semantics mirror the scanner**: same pattern, case-insensitive dedupe keeping first-seen
  casing, sorted count-desc then name — the two panels should feel like one feature.
- **State**: `TagList.tags_scope` ("local" | "craft") switches with the tree last highlighted;
  the header reads ALL TAGS / CRAFT TAGS. `active_source` gains `"craft-tags"` for a Craft tag
  driving the Files panel, so index updates and search-exit know what to restore.
- No new secrets surface (reuses the existing client/auth), so no fresh review pass this plan.

## Phases

### Phase 8 — client: tag discovery, per-tag docs, titles, links
- [x] `search_tags()` — discovery + extraction + counts, TTL-cached. Extraction reads the search
      *snippets* with bold match-markers stripped — `fetchBlocks` returns the enclosing page block
      (the title) for most matches, so snippets are the only faithful source. Live check: discovery
      counts equal per-tag query counts exactly (66/9/1)
- [x] `search_documents_by_tag(tag)` — deduped, newest-first; docs known from cached folder
      listings come free with their real `clickableLink`, the rest resolve titles on a two-worker
      pool with template links. A full folder walk was rejected (116 folders, ~75s live); six
      workers tripped the rate limit, hence `_request`'s one retry on 5xx/429 honoring Retry-After
- [x] `fetch_document_title(doc_id)` and `app_url_for(block_id)` (from `/connection`), cached
- Verify: `uv run pytest tests/test_craft_tags.py -q` — 13 client tests + live checks
- Status: **complete 2026-08-28**

### Phase 9 — UI: the scoped panel and craft-tag browsing
- [x] `tags_scope` switches with tree highlights; header flips ALL TAGS / CRAFT TAGS; each scope's
      list is kept and restored without refetching (a background rescan while Craft-scoped stores
      the new local tags rather than painting them)
- [x] Selecting a Craft tag lists its docs (`FILES (craft: #tag)`, with a loading notify — a cold
      busy tag takes ~10–30s); preview, `e`, and `a` (prepend) work from a tag listing;
      `active_source = "craft-tags"` survives index updates and search exit; `t` forces the scope
      back to local before hunting for #taskpaper
- Verify: `uv run pytest tests/test_craft_tags.py tests/test_craft_panel.py -q` — 20 + 15 passed;
  full suite 577
- Status: **complete 2026-08-28**

### Phase 10 — acceptance gate
Run once, at the end, against the real space:
- [ ] Launch with folders+tags+craft all on. Browse local folders (ALL TAGS shows index tags);
      move into the Craft tree (header flips to CRAFT TAGS, the three real tags appear with
      counts); select `#meetings` (its docs list with correct titles, newest first); preview one;
      `e` opens the *right* document in Craft.app (the template-link gate item); `a` prepends to
      it; move back to the folder tree and confirm ALL TAGS returns with the local tags intact
- Status: not started
