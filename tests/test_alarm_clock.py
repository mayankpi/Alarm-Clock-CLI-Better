import unittest
from argparse import Namespace
from datetime import datetime, timedelta
from io import StringIO

from alarm_clock import (
    Alarm,
    build_alarm,
    format_remaining,
    parse_duration,
    parse_time_of_day,
    ring_alarm,
)


class AlarmClockTests(unittest.TestCase):
    def test_parse_duration_accepts_common_units(self):
        self.assertEqual(parse_duration("30s"), timedelta(seconds=30))
        self.assertEqual(parse_duration("10m"), timedelta(minutes=10))
        self.assertEqual(parse_duration("1h30m 5s"), timedelta(hours=1, minutes=30, seconds=5))

    def test_parse_duration_rejects_empty_or_zero_values(self):
        with self.assertRaises(ValueError):
            parse_duration("")

        with self.assertRaises(ValueError):
            parse_duration("0m")

    def test_parse_time_of_day_uses_today_when_time_is_future(self):
        now = datetime(2026, 6, 8, 9, 0, 0)
        self.assertEqual(parse_time_of_day("09:30", now), datetime(2026, 6, 8, 9, 30, 0))

    def test_parse_time_of_day_rolls_to_tomorrow_when_time_has_passed(self):
        now = datetime(2026, 6, 8, 9, 0, 0)
        self.assertEqual(parse_time_of_day("08:30", now), datetime(2026, 6, 9, 8, 30, 0))

    def test_build_alarm_prefers_relative_duration(self):
        now = datetime(2026, 6, 8, 9, 0, 0)
        args = Namespace(at=None, in_duration="15m", message="stand up")
        alarm = build_alarm(args, now)

        self.assertEqual(alarm.trigger_at, datetime(2026, 6, 8, 9, 15, 0))
        self.assertEqual(alarm.message, "stand up")

    def test_format_remaining_is_stable(self):
        self.assertEqual(format_remaining(timedelta(hours=2, minutes=3, seconds=4)), "02:03:04")
        self.assertEqual(format_remaining(timedelta(seconds=-1)), "00:00:00")

    def test_ring_alarm_writes_bells_and_message(self):
        stdout = StringIO()
        alarm = Alarm(trigger_at=datetime(2026, 6, 8, 9, 0, 0), message="coffee")

        ring_alarm(alarm, stdout=stdout, bell_count=2)

        self.assertEqual(stdout.getvalue(), "\a\aALARM: coffee\n")


if __name__ == "__main__":
    unittest.main()
