# Roadmap

Planned and deferred work for Librarian. Single source of truth — keep roadmap content here
rather than scattering it across READMEs or issue comments.

## Planned

### Give projection a backend abstraction, then publish it
The Projects tool is **built and working** — `ProjectsModal`, `[tools] projects`, the soft import,
and the suspend-and-launch fallback all ship, with the embed verified against projection's own fakes.
What is missing is a way for anyone to *install* it.

The optional extra would be:

```toml
[project.optional-dependencies]
projects = ["projection @ git+https://github.com/7robots/projection.git ; python_version >= '3.11'"]
```

but that repository is **private**, so declaring it in a public project means `uv sync --extra
projects` fails for anyone without access — unlike remtui, which is public. So it is deliberately
*not* declared, and `uv pip install -e ~/GitHub/projection` installs it by hand.

**The install friction is fixed**: `install.sh` now syncs `--inexact`, so it no longer deletes a
hand-installed projection (it also passes `--extra reminders`, which it never did, so a fresh install
silently lacked remtui and fell back to the handoff). A bare `uv sync` is still exact and will remove
it — use `./install.sh` or `uv sync --inexact`.

What remains is only that **anyone without repo access cannot get the Projects panel** and falls back
to the executable.

**Why projection is private, and the intended direction** (Jefferson, 2026-08-11): the repo has stayed
private because it is heavily predicated on one team's use of a specific Smartsheet as the backing
source of truth — the sheet's identity, its column layout, and the vocabulary around it are baked in.
Publishing it as-is would ship someone else's schema.

The intended shape before going public: **projection works against an abstraction layer — a table with
consistent column headings — and supports different backend data sources chosen through a simple setup
process.** Smartsheet becomes one implementation of that interface rather than the assumption. That
subsumes the "split the panel into a public package" option below: with a real source interface, the
whole app can be public and the Smartsheet specifics become configuration rather than a private fork.

**Progress** (as of 2026-08-12): that work is essentially done in projection's own repo, tracked phase
by phase in **projection's `docs/ROADMAP.md`** — read it there rather than duplicating it here. Phases
0–5 have landed: a `Config` object, the local store as the source of record (schema v3, tombstones,
per-field times), a `Backend` protocol with a field-level three-way merge, scriptable `[[hooks]]` in
place of the built-in exec summary, provisioning with a first-run setup wizard, and **two backends
behind the interface** — Smartsheet and Cloudflare D1. `backend = ""` (local-only, no credential, no
network) is the default and fully supported.

That means the "ships someone else's schema" objection is answered: the Smartsheet specifics are
configuration, and a second implementation proved the interface is real rather than a description of
the first. **The remaining gate before the repo can go public is the security review below** — after
which the optional extra at the top of this section becomes declarable, and anyone can get the
Projects panel with `uv sync --extra projects`.

Worth knowing on this side: the setup wizard is a Textual dialog specifically so it works from inside
Librarian's `ProjectsModal` — there is no terminal to prompt into there, and the embed is how projection
usually gets opened. `,` opens it; `tests/test_projects_panel.py` pins that it behaves over Librarian's
screen stack. Two approaches were considered and rejected for the *packaging* question: vendoring clones into Librarian's
tree (trades the lockfile's reproducibility for "whatever HEAD was", does not help private access,
and — since one distribution name can only be installed once — leaves two clones on disk with the
wrong one silently authoritative), and git submodules (keeps pinning, but still needs credentials,
and uv rejects `sources` in `uv.toml`, so a machine-local path override is not expressible).

Note the two wrinkles that prompted this are now settled — `SmartsheetClient` loads its 1Password
token lazily on the first request, so constructing it cannot block or prompt for Touch ID at startup,
and the panel degrades to a message when Smartsheet is unreachable.

### Rethink what `q` means inside an embedded panel
**Needs a design conversation before any code.** Right now `q` is overloaded and the behavior reads
as inconsistent depending on which panel is open:

| Where | `q` does | Why |
|---|---|---|
| Librarian's own panels | quits Librarian | app-level binding |
| Calendar modal | closes the modal | screen binding; `priority=True` is defensive here, since nothing inside claims `q` |
| Reminders modal | closes the modal | screen binding, `priority=True` **required**: remtui's panel binds `q -> app.quit` |
| Projects modal | closes the modal | same as Reminders — projection's panel also binds `q -> app.quit` |
| remtui / projection standalone | quits that app | their own app-level binding |

So the same key means "quit the program" in one place and "back out one level" in another, and which
one you get depends on a detail — whether the embedded widget happens to claim `q` — that is
invisible from the outside. Escape is inconsistent too: the calendar modal binds it, the reminders
modal deliberately does not, because remtui's filter owns it.

Options worth weighing: make `q` uniformly "close the innermost thing" and move quit to `ctrl+q`;
keep `q` as quit and use only Escape to close modals; or have the host rewrite the embedded panel's
quit binding on mount so hosted panels never define the meaning. Whatever we pick should also settle
what happens to the *host's* keys while a panel is open — a `ModalScreen` currently hides all of
them, which is why `a`/`n`/`e` are re-declared on the calendar modal by hand.

### De-duplicate the taskpaper → markdown conversion
`librarian/taskpaper.py` and `taskpapertui/widgets/preview.py` hold the same conversion, differing
only in an arrow character in a docstring. TaskPaperTUI is the natural owner now that it has tests
covering it; Librarian could depend on it, or the pair could move to a small shared package.

## Cross-cutting (all four projects)

These span librarian, remtui, projection, and taskpapertui. Recorded here because librarian is the
hub — it embeds the other three — but the work touches each repo.

### Performance review
No measurements have been taken, so this is a review rather than a fix: **establish a baseline before
optimizing anything.** Nothing is known to be slow today; the point is to find out whether it is.

Worth measuring, roughly in order of suspicion:

- **librarian's startup scan** against the real vault (iCloud-backed Obsidian), not a fixture. Scanning
  skips by mtime, but the first run and any `SCANNER_VERSION` bump do the whole tree.
- **Index writes.** Every write is atomic (temp file + `os.replace()`) and the data directory may sit
  on iCloud Drive, where that pattern is markedly slower than on a local disk. `batch_writes()`
  already exists; the question is whether every write path uses it.
- **The file watcher.** Debounced rescans plus the tag-list rebuild on each change.
- **Preview rendering** for large markdown, and whether the 10-file LRU cache is the right size.
- **Subprocess round-trips.** remtui shells out to `remctl` per operation, and librarian to `icalPal`;
  both are per-call process spawns. projection's `SyncCoordinator` polls on `DATA_POLL_INTERVAL`.
- **Textual-specific traps** we have already been bitten by once: DOM rebuilds inside exclusive
  workers, and `on_resize` handlers that change the size they are reacting to.

Tooling: `textual console`, `cProfile` around the scan, and timing harnesses over a copy of the real
vault. Record the numbers in this file so the "is it slow?" question has an answer next time.

### Prototype a Rust/ratatui re-implementation — only if the review says so
**Explicitly conditional on the performance review above.** If the numbers are fine, or the problems
turn out to be I/O bound (subprocess spawns, iCloud, network), a rewrite fixes nothing — a faster
language does not make `op read` or a Smartsheet round-trip return sooner.

If a rewrite is warranted, [ratatui](https://ratatui.rs) is the obvious target: it is the maintained
successor to tui-rs and the mainstream choice for Rust TUIs.

**The load-bearing constraint, worth deciding before any code:** the embedding architecture is
Python-specific. librarian mounts remtui's `RemindersPanel` and projection's `ProjectsPanel` as
Textual widgets *in the same process*. Rewriting any one of those three in Rust means librarian can no
longer embed it, and that tool drops to the suspend-and-launch handoff — losing the panel experience
we just built. So the realistic candidates are:

- **taskpapertui**, which librarian only ever launches as an external program, so nothing is lost; or
- **librarian itself**, which is the host and embeds rather than being embedded — but then remtui and
  projection become unembeddable in it, which is the same problem from the other side; or
- **accept the handoff** for whichever app is rewritten, and treat the panel embedding as a
  Python-era feature.

A prototype should therefore be scoped as a throwaway that answers one question — is the performance
difference real and worth this? — not as a migration.

### Security and code review
The four repos have never had a deliberate security pass; taskpapertui got a pre-publication audit,
but that was scoped to "is anything in here specific to me", not to safety. Surfaces worth a careful
look:

- **Subprocess construction.** `op`, `icalPal`, `remctl`, `$EDITOR`, `taskpapertui`, and the
  `remtui`/`projection` executables are all spawned. Check argument lists are never shell-interpolated,
  and that PATH resolution cannot pick up an unexpected binary.
- **Untrusted input is not hypothetical here.** Calendar events and reminders carry text written by
  *other people* — meeting titles, attendee names, notes — and that text reaches rendered markdown,
  notification messages, and **filenames** (`action_new_file` builds a meeting note's name from the
  event title). The sanitizing there deserves adversarial attention.
- **Path handling.** Rename, move, delete, and export all take user-supplied destinations. Can any of
  them escape `scan_directory` or `export_directory`? Can a crafted `[[wiki link]]` resolve outside
  the vault?
- **HTML export sanitization** (`export.py`) strips dangerous tags and attributes. Confirm whether it
  is a denylist — denylists leak — and what happens with nested or malformed markup.
- **Token handling in projection.** The Smartsheet token is read from 1Password and held in memory.
  Verify it cannot reach a traceback, a log line, a notification, or the exported summary.
- **Data-loss review** rather than attacker-driven: atomic writes under iCloud, and what happens if
  two Librarian instances run against one index.

projection needs this pass **before** it goes public, so it pairs naturally with the backend
abstraction work above.

## Deferred

### Expand the Lucide → Nerd Font glyph table
`icons.NERD_GLYPHS` covers 66 of Lucide's 2,025 icon names; anything else falls back to a plain
folder glyph. Most Lucide names have a same-or-near-name Material Design counterpart in Nerd Fonts,
so a much larger table can be generated by joining the two name lists and hand-checking the misses.
Mechanical work, and it only helps people who pick icons outside the current 66 — kept separate so
it doesn't swamp a behavioral diff.

### Tag colors from Notebook Navigator
`obsidian.py` already loads the plugin's `tagColors` map but nothing consumes it. Low value while
the vault has only a couple of tags; revisit if tag use grows.

### Nerd Font detection beyond macOS
`icons.detect_glyph_style()` scans macOS font directories and an allowlist of terminals that embed
Nerd Font symbols. Linux and Windows font locations are not checked, so users there fall back to
emoji unless they set `style` explicitly.
