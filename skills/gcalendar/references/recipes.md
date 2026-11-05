# Recipes

Every command assumes `$GCALENDAR` is set as described in `SKILL.md`.

## Looking at a schedule

```bash
"$GCALENDAR" readonly today --json
"$GCALENDAR" readonly today --timezone America/Los_Angeles --json
"$GCALENDAR" readonly events --max 50 --json
"$GCALENDAR" readonly events --date 2024-03-15 --max 50 --json
"$GCALENDAR" readonly events --start 2024-03-01T09:00:00Z --end 2024-03-01T17:00:00Z
"$GCALENDAR" readonly events --cal alice@example.com
"$GCALENDAR" readonly search "standup" --max 10
"$GCALENDAR" readonly search "1:1" --start 2024-03-01T00:00:00Z --max 10
"$GCALENDAR" readonly get EVENT_ID
"$GCALENDAR" readonly instances EVENT_ID
"$GCALENDAR" readonly conflicts               # today only, ignores all-day events
```

> [!TIP]
>
> Raise `--max` when listing a full day — the default of 20 silently drops late
> afternoon events on a busy calendar. Add `--json` when you are going to parse
> the output or quote exact times, because the table view truncates long titles.
>
> To read another person's calendar, pass their address to `--cal`. You do not
> need any special impersonation flag, and there isn't one.

## Creating and changing events

```bash
"$GCALENDAR" mutate create --summary "Team Sync" \
  --start 2025-01-15T10:00:00Z --end 2025-01-15T11:00:00Z \
  --attendee a@example.com --attendee b@example.com --optional-attendee c@example.com

"$GCALENDAR" mutate create --summary "Private 1:1" \
  --start 2025-01-15T14:00:00Z --end 2025-01-15T15:00:00Z --visibility private

"$GCALENDAR" mutate create --summary "Design Review" \
  --start 2025-01-15T10:00:00Z --end 2025-01-15T11:00:00Z --gvc

"$GCALENDAR" mutate create --summary "Conference" --all-day \
  --start 2025-01-15 --end 2025-01-17

"$GCALENDAR" mutate create --summary "Out of Office" \
  --start 2025-01-15T10:00:00Z --end 2025-01-15T12:00:00Z \
  --ooo --ooo-message "In a workshop, response delayed."

"$GCALENDAR" mutate quick-add "Lunch at noon tomorrow"
"$GCALENDAR" mutate focus-time "Deep Work" --duration 2h
"$GCALENDAR" mutate focus-time "Write proposal" \
  --start 2026-04-22T17:00:00+01:00 --end 2026-04-22T17:25:00+01:00

"$GCALENDAR" mutate recurring "Standup" \
  --start 2024-03-01T09:00:00Z --end 2024-03-01T09:30:00Z \
  --rrule "FREQ=WEEKLY;BYDAY=MO,WE,FR" --attendee a@example.com --attendee b@example.com

"$GCALENDAR" mutate recurring "1:1" \
  --start 2024-03-01T10:00:00Z --end 2024-03-01T10:30:00Z \
  --rrule "FREQ=WEEKLY;COUNT=10" --gvc --modify --attendee a@example.com

"$GCALENDAR" mutate update EVENT_ID --summary "New Title" --start 2025-01-15T14:00:00Z
"$GCALENDAR" mutate update EVENT_ID --description "Flight details and confirmation code"
"$GCALENDAR" mutate update EVENT_ID --rrule "FREQ=WEEKLY;BYDAY=MO,WE"
"$GCALENDAR" mutate update EVENT_ID --rrule ""                      # drop the recurrence
"$GCALENDAR" mutate update EVENT_ID --attendee alice@example.com --attendee bob@example.com
"$GCALENDAR" mutate update EVENT_ID --remove-attendee bob@example.com
"$GCALENDAR" mutate update EVENT_ID --visibility public

"$GCALENDAR" mutate rsvp EVENT_ID --status accepted    # accepted | declined | tentative
"$GCALENDAR" mutate rsvp EVENT_ID --status declined --note "Conflict, will read notes"
"$GCALENDAR" mutate move EVENT_ID --to OTHER_CAL_ID
"$GCALENDAR" mutate delete EVENT_ID
"$GCALENDAR" mutate import-ics /path/to/event.ics
```

Points worth knowing before you run these:

-   **All-day events end on an exclusive date.** `--all-day --start 2025-01-15
    --end 2025-01-17` produces a two-day event covering the 15th and 16th. To
    book a single day, set `--end` to the following day.
-   **`--gvc` and `--meet-code` are mutually exclusive.** Use `--gvc` for a new
    Meet link, `--meet-code` to attach one that already exists.
-   **`--ooo-message` and `--ooo-decline-mode` require `--ooo`** on `create`;
    without it the command fails rather than quietly ignoring them.
-   **`recurring` takes its title positionally**, and accepts a narrower flag
    set than `create` — no optional attendees, location, or visibility. Create
    the series first, then `mutate update` it for the rest.
-   **`create` has no `--duration`.** Compute the end time and pass `--end`.
    `--duration` exists only on `focus-time` and `readonly next-free`.
-   **`update` merges attendees, it does not replace them.** `--attendee` only
    ever adds people or flips an existing person's optional bit. Dropping
    someone needs `--remove-attendee`, matched exactly and case-sensitively, so
    copy the address out of `readonly get`.
-   **`import-ics` reads only the title and the start/end timestamps.**
    Descriptions, locations, attendees and recurrence rules in the file are
    dropped, a multi-event file collapses into one event, and date-only all-day
    entries fail to parse. For anything richer, read the file yourself and build
    the event with `mutate create`.

## Finding a time that works

```bash
"$GCALENDAR" readonly freebusy --email colleague@example.com
"$GCALENDAR" readonly freebusy --email a@example.com --email b@example.com \
  --start 2025-01-15T00:00:00Z --end 2025-01-16T00:00:00Z
"$GCALENDAR" readonly next-free --duration 30m --after 2025-01-15T09:00:00Z
"$GCALENDAR" readonly working-hours
```

Check `freebusy` for everyone you are about to invite before you create the
event. A slot the user described as free is often only free on their own
calendar.

Two defaults that will mislead you if you take the output at face value:

-   **`freebusy` looks only 8 hours ahead** when `--end` is omitted. Pass
    `--start` and `--end` explicitly whenever the question is about a particular
    day or a longer stretch.
-   **`next-free` only knows about the user's own primary calendar**, scans a
    7-day window, and ignores working hours — so it will cheerfully return 3am,
    and it has not considered the other attendees at all. Treat its answer as a
    candidate, then confirm it with `freebusy` across every invitee and against
    the working-hours rows in `readonly working-hours` (which prints the whole
    Calendar settings table, not just the hours).

## Working out when someone is back

When a colleague shares availability but not event details, their time off still
shows up as one long busy block.

```bash
# 1. Look at the next couple of weeks.
"$GCALENDAR" readonly freebusy --email colleague@example.com \
  --start 2026-06-23T07:00:00Z --end 2026-07-07T07:00:00Z
```

The end of the continuous busy block is when they are back. Confirm with their
working location on the first day after it:

```bash
# 2. Are they actually in on their return date?
"$GCALENDAR" readonly workloc --email colleague@example.com --date 2026-07-08
```

> [!NOTE]
>
> The dates above are illustrative. Resolve "next two weeks" against the current
> date before running anything.

## Calendar metadata

```bash
"$GCALENDAR" readonly calendars                       # IDs for every visible calendar
"$GCALENDAR" readonly colors                          # color IDs for --color
"$GCALENDAR" readonly acl --cal primary               # who a calendar is shared with
```

Start with `readonly calendars` whenever the user names a calendar in prose ("my
team calendar"); the other commands need the ID, not the name.
