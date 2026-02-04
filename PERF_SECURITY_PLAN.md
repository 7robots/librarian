# Librarian Performance & Security Implementation Plan

Date: 2026-02-02

This plan prioritizes fixes from the performance/security review. Each item includes scope, rationale, and suggested verification.

## P0 — Security / Data Integrity (do first)

### 1) Sanitize HTML export output
**Why:** Exported HTML currently trusts markdown and filename inputs, which can embed unsafe HTML and break document structure. This is the highest user‑visible security risk.

**Scope:**
- Escape document title before injecting into `<title>`.
- Sanitize markdown output (or disable raw HTML) before writing HTML.

**Suggested changes:**
- Escape `title` in `markdown_to_html()` using `html.escape()`.
- Add sanitization (e.g., `bleach.clean`) or configure Markdown to escape raw HTML.
- Add tests for `<script>` in markdown and a filename containing `<` or `"`.

**Files:**
- `src/librarian/export.py`

**Verification:**
- Export a markdown file containing raw HTML (`<script>`) and confirm output is sanitized.
- Export a file with a filename like `bad<title>.md` and confirm valid HTML.

### 2) Remove WeasyPrint and PDF export
**Why:** Eliminate the PDF export path to simplify dependencies and reduce security surface area.

**Scope:**
- Remove PDF export code path and WeasyPrint dependency.
- Update UI/help text and README to indicate HTML-only export.

**Suggested changes:**
- Remove `export_to_pdf()` and PDF branches in `export_markdown()`.
- Update any user-facing strings that mention PDF export.
- Remove any optional dependency/extras for PDF export from packaging config (if present).

**Files:**
- `src/librarian/export.py`
- `src/librarian/app.py`
- `README.md`
- `pyproject.toml` (if it includes a pdf extra)

**Verification:**
- Export a file and confirm it produces HTML only.

### 3) Add index write locking (thread + process)
**Why:** Concurrent writes can corrupt `index.json` (multiple threads or multiple app instances). Data integrity is critical.

**Scope:**
- Use a `threading.Lock` to guard `_save_index()` and reads that depend on consistency.
- Add a file lock around writes (e.g., `portalocker` or OS‑native lock) so two processes don’t interleave.

**Files:**
- `src/librarian/database.py`

**Verification:**
- Simulate concurrent writes (threads or two app instances) and confirm no JSON corruption.

## P1 — Performance / UX (next)

### 4) Batch watcher updates
**Why:** Debounced watcher still writes index per file (JSON rewrite per change). This is heavy during bulk edits.

**Scope:**
- Wrap `_process_pending()`’s per‑file `rescan_file()` loop with `batch_writes()` or add a bulk update API.

**Files:**
- `src/librarian/watcher.py`
- `src/librarian/scanner.py` (if adding bulk API)
- `src/librarian/database.py`

**Verification:**
- Edit multiple markdown files quickly and confirm only one index write occurs.

### 5) Debounce search and/or move search to worker
**Why:** Search runs synchronously on every keystroke; large indexes can freeze UI.

**Scope:**
- Add a 150–250ms debounce before invoking `search_files()`.
- Optionally run search in a worker to keep UI responsive.

**Files:**
- `src/librarian/widgets/file_list.py`

**Verification:**
- With a large index, typing should remain responsive; results should update after debounce interval.

### 6) Avoid full rescan on rename/move
**Why:** Full rescan is expensive compared to rescanning affected files only.

**Scope:**
- When rename/move completes, call `rescan_file()` on new path and `remove_file()` on old path (or a helper).

**Files:**
- `src/librarian/app.py`
- `src/librarian/scanner.py`
- `src/librarian/database.py`

**Verification:**
- Rename/move a file and ensure index updates without full scan.

## P2 — Performance / Correctness (later)

### 7) Prevent preview worker result mismatch
**Why:** Multiple preview workers can complete out of order; using a single `_pending_preview_path` risks showing stale content.

**Scope:**
- Tie the file path to the worker result and discard mismatches.
- Or cancel/replace active preview worker group on new selection (Textual group handling).

**Files:**
- `src/librarian/app.py`

**Verification:**
- Rapidly scroll the file list and confirm preview always matches highlighted file.

### 8) Add optional tag/file secondary index
**Why:** `get_all_tags()` and `get_files_by_tag()` are O(n) across the full index each refresh. For large libraries, this is noticeable.

**Scope:**
- Maintain a secondary in‑memory mapping (tag → list of files) updated on add/remove.
- Invalidate/rebuild on `init_database()`.

**Files:**
- `src/librarian/database.py`

**Verification:**
- Benchmark tag refresh on large datasets; confirm improved performance.

## Notes
- If adding new dependencies (e.g., `bleach`, `portalocker`), update `pyproject.toml` and document optional extras if needed.
- Prefer minimal, targeted changes; avoid UI behavior regressions.
