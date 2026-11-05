# Working Location

Google Calendar records where a person is working from on a given day. The
`readonly workloc` and `mutate workloc-set` commands read and write that record.

This is also the most reliable way to work out which timezone a colleague is
actually in today, rather than the one their profile implies.

## Reading a location

```bash
# Your own location today
"$GCALENDAR" readonly workloc

# Someone else
"$GCALENDAR" readonly workloc --email alice@example.com

# Several people on a specific date
"$GCALENDAR" readonly workloc \
  --email alice@example.com --email bob@example.com --date 2024-03-15

# A date range
"$GCALENDAR" readonly workloc --email alice@example.com \
  --start 2024-03-10T00:00:00Z --end 2024-03-15T00:00:00Z

# JSON
"$GCALENDAR" readonly workloc --email alice@example.com --date 2024-03-15 --json
```

`--start` overrides `--date` and the two cannot be combined; `--end` requires
`--start` and defaults to one day after it.

### What comes back

Reported type | Meaning
------------- | -----------------------------------------------------
`office`      | In a building; the label carries the building ID
`home`        | Working from home
`custom`      | A free-text location the person typed
`unknown`     | A working-location event whose type is not recognized
`not set`     | No working location configured for that date

A one-off working location **overrides a recurring one** for the same date, and
the recurring entry is dropped from the output. This deduplication applies to
`--json` as well as the table, so the JSON is the resolved view rather than the
raw event list.

When you ask about several people and one lookup fails, that person comes back
as an `error` row while the others still resolve. When you ask about a single
person and the lookup fails, the whole command fails.

### Reading someone else's location

You are authenticated as yourself, so this only works for calendars that person
shares with you. There is no impersonation flag.

An empty result is therefore ambiguous: it means either "nothing configured" or
"not shared with you". Say which one you actually established rather than
reporting an absent location as "working from home".

## Setting a location

`workloc-set` writes only to the caller's own calendar.

```bash
# Today, at home
"$GCALENDAR" mutate workloc-set --type home

# A specific date, in an office building
"$GCALENDAR" mutate workloc-set --date 2026-05-12 --type office --building HQ-WEST-3

# A custom location
"$GCALENDAR" mutate workloc-set --type custom --label "Working from a hotel"

# Part of a day
"$GCALENDAR" mutate workloc-set --type home \
  --start 2026-05-12T09:00:00Z --end 2026-05-12T13:00:00Z

# Overwrite whatever is already set
"$GCALENDAR" mutate workloc-set --type home --date 2026-05-12 --force
```

`--type` is required. `office` additionally requires `--building` and rejects
`--label`; `custom` additionally requires `--label` and rejects `--building`;
`home` takes neither.

`--date` writes an all-day entry. `--start` with `--end` writes a timed one, and
the two forms cannot be combined.

> [!IMPORTANT]
>
> The command refuses to write when an existing working location overlaps the
> target date or range, so a failure here usually means one is already set. Do
> not reach for `--force` on your own: it **deletes** every overlapping entry
> before inserting the new one, which silently discards whatever the user had
> configured. Report what is already there and let the user decide.

> [!WARNING]
>
> **Working location does not know about time off.** Working location and Out of
> Office are separate kinds of event. Someone with a recurring "office" location
> who is on vacation still reports as "office". To tell whether a person is
> actually around, check `readonly freebusy` over the same period for a long
> continuous busy block.
