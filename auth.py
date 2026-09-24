"""
auth.py
-------
Everything related to who's logged in and what they're allowed to do.

Kept separate from app.py on purpose: if you ever need to change how
login works (e.g. add email verification, switch to a different user
store), this is the only file that should need to change.
"""

from functools import wraps
from flask import abort
from flask_login import LoginManager, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

import database

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "error"


class User(UserMixin):
    """
    Thin wrapper around a database row so Flask-Login can work with it.
    Flask-Login expects an object with .id, .is_authenticated, etc. --
    UserMixin provides sensible defaults for all of those.
    """

    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.role = row["role"]
        self.email = row["email"] if "email" in row.keys() else None

    @property
    def is_admin(self):
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id):
    """Called by Flask-Login on every request to reload the logged-in user."""
    row = database.get_user_by_id(int(user_id))
    return User(row) if row else None


def hash_password(plain_password):
    return generate_password_hash(plain_password)


def verify_password(password_hash, plain_password):
    return check_password_hash(password_hash, plain_password)


def admin_required(view_func):
    """
    Route decorator: use AFTER @login_required.
    Blocks any logged-in user who isn't an admin with a 403 Forbidden.

    Example:
        @app.route("/admin/employees")
        @login_required
        @admin_required
        def manage_employees():
            ...
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def ensure_default_admin():
    """
    Create a starter admin account on first run if no users exist yet, so
    there's always a way to log in on a fresh install.

    IMPORTANT: change this password immediately after first login in any
    real deployment. This exists purely so the app isn't locked-out of
    the box.
    """
    if not database.list_users():
        database.create_user(
            username="admin",
            password_hash=hash_password("admin123"),
            role="admin",
        )
        print(
            "\n"
            "==================================================\n"
            " No users existed yet -- created a default admin:\n"
            "   username: admin\n"
            "   password: admin123\n"
            " Log in and change this password immediately.\n"
            "==================================================\n"
        )
