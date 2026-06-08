# Alarm Clock CLI

A small Python command-line alarm clock built for a 30-minute engineering exercise.

## What I Chose To Build

The prompt is intentionally broad, so I scoped the project to one reliable one-shot alarm:

- Set an alarm by clock time: `--at 07:30`
- Set an alarm by relative duration: `--in 10m`, `--in 30s`, `--in 1h30m`
- Add an optional alarm message
- Show a live countdown in the terminal
- Ring with terminal bell characters and a clear message
- Keep the implementation dependency-free and testable

I did not add recurring alarms, persistence, multiple concurrent alarms, a database, or a web UI because those would increase surface area without improving the core CLI exercise much.

## AI-Assisted Requirements And Plan

Before coding, I used AI to refine the vague prompt into a practical implementation plan:

1. Build the smallest useful alarm clock that demonstrates product judgment.
2. Prefer a single-file Python CLI with no external runtime dependencies.
3. Support both absolute and relative scheduling because users naturally think in both forms.
4. Separate parsing and scheduling logic from the waiting loop so tests do not need real delays.
5. Add a README that explains tradeoffs, usage, validation, and future improvements.

## Usage

Requires Python 3.10 or newer.

```powershell
python alarm_clock.py --in 30s --message "Stretch"
```

```powershell
python alarm_clock.py --at 14:30 --message "Join interview"
```

Preview without waiting:

```powershell
python alarm_clock.py --in 10m --dry-run
```

Show help:

```powershell
python alarm_clock.py --help
```

## Examples

```text
Alarm set for 2026-06-08 14:30:00 (00:09:58 remaining)
ALARM: Join interview
```

When the alarm fires, the app emits terminal bell characters. Whether that produces an audible sound depends on the terminal and operating system settings.

## Testing

Run tests with the Python standard library:

```powershell
python -m unittest discover -s tests
```

The tests cover duration parsing, time-of-day rollover, alarm construction, formatting, and alert output.

## Design Notes

- `argparse` keeps the CLI familiar and avoids unnecessary dependencies.
- `--at` and `--in` are mutually exclusive to prevent ambiguous schedules.
- Past absolute times roll to the next day, matching how alarm clocks usually behave.
- The wait loop accepts injectable `sleep`, `now`, and `stdout` functions, so it can be tested or adapted later.
- The app exits cleanly on `Ctrl+C`.

## Future Improvements

- Optional snooze support.
- Configurable sound command per OS.
- Multiple named alarms in one process.
- Packaging entry point so users can run `alarm` directly after installation.
- More explicit timezone handling for travel or remote work scenarios.
