"""Command-line alarm clock.

This module keeps the user-facing CLI small while making the parsing and
scheduling logic testable. It intentionally avoids external dependencies so the
exercise can run anywhere Python 3.10+ is available.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, TextIO


DURATION_PATTERN = re.compile(r"^\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?:(?P<seconds>\d+)s)?\s*$")


@dataclass(frozen=True)
class Alarm:
    """A scheduled alarm."""

    trigger_at: datetime
    message: str

    def remaining(self, now: datetime | None = None) -> timedelta:
        current = now or datetime.now()
        return max(self.trigger_at - current, timedelta())


def parse_duration(value: str) -> timedelta:
    """Parse durations like 30s, 10m, 1h30m, or 1h 5m 10s."""

    match = DURATION_PATTERN.match(value)
    if not match:
        raise ValueError("duration must look like 30s, 10m, 1h30m, or 1h 5m 10s")

    parts = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    duration = timedelta(hours=parts["hours"], minutes=parts["minutes"], seconds=parts["seconds"])
    if duration <= timedelta():
        raise ValueError("duration must be greater than zero")
    return duration


def parse_time_of_day(value: str, now: datetime | None = None) -> datetime:
    """Parse HH:MM or HH:MM:SS and return the next occurrence."""

    current = now or datetime.now()
    formats = ("%H:%M:%S", "%H:%M")
    parsed_time = None
    for fmt in formats:
        try:
            parsed_time = datetime.strptime(value, fmt).time()
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError("time must be in 24-hour HH:MM or HH:MM:SS format")

    scheduled = current.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=parsed_time.second,
        microsecond=0,
    )
    if scheduled <= current:
        scheduled += timedelta(days=1)
    return scheduled


def build_alarm(args: argparse.Namespace, now: datetime | None = None) -> Alarm:
    """Create an alarm from parsed CLI arguments."""

    current = now or datetime.now()
    if args.in_duration:
        trigger_at = current + parse_duration(args.in_duration)
    else:
        trigger_at = parse_time_of_day(args.at, current)

    return Alarm(trigger_at=trigger_at, message=args.message)


def format_remaining(delta: timedelta) -> str:
    """Format a remaining duration as HH:MM:SS."""

    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def wait_for_alarm(
    alarm: Alarm,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = datetime.now,
    stdout: TextIO = sys.stdout,
) -> None:
    """Wait until an alarm fires, updating one terminal line."""

    while True:
        remaining = alarm.remaining(now())
        if remaining <= timedelta():
            break

        stdout.write(
            f"\rAlarm set for {alarm.trigger_at:%Y-%m-%d %H:%M:%S} "
            f"({format_remaining(remaining)} remaining)"
        )
        stdout.flush()
        sleep(min(1.0, remaining.total_seconds()))

    stdout.write("\n")
    stdout.flush()


def ring_alarm(alarm: Alarm, *, stdout: TextIO = sys.stdout, bell_count: int = 3) -> None:
    """Print the alarm notification and emit terminal bells."""

    bells = "\a" * max(1, bell_count)
    stdout.write(f"{bells}ALARM: {alarm.message}\n")
    stdout.flush()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="Set a one-shot alarm from the command line.",
    )

    schedule = parser.add_mutually_exclusive_group(required=True)
    schedule.add_argument("--at", metavar="HH:MM", help="ring at the next occurrence of a 24-hour time")
    schedule.add_argument(
        "--in",
        dest="in_duration",
        metavar="DURATION",
        help="ring after a duration such as 30s, 10m, or 1h30m",
    )

    parser.add_argument(
        "-m",
        "--message",
        default="Time's up",
        help="message to display when the alarm rings",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show when the alarm would ring without waiting",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        build_alarm(args)
    except ValueError as exc:
        parser.error(str(exc))

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    alarm = build_alarm(args)

    if args.dry_run:
        print(f"Alarm would ring at {alarm.trigger_at:%Y-%m-%d %H:%M:%S}: {alarm.message}")
        return 0

    try:
        wait_for_alarm(alarm)
        ring_alarm(alarm)
    except KeyboardInterrupt:
        print("\nAlarm cancelled.")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
