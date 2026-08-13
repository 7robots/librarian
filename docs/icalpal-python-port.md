# Replacing icalPal with a Python CLI

Feasibility analysis, 2026-08-13. **Decided: this is happening** — the roadmap entry that points here
is under *Planned*, scoped to Tier 1 below. The analysis is kept in full, including the arguments
against, so the reasoning behind the scope is legible later.

Read against icalPal **4.1.1** as installed (`/opt/homebrew/Cellar/icalpal/4.1.1/gems/icalPal-4.1.1`),
which is the published source of https://github.com/ajrosen/icalPal, plus the live
`Calendar.sqlitedb` on this machine.

## Why the question came up

On 2026-08-13 Librarian's Calendar tool stopped working, and the interesting part is *how*:

- icalPal's shebang is `#!/opt/homebrew/opt/ruby/bin/ruby`, and Homebrew's `ruby` formula had been
  removed. The script was left dangling.
- The cause was a chain nobody would guess. Homebrew now refuses to load formulae from untrusted
  third-party taps (`Refusing to load formula ajrosen/tap/icalpal from untrusted tap`). With the
  formula unreadable, Homebrew no longer knew icalpal depended on Ruby — `brew uses --installed ruby`
  came back empty — so a cleanup pass removed Ruby as an orphan.
- `brew install ruby` fixed it. The gems live self-contained under the icalpal Cellar with absolute
  paths baked into the wrapper, so only the interpreter was missing.

**icalPal's logic never broke. Its toolchain did, silently, through a dependency Librarian does not
control and cannot see.** That is the actual argument for a port — not speed, and not the code, which
is fine.

It also surfaced a smaller wart on our side: `calendar.resolve_icalpal()` checks only that the binary
exists and is executable, both of which were true, so Librarian reported
`Could not run icalPal: No such file or directory`. Accurate as an `OSError` passthrough, misleading
in this case — it reads as "icalPal is not installed" when the truth was "its interpreter is not".

## The decisive finding: icalPal never touches EventKit

This determines the whole answer. Despite appearances, icalPal contains **no native code and no Apple
framework linkage**:

- `lib/EventKit.rb` is not a binding. It is a hardcoded table of constants transcribed from Apple's
  documentation — `EKEventStatus`, `EKEventAvailability`, `EKSourceType`, and friends.
- `ext/extconf.rb` looks like a C extension and is not one. It installs gem dependencies, then writes
  a fake `Makefile` containing `clean: true` / `install: true` and exits.

What it actually does is one line:

```ruby
db = SQLite3::Database.new(db_file, { readonly: true, results_as_hash: true })
```

against Apple's private store at
`~/Library/Group Containers/group.com.apple.calendar/Calendar.sqlitedb`.

So a Python port needs **no Swift, no Objective-C, no PyObjC** — `sqlite3` is in the standard library.
Verified on this machine: stdlib Python opened the 86 MB database read-only and read **14,412
`CalendarItem` rows across 84 columns**.

## Why this is easier than remctl was

remctl is the obvious model — a Python CLI over an Apple data store — but the two problems are not
symmetric, and the difference is all in the *direction* of the data:

| | remctl | an icalPal port |
|---|---|---|
| Direction | read **and write** | read-only |
| Access path | EventKit / ReminderKit | direct SQLite |
| Native code | 3,672 LOC of Swift + Objective-C | none needed |
| Permissions | 621 LOC of `remctl-permissions.swift` | inherits the terminal's Full Disk Access |

remctl needs compiled bridges because *writing* to Reminders requires going through Apple's
frameworks. Reading calendars does not. And a plain CLI asking for EventKit access is genuinely
painful — no bundle ID, no `Info.plist`, therefore no TCC prompt — which is exactly why remctl carries
hundreds of lines of permission plumbing. The SQLite route sidesteps that by riding on the Full Disk
Access the terminal already holds.

This is worth stating plainly because it inverts the intuition: the tool that *looks* like it needs
Apple frameworks needs none, and the reason is that it only reads.

## Size of the job

icalPal is **1,923 lines of Ruby** in total, and most of it is not the hard part:

| File | LOC | Portability |
|---|---|---|
| `event.rb` | 397 | the SQL (copyable verbatim) + recurrence (**the hard ~200**) |
| `options.rb` | 389 | optparse boilerplate → argparse; mechanical |
| `reminder.rb` | 275 | a separate Core-Data-ish `zremcd*` store — **remctl already owns this** |
| `ToICalPal.rb` | 199 | output formatters (default, csv, json, md, rdoc) |
| `rdt.rb` | 116 | date math and relative dates; trivial |
| `icalPal.rb` | 179 | dispatch, `load_data`, constants |
| `defaults.rb` / `utils.rb` / `calendar.rb` / `store.rb` | 244 | trivial |

The commands are `events`, `eventsToday`, `tasks`, `calendars`, and `accounts` (with `stores` and
`reminders` as aliases).

### The SQL is a gift

One ~60-line `SELECT`, liftable unchanged. It joins `Store → Calendar → CalendarItem`, then outer-joins
`Location`, `Recurrence`, `ExceptionDate`, `Alarm`, `Participant`, and `Identity`, and uses
`json_group_array` to aggregate attendees and exception dates into JSON columns — so the messy
one-to-many flattening is already done in the query rather than in application code. It filters
`WHERE Store.disabled IS NOT 1` and groups by `CalendarItem.rowid`.

Two constants you need and would otherwise have to rediscover:

```ruby
ITIME = 978_307_200                                    # Apple epoch (2001-01-01) → Unix
DOW   = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 }
```

## The hard part: recurrence

Roughly 200 lines of `event.rb`, and the only place where a port would earn its bugs. icalPal
hand-rolls the expansion, walking dates forward while applying, in order:

- **Apple's proprietary `specifier` string**, parsed by hand: `D=` day-of-week (optionally signed, as
  in `+1MO`), `M=` day-of-month, `O=` month-of-year, `S=` nth.
- **`frequency` and `interval`** from the `Recurrence` table, plus `count` and an end date.
- **Exception dates** — the `xdate` JSON array — removed after expansion.
- **Detached or modified occurrences**, found by scanning for rows whose `orig_item_id` points back at
  the series and skipping the original date.
- **Floating timezones** (`start_tz == '_float'`) and DST correction, done by round-tripping through
  `Time` to pick up the right UTC offset.

Multi-day events are separately exploded into one event per day, each clipped to `23:59:59`.

### Two ways to beat the original here

**1. Map to RFC 5545 and let `dateutil.rrule` do it.** Apple's specifier translates almost directly:

| Apple | RFC 5545 |
|---|---|
| `D=MO,WE` | `BYDAY=MO,WE` |
| `M=1,15` | `BYMONTHDAY=1,15` |
| `O=3` | `BYMONTH=3` |
| `S=-1` | `BYSETPOS=-1` |
| `frequency` / `interval` | `FREQ` / `INTERVAL` |
| `count` / `end_date` | `COUNT` / `UNTIL` |
| `ExceptionDate` rows | `EXDATE` |

That replaces hand-rolled date walking with a battle-tested engine, at the cost of one dependency.

**2. Skip expansion altogether — `OccurrenceCache`.** The schema contains Apple's *own* pre-expanded
occurrences, which icalPal does not use:

```
OccurrenceCache      6,889 rows   day, event_id, calendar_id, store_id,
                                  occurrence_date, occurrence_start_date, occurrence_end_date,
                                  latest_possible_alarm, earliest_possible_alarm, next_reminder_date
OccurrenceCacheDays  3,617 rows   calendar_id, store_id, day, count
Recurrence             763 rows   frequency, interval, week_start, count, specifier, ...
```

For "what is on today or this week" — all Librarian asks for — you could join against that table and
let Calendar.app's engine do the recurrence math. **This should be prototyped before writing a single
line of RRULE code.**

The caveat is in the name: it is a *cache*, maintained by Calendar.app for its own purposes. It may be
stale, or sparse for dates far out, or thin for calendars not recently displayed. Verify its coverage
against rule-based expansion before depending on it. A reasonable design uses it as a fast path with
rule expansion as the fallback.

## Scoping

| Tier | Scope | Estimate |
|---|---|---|
| **1** | What Librarian actually uses: today's events as JSON | a few hundred lines, an afternoon, **zero non-stdlib dependencies** |
| **2** | A useful CLI: date ranges, calendar include/exclude, JSON + CSV output | a weekend |
| **3** | Full icalPal parity: every output format, icalBuddy compatibility flags, tasks | a real project |

Tier 3 is not worth it here. `reminder.rb`'s 275 lines cover Reminders, and **remctl already owns
Reminders** — porting them would build a second implementation of something that works.

Tier 1 is the honest target, because it is the whole of what Librarian consumes:
`calendar.fetch_todays_events()` shells out to `icalPal eventsToday -o json` and parses the result.

## Risks, honestly

1. **The schema is private and undocumented.** Apple can rename a column in any macOS release. This
   is the standing maintenance tax and a port does not avoid it — icalPal carries the identical
   exposure and has been chasing it for years. Note we are *already* exposed: we depend on icalPal,
   which depends on this schema. remctl's own source observes that "EventKit and ReminderKit
   identifiers have diverged across macOS releases", so the shape of this pain is familiar.
   Mitigations: pin the query, keep a fixture database for tests, and fail loudly on a missing column
   rather than silently returning nothing.
2. **`OccurrenceCache` is a cache, not a source of record.** See above.
3. **The database is live.** Calendar.app writes while you read. Open read-only through a URI
   (`file:...?mode=ro`) and be WAL-aware, as icalPal does.
4. **Full Disk Access is still required.** A port does not escape TCC; it inherits the terminal's
   grant instead of prompting, exactly as today. Anything launched from the GUI needs its own grant.
5. **Trading a known-good implementation for a new one.** icalPal is mature and handles cases we have
   not thought of — birthday calendars and their `age` pseudo-property, subscribed calendars, the
   "Scheduled Reminders" pseudo-calendar, invitation status. A port starts at zero on all of it. This
   is the strongest argument for staying put.

## Verdict

**Very feasible, and unusually low-risk technically** — no native code, a copyable query, and one
genuinely hard subproblem with two credible ways around it. The work is small at Tier 1.

**Decided 2026-08-13: go ahead, at Tier 1.** The Ruby dependency has failed once already, silently and
through a chain nobody would guess, and it will keep being a dependency we neither control nor can
see. Tier 1 is an afternoon with no non-stdlib dependencies, which is a small price for removing a
whole class of failure from the Calendar tool.

Three things that follow from the analysis and should not be relitigated mid-build:

- **A separate CLI in its own repo**, in the remctl mould, not a module inside Librarian. The calendar
  code already speaks to a subprocess that emits JSON; keeping that boundary makes the port a drop-in
  swap, testable on its own, usable from anything else, and it quarantines Apple's private schema
  behind one interface instead of spreading it through the app.
- **Prototype `OccurrenceCache` first.** If it covers what we need, the hardest ~200 lines never get
  written. Check its coverage against rule-based expansion before depending on it.
- **The bar is parity on what we use, not parity with icalPal.** Birthdays and their `age`
  pseudo-property, subscribed calendars, "Scheduled Reminders", invitation status — icalPal handles
  all of it and a port starts at zero. Tier 3 is explicitly not the goal, and Reminders are remctl's
  job.

The risk that stays live is the one in the section above: the schema is private and can move under us.
That is not new — we already depend on it through icalPal — but after the port it becomes *our*
maintenance rather than someone else's. Pin the query, keep a fixture database, fail loudly on a
missing column.
