# Better Alarm Clock CLI - App Context

This file is the durable project memory for future changes, skills, or agents. Update it whenever requirements, architecture, command behavior, storage format, or testing strategy changes.

## Objective

Build a production-quality command-line alarm clock application in Python. The goal is to show structured problem definition, engineering tradeoff analysis, AI-assisted workflow, clean architecture, testing strategy, and maintainability.

## Constraints

- Python only.
- CLI only.
- No web UI, React, database, or external infrastructure.
- Local execution.
- Source code should be easy to understand and extend.
- Prefer standard-library dependencies unless a future requirement justifies more.

## Current MVP

The app supports persistent alarms with management commands:

- `alarm add 07:30`
- `alarm add 07:30 "Morning Workout"`
- `alarm add 07:30 "Morning Workout" --repeat daily`
- `alarm list`
- `alarm remove <id>`
- `alarm snooze <id> [duration]`
- `alarm repeat <id> none|daily`
- `alarm edit <id> [--time HH:MM] [--label "New Label"]`
- `alarm export <path>`
- `alarm import <path> [--replace]`
- `alarm run`

When a one-shot alarm is due, the run service prints alarm details, emits terminal bell characters, and marks the alarm as completed. When a daily repeating alarm is due, the service prints the same alert and reschedules it to the next future day.

## Architecture

Current implementation is in [alarm_clock.py](alarm_clock.py), organized into these logical layers:

- Model: `Alarm`
- Storage: `JsonAlarmStore`
- Application service: `AlarmService`
- Scheduler/runtime: `run_alarm_service`
- CLI: `argparse` parser and `main`

This keeps the exercise compact while preserving separation between business logic, persistence, runtime behavior, and command parsing.

## Storage

Database use is disallowed, so alarms persist in a JSON file.

Default path:

```text
~/.alarm_clock_alarms.json
```

Tests and demos can override storage:

```bash
python alarm_clock.py --storage ./alarms.json add 07:30 "Morning Workout"
```

Stored shape:

```json
[
  {
    "id": "123abc45",
    "time": "2026-08-15T07:30:00+05:30",
    "label": "Morning Workout",
    "status": "pending",
    "repeat": "none"
  }
]
```

Valid statuses:

- `pending`
- `completed`

Valid repeat values:

- `none`
- `daily`

## Time Handling

- Alarm input accepts `HH:MM` or `HH:MM:SS` in 24-hour local time.
- Snooze durations accept `30s`, `10m`, `1h30m`, or `1h 5m 10s`.
- Past clock times roll to the next day.
- Timestamps are stored as ISO-8601 strings with local timezone offset when available.
- Scheduling relies on standard-library `datetime` and local timezone awareness.

## Reliability Target

The run loop polls at most once per second, so alarms should trigger within one second while the process is running.

Known limitation: the app cannot wake a sleeping computer or notify when `alarm run` is not active.

## Testing Strategy

Use standard-library `unittest` so validation needs no dependency installation.

Current tests cover:

- Alarm creation.
- Time parsing and next-day rollover.
- Duration parsing.
- JSON persistence.
- Alarm deletion.
- Alarm editing.
- Alarm snoozing.
- Daily repeating alarm rescheduling.
- JSON export/import.
- Due alarm completion.
- Output formatting.
- CLI add/list/edit/snooze/repeat integration.
- Corrupted storage handling.

Run:

```bash
python -m unittest discover -s tests
```

## AI-Assisted Workflow

The intended process for this project:

1. Use AI to refine ambiguous requirements.
2. Ask AI for architecture options and tradeoffs.
3. Select a scope based on constraints and product value.
4. Use AI to scaffold implementation.
5. Review generated code before accepting it.
6. Write and run tests.
7. Use validation results to refactor or simplify.
8. Document decisions for future agents and maintainers.

## Future Extensions

Potential engineering improvements:

- Package entry point so users can run `alarm` directly.
- Atomic JSON writes for safer persistence.
- File locking if concurrent CLI writes become important.
- Configurable sound command per OS.
- Better timezone display and explicit timezone selection.
- Richer repeat rules such as weekdays or custom intervals.
