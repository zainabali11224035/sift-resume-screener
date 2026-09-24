"""
app.py
------
Flask web application. Routes are grouped into three areas:
  1. Auth       -- /login, /logout
  2. Core tool  -- /, /screen, /results/<id>, /guidelines
  3. Admin only -- /admin/employees (manage employee accounts)

Every route that touches real data requires login (@login_required).
Employee-management routes additionally require @admin_required.
"""

import os
import uuid
import csv
import io

from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import (
    login_user, logout_user, login_required, current_user,
)

import database
import parser as resume_parser
import matcher
import mailer
from auth import login_manager, User, hash_password, verify_password, admin_required, ensure_default_admin

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

app = Flask(__name__)
app.secret_key = os.environ.get("SIFT_SECRET_KEY", "dev-secret-key-change-in-production")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB total upload cap

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
database.init_db()
database.seed_skills_if_empty(resume_parser.SKILLS_DB)
ensure_default_admin()

login_manager.init_app(app)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user_row = database.get_user_by_username(username)

        # Already locked out? Don't even check the password.
        if user_row:
            is_locked, minutes_left = database.get_lockout_status(user_row)
            if is_locked:
                flash(
                    f"Account locked after too many failed attempts. "
                    f"Try again in {minutes_left} minute{'s' if minutes_left != 1 else ''}.",
                    "error",
                )
                return redirect(url_for("login"))

        if user_row and verify_password(user_row["password_hash"], password):
            database.reset_failed_logins(user_row["id"])
            login_user(User(user_row))
            database.log_activity(user_row["id"], user_row["username"], "login", "Signed in")
            flash(f"Welcome back, {user_row['username']}.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("home"))

        # Wrong password (or unknown username -- we still say the same
        # generic message so login can't be used to discover valid usernames).
        if user_row:
            locked, info = database.register_failed_login(username)
            if locked:
                database.log_activity(
                    user_row["id"], user_row["username"], "account_locked",
                    f"Locked for {info} minutes after {database.MAX_FAILED_ATTEMPTS} failed attempts",
                )
                mailer.notify_account_locked(user_row.get("email"), user_row["username"])
                flash(
                    f"Too many failed attempts. Account locked for {info} minutes.",
                    "error",
                )
                return redirect(url_for("login"))

        flash("Incorrect username or password.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    database.log_activity(current_user.id, current_user.username, "logout", "Signed out")
    logout_user()
    flash("You've been logged out.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Core tool routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def home():
    jobs = database.get_jobs_for_user(current_user.id, current_user.role)
    stats = database.get_dashboard_stats(current_user.id, current_user.role)
    return render_template("dashboard.html", jobs=jobs, stats=stats)


@app.route("/screen", methods=["GET", "POST"])
@login_required
def screen():
    if request.method == "GET":
        return render_template("screen.html")

    job_title = request.form.get("job_title", "").strip()
    jd_text = request.form.get("job_description", "").strip()
    files = request.files.getlist("resumes")

    if not job_title or not jd_text:
        flash("Please provide both a job title and a job description.", "error")
        return redirect(url_for("screen"))

    valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]
    if not valid_files:
        flash("Please upload at least one resume in PDF, DOCX, or TXT format.", "error")
        return redirect(url_for("screen"))

    jd_parsed = resume_parser.parse_job_description(jd_text, skills=database.get_all_skill_names())
    job_id = database.add_job(job_title, jd_text, jd_parsed.skills, created_by=current_user.id)

    resumes = []
    parse_errors = []
    skill_set = database.get_all_skill_names()
    for f in valid_files:
        temp_name = f"{uuid.uuid4().hex}_{f.filename}"
        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], temp_name)
        f.save(temp_path)
        try:
            parsed = resume_parser.parse_resume(temp_path, skills=skill_set)
            resumes.append((temp_name, parsed))
        except Exception as e:
            parse_errors.append(f"{f.filename}: could not be read ({e})")
        finally:
            os.remove(temp_path)

    if not resumes:
        flash("None of the uploaded resumes could be read. " + " ".join(parse_errors), "error")
        return redirect(url_for("screen"))

    ranked = matcher.rank_candidates(resumes, jd_parsed)
    for result in ranked:
        database.add_candidate_result(job_id, result)

    database.log_activity(
        current_user.id, current_user.username, "screen",
        f"Screened {len(ranked)} resume(s) for '{job_title}'",
    )
    mailer.notify_screening_complete(
        getattr(current_user, "email", None), current_user.username, job_title, len(ranked)
    )

    if parse_errors:
        flash("Some files were skipped: " + " ".join(parse_errors), "warning")

    return redirect(url_for("results", job_id=job_id))


@app.route("/results/<int:job_id>")
@login_required
def results(job_id):
    job = database.get_job(job_id)
    if not job:
        flash("That job posting could not be found.", "error")
        return redirect(url_for("home"))

    # Access control: employees can only view their own job postings.
    if not current_user.is_admin and job.get("created_by") != current_user.id:
        flash("You don't have access to that job posting.", "error")
        return redirect(url_for("home"))

    candidates = database.get_candidates_for_job(job_id)
    return render_template("results.html", job=job, candidates=candidates)


@app.route("/results/<int:job_id>/export.csv")
@login_required
def export_csv(job_id):
    job = database.get_job(job_id)
    if not job:
        flash("That job posting could not be found.", "error")
        return redirect(url_for("home"))

    if not current_user.is_admin and job.get("created_by") != current_user.id:
        flash("You don't have access to that job posting.", "error")
        return redirect(url_for("home"))

    candidates = database.get_candidates_for_job(job_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Name", "Email", "Phone", "Experience (yrs)",
        "Overall Score", "Skill Score", "Text Score",
        "Matched Skills", "Missing Skills",
    ])
    for i, c in enumerate(candidates, start=1):
        writer.writerow([
            i, c["name"], c["email"], c["phone"], c["experience_years"],
            c["overall_score"], c["skill_score"], c["text_score"],
            "; ".join(c["matched_skills"]), "; ".join(c["missing_skills"]),
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"shortlist_job_{job_id}.csv",
    )


@app.route("/guidelines")
@login_required
def guidelines():
    return render_template("guidelines.html")


@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        user_row = database.get_user_by_id(current_user.id)

        if not verify_password(user_row["password_hash"], current_password):
            flash("Your current password is incorrect.", "error")
        elif len(new_password) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new_password != confirm_password:
            flash("New password and confirmation don't match.", "error")
        else:
            database.update_user_password(current_user.id, hash_password(new_password))
            database.log_activity(current_user.id, current_user.username, "password_change", "Password updated")
            flash("Password updated successfully.", "success")
            return redirect(url_for("home"))

        return redirect(url_for("change_password"))

    return render_template("change_password.html")


@app.route("/account/email", methods=["POST"])
@login_required
def update_email():
    email = request.form.get("email", "").strip() or None
    database.update_user_email(current_user.id, email)
    database.log_activity(current_user.id, current_user.username, "update_email", "Updated notification email")
    flash("Notification email updated.", "success")
    return redirect(url_for("change_password"))


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
def delete_job(job_id):
    job = database.get_job(job_id)
    if not job:
        flash("That job posting could not be found.", "error")
        return redirect(url_for("home"))

    if not current_user.is_admin and job.get("created_by") != current_user.id:
        flash("You don't have access to that job posting.", "error")
        return redirect(url_for("home"))

    database.delete_job(job_id)
    database.log_activity(current_user.id, current_user.username, "delete_job", f"Deleted job '{job['title']}'")
    flash(f"Deleted job posting: {job['title']}.", "success")
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Admin-only: employee management
# ---------------------------------------------------------------------------

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    stats = database.get_admin_overview_stats()
    recent_jobs = database.get_recent_jobs(limit=8)
    recent_users = database.get_recent_users(limit=5)
    return render_template(
        "admin_panel.html", stats=stats, recent_jobs=recent_jobs, recent_users=recent_users
    )


@app.route("/admin/employees", methods=["GET", "POST"])
@login_required
@admin_required
def manage_employees():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "employee")
        email = request.form.get("email", "").strip() or None

        if role not in ("employee", "admin"):
            role = "employee"

        if not username or not password:
            flash("Username and password are both required.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif database.get_user_by_username(username):
            flash("That username is already taken.", "error")
        else:
            database.create_user(username, hash_password(password), role, email)
            database.log_activity(
                current_user.id, current_user.username, "create_user",
                f"Created account '{username}' ({role})",
            )
            mailer.notify_account_created(email, username, role)
            flash(f"Account created for {username} ({role}).", "success")

        return redirect(url_for("manage_employees"))

    users = database.list_users()
    return render_template("employees.html", users=users)


@app.route("/admin/employees/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_employee(user_id):
    target = database.get_user_by_id(user_id)
    if not target:
        flash("That account no longer exists.", "error")
        return redirect(url_for("manage_employees"))

    if target["id"] == current_user.id:
        flash("You can't delete your own account while logged in.", "error")
        return redirect(url_for("manage_employees"))

    if target["role"] == "admin" and database.count_admins() <= 1:
        flash("Can't delete the last remaining admin account.", "error")
        return redirect(url_for("manage_employees"))

    database.delete_user(user_id)
    database.log_activity(current_user.id, current_user.username, "delete_user", f"Removed account '{target['username']}'")
    flash(f"Removed account: {target['username']}.", "success")
    return redirect(url_for("manage_employees"))


@app.route("/admin/skills", methods=["GET", "POST"])
@login_required
@admin_required
def manage_skills():
    if request.method == "POST":
        new_skill = request.form.get("skill_name", "").strip().lower()
        if not new_skill:
            flash("Skill name can't be empty.", "error")
        elif new_skill in database.get_all_skill_names():
            flash(f"'{new_skill}' is already in the list.", "error")
        else:
            database.add_skill(new_skill)
            database.log_activity(current_user.id, current_user.username, "add_skill", f"Added skill '{new_skill}'")
            flash(f"Added skill: {new_skill}", "success")
        return redirect(url_for("manage_skills"))

    skills = database.list_skills()
    return render_template("skills.html", skills=skills)


@app.route("/admin/skills/<int:skill_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_skill(skill_id):
    database.delete_skill(skill_id)
    database.log_activity(current_user.id, current_user.username, "delete_skill", f"Removed skill id {skill_id}")
    flash("Skill removed.", "success")
    return redirect(url_for("manage_skills"))


@app.route("/admin/activity")
@login_required
@admin_required
def activity_log():
    logs = database.get_activity_log(limit=200)
    return render_template("activity_log.html", logs=logs)


@app.route("/admin/skill-demand")
@login_required
@admin_required
def skill_demand():
    demand = database.get_skill_demand(limit=15)
    return render_template("skill_demand.html", demand=demand)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(413)
def too_large(e):
    flash("Upload too large. Please keep the total under 20 MB.", "error")
    return redirect(url_for("screen"))


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
