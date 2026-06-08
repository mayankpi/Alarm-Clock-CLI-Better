"""Persistent command-line alarm clock.

The code is intentionally dependency-free and organized into small layers:
models, storage, application services, scheduler behavior, and CLI commands.
Keeping these pieces in one file makes the exercise easy to review while still
leaving obvious extension points.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, TextIO


PENDING = "pending"
COMPLETED = "completed"
DEFAULT_LABEL = "Alarm"
NO_REPEAT = "none"
DAILY_REPEAT = "daily"
VALID_REPEATS = {NO_REPEAT, DAILY_REPEAT}
DURATION_PATTERN = re.compile(r"^\s*(?:(?P<hours>\d+)h)?\s*(?:(?P<minutes>\d+)m)?\s*(?:(?P<seconds>\d+)s)?\s*$")


def default_storage_path() -> Path:
    """Return the default per-user alarm storage path."""

    return Path.home() / ".alarm_clock_alarms.json"


def local_now() -> datetime:
    """Return the current local time as a timezone-aware datetime."""

    return datetime.now().astimezone()


@dataclass(frozen=True)
class Alarm:
    """A scheduled alarm persisted as JSON."""

    id: str
    time: datetime
    label: str = DEFAULT_LABEL
    status: str = PENDING
    repeat: str = NO_REPEAT

    @property
    def is_pending(self) -> bool:
        return self.status == PENDING

    def is_due(self, now: datetime) -> bool:
        return self.is_pending and self.time <= now

    def complete(self, now: datetime | None = None) -> "Alarm":
        if self.repeat == DAILY_REPEAT:
            next_time = self.time + timedelta(days=1)
            current = now or local_now()
            while next_time <= current:
                next_time += timedelta(days=1)
            return Alarm(id=self.id, time=next_time, label=self.label, status=PENDING, repeat=self.repeat)
        return Alarm(id=self.id, time=self.time, label=self.label, status=COMPLETED, repeat=self.repeat)

    def reschedule(self, new_time: datetime) -> "Alarm":
        return Alarm(id=self.id, time=new_time, label=self.label, status=PENDING, repeat=self.repeat)

    def rename(self, label: str) -> "Alarm":
        return Alarm(id=self.id, time=self.time, label=label or DEFAULT_LABEL, status=self.status, repeat=self.repeat)

    def with_repeat(self, repeat: str) -> "Alarm":
        validate_repeat(repeat)
        status = PENDING if repeat != NO_REPEAT else self.status
        return Alarm(id=self.id, time=self.time, label=self.label, status=status, repeat=repeat)

    def to_record(self) -> dict[str, str]:
        return {
            "id": self.id,
            "time": self.time.isoformat(),
            "label": self.label,
            "status": self.status,
            "repeat": self.repeat,
        }

    @classmethod
    def from_record(cls, record: dict[str, str]) -> "Alarm":
        try:
            alarm_id = str(record["id"])
            alarm_time = datetime.fromisoformat(str(record["time"]))
            label = str(record.get("label") or DEFAULT_LABEL)
            status = str(record.get("status") or PENDING)
            repeat = str(record.get("repeat") or NO_REPEAT)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("storage contains an invalid alarm record") from exc

        if alarm_time.tzinfo is None:
            alarm_time = alarm_time.replace(tzinfo=local_now().tzinfo)
        if status not in {PENDING, COMPLETED}:
            raise ValueError(f"storage contains unknown alarm status: {status}")
        validate_repeat(repeat)
        return cls(id=alarm_id, time=alarm_time, label=label, status=status, repeat=repeat)


class JsonAlarmStore:
    """JSON-file persistence for alarms."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Alarm]:
        if not self.path.exists():
            return []

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"could not read storage file: {self.path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"storage file is not valid JSON: {self.path}") from exc

        if not isinstance(raw, list):
            raise ValueError("storage file must contain a JSON list")
        return [Alarm.from_record(record) for record in raw]

    def save(self, alarms: Iterable[Alarm]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records = [alarm.to_record() for alarm in sorted(alarms, key=lambda item: item.time)]
            self.path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"could not write storage file: {self.path}") from exc


def parse_alarm_time(value: str, now: datetime | None = None) -> datetime:
    """Parse HH:MM or HH:MM:SS and return the next local occurrence."""

    current = now or local_now()
    parsed_time = None
    for fmt in ("%H:%M:%S", "%H:%M"):
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


def parse_duration(value: str) -> timedelta:
    """Parse durations like 10m, 30s, 1h30m, or 1h 5m 10s."""

    match = DURATION_PATTERN.match(value)
    if not match:
        raise ValueError("duration must look like 30s, 10m, 1h30m, or 1h 5m 10s")

    parts = {name: int(raw or 0) for name, raw in match.groupdict().items()}
    duration = timedelta(hours=parts["hours"], minutes=parts["minutes"], seconds=parts["seconds"])
    if duration <= timedelta():
        raise ValueError("duration must be greater than zero")
    return duration


def validate_repeat(value: str) -> None:
    if value not in VALID_REPEATS:
        raise ValueError(f"repeat must be one of: {', '.join(sorted(VALID_REPEATS))}")


def format_alarm_time(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_remaining(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


class AlarmService:
    """Business workflows for creating, listing, deleting, and completing alarms."""

    def __init__(
        self,
        store: JsonAlarmStore,
        *,
        now: Callable[[], datetime] = local_now,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.now = now
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex[:8])

    def add_alarm(self, time_value: str, label: str = DEFAULT_LABEL, repeat: str = NO_REPEAT) -> Alarm:
        validate_repeat(repeat)
        alarms = self.store.load()
        alarm = Alarm(
            id=self._next_id({item.id for item in alarms}),
            time=parse_alarm_time(time_value, self.now()),
            label=label or DEFAULT_LABEL,
            repeat=repeat,
        )
        self.store.save([*alarms, alarm])
        return alarm

    def list_alarms(self) -> list[Alarm]:
        return self.store.load()

    def remove_alarm(self, alarm_id: str) -> Alarm:
        alarms = self.store.load()
        for alarm in alarms:
            if alarm.id == alarm_id:
                self.store.save(item for item in alarms if item.id != alarm_id)
                return alarm
        raise ValueError(f"alarm not found: {alarm_id}")

    def edit_alarm(
        self,
        alarm_id: str,
        *,
        time_value: str | None = None,
        label: str | None = None,
    ) -> Alarm:
        if time_value is None and label is None:
            raise ValueError("edit requires --time, --label, or both")

        alarms = self.store.load()
        updated_alarm = None
        updated = []
        for alarm in alarms:
            if alarm.id != alarm_id:
                updated.append(alarm)
                continue

            candidate = alarm
            if time_value is not None:
                candidate = candidate.reschedule(parse_alarm_time(time_value, self.now()))
            if label is not None:
                candidate = candidate.rename(label)
            updated_alarm = candidate
            updated.append(candidate)

        if updated_alarm is None:
            raise ValueError(f"alarm not found: {alarm_id}")
        self.store.save(updated)
        return updated_alarm

    def snooze_alarm(self, alarm_id: str, duration_value: str = "10m") -> Alarm:
        duration = parse_duration(duration_value)
        alarms = self.store.load()
        updated_alarm = None
        updated = []
        for alarm in alarms:
            if alarm.id == alarm_id:
                updated_alarm = alarm.reschedule(self.now() + duration)
                updated.append(updated_alarm)
            else:
                updated.append(alarm)

        if updated_alarm is None:
            raise ValueError(f"alarm not found: {alarm_id}")
        self.store.save(updated)
        return updated_alarm

    def set_repeat(self, alarm_id: str, repeat: str) -> Alarm:
        validate_repeat(repeat)
        alarms = self.store.load()
        updated_alarm = None
        updated = []
        for alarm in alarms:
            if alarm.id == alarm_id:
                updated_alarm = alarm.with_repeat(repeat)
                updated.append(updated_alarm)
            else:
                updated.append(alarm)

        if updated_alarm is None:
            raise ValueError(f"alarm not found: {alarm_id}")
        self.store.save(updated)
        return updated_alarm

    def export_alarms(self, destination: Path) -> int:
        alarms = self.store.load()
        JsonAlarmStore(destination).save(alarms)
        return len(alarms)

    def import_alarms(self, source: Path, *, replace: bool = False) -> int:
        imported = JsonAlarmStore(source).load()
        if replace:
            self.store.save(imported)
            return len(imported)

        existing = self.store.load()
        existing_ids = {alarm.id for alarm in existing}
        merged = list(existing)
        for alarm in imported:
            if alarm.id in existing_ids:
                alarm = Alarm(
                    id=self._next_id(existing_ids),
                    time=alarm.time,
                    label=alarm.label,
                    status=alarm.status,
                    repeat=alarm.repeat,
                )
            existing_ids.add(alarm.id)
            merged.append(alarm)
        self.store.save(merged)
        return len(imported)

    def complete_due_alarms(self) -> list[Alarm]:
        now = self.now()
        alarms = self.store.load()
        due = [alarm for alarm in alarms if alarm.is_due(now)]
        if not due:
            return []

        due_ids = {alarm.id for alarm in due}
        updated = [alarm.complete(now) if alarm.id in due_ids else alarm for alarm in alarms]
        self.store.save(updated)
        return due

    def next_pending_alarm(self) -> Alarm | None:
        pending = [alarm for alarm in self.store.load() if alarm.is_pending]
        if not pending:
            return None
        return min(pending, key=lambda alarm: alarm.time)

    def _next_id(self, existing_ids: set[str]) -> str:
        for _ in range(100):
            candidate = self.id_factory()
            if candidate not in existing_ids:
                return candidate
        raise RuntimeError("could not generate a unique alarm id")


def ring_alarm(alarm: Alarm, *, stdout: TextIO | None = None, bell_count: int = 3) -> None:
    stdout = stdout or sys.stdout
    bells = "\a" * max(1, bell_count)
    stdout.write(f"{bells}ALARM [{alarm.id}]\n")
    stdout.write(f"Time: {format_alarm_time(alarm.time)}\n")
    stdout.write(f"Label: {alarm.label}\n")
    if alarm.repeat != NO_REPEAT:
        stdout.write(f"Repeat: {alarm.repeat}\n")
    stdout.flush()


def run_alarm_service(
    service: AlarmService,
    *,
    sleep: Callable[[float], None] = time.sleep,
    stdout: TextIO | None = None,
    stop_after_idle: bool = False,
) -> None:
    """Monitor pending alarms and trigger due alarms within one-second polling."""

    stdout = stdout or sys.stdout
    stdout.write("Alarm service running. Press Ctrl+C to stop.\n")
    stdout.flush()

    while True:
        due_alarms = service.complete_due_alarms()
        for alarm in due_alarms:
            ring_alarm(alarm, stdout=stdout)

        next_alarm = service.next_pending_alarm()
        if next_alarm is None:
            stdout.write("No pending alarms.\n")
            stdout.flush()
            if stop_after_idle:
                return
            sleep(1.0)
            continue

        remaining = next_alarm.time - service.now()
        stdout.write(
            f"\rNext alarm {next_alarm.id} at {format_alarm_time(next_alarm.time)} "
            f"({format_remaining(remaining)} remaining)"
        )
        stdout.flush()
        sleep(min(1.0, max(0.0, remaining.total_seconds())))


def print_alarm_table(alarms: list[Alarm], *, stdout: TextIO | None = None) -> None:
    stdout = stdout or sys.stdout
    if not alarms:
        stdout.write("No alarms scheduled.\n")
        return

    time_values = [format_alarm_time(alarm.time) for alarm in alarms]
    time_width = max(len("TIME"), *(len(value) for value in time_values))
    id_width = max(len("ID"), *(len(alarm.id) for alarm in alarms))
    status_width = max(len("STATUS"), *(len(alarm.status) for alarm in alarms))

    stdout.write(f"{'ID':<{id_width}}  {'TIME':<{time_width}}  {'STATUS':<{status_width}}  {'REPEAT':<6}  LABEL\n")
    stdout.write(f"{'-' * id_width}  {'-' * time_width}  {'-' * status_width}  {'-' * 6}  {'-' * 20}\n")
    for alarm, formatted_time in zip(alarms, time_values):
        stdout.write(
            f"{alarm.id:<{id_width}}  {formatted_time:<{time_width}}  "
            f"{alarm.status:<{status_width}}  {alarm.repeat:<6}  {alarm.label}\n"
        )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alarm", description="Persistent command-line alarm clock.")
    parser.add_argument(
        "--storage",
        type=Path,
        default=default_storage_path(),
        help="path to the JSON alarm storage file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="create a pending alarm")
    add_parser.add_argument("time", help="24-hour time such as 07:30 or 07:30:15")
    add_parser.add_argument("label", nargs="?", default=DEFAULT_LABEL, help="optional alarm label")
    add_parser.add_argument("--repeat", choices=sorted(VALID_REPEATS), default=NO_REPEAT, help="repeat schedule")

    subparsers.add_parser("list", help="list stored alarms")

    remove_parser = subparsers.add_parser("remove", help="remove an alarm by id")
    remove_parser.add_argument("id", help="alarm id")

    snooze_parser = subparsers.add_parser("snooze", help="delay an alarm by a duration")
    snooze_parser.add_argument("id", help="alarm id")
    snooze_parser.add_argument("duration", nargs="?", default="10m", help="duration such as 10m, 30s, or 1h30m")

    repeat_parser = subparsers.add_parser("repeat", help="set an alarm repeat schedule")
    repeat_parser.add_argument("id", help="alarm id")
    repeat_parser.add_argument("repeat", choices=sorted(VALID_REPEATS), help="repeat schedule")

    edit_parser = subparsers.add_parser("edit", help="edit an alarm time or label")
    edit_parser.add_argument("id", help="alarm id")
    edit_parser.add_argument("--time", help="new 24-hour time such as 07:30")
    edit_parser.add_argument("--label", help="new alarm label")

    export_parser = subparsers.add_parser("export", help="export alarms to a JSON file")
    export_parser.add_argument("path", type=Path, help="destination JSON file")

    import_parser = subparsers.add_parser("import", help="import alarms from a JSON file")
    import_parser.add_argument("path", type=Path, help="source JSON file")
    import_parser.add_argument("--replace", action="store_true", help="replace existing alarms instead of merging")

    run_parser = subparsers.add_parser("run", help="monitor pending alarms")
    run_parser.add_argument(
        "--exit-when-idle",
        action="store_true",
        help="exit when there are no pending alarms, useful for tests and demos",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    service = AlarmService(JsonAlarmStore(args.storage))

    try:
        if args.command == "add":
            alarm = service.add_alarm(args.time, args.label, args.repeat)
            print(f"Added alarm {alarm.id} for {format_alarm_time(alarm.time)}: {alarm.label}")
            return 0

        if args.command == "list":
            print_alarm_table(service.list_alarms())
            return 0

        if args.command == "remove":
            alarm = service.remove_alarm(args.id)
            print(f"Removed alarm {alarm.id}: {alarm.label}")
            return 0

        if args.command == "snooze":
            alarm = service.snooze_alarm(args.id, args.duration)
            print(f"Snoozed alarm {alarm.id} until {format_alarm_time(alarm.time)}: {alarm.label}")
            return 0

        if args.command == "repeat":
            alarm = service.set_repeat(args.id, args.repeat)
            print(f"Updated alarm {alarm.id} repeat to {alarm.repeat}: {alarm.label}")
            return 0

        if args.command == "edit":
            alarm = service.edit_alarm(args.id, time_value=args.time, label=args.label)
            print(f"Updated alarm {alarm.id} for {format_alarm_time(alarm.time)}: {alarm.label}")
            return 0

        if args.command == "export":
            count = service.export_alarms(args.path)
            print(f"Exported {count} alarm(s) to {args.path}")
            return 0

        if args.command == "import":
            count = service.import_alarms(args.path, replace=args.replace)
            print(f"Imported {count} alarm(s) from {args.path}")
            return 0

        if args.command == "run":
            run_alarm_service(service, stop_after_idle=args.exit_when_idle)
            return 0
    except ValueError as exc:
        parser.error(str(exc))
    except KeyboardInterrupt:
        print("\nAlarm service stopped.")
        return 130

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
