"""Small SQLite progress store; the question bank itself stays in JSON."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parent.parent / "data" / "progress.db"


def connect(database_path=DEFAULT_DATABASE):
    """Open the local database and create its tables the first time."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY,
            question_id TEXT NOT NULL,
            category TEXT NOT NULL,
            submitted_answer TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            happened_on TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fact_reviews (
            fact_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            streak INTEGER NOT NULL DEFAULT 0,
            due_on TEXT NOT NULL,
            reviewed_on TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_activity (
            activity_date TEXT PRIMARY KEY
        );
        """
    )
    connection.commit()
    return connection


def record_response(connection, question, submitted_answer, is_correct, happened_on=None):
    """Store one attempt and mark the day active."""
    day = (happened_on or date.today()).isoformat()
    connection.execute(
        "INSERT INTO responses (question_id, category, submitted_answer, is_correct, happened_on) VALUES (?, ?, ?, ?, ?)",
        (question["id"], question["category"], submitted_answer, int(is_correct), day),
    )
    connection.execute("INSERT OR IGNORE INTO daily_activity (activity_date) VALUES (?)", (day,))
    connection.commit()


def review_fact(connection, fact_id, status, reviewed_on=None):
    """Schedule a fact again sooner after a miss and later after mastery."""
    if status not in ("know", "study"):
        raise ValueError("Fact review status must be 'know' or 'study'.")
    today = reviewed_on or date.today()
    previous = connection.execute(
        "SELECT streak FROM fact_reviews WHERE fact_id = ?", (fact_id,)
    ).fetchone()
    streak = (previous["streak"] + 1) if previous and status == "know" else int(status == "know")
    interval = min(30, 2 ** min(streak, 5)) if status == "know" else 1
    due_on = (today + timedelta(days=interval)).isoformat()
    connection.execute(
        """
        INSERT INTO fact_reviews (fact_id, status, streak, due_on, reviewed_on)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(fact_id) DO UPDATE SET
            status = excluded.status,
            streak = excluded.streak,
            due_on = excluded.due_on,
            reviewed_on = excluded.reviewed_on
        """,
        (fact_id, status, streak, due_on, today.isoformat()),
    )
    connection.commit()


def get_review_statuses(connection):
    """Return saved review state keyed by fact id."""
    rows = connection.execute("SELECT * FROM fact_reviews").fetchall()
    return {row["fact_id"]: dict(row) for row in rows}


def get_due_question_ids(connection, questions, today=None):
    """Map facts due today to their question ids for practice prioritization."""
    current_day = (today or date.today()).isoformat()
    due_facts = connection.execute(
        "SELECT fact_id FROM fact_reviews WHERE due_on <= ? AND status = 'study'",
        (current_day,),
    ).fetchall()
    due_ids = {row["fact_id"] for row in due_facts}
    return {
        question["id"]
        for question in questions
        if any(f"{question['id']}:{index}" in due_ids for index, _answer in enumerate(question["answers"]))
    }


def get_stats(connection, today=None):
    """Summarize learning activity and calculate the current daily streak."""
    current = today or date.today()
    row = connection.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(is_correct), 0) AS correct FROM responses"
    ).fetchone()
    reviews = connection.execute(
        "SELECT COUNT(*) AS mastered FROM fact_reviews WHERE status = 'know'"
    ).fetchone()
    active_days = {
        date.fromisoformat(item["activity_date"])
        for item in connection.execute("SELECT activity_date FROM daily_activity")
    }
    streak = 0
    check_day = current
    if check_day not in active_days and check_day - timedelta(days=1) in active_days:
        check_day -= timedelta(days=1)
    while check_day in active_days:
        streak += 1
        check_day -= timedelta(days=1)
    total = row["total"]
    return {
        "questions_completed": total,
        "accuracy": round((row["correct"] / total) * 100) if total else 0,
        "facts_mastered": reviews["mastered"],
        "streak": streak,
    }


def weak_categories(connection):
    """List topics with the lowest answer accuracy for review selection."""
    rows = connection.execute(
        """
        SELECT category, AVG(is_correct) AS accuracy, COUNT(*) AS attempts
        FROM responses
        GROUP BY category
        HAVING COUNT(*) >= 2
        ORDER BY accuracy ASC
        LIMIT 3
        """
    ).fetchall()
    return [row["category"] for row in rows]
