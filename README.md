# Todo App

A lightweight Flask-based to-do app with notes, priorities, due dates, reminders, and timers.

## What was fixed

- Fixed startup and runtime behavior to use `python3` and a configurable port.
- Hardened timer logic so only one task can be actively timed and elapsed time is not duplicated.
- Prevented timer state from being corrupted when a task is marked done.
- Normalized reminder values so browser comparisons are safe and consistent.
- Prevented invalid reminder comparisons from causing JavaScript errors.
- Kept the database schema migration behavior safe for older installs.

## How to run

```bash
cd /home/pamela/todo_app
python3 app.py
```

Then open:

- http://127.0.0.1:5000/

You can also override the port with:

```bash
PORT=5001 python3 app.py
```

## Notes

- The app uses SQLite and creates `todo.db` automatically on first run.
- If the default port is already in use, set `PORT` to a free port before starting the app.
