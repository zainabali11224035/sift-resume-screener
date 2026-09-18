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

## Roles & login

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
├── parser.py           # Resume & job description parsing
├── matcher.py           # Scoring & ranking engine
├── database.py         # SQLite data access layer (users, jobs, candidates)
├── templates/           # HTML pages (Jinja2)
├── static/css/         # Stylesheet
├── sample_data/        # Sample resumes for testing/demo
├── tests/               # pytest unit tests (34 tests)
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
