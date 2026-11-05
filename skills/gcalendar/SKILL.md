---
name: gcalendar
description: >-
  Read, create, update, and manage Google Calendar events, schedules, free/busy availability, working locations, focus time, and Out of Office blocks via the gcalendar CLI. Use when inspecting calendars, checking scheduling conflicts across timezones, creating or updating meetings with Google Meet links, RSVPing to invitations, or importing ICS files.
---

# Google Calendar

Work with the calendars and events the user names or links to. Commands that act
on a single event take an **event ID**; commands that act on a calendar take a
**calendar ID**, which is an email address for a person or a room.

>
> `mutate delete` removes an event immediately. There is no confirmation prompt,
> no `--confirm` flag, and no undo. **Never** delete an event unless the user
> explicitly asked you to delete that specific event, and say which event you
> are about to remove before you run it.
>
> **Calendar writes reach other people.** Creating, updating, moving, or
> deleting an event that has guests can email all of them, and an invitation
> cannot be recalled. Confirm the title, time, and guest list with the user
> before you write, rather than fixing it afterwards.
>
> **Never invite anyone the user did not name**, and never widen an event's
> visibility on your own initiative.

## Setup and Authentication

`gcalendar auth status` is the only way to tell whether you are logged in. Do
not run `--help`, search the filesystem or environment for tokens, check another
plugin's login, or run an operational command before logging in. Follow these
steps exactly.

**1. Register and check.** Run this skill's script with `auth status`. It
downloads the CLI, registers `gcalendar` on the agent's `PATH` (not the user's
shell), and reports whether you are logged in:

```bash
<path/to/this/skill>/scripts/gcalendar auth status
```

```powershell
# Windows (PowerShell)
& "<path\to\this\skill>\scripts\gcalendar.cmd" auth status
```

Every later call is just `gcalendar`. Never ask the user to run it; they cannot.
If it reports `Logged in`, you are ready.

**2. Log in for the user.** Start this as a background command:

```bash
gcalendar auth login
```

It prints an authorization URL and exits on its own once the user approves. Read
the URL from the task's log, open it in the user's browser or hand them the
link, then stop and wait. Confirm with `gcalendar auth status`.

## Usage

Do every Calendar operation — listing, searching, creating, updating, RSVPing —
through `gcalendar`. Every command sits under one of two namespaces:

-   `readonly` lists and searches events and checks availability without
    changing anything.
-   `mutate` creates, updates, deletes, and RSVPs to events.

So the commands read `gcalendar readonly events` and `gcalendar mutate create`.
Flat forms like `gcalendar events` still work but are deprecated and print a
migration warning; always write the namespaced form.

### Read the calendar before you write to it

> [!IMPORTANT]
>
> A time that looks free in the user's request is often already taken, and
> double-booking is the failure they will notice. Before creating or moving
> anything:
>
> 1.  Look at the day with `readonly events --date <date> --max 50 --json`.
> 2.  Check every invitee with `readonly freebusy --email ... --start ... --end
>     ...`, passing the range explicitly.
> 3.  Only then create the event, and report back the `Link:` the command
>     prints.
>
> The same applies to identity: run `readonly calendars` when the user refers to
> a calendar by name ("my team calendar") rather than guessing an ID, and
> `readonly get EVENT_ID` before editing an event you have not already read in
> this session.

### Times and timezones

> [!IMPORTANT]
>
> Timestamps are RFC3339 (`2025-01-15T10:00:00Z` or `2025-01-15T10:00:00-08:00`)
> and dates are `YYYY-MM-DD`. When neither `--timezone` nor an offset is given,
> the CLI uses the timezone from the user's Calendar settings.
>
> **Resolve relative dates before you build a command.** "Tomorrow", "next
> Tuesday", and "in two weeks" have to become concrete dates in the user's
> timezone first; never paste a relative phrase into `--start`. Use `readonly
> workloc` if you need to know which timezone a colleague is actually in.
>
> **All-day events end on an exclusive date.** `--all-day --start 2025-01-15
> --end 2025-01-16` is one day, the 15th. The CLI passes the dates straight
> through and will not add the extra day for you.

### Reporting back

Mutating commands print a `Link:` line for the event they created. Always pass
that URL through to the user so they can check the result, and quote the event
ID for anything they may want to change next.

Where a command prints nothing useful — `mutate update`, for instance, prints no
link — follow up with `readonly get EVENT_ID` rather than telling the user the
change "should" have worked.

## Recipes

See [references/recipes.md](references/recipes.md) for worked examples covering
viewing a schedule, creating and editing events, finding a slot that works for a
group, and determining when someone on leave is back.

## Commands

The essentials are below. For every flag of every command, including the
defaults that are easy to get wrong, see
[references/commands.md](references/commands.md).

| Command                  | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `readonly events`        | List events over a date or a range                |
| `readonly today`         | Today's events                                    |
| `readonly search`        | Search events by keyword                          |
| `readonly get`           | Full details for one event                        |
| `readonly instances`     | Occurrences of a recurring event                  |
| `readonly conflicts`     | Overlapping events today                          |
| `readonly calendars`     | List calendars and their IDs                      |
| `readonly colors`        | Color IDs for `--color`                           |
| `readonly acl`           | Who a calendar is shared with                     |
| `readonly freebusy`      | Busy intervals for one or more people             |
| `readonly next-free`     | First open slot on the user's own calendar        |
| `readonly working-hours` | Calendar settings, including timezone and working |
:                          : hours                                             :
| `readonly workloc`       | Where someone is working from                     |
| `mutate create`          | Create an event                                   |
| `mutate update`          | Update an event                                   |
| `mutate recurring`       | Create a recurring series from an RRULE           |
| `mutate focus-time`      | Block out solo focus time                         |
| `mutate quick-add`       | Create an event from a natural-language phrase    |
| `mutate rsvp`            | Respond to an invitation                          |
| `mutate move`            | Move an event to another calendar                 |
| `mutate delete`          | Delete an event                                   |
| `mutate import-ics`      | Import an event from an ICS file                  |
| `mutate workloc-set`     | Set your working location                         |

### Notifications

`--send-updates` controls who gets emailed, and it defaults to `none` on
`create`, `update`, `recurring`, and `delete`. That default is the safe one, but
it also means **guests are not told about an event you create or cancel** unless
you opt in with `--send-updates all`.

Decide deliberately and say which you chose: silent for the user's own blocks
and drafts, `all` when the user is actually inviting people or cancelling on
them.

### Meetings with other people

-   `--attendee` and `--optional-attendee` take one address each and repeat.
-   `--gvc` attaches a new Google Meet conference; `--meet-code` attaches one
    that already exists. They are mutually exclusive.
-   On `mutate update`, attendee flags **merge** into the existing guest list
    rather than replacing it. Use `--remove-attendee` to drop someone, matching
    the address exactly.
-   `--location` is free text and **does not book a room**. Rooms are calendar
    resources that have to be invited as attendees, so pass the room's resource
    address to `--attendee`. This CLI cannot search for rooms or check their
    availability by name; ask the user for the address, or check a candidate
    with `readonly freebusy --email <room address>`.

### Blocking time out

-   `mutate focus-time` creates a solo block. It takes no attendees, and
    `--duration` (default `1h`) applies from now unless you give `--start`.
-   `mutate create --ooo` creates an Out of Office event that can auto-decline
    conflicting invitations. `--ooo-message` and `--ooo-decline-mode` only work
    alongside `--ooo`.

## Working Location

`readonly workloc` and `mutate workloc-set` read and write where someone is
working from — office, home, or a custom location — which is also the most
reliable way to tell which timezone a colleague is in today.

See [references/working_location.md](references/working_location.md) for the
details, including the rule that a one-off location overrides a recurring one
and the reasons an empty result is ambiguous.

> [!WARNING]
>
> Working location is not time off. Someone with a recurring "office" location
> who is on vacation still reports as "office"; check `readonly freebusy` over
> the same period before telling the user that a colleague is around.

## Global Flags

-   `--json` — emit JSON instead of a table. Use it whenever you are going to
    parse the output or quote exact times, because the table view truncates.
-   `--timezone` — IANA timezone override, e.g. `America/Los_Angeles`. Defaults
    to the timezone in the user's Calendar settings.
-   `--legacy-mode` — how deprecated flat commands are handled: `allowed`,
    `deprecated` (default), or `banned`.
-   `-v`, `--version` — print the CLI build version.

# Core Implementation & Verification Checklist

| Check | Requirement | Status |
| :--- | :--- | :--- |
| **Input Validation** | Verify all parameters, schemas, and types before execution | Mandatory |
| **Error Handling** | Return explicit structured errors without silent fallbacks | Mandatory |
| **Verification** | Run static and runtime checks after changes | Mandatory |
