import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import database
import auth


@pytest.fixture(autouse=True)
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database.set_db_path(path)
    database.init_db()
    yield
    os.remove(path)


def test_password_hash_and_verify():
    hashed = auth.hash_password("mysecret123")
    assert hashed != "mysecret123"  # never store plain text
    assert auth.verify_password(hashed, "mysecret123") is True
    assert auth.verify_password(hashed, "wrongpassword") is False


def test_create_and_fetch_user():
    user_id = database.create_user("alice", auth.hash_password("pass123"), "employee")
    user = database.get_user_by_username("alice")
    assert user["id"] == user_id
    assert user["role"] == "employee"


def test_duplicate_username_rejected():
    database.create_user("bob", auth.hash_password("pass123"), "employee")
    with pytest.raises(Exception):
        database.create_user("bob", auth.hash_password("other"), "employee")


def test_ensure_default_admin_creates_one_when_empty():
    assert database.list_users() == []
    auth.ensure_default_admin()
    users = database.list_users()
    assert len(users) == 1
    assert users[0]["role"] == "admin"


def test_ensure_default_admin_does_nothing_if_users_exist():
    database.create_user("existing", auth.hash_password("pass123"), "employee")
    auth.ensure_default_admin()
    assert len(database.list_users()) == 1  # unchanged


def test_count_admins():
    database.create_user("admin1", auth.hash_password("pass123"), "admin")
    database.create_user("emp1", auth.hash_password("pass123"), "employee")
    assert database.count_admins() == 1
    database.create_user("admin2", auth.hash_password("pass123"), "admin")
    assert database.count_admins() == 2


def test_jobs_scoped_to_employee():
    emp1 = database.create_user("emp1", auth.hash_password("pass123"), "employee")
    emp2 = database.create_user("emp2", auth.hash_password("pass123"), "employee")

    database.add_job("Role A", "desc", {"python"}, created_by=emp1)
    database.add_job("Role B", "desc", {"sql"}, created_by=emp2)

    emp1_jobs = database.get_jobs_for_user(emp1, "employee")
    assert len(emp1_jobs) == 1
    assert emp1_jobs[0]["title"] == "Role A"


def test_admin_sees_all_jobs():
    admin_id = database.create_user("admin1", auth.hash_password("pass123"), "admin")
    emp1 = database.create_user("emp1", auth.hash_password("pass123"), "employee")

    database.add_job("Role A", "desc", {"python"}, created_by=emp1)
    database.add_job("Role B", "desc", {"sql"}, created_by=admin_id)

    admin_jobs = database.get_jobs_for_user(admin_id, "admin")
    assert len(admin_jobs) == 2


def test_delete_user():
    user_id = database.create_user("temp_user", auth.hash_password("pass123"), "employee")
    database.delete_user(user_id)
    assert database.get_user_by_username("temp_user") is None
