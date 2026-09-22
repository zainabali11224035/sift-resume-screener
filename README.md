# Sift — Resume Screening & Job Matcher

An AI-assisted resume screening tool built in Python. Paste a job
description, upload a batch of resumes, and get a ranked, explainable
shortlist showing exactly which skills each candidate matches and which
they're missing.

## Why this project

Recruiters routinely spend hours manually screening resumes for a single
opening. Sift automates the first pass — surfacing the strongest
candidates in seconds, with full transparency into why each one scored
the way they did (no black-box AI decision-making).

## Tech stack

- **Backend:** Python, Flask, Flask-Login (sessions/authentication)
- **Parsing:** pdfplumber (PDF), python-docx (Word)
- **Matching engine:** scikit-learn (TF-IDF + cosine similarity) + a
  custom skill-overlap scorer
- **Storage:** SQLite
- **Frontend:** server-rendered HTML/CSS (no JS framework required)
- **Testing:** pytest

## What's new

Recent additions on top of the original screening tool:

- **Home link** in the navbar for quick access back to the dashboard.
- **Login lockout** — after 5 failed login attempts, an account is
  locked for 15 minutes (configurable in `database.py`,
  `MAX_FAILED_ATTEMPTS` / `LOCKOUT_MINUTES`).
- **Dark / light mode** — toggle button in the navbar, preference saved
  per-browser (no server round-trip).
- **Activity log / audit trail** — Admin Panel → *Activity log* shows
  every login, logout, lockout, screening run, and account/skill change,
  newest first.
- **Skill demand chart** — Admin Panel → *Skill demand* shows which
  skills appear most often across every job description screened so
  far, as a bar chart.
- **Email notifications** (optional) — new-account welcome emails,
  account-lockout alerts, and screening-complete notifications. Off by
  default; see "Email notifications" below to turn it on.

## Email notifications

Notifications are sent through `mailer.py` using plain SMTP. If it isn't
configured, emails are just printed to the console instead of sent — the
app works fine either way.

To send real emails, set these environment variables before running the
app:

```bash
export SIFT_SMTP_HOST=smtp.gmail.com
export SIFT_SMTP_PORT=587
export SIFT_SMTP_USER=your_email@gmail.com
export SIFT_SMTP_PASSWORD=your_app_password
export SIFT_FROM_EMAIL=your_email@gmail.com   # optional, defaults to SIFT_SMTP_USER
```

(For Gmail, use an **App Password**, not your normal login password.)

Each user can set their own notification email from **Account** →
*Notification email* in the nav.



Sift now has account-based access:

- **Admin** — can manage employee accounts (`/admin/employees`), and can
  view every job posting screened by anyone on the team.
- **Employee** — can screen resumes and view results, but only for job
  postings they created themselves.

On first run, if no accounts exist yet, Sift automatically creates a
starter admin account:

```
username: admin
password: admin123
```

**Change this password (or delete and recreate the account) immediately
after your first login** — this default exists only so the app isn't
locked out of the box, not for real use.

To add more accounts: log in as admin → click "Employees" in the nav →
fill in the "Add a new account" form.

## Project structure

```
resume_screener/
├── app.py              # Flask routes / web layer
├── auth.py              # Login, password hashing, role checks
├── mailer.py            # Optional SMTP email notifications
├── parser.py           # Resume & job description parsing
├── matcher.py           # Scoring & ranking engine
├── database.py         # SQLite data access layer (users, jobs, candidates, activity log)
├── templates/           # HTML pages (Jinja2)
├── static/css/         # Stylesheet (incl. dark mode)
├── static/js/          # Dark mode toggle
├── sample_data/        # Sample resumes for testing/demo
├── tests/               # pytest unit tests
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000 in your browser.

## Running the tests

```bash
pytest tests/ -v
```

All 34 tests should pass. Tests cover the parser, the matching engine,
the database layer, and authentication/access-control independently,
plus integration-style tests of the full scoring pipeline.

## Starting fresh

If you want to wipe all accounts, job postings, and results and start
over (e.g. for a clean demo), stop the server and delete the database
file:

```bash
rm resume_screener.db
```

The next time you start the app, it will recreate the database and a
fresh default admin account.

## Trying it out

Use the sample resumes in `sample_data/` with a job description like:

> "We need a Python developer with experience in Flask, SQL, Docker, and AWS."

This will produce three clearly differentiated scores (strong, medium,
weak match) so you can see the ranking logic at work.

## Guidelines

See the in-app **Guidelines** page (`/guidelines`) for a full explanation
of the scoring formula, supported file types, and known limitations —
this is written for an end user, not a developer.

## Known limitations

- Skill detection relies on a fixed dictionary (`SKILLS_DB` in
  `parser.py`) — a skill not in that list won't be detected.
- Scanned/image-only PDFs won't extract text (no OCR).
- Name extraction is a heuristic (first non-contact-info line) and can
  be wrong for unconventional resume layouts.

## Possible next steps

- Add OCR support for scanned PDFs (e.g. via `pytesseract`)
- Let the skills dictionary be edited from the UI instead of the source code
- Add authentication so multiple recruiters can keep separate job postings
- Add a chart on the results page (e.g. score distribution histogram)
