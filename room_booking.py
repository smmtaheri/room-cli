#!/usr/bin/env python3
import argparse
import configparser
import os
import pickle
import re
import uuid
import requests
import textwrap
from pathlib import Path
from datetime import datetime, date, time, timedelta

BASE_URL = "https://bitex-mail.nobitex.net"
LOGIN_URL = f"{BASE_URL}/owa/auth.owa"
AVAILABILITY_URL = f"{BASE_URL}/owa/service.svc?action=GetUserAvailabilityInternal&ID=-76&AC=1"
CREATE_EVENT_URL = f"{BASE_URL}/owa/service.svc?action=CreateCalendarEvent&ID=-84&AC=1"

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = PROJECT_DIR / "config.ini"
COOKIE_FILE = PROJECT_DIR / ".cache" / "rooms_owa_cookies.pkl"
COOKIE_MAX_AGE_SECONDS = 8 * 60 * 60

ROOMS = [
    "Ethereum@nobitex.net",
    "Bitcoin@nobitex.net",
    "blockchain@nobitex.net",
    "dai@nobitex.net",
    "doge@nobitex.net",
    "link@nobitex.net",
    "lightning@nobitex.net",
    "ripple@nobitex.net",
    "Satoshi@nobitex.net",
    "Stellar@nobitex.net",
    "solana@nobitex.net",
    "not@nobitex.net",
    "ton@nobitex.net",
    "oracle@nobitex.net",
]

ROOM_INFO = {
    "ethereum": {"display": "Ethereum", "location": "1003", "unit": "Floor 10", "capacity": 12, "tv": True, "hr_only": False},
    "bitcoin": {"display": "Bitcoin", "location": "1002", "unit": "Floor 10", "capacity": 10, "tv": True, "hr_only": False},
    "blockchain": {"display": "Blockchain", "location": "4th Floor", "unit": "Floor 4", "capacity": 16, "tv": True, "hr_only": False},
    "dai": {"display": "DAI", "location": "1002", "unit": "Floor 10", "capacity": 4, "tv": False, "hr_only": False},
    "doge": {"display": "Doge", "location": "1002", "unit": "Floor 10", "capacity": None, "tv": None, "hr_only": False},
    "link": {"display": "Link", "location": "1002", "unit": "Floor 10", "capacity": 4, "tv": True, "hr_only": True},
    "lightning": {"display": "Lightning", "location": "4th Floor", "unit": "Floor 4", "capacity": 6, "tv": True, "hr_only": False},
    "ripple": {"display": "Ripple", "location": "1002", "unit": "Floor 10", "capacity": 4, "tv": False, "hr_only": False},
    "satoshi": {"display": "Satoshi", "location": "1002", "unit": "Floor 10", "capacity": 4, "tv": True, "hr_only": False},
    "stellar": {"display": "Stellar", "location": "1002", "unit": "Floor 10", "capacity": 4, "tv": True, "hr_only": False},
    "solana": {"display": "Solana", "location": "1001", "unit": "Floor 10", "capacity": 10, "tv": True, "hr_only": False},
    "not": {"display": "NOT", "location": "8th Floor", "unit": "Floor 8", "capacity": 4, "tv": False, "hr_only": False},
    "ton": {"display": "TON", "location": "8th Floor", "unit": "Floor 8", "capacity": 4, "tv": False, "hr_only": False},
    "oracle": {"display": "Oracle", "location": "2nd Floor", "unit": "Floor 2", "capacity": 6, "tv": True, "hr_only": False},
}

BUSY_TYPES = {"Busy", "Tentative", "OOF"}

ALIASES = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "cardano": "blockchain",
    "blockchain": "blockchain",
    "dai": "dai",
    "doge": "doge",
    "link": "link",
    "lightning": "lightning",
    "ripple": "ripple",
    "solana": "solana",
    "not": "not",
    "ton": "ton",
    "oracle": "oracle",
    "satoshi": "satoshi",
    "stellar": "stellar",
}

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def strip_ansi(s):
    return re.sub(r"\033\[[0-9;]*m", "", str(s))


def visible_len(s):
    return len(strip_ansi(s))


def h(n):
    return "─" * n


def parse_hhmm(value):
    return datetime.strptime(value, "%H:%M").time()


WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def resolve_weekday(base_day, target_weekday, direction):
    delta = (target_weekday - base_day.weekday()) % 7
    if direction == "next":
        if delta == 0:
            delta = 7
        return base_day + timedelta(days=delta)
    if direction == "last":
        if delta == 0:
            delta = 7
        return base_day - timedelta(days=(7 - delta))
    raise ValueError("Invalid direction")


def parse_when_expression(value, today=None):
    if not value:
        return None

    text = value.strip().lower()
    today = today or date.today()

    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text == "yesterday":
        return today - timedelta(days=1)

    m = re.fullmatch(r"([+-])\s*(\d+)\s*(?:d|day|days)?", text)
    if m:
        sign, n = m.groups()
        delta = int(n) * (1 if sign == "+" else -1)
        return today + timedelta(days=delta)

    if text in WEEKDAYS:
        target = WEEKDAYS[text]
        delta = (target - today.weekday()) % 7
        return today + timedelta(days=delta)

    m = re.fullmatch(r"(next|last)\s+([a-z]+)", text)
    if m and m.group(2) in WEEKDAYS:
        return resolve_weekday(today, WEEKDAYS[m.group(2)], m.group(1))

    m = re.fullmatch(r"(next|last)\s+week\s+([a-z]+)", text)
    if m and m.group(2) in WEEKDAYS:
        week_base = today + timedelta(days=7 if m.group(1) == "next" else -7)
        target = WEEKDAYS[m.group(2)]
        delta = target - week_base.weekday()
        return week_base + timedelta(days=delta)

    raise SystemExit(
        "Invalid --when value. Examples: today, tomorrow, yesterday, +2, -2, saturday, next saturday, last friday, next week monday."
    )


def resolve_day(date_text, when_text):
    if date_text and when_text:
        raise SystemExit("Use only one of --date or --when.")

    if when_text:
        return parse_when_expression(when_text)

    if date_text:
        return date.fromisoformat(date_text)

    return date.today()


def normalize_room(email):
    return email.split("@")[0].lower()


def room_keys():
    return {normalize_room(email) for email in ROOMS}


def normalize_room_arg(room):
    key = ALIASES.get(room.lower(), room.lower())
    if key not in room_keys():
        raise SystemExit(f"Unknown room: {room}")
    return key


def default_now():
    return datetime.now().replace(second=0, microsecond=0)


def load_credentials():
    parser = configparser.ConfigParser()

    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Missing config file: {CONFIG_FILE}. Copy sample.config.ini to config.ini and fill it."
        )

    parser.read(CONFIG_FILE)

    if "owa" not in parser:
        raise RuntimeError("config.ini is missing [owa] section.")

    username = parser.get("owa", "username", fallback="").strip()
    password = parser.get("owa", "password", fallback="").strip()

    if not username or not password:
        raise RuntimeError("config.ini must define non-empty owa.username and owa.password.")

    return username, password


def save_cookies(session):
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILE, "wb") as f:
        pickle.dump(session.cookies, f)
    os.chmod(COOKIE_FILE, 0o600)


def load_cookies(session):
    if not COOKIE_FILE.exists():
        return False

    age = datetime.now().timestamp() - COOKIE_FILE.stat().st_mtime
    if age > COOKIE_MAX_AGE_SECONDS:
        return False

    try:
        with open(COOKIE_FILE, "rb") as f:
            session.cookies.update(pickle.load(f))
        return True
    except Exception:
        return False


def delete_cached_cookies():
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()


def is_login_page(resp):
    url = resp.url.lower()
    text = resp.text.lower()

    return (
        "logon.aspx" in url
        or "auth/logon" in url
        or "logon.aspx" in text
    )


def create_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/owa/",
    })

    session.cookies.set("PrivateComputer", "true", domain="bitex-mail.nobitex.net")
    session.cookies.set("PBack", "0", domain="bitex-mail.nobitex.net")

    return session


def login_owa():
    username, password = load_credentials()
    session = create_session()

    if load_cookies(session):
        try:
            test_resp = session.get(
                f"{BASE_URL}/owa/",
                timeout=20,
                allow_redirects=True,
            )

            if not is_login_page(test_resp):
                return session

            delete_cached_cookies()

        except requests.RequestException:
            delete_cached_cookies()

    payload = {
        "destination": f"{BASE_URL}/owa/",
        "flags": "4",
        "forcedownlevel": "0",
        "username": username,
        "password": password,
        "passwordText": "",
        "isUtf8": "1",
    }

    resp = session.post(
        LOGIN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
        timeout=20,
    )

    if is_login_page(resp):
        raise RuntimeError(
            "OWA login failed. Check username/password or login rate limit."
        )

    save_cookies(session)
    return session


def build_body(day):
    start = datetime.combine(day, time(0, 0))
    end = start + timedelta(days=1)

    return {
        "request": {
            "__type": "GetUserAvailabilityInternalJsonRequest:#Exchange",
            "Header": {
                "__type": "JsonRequestHeaders:#Exchange",
                "RequestServerVersion": "Exchange2013",
                "TimeZoneContext": {
                    "__type": "TimeZoneContext:#Exchange",
                    "TimeZoneDefinition": {
                        "__type": "TimeZoneDefinitionType:#Exchange",
                        "Id": "Iran Standard Time",
                    },
                },
            },
            "Body": {
                "__type": "GetUserAvailabilityRequest:#Exchange",
                "MailboxDataArray": [
                    {
                        "__type": "MailboxData:#Exchange",
                        "Email": {
                            "__type": "EmailAddress:#Exchange",
                            "Address": email,
                        },
                    }
                    for email in ROOMS
                ],
                "FreeBusyViewOptions": {
                    "__type": "FreeBusyViewOptions:#Exchange",
                    "MergedFreeBusyIntervalInMinutes": 30,
                    "RequestedView": "DetailedMerged",
                    "TimeWindow": {
                        "__type": "Duration:#Exchange",
                        "StartTime": start.isoformat(),
                        "EndTime": end.isoformat(),
                    },
                },
            },
        }
    }


def fetch(day, session):
    canary = session.cookies.get("X-OWA-CANARY")

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json; charset=UTF-8",
        "Action": "GetUserAvailabilityInternal",
        "X-OWA-ActionName": "GetUserAvailabilityInternalAction",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
    }

    if canary:
        headers["X-OWA-CANARY"] = canary

    resp = session.post(
        AVAILABILITY_URL,
        headers=headers,
        json=build_body(day),
        timeout=20,
    )

    if resp.status_code in (401, 403) or is_login_page(resp):
        delete_cached_cookies()
        raise RuntimeError(
            "OWA session expired. Cached cookies removed. Run again to login."
        )

    resp.raise_for_status()
    return resp.json()


def parse_busy(data):
    result = {}
    errors = {}

    for email, resp in zip(ROOMS, data["Body"]["Responses"]):
        room = normalize_room(email)

        msg = resp.get("ResponseMessage", {})
        response_code = msg.get("ResponseCode")

        if response_code != "NoError":
            errors[room] = response_code
            result[room] = []
            continue

        items = resp.get("CalendarView", {}).get("Items") or []
        busy = []

        for item in items:
            if item.get("FreeBusyType") in BUSY_TYPES:
                busy.append((
                    datetime.fromisoformat(item["Start"]),
                    datetime.fromisoformat(item["End"]),
                    item.get("FreeBusyType"),
                    item.get("Subject", ""),
                ))

        result[room] = busy

    if errors:
        print(f"{YELLOW}Warning: skipped rooms with API errors: {errors}{RESET}")

    return result


def overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def get_overlapping_busy_items(busy_items, start, end):
    return [
        item
        for item in busy_items
        if overlaps(start, end, item[0], item[1])
    ]


def reserver_full_name(subject):
    return subject.strip() or "Unknown"


def reserver_names_for_range(busy_items, start, end):
    names = []

    for _, _, _, subject in get_overlapping_busy_items(busy_items, start, end):
        name = reserver_full_name(subject)

        if name not in names:
            names.append(name)

    return names


def room_name_with_reservers(room, busy_items, start, end):
    names = reserver_names_for_range(busy_items, start, end)

    if not names:
        return room

    return f"{room}({', '.join(names)})"


def room_is_free(busy_items, start, end):
    return not any(
        overlaps(start, end, b_start, b_end)
        for b_start, b_end, *_ in busy_items
    )


def busy_minutes(busy_items, start, end):
    total = 0
    merged = []

    for b_start, b_end, *_ in sorted(busy_items):
        s = max(start, b_start)
        e = min(end, b_end)
        if s >= e:
            continue

        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)

    for s, e in merged:
        total += int((e - s).total_seconds() // 60)

    return total


def minutes_to_hhmm(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h}h{m:02d}m"


def merge_intervals(intervals):
    merged = []
    for s, e in sorted(intervals):
        if s >= e:
            continue
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return merged


def overlap_window(start, end, win_start, win_end):
    s = max(start, win_start)
    e = min(end, win_end)
    if s >= e:
        return None
    return s, e


def room_info(room):
    return ROOM_INFO.get(room, {
        "display": room,
        "location": "?",
        "unit": "?",
        "capacity": None,
        "tv": None,
        "hr_only": False,
    })


def room_info_text(room):
    info = room_info(room)
    cap = "?" if info["capacity"] is None else str(info["capacity"])
    tv = "✅" if info["tv"] is True else "✖️" if info["tv"] is False else "?"
    hr = " | HR only" if info["hr_only"] else ""
    return f'{info["display"]} | {info["unit"]} | 📍:{info["location"]} | 👥:{cap} | TV:{tv}{hr}'


def room_display_for_booking(room):
    info = room_info(room)
    cap = "?" if info["capacity"] is None else str(info["capacity"])
    tv = "✅" if info["tv"] is True else "✖️" if info["tv"] is False else "?"
    hr = " (HR only)" if info["hr_only"] else ""
    return f'{info["display"]} (📍:{info["location"]} | 👥:{cap} | TV:{tv}){hr}'


def room_matches_filters(room, people=None, tv=None, unit=None, include_hr=False):
    info = room_info(room)

    if people is not None:
        if info["capacity"] is None or info["capacity"] < people:
            return False

    if tv is True and info["tv"] is not True:
        return False

    if tv is False and info["tv"] is not False:
        return False

    if unit:
        needle = unit.lower()
        if needle not in str(info["unit"]).lower() and needle not in str(info["location"]).lower():
            return False

    if not include_hr and info["hr_only"]:
        return False

    return True


def status_symbol(is_free):
    return f"{GREEN}● FREE{RESET}" if is_free else f"{RED}● BUSY{RESET}"


def room_box_lines(name, busy_by_room, start, end, min_width=16, max_width=34):
    key = ALIASES.get(name.lower(), name.lower())
    known = key in busy_by_room
    busy_items = busy_by_room.get(key, [])
    free = room_is_free(busy_items, start, end) if known else None
    color = GREEN if free is True else RED if free is False else YELLOW

    names = reserver_names_for_range(busy_items, start, end) if known else ["STATUS UNKNOWN"]

    longest = max([len(name), *(len(person) for person in names)] or [len(name)])
    width = min(max_width, max(min_width, longest + 4))
    inner_width = width - 2
    text_width = inner_width - 2

    people_lines = []

    for person in names:
        wrapped = textwrap.wrap(
            person,
            width=text_width,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [person]

        for part in wrapped:
            if len(part) > text_width:
                part = part[:max(0, text_width - 3)] + "..."
            people_lines.append(part)

    if not people_lines:
        people_lines = [""]

    lines = [
        f"{color}┌{h(inner_width)}┐{RESET}",
        f"{color}│{name.center(inner_width)}│{RESET}",
    ]

    for person_line in people_lines:
        lines.append(f"{color}│{person_line.center(inner_width)}│{RESET}")

    lines.append(f"{color}└{h(inner_width)}┘{RESET}")

    return lines, width


def pad_visible(s, width):
    return s + (" " * max(0, width - visible_len(s)))


def render_at(x, boxes, gap=4):
    row = " " * x

    for i, box in enumerate(boxes):
        if i:
            row += " " * gap
        row += box

    return row


def normalize_box_height(box_lines, target_height):
    lines_ = list(box_lines)
    color = GREEN if "92m" in lines_[0] else RED
    inner_width = visible_len(lines_[0]) - 2

    while len(lines_) < target_height:
        lines_.insert(-1, f"{color}│{' ' * inner_width}│{RESET}")

    return lines_


def render_box_group_at(x, box_items, gap=4):
    max_height = max(len(lines_) for lines_, _ in box_items)

    normalized = [
        normalize_box_height(lines_, max_height)
        for lines_, _ in box_items
    ]

    rendered = []

    for i in range(max_height):
        parts = [box[i] for box in normalized]
        rendered.append(render_at(x, parts, gap=gap))

    return rendered


def print_floor_block(title, rendered_rows, padding_right=2):
    width = max(visible_len(row) for row in rendered_rows) + padding_right

    print()
    print(title.center(width))
    print("┌" + h(width) + "┐")

    for row in rendered_rows:
        print("│" + pad_visible(row, width) + "│")

    print("└" + h(width) + "┘")


def render_room_grid(layout, box, gap=3):
    rows = [[box(name) if name else None for name in row] for row in layout]
    widths = [
        max((item[1] for row in rows if (item := row[col]) is not None), default=16)
        for col in range(len(layout[0]))
    ]
    rendered = []

    for row in rows:
        height = max(len(item[0]) for item in row if item is not None)
        for line_index in range(height):
            cells = [
                pad_visible(item[0][line_index], widths[col])
                if item is not None and line_index < len(item[0])
                else " " * widths[col]
                for col, item in enumerate(row)
            ]
            rendered.append((" " * gap).join(cells))
        rendered.append("")

    return rendered[:-1]


def print_map(busy_by_room, day, from_t, to_t):
    start = datetime.combine(day, from_t)
    end = datetime.combine(day, to_t)

    def box(room):
        return room_box_lines(room, busy_by_room, start, end)

    print(f"\n{BOLD}Map view: {day} {from_t} → {to_t}{RESET}")
    print(f"{GREEN}Green = free{RESET} | {RED}Red = busy{RESET} | {YELLOW}Yellow = status unknown{RESET}")

    floor10_rows = render_room_grid(
        [
            [None, None, None, "Solana", None],
            [None, None, None, None, "Bitcoin"],
            ["Node 1", "Link 1", None, None, "Sandbox"],
            ["Node 2", "Link 2", None, "Satoshi", "Doge"],
            ["Stellar", None, None, None, None],
            ["Ethereum", None, None, None, None],
        ],
        box,
    )

    print_floor_block("Floor 10", floor10_rows)

    floor8_rows = render_box_group_at(
        10,
        [box("TON")],
        gap=10,
    )
    print_floor_block("Floor 8", floor8_rows)

    ajori_rows = render_box_group_at(
        10,
        [box("Blockchain"), box("Oracle")],
        gap=10,
    )
    print_floor_block("Ajori", ajori_rows)


def print_free_rooms(busy_by_room, start, minutes=60, people=None, tv=None, unit=None, include_hr=False):
    end = start + timedelta(minutes=minutes)

    print(f"\n{BOLD}{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%H:%M')}{RESET}\n")

    free = []
    busy = []

    for room in sorted(busy_by_room):
        if not room_matches_filters(room, people, tv, unit, include_hr):
            continue

        room_label = room_name_with_reservers(room, busy_by_room[room], start, end)
        room_label = f"{room_label} [{room_info_text(room)}]"

        if room_is_free(busy_by_room[room], start, end):
            free.append(room_label)
        else:
            busy.append(room_label)

    print(f"{GREEN}FREE:{RESET}")
    print("\n".join(f"  - {x}" for x in free) if free else "  -")
    print(f"\n{RED}BUSY:{RESET}")
    print("\n".join(f"  - {x}" for x in busy) if busy else "  -")


def print_range_summary(busy_by_room, day, from_t, to_t, people=None, tv=None, unit=None, include_hr=False):
    start = datetime.combine(day, from_t)
    end = datetime.combine(day, to_t)

    print(f"\n{BOLD}Range {start.strftime('%H:%M')} → {end.strftime('%H:%M')}{RESET}\n")

    for room in sorted(busy_by_room):
        if not room_matches_filters(room, people, tv, unit, include_hr):
            continue

        room_label = room_name_with_reservers(room, busy_by_room[room], start, end)
        free = room_is_free(busy_by_room[room], start, end)
        print(f"{room_label:<40} {status_symbol(free)}  {room_info_text(room)}")


def print_room_timeline(busy_by_room, room, day, from_t, to_t, step_minutes):
    room = normalize_room_arg(room)

    if room not in busy_by_room:
        raise SystemExit(f"Unknown room: {room}")

    start = datetime.combine(day, from_t)
    end = datetime.combine(day, to_t)
    cursor = start

    room_label = room_name_with_reservers(room, busy_by_room[room], start, end)

    print(f"\n{BOLD}{room_label} timeline: {from_t.strftime('%H:%M')} → {to_t.strftime('%H:%M')}{RESET}")
    print(f"{CYAN}{room_info_text(room)}{RESET}\n")

    while cursor < end:
        slot_end = min(cursor + timedelta(minutes=step_minutes), end)
        slot_label = room_name_with_reservers(room, busy_by_room[room], cursor, slot_end)
        free = room_is_free(busy_by_room[room], cursor, slot_end)

        color = GREEN if free else RED
        label = "FREE" if free else "BUSY"
        bar = "░░░░░░" if free else "██████"

        print(
            f"{cursor.strftime('%H:%M')} - {slot_end.strftime('%H:%M')} | "
            f"{slot_label:<40} | {color}{bar} {label}{RESET}"
        )

        cursor = slot_end


def print_rooms_info(people=None, tv=None, unit=None, include_hr=True):
    print(f"\n{BOLD}Rooms info{RESET}\n")

    for room in sorted(normalize_room(email) for email in ROOMS):
        if not room_matches_filters(room, people, tv, unit, include_hr):
            continue
        print(f"- {room:<10} {room_info_text(room)}")


def print_person_report(busy_by_room, window_start, window_end, name_filter=None):
    people = {}

    for room, busy_items in busy_by_room.items():
        for start, end, fb_type, subject in busy_items:
            person = reserver_full_name(subject)
            if name_filter and name_filter.lower() not in person.lower():
                continue
            clipped = overlap_window(start, end, window_start, window_end)
            if not clipped:
                continue
            people.setdefault(person, [])
            people[person].append((clipped[0], clipped[1], room, fb_type))

    total_window_minutes = int((window_end - window_start).total_seconds() // 60)
    print(
        f"\n{BOLD}Person report{RESET} "
        f"({window_start.strftime('%Y-%m-%d %H:%M')} → {window_end.strftime('%H:%M')})\n"
    )

    if not people:
        print(f"{YELLOW}No reservation found.{RESET}")
        return

    for person in sorted(people):
        intervals = [(s, e) for s, e, *_ in people[person]]
        merged = merge_intervals(intervals)
        busy_m = sum(int((e - s).total_seconds() // 60) for s, e in merged)
        free_m = max(0, total_window_minutes - busy_m)
        busy_pct = (busy_m / total_window_minutes * 100) if total_window_minutes else 0
        free_pct = (free_m / total_window_minutes * 100) if total_window_minutes else 0

        print(f"{CYAN}{person}{RESET}")
        print(
            f"  Summary: busy={minutes_to_hhmm(busy_m)} ({busy_pct:.1f}%) | "
            f"free={minutes_to_hhmm(free_m)} ({free_pct:.1f}%)"
        )
        for start, end, room, fb_type in sorted(people[person]):
            print(
                f"  - {start.strftime('%H:%M')} → {end.strftime('%H:%M')} | "
                f"{room:<10} | {fb_type:<9} | {room_info_text(room)}"
            )
        print()


def print_daily_summary(busy_by_room, day, from_t, to_t, include_hr=False):
    start = datetime.combine(day, from_t)
    end = datetime.combine(day, to_t)
    total = int((end - start).total_seconds() // 60)

    rows = []

    for room, busy_items in busy_by_room.items():
        if not room_matches_filters(room, include_hr=include_hr):
            continue

        busy_m = busy_minutes(busy_items, start, end)
        free_m = max(0, total - busy_m)
        free_pct = (free_m / total * 100) if total else 0
        busy_pct = (busy_m / total * 100) if total else 0

        rows.append((free_pct, busy_pct, free_m, busy_m, room))

    rows.sort(reverse=True)

    print(f"\n{BOLD}Daily summary {from_t.strftime('%H:%M')} → {to_t.strftime('%H:%M')}{RESET}\n")
    print(f"{'Room':<12} {'Free%':>7} {'Busy%':>7} {'Free':>8} {'Busy':>8} Info")
    print("-" * 120)

    for free_pct, busy_pct, free_m, busy_m, room in rows:
        print(
            f"{room:<12} "
            f"{free_pct:>6.1f}% "
            f"{busy_pct:>6.1f}% "
            f"{free_m//60:>2}h{free_m%60:02d}m "
            f"{busy_m//60:>2}h{busy_m%60:02d}m "
            f"{room_info_text(room)}"
        )

    if rows:
        most_available = rows[0][4]
        most_busy = sorted(rows, key=lambda x: x[3], reverse=True)[0][4]
        print()
        print(f"{GREEN}Most available:{RESET} {room_info_text(most_available)}")
        print(f"{RED}Most busy:{RESET} {room_info_text(most_busy)}")


def get_time_range(day, from_time=None, to_time=None, duration=60):
    now_dt = default_now()

    if from_time and to_time:
        start = datetime.combine(day, parse_hhmm(from_time))
        end = datetime.combine(day, parse_hhmm(to_time))

    elif from_time and not to_time:
        start = datetime.combine(day, parse_hhmm(from_time))
        end = start + timedelta(minutes=duration)

    elif not from_time and not to_time:
        start = datetime.combine(day, now_dt.time())
        end = start + timedelta(minutes=duration)

    else:
        raise SystemExit("Invalid time range")

    if end <= start:
        raise SystemExit("End time must be after start time")

    return start, end


def find_room_email(room):
    for email in ROOMS:
        if normalize_room(email) == room:
            return email
    raise SystemExit(f"Unknown room: {room}")


def build_booking_body(room, subject, start_dt, end_dt):
    email = find_room_email(room)
    display = room_display_for_booking(room)

    html = """
<html>
  <body>
    <div style="font-size:12pt;font-family:Calibri,Helvetica,sans-serif;">
      <p><br></p>
    </div>
  </body>
</html>
""".strip()

    return {
        "__type": "CreateItemJsonRequest:#Exchange",
        "Header": {
            "__type": "JsonRequestHeaders:#Exchange",
            "RequestServerVersion": "V2017_08_18",
            "TimeZoneContext": {
                "__type": "TimeZoneContext:#Exchange",
                "TimeZoneDefinition": {
                    "__type": "TimeZoneDefinitionType:#Exchange",
                    "Id": "Iran Standard Time",
                },
            },
        },
        "Body": {
            "__type": "CreateItemRequest:#Exchange",
            "Items": [
                {
                    "__type": "CalendarItem:#Exchange",
                    "ClientSeriesId": str(uuid.uuid4()),
                    "Subject": subject,
                    "Body": {
                        "__type": "BodyContentType:#Exchange",
                        "BodyType": "HTML",
                        "Value": html,
                    },
                    "Sensitivity": "Normal",
                    "ReminderIsSet": True,
                    "ReminderMinutesBeforeStart": 15,
                    "IsResponseRequested": True,
                    "DoNotForwardMeeting": False,
                    "IsAllDayEvent": False,
                    "Start": start_dt.strftime("%Y-%m-%dT%H:%M:%S.000"),
                    "End": end_dt.strftime("%Y-%m-%dT%H:%M:%S.000"),
                    "FreeBusyType": "Busy",
                    "Resources": [
                        {
                            "__type": "AttendeeType:#Exchange",
                            "Mailbox": {
                                "Name": display,
                                "EmailAddress": email,
                                "RoutingType": "SMTP",
                                "MailboxType": "Mailbox",
                            },
                        }
                    ],
                    "Location": {
                        "__type": "EnhancedLocation:#Exchange",
                        "Annotation": "",
                        "DisplayName": display,
                        "PostalAddress": {
                            "__type": "PersonaPostalAddress:#Exchange",
                            "Type": "Business",
                            "LocationSource": "Resource",
                            "LocationUri": email,
                        },
                    },
                    "unfoldedIndex": 0,
                }
            ],
            "ClientSupportsIrm": True,
            "SavedItemFolderId": {
                "__type": "TargetFolderId:#Exchange",
                "BaseFolderId": {
                    "__type": "DistinguishedFolderId:#Exchange",
                    "Id": "calendar",
                },
            },
        },
    }


def create_booking(session, room, subject, start_dt, end_dt):
    canary = session.cookies.get("X-OWA-CANARY")

    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json; charset=UTF-8",
        "Action": "CreateCalendarEvent",
        "X-OWA-ActionName": "CreateCalendarEventAction",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
    }

    if canary:
        headers["X-OWA-CANARY"] = canary

    resp = session.post(
        CREATE_EVENT_URL,
        headers=headers,
        json=build_booking_body(room, subject, start_dt, end_dt),
        timeout=20,
    )

    if resp.status_code in (401, 403) or is_login_page(resp):
        delete_cached_cookies()
        raise RuntimeError("OWA session expired. Cached cookies removed. Run again.")

    resp.raise_for_status()
    return resp.json()


def book_room(session, busy_by_room, room, subject, start, end):
    room = normalize_room_arg(room)

    if not room_is_free(busy_by_room.get(room, []), start, end):
        label = room_name_with_reservers(room, busy_by_room.get(room, []), start, end)
        raise SystemExit(f"{RED}Room is busy:{RESET} {label}")

    create_booking(session, room, subject, start, end)
    print(
        f"{GREEN}Booking request sent:{RESET} "
        f"{room_info_text(room)} | {start.strftime('%H:%M')} → {end.strftime('%H:%M')} | {subject}"
    )


def smart_book(session, busy_by_room, subject, start, end, people=None, tv=None, unit=None, include_hr=False):
    candidates = []

    for room in sorted(busy_by_room):
        if not room_matches_filters(room, people, tv, unit, include_hr):
            continue

        if room_is_free(busy_by_room[room], start, end):
            cap = room_info(room)["capacity"]
            score = cap if cap is not None else 999
            candidates.append((score, room))

    if not candidates:
        raise SystemExit(f"{RED}No free room matched your requirements.{RESET}")

    candidates.sort()
    selected = candidates[0][1]

    print(f"{GREEN}Smart selected:{RESET} {room_info_text(selected)}")
    create_booking(session, selected, subject, start, end)
    print(
        f"{GREEN}Booking request sent:{RESET} "
        f"{selected} | {start.strftime('%H:%M')} → {end.strftime('%H:%M')} | {subject}"
    )


def add_filters(parser):
    parser.add_argument("--people", type=int)
    parser.add_argument("--tv", action="store_true")
    parser.add_argument("--no-tv", action="store_true")
    parser.add_argument("--unit")
    parser.add_argument("--include-hr", action="store_true")


def resolve_tv(args):
    if getattr(args, "tv", False):
        return True
    if getattr(args, "no_tv", False):
        return False
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--when")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_free = sub.add_parser("free")
    p_free.add_argument("from_time", nargs="?")
    p_free.add_argument("to_time", nargs="?")
    p_free.add_argument("--duration", type=int, default=60)
    add_filters(p_free)

    p_range = sub.add_parser("range")
    p_range.add_argument("from_time", nargs="?")
    p_range.add_argument("to_time", nargs="?")
    p_range.add_argument("--duration", type=int, default=60)
    add_filters(p_range)

    p_map = sub.add_parser("map")
    p_map.add_argument("from_time", nargs="?")
    p_map.add_argument("to_time", nargs="?")
    p_map.add_argument("--duration", type=int, default=60)

    p_room = sub.add_parser("room")
    p_room.add_argument("room")
    p_room.add_argument("from_time", nargs="?")
    p_room.add_argument("to_time", nargs="?")
    p_room.add_argument("--duration", type=int, default=60)
    p_room.add_argument("--step", type=int, default=30)

    p_info = sub.add_parser("info")
    add_filters(p_info)

    p_person = sub.add_parser("person")
    p_person.add_argument("--name")
    p_person.add_argument("from_time", nargs="?")
    p_person.add_argument("to_time", nargs="?")
    p_person.add_argument("--duration", type=int, default=60)

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("from_time", nargs="?")
    p_summary.add_argument("to_time", nargs="?")
    p_summary.add_argument("--duration", type=int, default=60)
    p_summary.add_argument("--include-hr", action="store_true")

    p_book = sub.add_parser("book")
    p_book.add_argument("room")
    p_book.add_argument("from_time")
    p_book.add_argument("to_time")
    p_book.add_argument("--subject", required=True)

    p_smart = sub.add_parser("smart-book")
    p_smart.add_argument("from_time")
    p_smart.add_argument("to_time")
    p_smart.add_argument("--subject", required=True)
    add_filters(p_smart)

    args = parser.parse_args()
    day = resolve_day(args.date, args.when)

    if args.cmd == "info":
        print_rooms_info(
            people=args.people,
            tv=resolve_tv(args),
            unit=args.unit,
            include_hr=args.include_hr,
        )
        return

    session = login_owa()
    data = fetch(day, session)
    busy_by_room = parse_busy(data)

    if args.cmd == "free":
        start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        minutes = int((end - start).total_seconds() / 60)
        print_free_rooms(
            busy_by_room,
            start,
            minutes=minutes,
            people=args.people,
            tv=resolve_tv(args),
            unit=args.unit,
            include_hr=args.include_hr,
        )

    elif args.cmd == "range":
        start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        print_range_summary(
            busy_by_room,
            day,
            start.time(),
            end.time(),
            people=args.people,
            tv=resolve_tv(args),
            unit=args.unit,
            include_hr=args.include_hr,
        )

    elif args.cmd == "map":
        start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        print_map(busy_by_room, day, start.time(), end.time())

    elif args.cmd == "room":
        start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        print_room_timeline(
            busy_by_room,
            args.room,
            day,
            start.time(),
            end.time(),
            args.step,
        )

    elif args.cmd == "person":
        if args.from_time or args.to_time:
            start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        else:
            start = datetime.combine(day, time(0, 0))
            end = start + timedelta(days=1)
        print_person_report(busy_by_room, start, end, name_filter=args.name)

    elif args.cmd == "summary":
        start, end = get_time_range(day, args.from_time, args.to_time, args.duration)
        print_daily_summary(
            busy_by_room,
            day,
            start.time(),
            end.time(),
            include_hr=args.include_hr,
        )

    elif args.cmd == "book":
        start, end = get_time_range(day, args.from_time, args.to_time, duration=60)
        book_room(session, busy_by_room, args.room, args.subject, start, end)

    elif args.cmd == "smart-book":
        start, end = get_time_range(day, args.from_time, args.to_time, duration=60)
        smart_book(
            session,
            busy_by_room,
            args.subject,
            start,
            end,
            people=args.people,
            tv=resolve_tv(args),
            unit=args.unit,
            include_hr=args.include_hr,
        )


if __name__ == "__main__":
    main()
