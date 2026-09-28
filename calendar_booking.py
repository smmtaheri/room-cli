import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil.parser import isoparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKENS_DIR = BASE_DIR / "tokens"
TEAMS_FILE = BASE_DIR / "teams.json"

DEFAULT_TIMEZONE = "Europe/Amsterdam"


def get_calendar_service(user_key="default"):
    TOKENS_DIR.mkdir(exist_ok=True)

    token_file = TOKENS_DIR / f"{user_key}.json"
    creds = None

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.valid:
        return build("calendar", "v3", credentials=creds)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE),
            SCOPES,
        )

        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )

    token_file.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def load_teams():
    if not TEAMS_FILE.exists():
        return {}

    content = TEAMS_FILE.read_text().strip()

    if not content:
        return {}

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def save_teams(teams):
    TEAMS_FILE.write_text(json.dumps(teams, indent=2, sort_keys=True))


def validate_emails(emails):
    pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    invalid = [email for email in emails if not pattern.match(email)]

    if invalid:
        raise ValueError(f"Invalid email(s): {', '.join(invalid)}")


def parse_day(day, timezone):
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)

    if day == "today":
        target = now
    elif day == "tomorrow":
        target = now + timedelta(days=1)
    else:
        target = datetime.fromisoformat(day).replace(tzinfo=tz)

    return target.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_hhmm(value):
    hour, minute = map(int, value.split(":"))

    if hour == 24 and minute == 0:
        return 24, 0

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Invalid time: {value}")

    return hour, minute


def apply_time(day_start, time_text):
    hour, minute = parse_hhmm(time_text)

    if hour == 24 and minute == 0:
        return day_start + timedelta(days=1)

    return day_start.replace(hour=hour, minute=minute)


def format_duration(delta):
    minutes = int(delta.total_seconds() // 60)

    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60
    rest = minutes % 60

    if rest == 0:
        return f"{hours} hour" if hours == 1 else f"{hours} hours"

    return f"{hours}h {rest}m"


def merge_busy_blocks(busy_blocks):
    if not busy_blocks:
        return []

    busy_blocks = sorted(busy_blocks, key=lambda item: item[0])
    merged = [busy_blocks[0]]

    for start, end in busy_blocks[1:]:
        last_start, last_end = merged[-1]

        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def get_free_slots_from_busy(busy_blocks, work_start, work_end):
    busy_blocks = merge_busy_blocks(busy_blocks)

    free_slots = []
    cursor = work_start

    for busy_start, busy_end in busy_blocks:
        if busy_end <= work_start or busy_start >= work_end:
            continue

        busy_start = max(busy_start, work_start)
        busy_end = min(busy_end, work_end)

        if cursor < busy_start:
            free_slots.append((cursor, busy_start))

        if busy_end > cursor:
            cursor = busy_end

    if cursor < work_end:
        free_slots.append((cursor, work_end))

    return free_slots


def print_busy_blocks_by_participant(debug_busy_by_email):
    print()
    print("Busy blocks by participant:")

    for email, blocks in debug_busy_by_email.items():
        print()
        print(email)

        if not blocks:
            print("  - no busy blocks")
            continue

        for busy_start, busy_end in blocks:
            print(f"  - {busy_start:%H:%M} → {busy_end:%H:%M}")


def print_free_slots(title, free_slots, min_duration_minutes):
    min_duration = timedelta(minutes=min_duration_minutes)

    valid_slots = [
        (start, end)
        for start, end in free_slots
        if end - start >= min_duration
    ]

    print()
    print(title)
    print()

    if not valid_slots:
        print("No suitable free slots found.")
        return

    print("┌────┬──────────────────────┬────────────┬────────────┐")
    print("│ #  │ Free slot            │ Duration   │ Quality    │")
    print("├────┼──────────────────────┼────────────┼────────────┤")

    best_slot = max(valid_slots, key=lambda x: x[1] - x[0])

    for index, (start, end) in enumerate(valid_slots, start=1):
        duration = end - start
        quality = "Best" if (start, end) == best_slot else "Good"

        time_range = f"{start:%H:%M} → {end:%H:%M}"
        duration_text = format_duration(duration)

        print(
            f"│ {index:<2} │ {time_range:<20} │ "
            f"{duration_text:<10} │ {quality:<10} │"
        )

    print("└────┴──────────────────────┴────────────┴────────────┘")

    suggested_start = best_slot[0]
    suggested_end = suggested_start + min_duration

    print()
    print(f"✅ Suggested: {suggested_start:%H:%M} → {suggested_end:%H:%M}")


def suggest_common_free_time(
    emails,
    day,
    duration_minutes,
    timezone,
    work_start_text,
    work_end_text,
    debug_busy=False,
):
    validate_emails(emails)

    service = get_calendar_service()
    day_start = parse_day(day, timezone)
    day_end = day_start + timedelta(days=1)

    work_start = apply_time(day_start, work_start_text)
    work_end = apply_time(day_start, work_end_text)

    print()
    print("Search window:")
    print(f"  requested day: {day}")
    print(f"  timezone:      {timezone}")
    print(f"  day_start:     {day_start.isoformat()}")
    print(f"  day_end:       {day_end.isoformat()}")
    print(f"  work_start:    {work_start.isoformat()}")
    print(f"  work_end:      {work_end.isoformat()}")

    if work_end <= work_start:
        raise ValueError("work-end must be after work-start")

    body = {
        "timeMin": day_start.isoformat(),
        "timeMax": day_end.isoformat(),
        "timeZone": timezone,
        "items": [{"id": email} for email in emails],
    }

    response = service.freebusy().query(body=body).execute()

    all_busy_blocks = []
    debug_busy_by_email = {}

    for email in emails:
        calendar_data = response["calendars"].get(email, {})

        if "errors" in calendar_data:
            raise RuntimeError(
                f"Could not read calendar for {email}: "
                f"{calendar_data['errors']}"
            )

        debug_busy_by_email[email] = []

        for item in calendar_data.get("busy", []):
            busy_start = isoparse(item["start"])
            busy_end = isoparse(item["end"])

            debug_busy_by_email[email].append((busy_start, busy_end))
            all_busy_blocks.append((busy_start, busy_end))

    print()
    print("Participants:")
    for email in emails:
        print(f"  - {email}")

    if debug_busy:
        print_busy_blocks_by_participant(debug_busy_by_email)

    free_slots = get_free_slots_from_busy(
        busy_blocks=all_busy_blocks,
        work_start=work_start,
        work_end=work_end,
    )

    print_free_slots(
        title=f"Common free slots on {day_start:%Y-%m-%d}",
        free_slots=free_slots,
        min_duration_minutes=duration_minutes,
    )


def team_add(name, emails):
    validate_emails(emails)

    teams = load_teams()
    teams[name] = sorted(set(emails))
    save_teams(teams)

    print(f"Saved team: {name}")
    for email in teams[name]:
        print(f"  - {email}")


def team_list():
    teams = load_teams()

    if not teams:
        print("No teams found.")
        return

    for name, emails in teams.items():
        print()
        print(name)
        for email in emails:
            print(f"  - {email}")


def resolve_emails(args):
    emails = []

    if args.emails:
        emails.extend(args.emails)

    if args.team:
        teams = load_teams()

        if args.team not in teams:
            raise ValueError(f"Team not found: {args.team}")

        emails.extend(teams[args.team])

    emails = sorted(set(emails))

    if not emails:
        raise ValueError("Pass --emails or --team")

    return emails


def main():
    parser = argparse.ArgumentParser(
        prog="calendar-booking",
        description="Find common free calendar slots.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    suggest = sub.add_parser("suggest")
    suggest.add_argument("--emails", nargs="+")
    suggest.add_argument("--team")
    suggest.add_argument("--day", default="tomorrow")
    suggest.add_argument("--duration", type=int, default=30)
    suggest.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    suggest.add_argument("--work-start", default="09:00")
    suggest.add_argument("--work-end", default="18:00")
    suggest.add_argument("--debug-busy", action="store_true")

    team = sub.add_parser("team")
    team_sub = team.add_subparsers(dest="team_command", required=True)

    team_add_parser = team_sub.add_parser("add")
    team_add_parser.add_argument("name")
    team_add_parser.add_argument("--emails", nargs="+", required=True)

    team_sub.add_parser("list")

    args = parser.parse_args()

    if args.command == "suggest":
        emails = resolve_emails(args)

        suggest_common_free_time(
            emails=emails,
            day=args.day,
            duration_minutes=args.duration,
            timezone=args.timezone,
            work_start_text=args.work_start,
            work_end_text=args.work_end,
            debug_busy=args.debug_busy,
        )

    elif args.command == "team":
        if args.team_command == "add":
            team_add(args.name, args.emails)
        elif args.team_command == "list":
            team_list()


if __name__ == "__main__":
    main()