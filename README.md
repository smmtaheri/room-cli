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

Using Poetry:

```bash
poetry install
poetry run python room_booking.py --help
```

Or with pip:

```bash
pip install requests
python3 room_booking.py --help
```

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
python3 room_booking.py [--date YYYY-MM-DD] COMMAND [COMMAND_OPTIONS]
```

If `--date` is not provided, today is used.

## Commands

### `free`

Show free and busy rooms for a range. If no time is provided, current time + `--duration` is used.

```bash
python3 room_booking.py free
python3 room_booking.py free 14:00
python3 room_booking.py free 14:00 15:00 --people 6 --tv
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
python3 room_booking.py range 10:00 11:00
python3 room_booking.py range 10:00 11:00 --unit "Floor 10" --include-hr
```

Supported options are the same as `free`.

### `map`

Show text-based room map (green = free, red = busy).

```bash
python3 room_booking.py map
python3 room_booking.py map 15:00
python3 room_booking.py map 10:00 11:00
python3 room_booking.py map 10:00 --duration 90
```

Supported options:

```bash
--duration MINUTES
```

### `room`

Show timeline for one room.

```bash
python3 room_booking.py room ethereum
python3 room_booking.py room bitcoin 09:00 18:00 --step 30
```

Supported options:

```bash
--duration MINUTES
--step MINUTES
```

### `info`

Show static room information.

```bash
python3 room_booking.py info
python3 room_booking.py info --people 8 --tv --unit "Floor 10"
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

Search reservations by reserver name (taken from event subject).

```bash
python3 room_booking.py person
python3 room_booking.py person --name "Ali"
```

### `summary`

Show daily summary per room in a range (free/busy percentages and durations).

```bash
python3 room_booking.py summary
python3 room_booking.py summary 09:00 18:00 --include-hr
```

Supported options:

```bash
--duration MINUTES
--include-hr
```

### `book`

Book a specific room if free.

```bash
python3 room_booking.py book ethereum 14:00 15:00 --subject "Backend Sync"
```

### `smart-book`

Auto-select the best matching free room and book it.

```bash
python3 room_booking.py smart-book 11:00 12:00 --subject "Product Meeting"
python3 room_booking.py smart-book 15:00 16:00 --subject "Demo" --people 8 --tv
```

Supported options:

```bash
--people NUMBER
--tv
--no-tv
--unit TEXT
--include-hr
```

## Available Rooms

```text
ethereum
bitcoin
cardano
dai
doge
link
lightning
ripple
solana
not
ton
oracle
```

Aliases:

```text
eth -> ethereum
btc -> bitcoin
```

## Notes

- The script reads OWA credentials from `config.ini`.
- Cookie cache is stored in `.cache/rooms_owa_cookies.pkl` inside this repo.
- HR-only rooms are hidden by default unless `--include-hr` is used.
- Unknown room capacity or TV status is shown as `?`.
- Times should be in `HH:MM` format.