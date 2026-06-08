"""Persistent command-line alarm clock.

The code is intentionally dependency-free and organized into small layers:
models, storage, application services, scheduler behavior, and CLI commands.
Keeping these pieces in one file makes the exercise easy to review while still
leaving obvious extension points.
"""

from __future__ import annotations

import argparse
import json
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

    @property
    def is_pending(self) -> bool:
        return self.status == PENDING

    def is_due(self, now: datetime) -> bool:
        return self.is_pending and self.time <= now

    def complete(self) -> "Alarm":
        return Alarm(id=self.id, time=self.time, label=self.label, status=COMPLETED)

    def to_record(self) -> dict[str, str]:
        return {
            "id": self.id,
            "time": self.time.isoformat(),
            "label": self.label,
            "status": self.status,
        }

    @classmethod
    def from_record(cls, record: dict[str, str]) -> "Alarm":
        try:
            alarm_id = str(record["id"])
            alarm_time = datetime.fromisoformat(str(record["time"]))
            label = str(record.get("label") or DEFAULT_LABEL)
            status = str(record.get("status") or PENDING)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("storage contains an invalid alarm record") from exc

        if alarm_time.tzinfo is None:
            alarm_time = alarm_time.replace(tzinfo=local_now().tzinfo)
        if status not in {PENDING, COMPLETED}:
            raise ValueError(f"storage contains unknown alarm status: {status}")
        return cls(id=alarm_id, time=alarm_time, label=label, status=status)


class JsonAlarmStore:
    """JSON-file persistence for alarms."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Alarm]:
        if not self.path.exists():
            return []

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"storage file is not valid JSON: {self.path}") from exc

        if not isinstance(raw, list):
            raise ValueError("storage file must contain a JSON list")
        return [Alarm.from_record(record) for record in raw]

    def save(self, alarms: Iterable[Alarm]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = [alarm.to_record() for alarm in sorted(alarms, key=lambda item: item.time)]
        self.path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


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

    def add_alarm(self, time_value: str, label: str = DEFAULT_LABEL) -> Alarm:
        alarms = self.store.load()
        alarm = Alarm(
            id=self._next_id({item.id for item in alarms}),
            time=parse_alarm_time(time_value, self.now()),
            label=label or DEFAULT_LABEL,
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

    def complete_due_alarms(self) -> list[Alarm]:
        now = self.now()
        alarms = self.store.load()
        due = [alarm for alarm in alarms if alarm.is_due(now)]
        if not due:
            return []

        due_ids = {alarm.id for alarm in due}
        updated = [alarm.complete() if alarm.id in due_ids else alarm for alarm in alarms]
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

    stdout.write(f"{'ID':<{id_width}}  {'TIME':<{time_width}}  {'STATUS':<{status_width}}  LABEL\n")
    stdout.write(f"{'-' * id_width}  {'-' * time_width}  {'-' * status_width}  {'-' * 20}\n")
    for alarm, formatted_time in zip(alarms, time_values):
        stdout.write(
            f"{alarm.id:<{id_width}}  {formatted_time:<{time_width}}  "
            f"{alarm.status:<{status_width}}  {alarm.label}\n"
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

    subparsers.add_parser("list", help="list stored alarms")

    remove_parser = subparsers.add_parser("remove", help="remove an alarm by id")
    remove_parser.add_argument("id", help="alarm id")

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
            alarm = service.add_alarm(args.time, args.label)
            print(f"Added alarm {alarm.id} for {format_alarm_time(alarm.time)}: {alarm.label}")
            return 0

        if args.command == "list":
            print_alarm_table(service.list_alarms())
            return 0

        if args.command == "remove":
            alarm = service.remove_alarm(args.id)
            print(f"Removed alarm {alarm.id}: {alarm.label}")
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
