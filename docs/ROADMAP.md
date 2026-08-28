# Roadmap

Planned and deferred work for Librarian. Single source of truth — keep roadmap content here
rather than scattering it across READMEs or issue comments.

## Planned

### ~~Give projection a backend abstraction, then publish it~~ — done 2026-08-13
The Projects panel is installable by anyone: `uv sync --extra projects`, declared like remtui's.

projection went through six phases to get there (a `Config` object, the local store as the source of
record, a `Backend` protocol with a field-level three-way merge, scriptable hooks, provisioning with
a first-run setup wizard, and a second backend in Cloudflare D1), then a security review, and is now
public at **https://github.com/7robots/projection**. Its own `docs/ROADMAP.md` carries the phase
history and what remains there; nothing about it is tracked here any more.

Two things worth keeping on this side:

- **The suspend-and-launch fallback stays.** It is not vestigial: projection needs Python 3.11+, so
  the extra carries a marker and the panel is simply unavailable below that — the same reason remtui's
  extra carries one for 3.12.
- **This machine runs a private fork** (`7robots/arch-projection`, cloned at `~/GitHub/arch-projection`)
  so team-specific customizations stay versioned without shipping publicly. It is installed editable,
  which survives `./install.sh` — that syncs `--inexact` — but a bare `uv sync` is exact and would
  replace it with the published package.

### Craft tags browser
From the Craft-module acceptance gate (2026-08-28). The `[tools] tags` switch half landed the same
day (tags panel optional, default on; `folders=false, tags=false, craft=true` gives a Craft-only
sidebar). What remains is the Craft tags feature itself, design agreed as **source-scoped**: the
Tags panel shows the active source's tags rather than one source winning a fixed priority.

Feasibility, verified live 2026-08-28: `GET /documents/search?regexps=<RE2>` sweeps the whole
space. One query with librarian's tag pattern (`(^|\s)#[a-zA-Z][a-zA-Z0-9_-]+`) returned every
tagged doc (83 matches, 73 docs — the documented top-20 cap did **not** apply), and tag names are
extractable client-side from the matched-block markdown (snippets bold matches as `**#tag**` and
elide with `...`; `fetchBlocks=true` returns the full blocks when fidelity matters). Per-tag doc
listings are one precise query each (`#meetings` → 9 docs), sorted newest-modified first. Two
costs to design around: results carry **no document title** (resolve per doc via
`GET /blocks?id=&maxDepth=0`, cacheable — `include` is a content filter, not a field selector),
and a space-wide regex sweep is one slow request (~1–2s), wanting the same TTL-cache treatment as
folders.

### Create a new Craft note from Librarian
Deferred out of the Craft module plan (`docs/plans/craft-module.md`, phases 5–7): the plan ships
browsing, preview, open-in-Craft, and the prepend flow for existing meeting notes. Creating a note
is a different flow — folder choice, title, template, tag line — and `POST /documents` is a single
documented endpoint, so it layers on cleanly once the module exists. Promote to a plan when wanted.

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

### Replace icalPal with a Python CLI
**Built 2026-08-14 as [calctl](https://github.com/7robots/calctl) (`~/GitHub/calctl`), and Librarian
switched over the same day — see *Switch the Calendar tool over to calctl* below. Full write-up in
[icalpal-python-port.md](icalpal-python-port.md).** The analysis that led here is kept for the record.

Prompted by the Calendar tool breaking that day. icalPal's logic was fine; Homebrew had autoremoved
the *Ruby interpreter* its shebang points at, because an untrusted tap made the icalpal formula
unreadable and its dependency therefore invisible. `brew install ruby` fixed it. The exposure is a
toolchain Librarian does not control and cannot see, and it fails in a way that took real digging to
diagnose.

Short version of the analysis: icalPal contains no native code and never touches EventKit — it reads
Apple's private `Calendar.sqlitedb` with read-only SQLite, which Python's stdlib does equally well. So
unlike remctl, which needs 3,672 lines of Swift and Objective-C because it *writes* through EventKit,
a port needs no bridge at all. The whole gem is 1,923 lines, its SQL is copyable verbatim, and the one
hard part — expanding Apple's proprietary recurrence `specifier` — has two ways around it, including
an `OccurrenceCache` table holding Apple's own pre-expanded occurrences that icalPal does not use.

**Scope is Tier 1 only:** what Librarian actually consumes is one command, `eventsToday -o json`.
Tier 3 parity is explicitly not the goal — `reminder.rb`'s 275 lines cover Reminders, and remctl
already owns those.

Two decisions were made up front, and both held:

- **Its own repo, in the remctl mould** — not a module inside Librarian. The calendar code already
  talks to a subprocess that emits JSON, so keeping that boundary makes the port a drop-in swap,
  testable on its own, and keeps Apple's private schema quarantined behind one interface.
- **Prototype `OccurrenceCache` before writing any RRULE code.** If Apple's own pre-expanded
  occurrences cover what we need, the hardest 200 lines never get written.

**How it turned out (2026-08-14).**

`OccurrenceCache` was prototyped first and **rejected on measurement**: only 265 of 763 recurring
series in the real database have any rows there, and over ±60 days it misses 98 of 813 events. Worse,
an absence in it cannot be distinguished from "no event", so it cannot even serve as a fast path with
rule expansion as the fallback — you would have to do the expansion anyway to know. The RRULE mapping
was written, using `dateutil.rrule`; that is calctl's one non-stdlib dependency.

Verified against icalPal over ±60 days: **824 occurrences from calctl, 848 from icalPal**, with every
difference arbitrated against Apple's own `OccurrenceCache` as an independent oracle. calctl was
correct in all of them. Four icalPal bugs account for the gap — `interval` ignored for
specifier-based monthly rules (quarterly meetings appearing monthly), monthly series double-reported
across a DST change, recurrence end ignored for all-day series, and `sctime` lagging a day from day
two of a multi-day all-day event, which is what put those events on the wrong day in Librarian.

The eyes-open cost turned out smaller than expected. Birthday calendars work, because their floating
`_float` timestamps are handled by the same conversion all-day events need; the `age`
pseudo-property is not ported, and Librarian never displayed it. Reminders remain remctl's job.

The wart on our side is fixed too: the old `resolve_icalpal()` checked only that the binary existed
and was executable, so a dangling shebang surfaced as `Could not run icalPal: No such file or
directory` — which reads as "not installed" when the truth was "its interpreter is missing". An
`ENOENT` from `exec` on a file that *is* present now says so.

### ~~Switch the Calendar tool over to calctl~~ — done 2026-08-14
`calendar.py` now resolves a *backend* rather than one named tool. `BACKENDS = ("calctl", "icalPal")`
is the auto-detect order, so with `[calendar] command` empty the first found on PATH wins — meaning
installing calctl switches Librarian over with no config change, and icalPal keeps working for anyone
who has only that.

Three decisions, since the entry above asked for them:

- **`[calendar] command` replaces `icalpal_path`**, which named one specific third-party tool. The old
  key is still read, following the `[calendar] enabled` → `[tools] calendar` precedent. The fallback
  fires on an *empty* `command`, not just a missing one: migration appends `command = ""` to a file
  that may already carry a real `icalpal_path`, and `save()` only writes `command`, so adopting the
  old value on load is what stops the next save from dropping it silently.
- **Auto-detect, not an explicit path.** calctl is preferred when present, which makes the switch a
  matter of installing it. A bare name resolves on PATH and a path is used as given — the same rule
  `reminders` and `projects` already follow, so all three behave alike.
- **Error messages name the backend that failed** instead of a hardcoded "icalPal", and
  `INSTALL_HINT` points at calctl.

Verified on the real config: `command` empty, auto-detect resolves `~/bin/calctl`, 11 events through
`CalendarModal`. One visible improvement beyond the swap — icalPal emits `["None"]` for an event with
no attendees, which Librarian rendered as an attendee named "None"; calctl emits `[]`.

### ~~De-duplicate the taskpaper → markdown conversion~~ — dropped 2026-08-13
`librarian/taskpaper.py` and `taskpapertui/widgets/preview.py` hold the same conversion, differing
only in an arrow character in a docstring, and the plan was for TaskPaperTUI to own it.

**Not worth doing now.** Jefferson has stopped using taskpapertui entirely, in favour of remtui or
projection depending on the workflow, so the payoff — one owner for a small function — would buy a
dependency on an app he no longer runs. Librarian keeps its own copy, which is nobody's burden at ~40
lines.

Note what this does *not* change: `.taskpaper` **files** are still first-class in Librarian — indexed
by the scanner, converted for preview and export by `taskpaper.py`, and opened by `e` with the
`taskpaper` editor setting. That support is independent of taskpapertui the application, and the
`[tools] taskpaper` launcher remains a suspend-and-launch handoff, which is where it stays.

## Cross-cutting (all four projects)

These span librarian, remtui, projection, and taskpapertui. Recorded here because librarian is the
hub — it embeds the other three — but the work touches each repo.

### Performance review
**Started 2026-08-13 with the preview, which was the one thing that actually felt slow.** Measured
against the real vault (1117 notes) rather than a fixture, and the answer was not where it was
expected:

| Where the time went | Measured |
|---|---|
| Reading the file, including iCloud and the LRU cache | **0.0 ms** |
| Wiki-link preprocessing | **0.0 ms** |
| `Markdown.update()` — Textual mounts one widget per block, on the message loop | **~0.3 ms per widget** |

So rendering was the entire cost, and it scales with *block count*, not bytes: a 15 KB note with 40
lines rendered in 17 ms while a 4 KB note with 60 lines took 51 ms. The worst note in the vault
(61 KB, 264 blocks, 4197 widgets) took **1.9 s**, and scrolling eight long notes cost **3.4 s of
frozen UI** — because every file passed rendered in full and a render cannot be interrupted once
started. The vault's median note is 4 blocks and renders in ~1 ms; 13% exceed 80 lines and 30 notes
exceed 400.

Fixed by rendering less, not by rendering faster: the debounce now outlasts a held arrow key (0.05 →
0.15 s, macOS repeats at ~33 ms), the load worker is exclusive, and a browse render is capped to the
first 80 lines — which holds the worst note to ~55 ms. Notes under 150 lines fill themselves in a
moment after the cursor stops; longer ones say so in the header and complete when the pane is
focused, since paying 1.7 s for a pause is the freeze this removes. **Scrolling that folder: 3484 ms →
53 ms.**

**A further step was designed, measured, and deliberately not taken** (Jefferson, 2026-08-13). The
remaining cost is the ~1.7 s to render the longest notes in full, which is now paid only when you
focus the pane. It could be removed by rendering with **Rich's `Markdown` inside a `Static`** while
browsing — one widget instead of 4197, measured at **20 ms for the note that takes 1927 ms as a
Textual widget** — and swapping in the real `Markdown` widget when the pane takes focus.

It is not being done, for two reasons worth keeping written down:

- **What it buys is a pause you asked for.** After the fix above, that 1.7 s only happens on a note
  you deliberately focused to read. Trading for it is not obviously right.
- **What it costs is wiki links.** Rich renders links as terminal hyperlinks, which Textual cannot
  intercept — so `[[wiki link]]` clicking, a core feature here, would not work while browsing. The
  swap also re-renders visibly, since Rich and Textual style markdown differently.

Revisit if the focus-time render starts to grate, if notes get much longer, or if wiki-link
navigation moves to a keyboard-driven "follow link" command, which would make the trade free.

Still worth measuring, and now with a method that worked — measure the real vault, split the path into
parts, and distrust the obvious suspect:

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
**Explicitly conditional on the performance review above, and that condition now looks unmet.** The
one thing that felt slow was the preview, and it was neither Python nor I/O: it was mounting 4197
widgets on the message loop, which a rewrite in any language would still have to do unless it also
rendered less. Rendering less fixed it — 3484 ms → 53 ms — in about forty lines. Revisit only if
something *else* turns out to be slow and profiles as CPU-bound in Python itself.

If the numbers had been fine, or the problems had turned out to be I/O bound (subprocess spawns,
iCloud, network), a rewrite fixes nothing — a faster language does not make `op read` or a Smartsheet
round-trip return sooner.

If a rewrite is warranted, [ratatui](https://ratatui.rs) is the obvious target: it is the maintained
successor to tui-rs and the mainstream choice for Rust TUIs.

**The load-bearing constraint, worth deciding before any code:** the embedding architecture is
Python-specific. librarian mounts remtui's `RemindersPanel` and projection's `ProjectsPanel` as
Textual widgets *in the same process*. Rewriting any one of those three in Rust means librarian can no
longer embed it, and that tool drops to the suspend-and-launch handoff — losing the panel experience
we just built. So the realistic candidates are:

- **taskpapertui**, which librarian only ever launches as an external program, so nothing is lost —
  and which is now unused besides, making it the cheapest possible throwaway; or
- **librarian itself**, which is the host and embeds rather than being embedded — but then remtui and
  projection become unembeddable in it, which is the same problem from the other side; or
- **accept the handoff** for whichever app is rewritten, and treat the panel embedding as a
  Python-era feature.

A prototype should therefore be scoped as a throwaway that answers one question — is the performance
difference real and worth this? — not as a migration.

### Security and code review
Three of the four repos still need this (projection's ran on 2026-08-12 — see its roadmap), and
taskpapertui is now unused, so it is the lowest priority of them. taskpapertui got a pre-publication audit,
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

### Render the preview with Rich while browsing
Designed and measured on 2026-08-13, then deferred on purpose — the full write-up lives with the
performance numbers under **Performance review** above, since the reasoning only makes sense next to
them. Short version: 20 ms instead of 1927 ms for the worst note, at the cost of wiki-link clicking
while browsing, to remove a pause that now only happens when you ask for it.

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
