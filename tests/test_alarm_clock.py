import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from alarm_clock import (
    Alarm,
    AlarmService,
    DAILY_REPEAT,
    JsonAlarmStore,
    NO_REPEAT,
    PENDING,
    COMPLETED,
    format_remaining,
    main,
    parse_alarm_time,
    parse_duration,
    print_alarm_table,
    ring_alarm,
)


FIXED_NOW = datetime(2026, 6, 8, 9, 0, 0, tzinfo=timezone.utc)


class AlarmClockTests(unittest.TestCase):
    def test_parse_alarm_time_uses_today_when_time_is_future(self):
        self.assertEqual(parse_alarm_time("09:30", FIXED_NOW), datetime(2026, 6, 8, 9, 30, tzinfo=timezone.utc))

    def test_parse_alarm_time_rolls_to_tomorrow_when_time_has_passed(self):
        self.assertEqual(parse_alarm_time("08:30", FIXED_NOW), datetime(2026, 6, 9, 8, 30, tzinfo=timezone.utc))

    def test_parse_alarm_time_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            parse_alarm_time("tomorrow")

    def test_parse_duration_accepts_common_units(self):
        self.assertEqual(parse_duration("30s"), timedelta(seconds=30))
        self.assertEqual(parse_duration("10m"), timedelta(minutes=10))
        self.assertEqual(parse_duration("1h30m 5s"), timedelta(hours=1, minutes=30, seconds=5))

    def test_add_alarm_persists_pending_alarm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            service = AlarmService(store, now=lambda: FIXED_NOW, id_factory=lambda: "abc123")

            alarm = service.add_alarm("09:30", "Morning Workout", repeat=DAILY_REPEAT)

            self.assertEqual(alarm.id, "abc123")
            self.assertEqual(alarm.status, PENDING)
            self.assertEqual(alarm.label, "Morning Workout")
            self.assertEqual(alarm.repeat, DAILY_REPEAT)
            self.assertEqual(store.load(), [alarm])

    def test_remove_alarm_deletes_matching_alarm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            service = AlarmService(store, now=lambda: FIXED_NOW, id_factory=lambda: "abc123")
            service.add_alarm("09:30", "Morning Workout")

            removed = service.remove_alarm("abc123")

            self.assertEqual(removed.label, "Morning Workout")
            self.assertEqual(store.load(), [])

    def test_complete_due_alarms_marks_due_alarms_completed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            due = Alarm(id="due", time=FIXED_NOW - timedelta(seconds=1), label="Due", status=PENDING)
            future = Alarm(id="future", time=FIXED_NOW + timedelta(minutes=1), label="Future", status=PENDING)
            store.save([future, due])
            service = AlarmService(store, now=lambda: FIXED_NOW)

            completed = service.complete_due_alarms()
            alarms = {alarm.id: alarm for alarm in store.load()}

            self.assertEqual([alarm.id for alarm in completed], ["due"])
            self.assertEqual(alarms["due"].status, COMPLETED)
            self.assertEqual(alarms["future"].status, PENDING)

    def test_daily_repeat_alarm_reschedules_after_trigger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            due = Alarm(id="due", time=FIXED_NOW - timedelta(seconds=1), label="Due", repeat=DAILY_REPEAT)
            store.save([due])
            service = AlarmService(store, now=lambda: FIXED_NOW)

            completed = service.complete_due_alarms()
            [stored] = store.load()

            self.assertEqual([alarm.id for alarm in completed], ["due"])
            self.assertEqual(stored.status, PENDING)
            self.assertEqual(stored.repeat, DAILY_REPEAT)
            self.assertGreater(stored.time, FIXED_NOW)

    def test_snooze_alarm_reschedules_and_reopens_alarm(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            alarm = Alarm(id="abc123", time=FIXED_NOW, label="Break", status=COMPLETED)
            store.save([alarm])
            service = AlarmService(store, now=lambda: FIXED_NOW)

            updated = service.snooze_alarm("abc123", "15m")

            self.assertEqual(updated.time, FIXED_NOW + timedelta(minutes=15))
            self.assertEqual(updated.status, PENDING)

    def test_edit_alarm_updates_time_and_label(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            service = AlarmService(store, now=lambda: FIXED_NOW, id_factory=lambda: "abc123")
            service.add_alarm("09:30", "Old")

            updated = service.edit_alarm("abc123", time_value="10:00", label="New")

            self.assertEqual(updated.time, datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc))
            self.assertEqual(updated.label, "New")

    def test_set_repeat_updates_repeat_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir) / "alarms.json")
            service = AlarmService(store, now=lambda: FIXED_NOW, id_factory=lambda: "abc123")
            service.add_alarm("09:30", "Workout")

            updated = service.set_repeat("abc123", DAILY_REPEAT)

            self.assertEqual(updated.repeat, DAILY_REPEAT)

    def test_export_and_import_alarms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_store = JsonAlarmStore(Path(temp_dir) / "source.json")
            destination_store = JsonAlarmStore(Path(temp_dir) / "destination.json")
            export_path = Path(temp_dir) / "export.json"
            source_service = AlarmService(source_store, now=lambda: FIXED_NOW, id_factory=lambda: "abc123")
            source_service.add_alarm("09:30", "Exported")

            self.assertEqual(source_service.export_alarms(export_path), 1)
            destination_service = AlarmService(destination_store, now=lambda: FIXED_NOW)

            self.assertEqual(destination_service.import_alarms(export_path), 1)

            imported = destination_store.load()
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].label, "Exported")

    def test_store_rejects_corrupted_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alarms.json"
            path.write_text("{bad json", encoding="utf-8")
            store = JsonAlarmStore(path)

            with self.assertRaises(ValueError):
                store.load()

    def test_store_wraps_write_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = JsonAlarmStore(Path(temp_dir))

            with self.assertRaises(ValueError):
                store.save([Alarm(id="abc123", time=FIXED_NOW)])

    def test_format_remaining_is_stable(self):
        self.assertEqual(format_remaining(timedelta(hours=2, minutes=3, seconds=4)), "02:03:04")
        self.assertEqual(format_remaining(timedelta(seconds=-1)), "00:00:00")

    def test_ring_alarm_writes_bells_and_details(self):
        stdout = StringIO()
        alarm = Alarm(id="abc123", time=FIXED_NOW, label="coffee")

        ring_alarm(alarm, stdout=stdout, bell_count=2)

        output = stdout.getvalue()
        self.assertIn("\a\aALARM [abc123]", output)
        self.assertIn("Label: coffee", output)

    def test_print_alarm_table_handles_empty_list(self):
        stdout = StringIO()

        print_alarm_table([], stdout=stdout)

        self.assertEqual(stdout.getvalue(), "No alarms scheduled.\n")

    def test_cli_add_and_list_use_storage_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = str(Path(temp_dir) / "alarms.json")
            stdout = StringIO()

            with redirect_stdout(stdout):
                self.assertEqual(main(["--storage", storage, "add", "23:59", "Demo"]), 0)
                alarms = JsonAlarmStore(Path(storage)).load()
                self.assertEqual(main(["--storage", storage, "edit", alarms[0].id, "--label", "Edited"]), 0)
                self.assertEqual(main(["--storage", storage, "snooze", alarms[0].id, "5m"]), 0)
                self.assertEqual(main(["--storage", storage, "repeat", alarms[0].id, NO_REPEAT]), 0)
                self.assertEqual(main(["--storage", storage, "list"]), 0)

            alarms = JsonAlarmStore(Path(storage)).load()
            self.assertEqual(len(alarms), 1)
            self.assertEqual(alarms[0].label, "Edited")


if __name__ == "__main__":
    unittest.main()
