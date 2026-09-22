"""
test_app.py
-----------
Integration tests that exercise real HTTP routes via Flask's test client,
rather than calling internal functions directly. These catch bugs that
unit tests miss -- e.g. a route forgetting @login_required, or a
redirect going to the wrong place.
"""

import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import database
import app as app_module


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.set_db_path(path)
    database.init_db()
    database.seed_skills_if_empty({"python", "sql", "flask"})

    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False

    with app_module.app.test_client() as test_client:
        yield test_client

    os.remove(path)


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def create_admin_and_login(client, username="admin1", password="adminpass123"):
    password_hash = app_module.hash_password(password)
    database.create_user(username, password_hash, "admin")
    login(client, username, password)


def create_employee_and_login(client, username="emp1", password="emppass123"):
    password_hash = app_module.hash_password(password)
    database.create_user(username, password_hash, "employee")
    login(client, username, password)


def test_home_redirects_to_login_when_not_authenticated(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_with_correct_credentials_succeeds(client):
    create_admin_and_login(client)
    response = client.get("/")
    assert response.status_code == 200
    assert b"job postings" in response.data.lower()


def test_login_with_wrong_password_fails(client):
    password_hash = app_module.hash_password("correctpass")
    database.create_user("bob", password_hash, "employee")
    response = login(client, "bob", "wrongpass")
    assert b"Incorrect username or password" in response.data


def test_logout_requires_login_again(client):
    create_employee_and_login(client)
    client.get("/logout")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302


def test_employee_cannot_access_employee_management(client):
    create_employee_and_login(client)
    response = client.get("/admin/employees")
    assert response.status_code == 403


def test_admin_can_access_employee_management(client):
    create_admin_and_login(client)
    response = client.get("/admin/employees")
    assert response.status_code == 200


def test_employee_cannot_access_skills_management(client):
    create_employee_and_login(client)
    response = client.get("/admin/skills")
    assert response.status_code == 403


def test_admin_can_add_and_remove_skill(client):
    create_admin_and_login(client)
    client.post("/admin/skills", data={"skill_name": "graphql"})
    assert "graphql" in database.get_all_skill_names()

    skills = database.list_skills()
    skill_id = next(s["id"] for s in skills if s["name"] == "graphql")
    client.post(f"/admin/skills/{skill_id}/delete")
    assert "graphql" not in database.get_all_skill_names()


def test_change_password_with_wrong_current_password_fails(client):
    password_hash = app_module.hash_password("originalpass")
    user_id = database.create_user("carol", password_hash, "employee")
    login(client, "carol", "originalpass")

    response = client.post(
        "/account/password",
        data={
            "current_password": "wrongpass",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
        follow_redirects=True,
    )
    assert b"current password is incorrect" in response.data


def test_change_password_success_allows_login_with_new_password(client):
    password_hash = app_module.hash_password("originalpass")
    database.create_user("dave", password_hash, "employee")
    login(client, "dave", "originalpass")

    client.post(
        "/account/password",
        data={
            "current_password": "originalpass",
            "new_password": "brandnewpass",
            "confirm_password": "brandnewpass",
        },
    )
    client.get("/logout")

    response = login(client, "dave", "brandnewpass")
    assert b"job postings" in response.data.lower()


def test_employee_job_isolation_over_http(client):
    # emp1 screens a batch
    create_employee_and_login(client, "emp1", "pass12345")
    client.post(
        "/screen",
        data={
            "job_title": "Emp1's Job",
            "job_description": "Need Python and SQL",
            "resumes": [],
        },
    )
    # (no real file uploaded here, so this specific job may not get created --
    # the real point of this test is the isolation check below using direct
    # DB setup instead)
    client.get("/logout")

    job_id = database.add_job("Direct Job", "desc", {"python"}, created_by=1)

    create_employee_and_login(client, "emp2", "pass12345")
    response = client.get(f"/results/{job_id}", follow_redirects=True)
    assert b"don&#39;t have access" in response.data or b"access" in response.data.lower()


def test_delete_job_removes_it_from_dashboard(client):
    create_admin_and_login(client)
    job_id = database.add_job("Temp Job", "desc", {"python"}, created_by=1)

    response_before = client.get("/")
    assert b"Temp Job" in response_before.data

    client.post(f"/jobs/{job_id}/delete", follow_redirects=True)
    response_after = client.get("/")
    assert b"Temp Job" not in response_after.data


def test_guidelines_page_requires_login(client):
    response = client.get("/guidelines", follow_redirects=False)
    assert response.status_code == 302

    create_employee_and_login(client)
    response = client.get("/guidelines")
    assert response.status_code == 200


def test_employee_cannot_access_admin_panel(client):
    create_employee_and_login(client)
    response = client.get("/admin")
    assert response.status_code == 403


def test_admin_can_access_admin_panel(client):
    create_admin_and_login(client)
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Admin Panel" in response.data


def test_admin_panel_shows_correct_stats(client):
    create_admin_and_login(client)
    database.create_user("emp1", "hash", "employee")
    job_id = database.add_job("Test Job", "desc", {"python"}, created_by=1)
    database.add_candidate_result(job_id, {"name": "Cand", "overall_score": 75})

    response = client.get("/admin")
    assert b"Test Job" in response.data
    assert b"emp1" in response.data
