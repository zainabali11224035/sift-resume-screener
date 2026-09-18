import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import database


@pytest.fixture(autouse=True)
def temp_db():
    """Point the database module at a fresh temp file for every test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.set_db_path(path)
    database.init_db()
    yield
    os.remove(path)


def test_add_and_get_job():
    job_id = database.add_job("Backend Developer", "Need Python and SQL", {"python", "sql"})
    job = database.get_job(job_id)
    assert job["title"] == "Backend Developer"
    assert "python" in job["required_skills"]


def test_add_candidate_result_and_retrieve():
    job_id = database.add_job("Backend Developer", "Need Python", {"python"})
    result = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "123-456-7890",
        "experience_years": 4,
        "overall_score": 88.5,
        "skill_score": 90.0,
        "text_score": 80.0,
        "matched_skills": ["python"],
        "missing_skills": [],
    }
    database.add_candidate_result(job_id, result)
    candidates = database.get_candidates_for_job(job_id)
    assert len(candidates) == 1
    assert candidates[0]["name"] == "Jane Doe"
    assert candidates[0]["overall_score"] == 88.5
    assert candidates[0]["matched_skills"] == ["python"]


def test_candidates_ordered_by_score_desc():
    job_id = database.add_job("Role", "desc", {"python"})
    database.add_candidate_result(job_id, {"name": "Low", "overall_score": 40})
    database.add_candidate_result(job_id, {"name": "High", "overall_score": 95})
    candidates = database.get_candidates_for_job(job_id)
    assert candidates[0]["name"] == "High"
    assert candidates[1]["name"] == "Low"


def test_clear_all_removes_data():
    database.add_job("Role", "desc", {"python"})
    database.clear_all()
    with database.get_connection() as conn:
        jobs = conn.execute("SELECT * FROM jobs").fetchall()
    assert len(jobs) == 0


def test_get_job_nonexistent_returns_none():
    assert database.get_job(9999) is None
