# Meeting Room CLI

A Python CLI tool for checking and booking meeting rooms through OWA / Exchange.

## Features

- Check free/busy rooms for a time range
- Show range summary across all rooms
- Show a text-based room map
- Show timeline for one room
- Search meetings by reserver name (subject)
- Show daily room availability summary
- Book a specific room
- Smart-book the best matching available room

## Installation

Using uv:

```bash
uv sync
uv run python room_booking.py --help
uv run python calendar_booking.py --help
```

`uv sync` creates `.venv` and installs the dependencies from `uv.lock`.

## Configuration

Create `config.ini` in the project root (next to `room_booking.py`):

```ini
[owa]
username = your_username
password = your_password
```

You can copy `sample.config.ini` as a starting point.

## Usage

General format:

```bash
uv run python room_booking.py [--date YYYY-MM-DD | --when EXPRESSION] COMMAND [COMMAND_OPTIONS]
```

If neither `--date` nor `--when` is provided, today is used.

Date selectors:

```bash
--date 2026-05-02
--when today
--when tomorrow
--when yesterday
--when +2
--when -2
--when saturday
--when "next saturday"
--when "last friday"
--when "next week monday"
```

## Quick Examples

```bash
# Free rooms for today office hours
uv run python room_booking.py --when today free 09:00 18:00

# Free rooms tomorrow with filters
uv run python room_booking.py --when tomorrow free 09:00 18:00 --people 8 --tv

# Room map for next Saturday at 11:00
uv run python room_booking.py --when "next saturday" map 11:00 --duration 60

# Ali's busy/free summary this week Saturday (workday window)
uv run python room_booking.py --when saturday person --name "Ali" 09:00 18:00

# Book a room for next week Monday
uv run python room_booking.py --when "next week monday" book ethereum 14:00 15:00 --subject "Backend Sync"

# Smart-book tomorrow with constraints
uv run python room_booking.py --when tomorrow smart-book 11:00 12:00 --subject "Product Meeting" --people 6 --tv
```

## Commands

### `free`

Show free and busy rooms for a range. If no time is provided, current time + `--duration` is used.

```bash
uv run python room_booking.py free
uv run python room_booking.py free 14:00
uv run python room_booking.py free 14:00 15:00 --people 6 --tv
uv run python room_booking.py --when tomorrow free 09:00 18:00
uv run python room_booking.py --when "next saturday" free 10:00 12:00 --unit "Floor 10"
```

Supported options:

```bash
--duration MINUTES
--people NUMBER
--tv
--no-tv
--unit TEXT
--include-hr
```

### `range`

Show one-line free/busy status per room for a range.

```bash
uv run python room_booking.py range 10:00 11:00
uv run python room_booking.py range 10:00 11:00 --unit "Floor 10" --include-hr
uv run python room_booking.py --when +2 range 09:00 18:00
```

Supported options are the same as `free`.

### `map`

Show the updated text-based room map (green = free, red = busy, yellow = mailbox status unknown).
Floor 10 has separate Node 1, Link 1, Node 2, and Link 2 rooms. The room
labelled Sunda in the source sketch is Sandbox. Solana is at the top; Bitcoin
and Sandbox are higher on the opposite side of the Node/Link pairs; Satoshi and
Doge sit side by side opposite Node 2 and Link 2. Floor 8 shows only TON.

```bash
uv run python room_booking.py map
uv run python room_booking.py map 15:00
uv run python room_booking.py map 10:00 11:00
uv run python room_booking.py map 10:00 --duration 90
uv run python room_booking.py --when tomorrow map 09:00 10:00
```

To view the corrected floor plan without connecting to OWA, open `room-map.svg`
in a browser or run `xdg-open room-map.svg` from the project directory.
The map shows Node 1, Link 1, Node 2, Link 2, and Sandbox in yellow until
their exact Exchange mailbox addresses are configured.

Supported options:

```bash
--duration MINUTES
```

### `room`

Show timeline for one room.

```bash
uv run python room_booking.py room ethereum
uv run python room_booking.py room bitcoin 09:00 18:00 --step 30
uv run python room_booking.py --when "next friday" room eth 09:00 18:00 --step 15
```

Supported options:

```bash
--duration MINUTES
--step MINUTES
```

### `info`

Show static room information.

```bash
uv run python room_booking.py info
uv run python room_booking.py info --people 8 --tv --unit "Floor 10"
```

Supported options:

```bash
--people NUMBER
--tv
--no-tv
--unit TEXT
--include-hr
```

### `person`

Search reservations by reserver name (taken from event subject), with date/time range summary.

```bash
uv run python room_booking.py person
uv run python room_booking.py person --name "Ali"
uv run python room_booking.py --when tomorrow person --name "Ali" 09:00 18:00
uv run python room_booking.py --date 2026-05-10 person --name "Ali" 09:00 --duration 540
uv run python room_booking.py --when "next week monday" person --name "Ali"
```

Supported options:

```bash
--name TEXT
--duration MINUTES
```

Behavior:
- If no time is passed, `person` uses full day (`00:00` to `24:00`) for the selected date.
- Prints busy/free totals for each matched person in the selected window.

### `summary`

Show daily summary per room in a range (free/busy percentages and durations).

```bash
uv run python room_booking.py summary
uv run python room_booking.py summary 09:00 18:00 --include-hr
uv run python room_booking.py --when tomorrow summary 09:00 18:00
```

Supported options:

```bash
--duration MINUTES
--include-hr
```

### `book`

Book a specific room if free.

```bash
uv run python room_booking.py book ethereum 14:00 15:00 --subject "Backend Sync"
uv run python room_booking.py --when tomorrow book btc 11:00 12:00 --subject "Data Review"
uv run python room_booking.py --when "next saturday" book blockchain 10:00 11:30 --subject "Planning"
```

### `smart-book`

Auto-select the best matching free room and book it.

```bash
uv run python room_booking.py smart-book 11:00 12:00 --subject "Product Meeting"
uv run python room_booking.py smart-book 15:00 16:00 --subject "Demo" --people 8 --tv
uv run python room_booking.py --when tomorrow smart-book 09:00 10:00 --subject "Standup" --people 6
uv run python room_booking.py --when +3 smart-book 14:00 15:00 --subject "Design Review" --unit "Floor 10"
```

Supported options:

```bash
--people NUMBER
--tv
--no-tv
--unit TEXT
--include-hr
```

## Configured OWA Mailboxes

The list below is the existing Exchange mailbox configuration. The new floor
plan is already shown by `map`, but the five new room labels are not yet linked
to Exchange mailboxes. Other older mailbox names may still appear in `free`,
`info`, and related commands until the mailbox list is updated.

```text
ethereum
bitcoin
blockchain
dai
doge
link
lightning
ripple
satoshi
stellar
solana
not
ton
oracle
```

Aliases:

```text
eth -> ethereum
btc -> bitcoin
cardano -> blockchain
```

## Notes

- The script reads OWA credentials from `config.ini`.
- Cookie cache is stored in `.cache/rooms_owa_cookies.pkl` inside this repo.
- Date can be selected using exact `--date` or natural `--when` expressions.
- HR-only rooms are hidden by default unless `--include-hr` is used.
- Unknown room capacity or TV status is shown as `?`.
- Times should be in `HH:MM` format.
