import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from parser import (
    extract_email,
    extract_phone,
    extract_skills,
    extract_experience_years,
    extract_name,
    parse_job_description,
)


def test_extract_email_found():
    text = "Contact me at jane.doe@example.com for details."
    assert extract_email(text) == "jane.doe@example.com"


def test_extract_email_not_found():
    text = "No contact info here."
    assert extract_email(text) is None


def test_extract_phone_found():
    text = "Call me at +1 415-555-0132 anytime."
    assert extract_phone(text) is not None


def test_extract_skills_basic():
    text = "Experienced in Python, Django, and SQL. Also familiar with React."
    skills = extract_skills(text)
    assert "python" in skills
    assert "django" in skills
    assert "sql" in skills
    assert "react" in skills


def test_extract_skills_no_partial_match():
    # "java" should NOT match inside "javascript"
    text = "I only know JavaScript, not the other one."
    skills = extract_skills(text)
    assert "javascript" in skills
    assert "java" not in skills


def test_extract_experience_years_found():
    text = "I have 5 years of experience in backend development."
    assert extract_experience_years(text) == 5


def test_extract_experience_years_default_zero():
    text = "Fresh graduate looking for opportunities."
    assert extract_experience_years(text) == 0


def test_extract_name_first_line():
    text = "John Smith\nSoftware Engineer\njohn@example.com"
    assert extract_name(text) == "John Smith"


def test_extract_name_skips_email_line():
    text = "john@example.com\nJohn Smith\nSoftware Engineer"
    assert extract_name(text) == "John Smith"


def test_parse_job_description():
    jd_text = "We need a Python developer with 3 years of experience in Flask and SQL."
    parsed = parse_job_description(jd_text)
    assert "python" in parsed.skills
    assert "flask" in parsed.skills
    assert parsed.experience_years == 3


def test_extract_skills_empty_text():
    assert extract_skills("") == set()
