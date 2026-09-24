"""
database.py
-----------
Thin data-access layer over SQLite. Nothing outside this module should
write raw SQL -- this keeps the rest of the app (and the tests) decoupled
from the storage engine.
"""

import sqlite3
import json
from datetime import datetime, timedelta
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
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Lightweight migrations for installs that already have a users table
        # from before lockout/email support existed. SQLite has no
        # "ADD COLUMN IF NOT EXISTS", so we just swallow the duplicate-column
        # error on installs that already have the column.
        for statement in (
            "ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN locked_until TEXT",
            "ALTER TABLE users ADD COLUMN email TEXT",
            "ALTER TABLE candidates ADD COLUMN education TEXT",
            "ALTER TABLE candidates ADD COLUMN certifications TEXT",
            "ALTER TABLE candidates ADD COLUMN links TEXT",
        ):
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # column already exists


def seed_skills_if_empty(default_skills):
    """
    Populate the skills table from a starter list, but only if it's
    currently empty. Lets the skill list live in the database (so admins
    can edit it) while still shipping with a sensible default.
    """
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM skills").fetchone()["c"]
        if count == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO skills (name) VALUES (?)",
                [(s,) for s in sorted(default_skills)],
            )


def get_all_skill_names():
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM skills ORDER BY name ASC").fetchall()
        return {row["name"] for row in rows}


def list_skills():
    """Returns skills with their ids, for rendering a management UI."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM skills ORDER BY name ASC").fetchall()
        return [dict(row) for row in rows]


def add_skill(name):
    name = name.strip().lower()
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO skills (name) VALUES (?)", (name,))


def delete_skill(skill_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username, password_hash, role="employee", email=None):
    """Insert a new user. Raises sqlite3.IntegrityError if username taken."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, email),
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


def update_user_password(user_id, new_password_hash):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_password_hash, user_id),
        )


def update_user_email(user_id, email):
    with get_connection() as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))


# ---------------------------------------------------------------------------
# Login lockout
# ---------------------------------------------------------------------------
# After MAX_FAILED_ATTEMPTS wrong passwords in a row, the account is locked
# for LOCKOUT_MINUTES. A correct login (or the lockout window passing)
# resets the counter.

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def register_failed_login(username):
    """
    Bump the failed-attempt counter for a username. If it reaches the
    threshold, lock the account and return (locked=True, minutes).
    Returns (locked=False, attempts_left) otherwise. No-op (False, None)
    if the username doesn't exist, so login can't be used to enumerate users.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, failed_attempts FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return False, None

        attempts = row["failed_attempts"] + 1
        if attempts >= MAX_FAILED_ATTEMPTS:
            locked_until = (datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (attempts, locked_until, row["id"]),
            )
            return True, LOCKOUT_MINUTES
        else:
            conn.execute(
                "UPDATE users SET failed_attempts = ? WHERE id = ?",
                (attempts, row["id"]),
            )
            return False, MAX_FAILED_ATTEMPTS - attempts


def reset_failed_logins(user_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (user_id,),
        )


def get_lockout_status(user_row):
    """
    Given a user row (dict or sqlite3.Row) that includes locked_until,
    returns (is_locked, minutes_remaining). Automatically treats an
    expired lock as not-locked (the counter gets cleared on next
    successful check via reset_failed_logins).
    """
    locked_until = user_row["locked_until"] if user_row else None
    if not locked_until:
        return False, 0
    try:
        expires = datetime.fromisoformat(locked_until)
    except ValueError:
        return False, 0
    remaining = (expires - datetime.utcnow()).total_seconds()
    if remaining <= 0:
        return False, 0
    return True, max(1, round(remaining / 60))


# ---------------------------------------------------------------------------
# Activity log / audit trail
# ---------------------------------------------------------------------------

def log_activity(user_id, username, action, details=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, username, action, details) VALUES (?, ?, ?, ?)",
            (user_id, username, action, details),
        )


def get_activity_log(limit=200):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


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
                ORDER BY jobs.created_at DESC, jobs.id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT jobs.*, users.username AS created_by_name,
                       (SELECT COUNT(*) FROM candidates WHERE candidates.job_id = jobs.id) AS candidate_count
                FROM jobs LEFT JOIN users ON jobs.created_by = users.id
                WHERE jobs.created_by = ?
                ORDER BY jobs.created_at DESC, jobs.id DESC
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
                matched_skills, missing_skills, education, certifications, links
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(result.get("education", [])),
                json.dumps(result.get("certifications", [])),
                json.dumps(result.get("links", {})),
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
            c["education"] = json.loads(c["education"] or "[]")
            c["certifications"] = json.loads(c["certifications"] or "[]")
            c["links"] = json.loads(c["links"] or "{}")
            candidates.append(c)
        return candidates


def clear_all():
    """Wipe all data -- used between test runs and for a manual reset."""
    with get_connection() as conn:
        conn.executescript("DELETE FROM candidates; DELETE FROM jobs;")


def delete_job(job_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def get_dashboard_stats(user_id, role):
    """
    Summary numbers for the dashboard header:
    total job postings, total candidates screened, average match score.
    Admins see team-wide numbers; employees see only their own.
    """
    with get_connection() as conn:
        if role == "admin":
            jobs_row = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()
            cand_row = conn.execute(
                "SELECT COUNT(*) as c, AVG(overall_score) as avg_score FROM candidates"
            ).fetchone()
        else:
            jobs_row = conn.execute(
                "SELECT COUNT(*) as c FROM jobs WHERE created_by = ?", (user_id,)
            ).fetchone()
            cand_row = conn.execute(
                """
                SELECT COUNT(*) as c, AVG(overall_score) as avg_score
                FROM candidates
                WHERE job_id IN (SELECT id FROM jobs WHERE created_by = ?)
                """,
                (user_id,),
            ).fetchone()

        avg_score = cand_row["avg_score"]
        return {
            "total_jobs": jobs_row["c"],
            "total_candidates": cand_row["c"],
            "avg_score": round(avg_score, 1) if avg_score is not None else None,
        }


def get_admin_overview_stats():
    """
    System-wide numbers for the Admin Panel hub page: how many people have
    accounts, how much screening has happened, how big the skills list is.
    """
    with get_connection() as conn:
        users_row = conn.execute(
            "SELECT "
            "SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) as admins, "
            "SUM(CASE WHEN role = 'employee' THEN 1 ELSE 0 END) as employees "
            "FROM users"
        ).fetchone()
        jobs_row = conn.execute("SELECT COUNT(*) as c FROM jobs").fetchone()
        cand_row = conn.execute("SELECT COUNT(*) as c FROM candidates").fetchone()
        skills_row = conn.execute("SELECT COUNT(*) as c FROM skills").fetchone()

        return {
            "total_admins": users_row["admins"] or 0,
            "total_employees": users_row["employees"] or 0,
            "total_jobs": jobs_row["c"],
            "total_candidates": cand_row["c"],
            "total_skills": skills_row["c"],
        }


def get_recent_jobs(limit=8):
    """Latest job postings across the whole team, for the Admin Panel's activity feed."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT jobs.*, users.username AS created_by_name,
                   (SELECT COUNT(*) FROM candidates WHERE candidates.job_id = jobs.id) AS candidate_count
            FROM jobs LEFT JOIN users ON jobs.created_by = users.id
            ORDER BY jobs.created_at DESC, jobs.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_skill_demand(limit=12):
    """
    How often each skill has been REQUIRED across all job postings screened
    so far -- i.e. what employers are actually asking for. Powers the
    Skill Demand chart in the Admin Panel.
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT required_skills FROM jobs").fetchall()

    counts = {}
    for row in rows:
        try:
            skills = json.loads(row["required_skills"] or "[]")
        except (TypeError, ValueError):
            skills = []
        for skill in skills:
            counts[skill] = counts.get(skill, 0) + 1

    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [{"skill": skill, "count": count} for skill, count in ranked[:limit]]


def get_recent_users(limit=5):
    """Latest accounts created, for the Admin Panel's activity feed."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
