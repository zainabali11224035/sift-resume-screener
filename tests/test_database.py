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


def test_seed_skills_populates_when_empty():
    assert database.get_all_skill_names() == set()
    database.seed_skills_if_empty({"python", "sql", "docker"})
    assert database.get_all_skill_names() == {"python", "sql", "docker"}


def test_seed_skills_does_nothing_if_already_populated():
    database.add_skill("python")
    database.seed_skills_if_empty({"java", "c++"})
    assert database.get_all_skill_names() == {"python"}


def test_add_and_delete_skill():
    database.add_skill("Kubernetes")  # stored lowercase regardless of input case
    assert "kubernetes" in database.get_all_skill_names()

    skills = database.list_skills()
    skill_id = next(s["id"] for s in skills if s["name"] == "kubernetes")
    database.delete_skill(skill_id)
    assert "kubernetes" not in database.get_all_skill_names()


def test_add_duplicate_skill_is_ignored():
    database.add_skill("python")
    database.add_skill("python")
    assert len(database.list_skills()) == 1


def test_update_user_password():
    user_id = database.create_user("alice", "old_hash", "employee")
    database.update_user_password(user_id, "new_hash")
    user = database.get_user_by_id(user_id)
    assert user["password_hash"] == "new_hash"


def test_delete_job_removes_candidates_too():
    job_id = database.add_job("Role", "desc", {"python"}, created_by=None)
    database.add_candidate_result(job_id, {"name": "Test", "overall_score": 50})
    assert len(database.get_candidates_for_job(job_id)) == 1

    database.delete_job(job_id)
    assert database.get_job(job_id) is None
    assert database.get_candidates_for_job(job_id) == []


def test_dashboard_stats_empty():
    stats = database.get_dashboard_stats(1, "admin")
    assert stats["total_jobs"] == 0
    assert stats["total_candidates"] == 0
    assert stats["avg_score"] is None


def test_dashboard_stats_with_data():
    admin_id = database.create_user("admin1", "hash", "admin")
    job_id = database.add_job("Role", "desc", {"python"}, created_by=admin_id)
    database.add_candidate_result(job_id, {"name": "A", "overall_score": 80})
    database.add_candidate_result(job_id, {"name": "B", "overall_score": 60})

    stats = database.get_dashboard_stats(admin_id, "admin")
    assert stats["total_jobs"] == 1
    assert stats["total_candidates"] == 2
    assert stats["avg_score"] == 70.0


def test_dashboard_stats_scoped_to_employee():
    emp1 = database.create_user("emp1", "hash", "employee")
    emp2 = database.create_user("emp2", "hash", "employee")
    job1 = database.add_job("Role A", "desc", {"python"}, created_by=emp1)
    database.add_job("Role B", "desc", {"sql"}, created_by=emp2)
    database.add_candidate_result(job1, {"name": "A", "overall_score": 90})

    stats = database.get_dashboard_stats(emp1, "employee")
    assert stats["total_jobs"] == 1
    assert stats["total_candidates"] == 1
