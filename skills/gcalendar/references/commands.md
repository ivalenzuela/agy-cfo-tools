# Command Reference

Every command and flag below was taken from the `gcalendar` binary this plugin
ships. Anything not listed here does not exist; check with `"$GCALENDAR"
<namespace> <command> --help` before assuming otherwise.

Commands live under two namespaces:

-   `readonly` — inspects calendars and events, changes nothing.
-   `mutate` — creates, updates, deletes, and RSVPs.

The flat, un-namespaced forms (`gcalendar events`) are deprecated aliases that
print a migration warning on stderr. Always write the namespaced form.

## Global flags

These are accepted by every command.

| Flag              | Description                                            |
| ----------------- | ------------------------------------------------------ |
| `--json`          | Emit JSON instead of a table                           |
| `--timezone`      | IANA timezone override (e.g. `America/Los_Angeles`).   |
:                   : When omitted, the timezone is read from the user's     :
:                   : Calendar settings, falling back to the machine's local :
:                   : zone                                                   :
| `--legacy-mode`   | How deprecated flat commands are handled: `allowed`,   |
:                   : `deprecated` (default), `banned`                       :
| `-v`, `--version` | Print the CLI build version                            |
| `-h`, `--help`    | Help for the command                                   |

## `readonly`

### `readonly events`

List events on a calendar.

Flag      | Description
--------- | ---------------------------------------
`--cal`   | Calendar ID (default `primary`)
`--date`  | Single date to list (`YYYY-MM-DD`)
`--start` | Range start (RFC3339)
`--end`   | Range end (RFC3339); requires `--start`
`--max`   | Maximum number of events (default `20`)

`--date` cannot be combined with `--start` / `--end`.

### `readonly today`

Today's events on a calendar. Takes `--cal` only; the global `--timezone`
decides which day "today" means.

### `readonly search`

`readonly search [query]` — full-text search over events.

Flag      | Description
--------- | ----------------------------------------
`--cal`   | Calendar ID (default `primary`)
`--start` | Range start (RFC3339)
`--end`   | Range end (RFC3339)
`--max`   | Maximum number of results (default `10`)

The default `--max` is `10` here but `20` for `readonly events`.

### `readonly get`

`readonly get [eventID]` — full details for one event, including a `Link:` line
to the event in the Calendar UI. Takes `--cal`.

### `readonly instances`

`readonly instances [eventID]` — the individual occurrences of a recurring
event. Takes `--cal` and `--max` (default `20`).

### `readonly conflicts`

Overlapping events, **today only**, on one calendar. Takes `--cal`; there is no
flag to widen the window, so scanning a week means looking at each day's events
yourself. All-day events are ignored, so an overlap with a conference or a
vacation block will not be reported.

### `readonly calendars`

Every calendar the user can see, with the calendar IDs the other commands
expect. No flags beyond the global ones.

### `readonly colors`

The event and calendar color palette, giving the numeric IDs that `--color`
takes. No flags beyond the global ones.

### `readonly acl`

Sharing rules for a calendar. Takes `--cal`.

### `readonly freebusy`

Busy intervals for one or more people.

Flag      | Description
--------- | -----------------------------------------
`--email` | Email to check; repeat for several people
`--start` | Range start (RFC3339)
`--end`   | Range end (RFC3339)

Defaults are narrow: with no `--start` the window begins now, and with no
`--end` it covers only the **next 8 hours**. Pass both explicitly whenever you
care about a specific day or a multi-day range. With no `--email`, it reports
the caller's own primary calendar.

### `readonly next-free`

First open slot of a given length.

Flag         | Description
------------ | ---------------------------------------------
`--duration` | Slot length, e.g. `30m`, `1h` (default `30m`)
`--after`    | Search from this time (RFC3339, default: now)

It searches **7 days** from the start point, looks only at the caller's primary
calendar, and ignores working hours — so it will happily suggest 3am, and it
knows nothing about the other attendees. Use `readonly freebusy` with every
attendee's address when the slot has to work for a group, and sanity-check the
result against `readonly working-hours` before proposing it.

### `readonly working-hours`

Despite the name, this prints the user's **entire** Calendar settings table,
which is where the timezone and working-hours values live among the rest. Read
the row you need rather than treating the output as a working-hours report. No
flags beyond the global ones.

### `readonly workloc`

Where someone is working from. See [working_location.md](working_location.md).

Flag      | Description
--------- | --------------------------------------------------
`--email` | Email to check; repeatable; defaults to the caller
`--date`  | Date to query (`YYYY-MM-DD`, default: today)
`--start` | Range start (RFC3339); overrides `--date`
`--end`   | Range end (RFC3339); requires `--start`

`--date` and `--start` are mutually exclusive.

## `mutate`

### `mutate create`

| Flag                  | Description                             |
| --------------------- | --------------------------------------- |
| `--summary`           | Event title                             |
| `--description`       | Description; multi-line supported       |
| `--location`          | Free-text location. Does **not** book a |
:                       : room                                    :
| `--start`             | Start (RFC3339, or `YYYY-MM-DD` with    |
:                       : `--all-day`)                            :
| `--end`               | End (RFC3339, or `YYYY-MM-DD` with      |
:                       : `--all-day`)                            :
| `--all-day`           | Create an all-day event                 |
| `--attendee`          | Attendee email; repeat for several      |
| `--optional-attendee` | Attendee marked optional; repeat for    |
:                       : several                                 :
| `--visibility`        | `default`, `public`, `private`,         |
:                       : `confidential`                          :
| `--transparency`      | `opaque` (busy) or `transparent`        |
:                       : (free); default `opaque`                :
| `--color`             | Color ID from `readonly colors`         |
| `--gvc`               | Attach a new Google Meet conference     |
| `--meet-code`         | Attach an existing Meet code or URL.    |
:                       : Mutually exclusive with `--gvc`         :
| `--modify`            | Let guests modify the event             |
| `--send-updates`      | `all`, `externalOnly`, `none` (default  |
:                       : `none`)                                 :
| `--ooo`               | Create as an Out of Office event        |
| `--ooo-message`       | Decline message; requires `--ooo`       |
| `--ooo-decline-mode`  | `declineNone`,                          |
:                       : `declineAllConflictingInvitations`,     :
:                       : `declineOnlyNewConflictingInvitations`; :
:                       : requires `--ooo`                        :
| `--attachment-url`    | Attachment URL                          |
| `--attachment-title`  | Attachment title                        |
| `--cal`               | Calendar ID (default `primary`)         |

There is no `--duration` on `create`; give an explicit `--end`.

With `--all-day`, the dates are passed through untouched and the **end date is
exclusive**: a single-day event is `--start 2024-03-01 --end 2024-03-02`. The
CLI does not add the extra day for you.

Duplicate attendee addresses are collapsed case-insensitively, with optional
attendees taking precedence, and the organizer is auto-accepted if they appear
in the list. `create` prints a `Link:` line for the new event.

### `mutate update`

`mutate update [eventID]` — reads the event, applies only the flags you actually
passed, and writes it back. It refuses to edit an event you do not organize
unless that event allows guests to modify it.

Flag                  | Description
--------------------- | ----------------------------------------------
`--summary`           | Event title
`--description`       | Description; `""` or `null` clears it
`--location`          | Free-text location
`--start`             | Start (RFC3339)
`--end`               | End (RFC3339)
`--rrule`             | Recurrence rule; `""` or `null` clears it
`--attendee`          | Attendee email; repeatable
`--optional-attendee` | Optional attendee email; repeatable
`--remove-attendee`   | Attendee email to drop; repeatable
`--visibility`        | `default`, `public`, `private`, `confidential`
`--transparency`      | `opaque` or `transparent`
`--color`             | Color ID from `readonly colors`
`--gvc`               | Attach a Google Meet conference
`--modify`            | Let guests modify the event
`--send-updates`      | `all`, `externalOnly`, `none` (default `none`)
`--ooo-message`       | Decline message for an event already OOO
`--ooo-decline-mode`  | Auto-decline mode for an event already OOO
`--attachment-url`    | Attachment URL; **appends** to existing ones
`--attachment-title`  | Attachment title
`--cal`               | Calendar ID (default `primary`)

Differences from `create` worth holding on to:

-   **Attendee flags merge, they do not replace.** `--attendee` and
    `--optional-attendee` add people or flip an existing person's optional bit;
    nobody is ever dropped by them. Removing someone needs `--remove-attendee`,
    which matches the address **exactly and case-sensitively** — copy it out of
    `readonly get` rather than retyping it.
-   **No `--all-day` and no `--meet-code`.** `--start` / `--end` on update
    always write a timed event, so an all-day event cannot be rescheduled this
    way.
-   **`--gvc` overwrites any existing conference** with a fresh Meet link, and
    there is no flag to remove one.
-   Setting `--rrule` replaces only the recurrence rule, leaving exception dates
    intact, and fails on a single instance of a series — target the series
    itself.
-   `update` prints no `Link:` line; use `readonly get` if you need the URL.

### `mutate recurring`

`mutate recurring [summary]` — the title is a positional argument, not a flag.
`--start`, `--end` and `--rrule` are all required.

Flag             | Description
---------------- | --------------------------------------------------
`--rrule`        | Recurrence rule, e.g. `FREQ=WEEKLY;BYDAY=MO,WE,FR`
`--start`        | First occurrence start (RFC3339)
`--end`          | First occurrence end (RFC3339)
`--description`  | Description
`--attendee`     | Attendee email; repeatable
`--gvc`          | Attach a Google Meet conference
`--modify`       | Let guests modify the event
`--send-updates` | `all`, `externalOnly`, `none` (default `none`)
`--cal`          | Calendar ID (default `primary`)

A leading `RRULE:` on the rule is tolerated. The series timezone comes from the
user's Calendar settings.

`recurring` has no `--optional-attendee`, `--location`, `--visibility` or
`--color`. To set those, create the series and then `mutate update` it.

### `mutate focus-time`

`mutate focus-time [title]` — the title is positional and optional, defaulting
to "Focus Time".

Flag            | Description
--------------- | ------------------------------------------------
`--duration`    | Length from now, e.g. `30m`, `1h` (default `1h`)
`--start`       | Explicit start (RFC3339)
`--end`         | Explicit end (RFC3339)
`--description` | Description
`--cal`         | Calendar ID (default `primary`)

`--start` with `--end` gives an exact window and `--duration` is ignored;
`--start` alone runs for `--duration`; neither starts the block now. `--end`
without `--start` is an error.

Focus time takes no attendees; it is a solo block, and it marks the user busy.

### `mutate quick-add`

`mutate quick-add [text]` — hands a natural-language phrase such as `"Lunch at
noon tomorrow"` to Calendar and lets the server parse it. No flags beyond the
global ones, so it always writes to the primary calendar and never notifies
anyone.

The interpretation is Calendar's, not yours: read back the `When:` line it
prints, and confirm it with the user before treating the event as correct.

### `mutate delete`

`mutate delete [eventID]`.

Flag             | Description
---------------- | ----------------------------------------------
`--send-updates` | `all`, `externalOnly`, `none` (default `none`)
`--cal`          | Calendar ID (default `primary`)

There is no confirmation prompt and no `--confirm` flag. The deletion happens
the moment the command runs.

### `mutate rsvp`

`mutate rsvp [eventID]`. Fails unless the caller is an attendee of the event.

Flag       | Description
---------- | --------------------------------------------------------
`--status` | `accepted`, `declined`, `tentative` (default `accepted`)
`--note`   | Response note attached to the RSVP
`--cal`    | Calendar ID (default `primary`)

`--status` is **not** validated locally, so a typo is sent to the API as-is.
Write one of the three documented values exactly.

### `mutate move`

`mutate move [eventID]` — move an event between calendars.

Flag     | Description
-------- | --------------------------------------
`--from` | Source calendar ID (default `primary`)
`--to`   | Destination calendar ID

`--to` is required in practice but not checked locally; omitting it produces a
server-side error. Get the ID from `readonly calendars`.

### `mutate import-ics`

`mutate import-ics [file]` — import an event from an `.ics` file. No flags
beyond the global ones, so it always writes to the primary calendar.

The parser is deliberately minimal and this shapes what you can promise the
user:

-   It reads only `SUMMARY`, `UID`, `DTSTART` and `DTEND`. Description,
    location, attendees and recurrence rules in the file are dropped.
-   It does not split `VEVENT` blocks, so a file holding several events
    collapses into a single event built from the last values seen.
-   Timestamps must carry a time (`20240301T150405Z` or `20240301T150405`).
    Date-only all-day entries fail to parse.

For anything richer, read the file yourself and build the event with `mutate
create`.

### `mutate workloc-set`

Set the caller's working location. See
[working_location.md](working_location.md).

Flag         | Description
------------ | ----------------------------------------------
`--type`     | `office`, `home`, or `custom` (required)
`--building` | Building ID; required when `--type office`
`--label`    | Free-text label; required when `--type custom`
`--date`     | Date to set (`YYYY-MM-DD`, default: today)
`--start`    | Range start (RFC3339); overrides `--date`
`--end`      | Range end (RFC3339); requires `--start`
`--force`    | Overwrite an existing location for that date
`--cal`      | Calendar ID (default `primary`)

`--building` is rejected for `home` and `custom`, and `--label` is rejected for
`home` and `office`. `--date` produces an all-day entry; `--start` with `--end`
produces a timed one, and the two forms are mutually exclusive.
