"""FlowPilot: a focused planning app for work, personal, and health tasks.
Run with:  python3 app.py   then open http://127.0.0.1:5000
"""
import os
import sqlite3
import time
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, g

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "todo.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


@app.before_request
def ensure_db():
    init_db()


def init_db():
    with sqlite3.connect(DB) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            notes TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            priority TEXT DEFAULT 'medium',
            due TEXT,
            done INTEGER DEFAULT 0,
            time_spent INTEGER DEFAULT 0,
            remaining_seconds INTEGER DEFAULT 1500,
            timer_started INTEGER,
            remind_at TEXT DEFAULT '',
            reminded INTEGER DEFAULT 0
        )""")
        existing = [row[1] for row in db.execute("PRAGMA table_info(tasks)")]
        for col, definition in [("category", "TEXT DEFAULT 'general'"),
                                ("priority", "TEXT DEFAULT 'medium'"),
                                ("time_spent", "INTEGER DEFAULT 0"),
                                ("remaining_seconds", "INTEGER DEFAULT 1500"),
                                ("timer_started", "INTEGER"),
                                ("remind_at", "TEXT DEFAULT ''"),
                                ("reminded", "INTEGER DEFAULT 0")]:
            if col not in existing:
                db.execute(f"ALTER TABLE tasks ADD COLUMN {col} {definition}")


@app.template_filter("hms")
def hms(seconds):
    """Display mm:ss for a 25-minute Pomodoro."""
    seconds = int(seconds or 0)
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}:{secs:02d}"


def normalize_reminder(value):
    if not value:
        return ""
    return value.strip().replace("Z", "")


@app.route("/")
def index():
    view = request.args.get("view", "all")
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "all")

    sql, params = "SELECT * FROM tasks WHERE 1=1", []
    if view == "pending":
        sql += " AND done = 0"
    elif view == "done":
        sql += " AND done = 1"
    if category != "all":
        sql += " AND category = ?"
        params.append(category)
    if q:
        sql += " AND (title LIKE ? OR notes LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += """ ORDER BY
        CASE WHEN done = 0 AND due IS NOT NULL AND due < date('now') THEN 0 ELSE 1 END,
        CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
        due IS NULL OR due = '', due"""
    tasks = get_db().execute(sql, params).fetchall()

    counts = get_db().execute(
        "SELECT SUM(done = 0) AS open, SUM(done = 1) AS done FROM tasks").fetchone()
    return render_template("index.html", tasks=tasks, view=view, q=q,
                           category=category,
                           today=date.today().isoformat(), now=int(time.time()),
                           open_count=counts["open"] or 0,
                           done_count=counts["done"] or 0)


@app.route("/add", methods=["POST"])
def add():
    title = request.form["title"].strip()
    if title:
        db = get_db()
        remind_at = normalize_reminder(request.form.get("remind_at", ""))
        db.execute("INSERT INTO tasks (title, category, priority, due, remind_at, remaining_seconds) VALUES (?, ?, ?, ?, ?, 1500)",
                   (title,
                    request.form.get("category", "general"),
                    request.form.get("priority", "medium"),
                    request.form.get("due", ""),
                    remind_at))
        db.commit()
    return redirect(url_for("index"))


@app.route("/toggle/<int:task_id>", methods=["POST"])
def toggle(task_id):
    db = get_db()
    current = db.execute("SELECT done, timer_started, remaining_seconds FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if current is None:
        return redirect(url_for("index"))

    new_done = 1 - current["done"]
    db.execute("UPDATE tasks SET done = ? WHERE id = ?", (new_done, task_id))

    if new_done == 1 and current["timer_started"] is not None:
        now = int(time.time())
        elapsed = max(0, now - current["timer_started"])
        remaining = max(0, current["remaining_seconds"] - elapsed)
        db.execute("UPDATE tasks SET remaining_seconds = ?, timer_started = NULL WHERE id = ?",
                   (remaining, task_id))

    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/notes/<int:task_id>", methods=["POST"])
def save_notes(task_id):
    db = get_db()
    db.execute("UPDATE tasks SET notes = ? WHERE id = ?",
               (request.form["notes"], task_id))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/timer/<int:task_id>", methods=["POST"])
def timer(task_id):
    """Start or pause a Pomodoro. Only one timer may run globally."""
    db = get_db()
    now = int(time.time())
    current = db.execute("SELECT timer_started, remaining_seconds FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if current is None:
        return redirect(request.referrer or url_for("index"))

    active = db.execute("SELECT id, timer_started, remaining_seconds FROM tasks WHERE timer_started IS NOT NULL AND id != ? LIMIT 1", (task_id,)).fetchone()
    if active:
        elapsed = max(0, now - active["timer_started"])
        remaining = max(0, active["remaining_seconds"] - elapsed)
        db.execute("UPDATE tasks SET remaining_seconds = ?, timer_started = NULL WHERE id = ?",
                   (remaining, active["id"]))

    if current["timer_started"] is not None:
        elapsed = max(0, now - current["timer_started"])
        remaining = max(0, current["remaining_seconds"] - elapsed)
        db.execute("UPDATE tasks SET remaining_seconds = ?, timer_started = NULL WHERE id = ?",
                   (remaining, task_id))
    else:
        db.execute("UPDATE tasks SET timer_started = ? WHERE id = ? AND done = 0",
                   (now, task_id))

    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/timer/<int:task_id>/save", methods=["POST"])
def timer_save(task_id):
    remaining = max(0, int(request.form.get("remaining_seconds", 1500)))
    db = get_db()
    db.execute("UPDATE tasks SET remaining_seconds = ? WHERE id = ?",
               (remaining, task_id))
    db.commit()
    return ("", 204)


@app.route("/timer/<int:task_id>/reset", methods=["POST"])
def timer_reset(task_id):
    db = get_db()
    db.execute("UPDATE tasks SET remaining_seconds = 1500, timer_started = NULL WHERE id = ?", (task_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/timer/<int:task_id>/complete", methods=["POST"])
def timer_complete(task_id):
    db = get_db()
    db.execute("UPDATE tasks SET time_spent = time_spent + 1500, remaining_seconds = 1500, timer_started = NULL WHERE id = ?",
               (task_id,))
    db.commit()
    return ("", 204)


@app.route("/remind/<int:task_id>", methods=["POST"])
def set_reminder(task_id):
    db = get_db()
    value = normalize_reminder(request.form.get("remind_at", ""))
    db.execute("UPDATE tasks SET remind_at = ?, reminded = 0 WHERE id = ?",
               (value, task_id))
    db.commit()
    return redirect(request.referrer or url_for("index"))


@app.route("/reminded/<int:task_id>", methods=["POST"])
def mark_reminded(task_id):
    db = get_db()
    db.execute("UPDATE tasks SET reminded = 1 WHERE id = ?", (task_id,))
    db.commit()
    return ("", 204)


@app.route("/delete/<int:task_id>", methods=["POST"])
def delete(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return redirect(request.referrer or url_for("index"))


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="127.0.0.1", port=port, use_reloader=False)