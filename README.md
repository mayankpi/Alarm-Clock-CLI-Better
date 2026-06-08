# Better Alarm Clock CLI

A production-minded Python command-line alarm clock for a senior engineering build exercise.

The app intentionally stays small, but it now supports the core alarm lifecycle: create, list, edit, snooze, repeat, remove, import/export, run, trigger, and persist alarms.

## Commands

Requires Python 3.10 or newer.

Add an alarm:

```powershell
python alarm_clock.py add 07:30
```

Add an alarm with a label:

```powershell
python alarm_clock.py add 07:30 "Morning Workout"
```

Add a daily repeating alarm:

```powershell
python alarm_clock.py add 07:30 "Morning Workout" --repeat daily
```

List alarms:

```powershell
python alarm_clock.py list
```

Remove an alarm:

```powershell
python alarm_clock.py remove <id>
```

Snooze an alarm for 10 minutes:

```powershell
python alarm_clock.py snooze <id>
```

Snooze with an explicit duration:

```powershell
python alarm_clock.py snooze <id> 5m
```

Edit an alarm:

```powershell
python alarm_clock.py edit <id> --time 08:00 --label "Gym"
```

Make an alarm repeat daily:

```powershell
python alarm_clock.py repeat <id> daily
```

Turn repeat off:

```powershell
python alarm_clock.py repeat <id> none
```

Export alarms:

```powershell
python alarm_clock.py export .\alarms-backup.json
```

Import alarms:

```powershell
python alarm_clock.py import .\alarms-backup.json
```

Replace existing alarms during import:

```powershell
python alarm_clock.py import .\alarms-backup.json --replace
```

Run the alarm service:

```powershell
python alarm_clock.py run
```

Use a custom storage file for demos or tests:

```powershell
python alarm_clock.py --storage .\alarms.json add 07:30 "Morning Workout"
```

## Current Behavior

- Alarm times use local 24-hour clock input: `HH:MM` or `HH:MM:SS`.
- Snooze durations use values like `30s`, `10m`, `1h30m`, or `1h 5m 10s`.
- If the time already passed today, the alarm is scheduled for tomorrow.
- Alarms are stored in JSON at `~/.alarm_clock_alarms.json` by default.
- `run` polls pending alarms once per second.
- When a one-shot alarm triggers, the app emits terminal bell characters, prints alarm details, and marks the alarm completed.
- When a daily repeating alarm triggers, the app emits the alert and reschedules it for the next future day.

## Requirements And Design Context

The durable project context lives in [APP_CONTEXT.md](APP_CONTEXT.md). Use that file when returning to the project later, adding skills, or handing work to another agent.

It captures:

- Objective and constraints.
- Current commands.
- Architecture layers.
- Storage format.
- Time handling decisions.
- Testing strategy.
- AI-assisted workflow.
- Future extension ideas.

## Design Choices

- `argparse` keeps the CLI familiar and dependency-free.
- JSON file storage satisfies persistence without violating the no-database constraint.
- Business workflows live in `AlarmService`, separate from CLI parsing.
- `JsonAlarmStore` isolates persistence.
- The scheduler loop uses injectable `sleep` and service time providers so core behavior can be tested without real waiting.
- The implementation stays in one file for exercise readability while preserving clear logical layers.

## Testing

Run tests with the Python standard library:

```powershell
python -m unittest discover -s tests
```

The tests cover alarm creation, time validation, duration parsing, next-day rollover, JSON persistence, deletion, edit, snooze, repeat, export/import, due-alarm completion, corrupted storage, formatting, alert output, and CLI storage override behavior.

## AI-Assisted Development Notes

The implementation follows the requested AI-assisted workflow:

1. Refine ambiguous requirements into a focused MVP.
2. Compare persistence options and accept JSON storage.
3. Separate CLI, application, scheduler, and storage responsibilities.
4. Implement incrementally.
5. Review generated code for scope and maintainability.
6. Validate with unit tests and CLI smoke checks.

## Future Improvements

- Package entry point so users can run `alarm` directly.
- Atomic writes for safer JSON persistence.
- File locking if concurrent commands become important.
- Optional OS-specific sound command.
- Richer repeat rules such as weekdays or custom intervals.
