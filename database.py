"""
database.py
-----------
Thin data-access layer over SQLite. Nothing outside this module should
write raw SQL -- this keeps the rest of the app (and the tests) decoupled
from the storage engine.
"""

import sqlite3
import json
from contextlib import contextmanager

DB_PATH = "resume_screener.db"


def get_db_path():
    return DB_PATH


def set_db_path(path):
    """Allows tests to point the module at a temporary database file."""
    global DB_PATH
    DB_PATH = path


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                required_skills TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                name TEXT,
                email TEXT,
                phone TEXT,
                skills TEXT,
                experience_years INTEGER DEFAULT 0,
                overall_score REAL,
                skill_score REAL,
                text_score REAL,
                matched_skills TEXT,
                missing_skills TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
            );
            """
        )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username, password_hash, role="employee"):
    """Insert a new user. Raises sqlite3.IntegrityError if username taken."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        return cursor.lastrowid


def get_user_by_username(username):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]


def delete_user(user_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def count_admins():
    """Used to prevent deleting the last remaining admin account."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE role = 'admin'"
        ).fetchone()
        return row["c"]


def add_job(title, description, required_skills, created_by=None):
    """Insert a job posting and return its new id."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs (title, description, required_skills, created_by) VALUES (?, ?, ?, ?)",
            (title, description, json.dumps(sorted(required_skills)), created_by),
        )
        return cursor.lastrowid


def get_job(job_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def get_jobs_for_user(user_id, role):
    """Admins see every job posting; employees see only their own."""
    with get_connection() as conn:
        if role == "admin":
            rows = conn.execute(
                """
                SELECT jobs.*, users.username AS created_by_name,
                       (SELECT COUNT(*) FROM candidates WHERE candidates.job_id = jobs.id) AS candidate_count
                FROM jobs LEFT JOIN users ON jobs.created_by = users.id
                ORDER BY jobs.created_at DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT jobs.*, users.username AS created_by_name,
                       (SELECT COUNT(*) FROM candidates WHERE candidates.job_id = jobs.id) AS candidate_count
                FROM jobs LEFT JOIN users ON jobs.created_by = users.id
                WHERE jobs.created_by = ?
                ORDER BY jobs.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def add_candidate_result(job_id, result):
    """Persist one ranked candidate result for a job."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO candidates (
                job_id, name, email, phone, skills, experience_years,
                overall_score, skill_score, text_score,
                matched_skills, missing_skills
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                result.get("name"),
                result.get("email"),
                result.get("phone"),
                json.dumps(result.get("matched_skills", []) + result.get("missing_skills", [])),
                result.get("experience_years", 0),
                result.get("overall_score", 0),
                result.get("skill_score", 0),
                result.get("text_score", 0),
                json.dumps(result.get("matched_skills", [])),
                json.dumps(result.get("missing_skills", [])),
            ),
        )


def get_candidates_for_job(job_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE job_id = ? ORDER BY overall_score DESC",
            (job_id,),
        ).fetchall()
        candidates = []
        for row in rows:
            c = dict(row)
            c["matched_skills"] = json.loads(c["matched_skills"] or "[]")
            c["missing_skills"] = json.loads(c["missing_skills"] or "[]")
            candidates.append(c)
        return candidates


def clear_all():
    """Wipe all data -- used between test runs and for a manual reset."""
    with get_connection() as conn:
        conn.executescript("DELETE FROM candidates; DELETE FROM jobs;")
