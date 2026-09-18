import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from parser import ParsedDocument
from matcher import skill_overlap_score, text_similarity_score, match_candidate, rank_candidates


def test_skill_overlap_perfect_match():
    resume_skills = {"python", "sql", "flask"}
    jd_skills = {"python", "sql", "flask"}
    score, matched, missing = skill_overlap_score(resume_skills, jd_skills)
    assert score == 1.0
    assert matched == jd_skills
    assert missing == set()


def test_skill_overlap_partial_match():
    resume_skills = {"python", "sql"}
    jd_skills = {"python", "sql", "docker"}
    score, matched, missing = skill_overlap_score(resume_skills, jd_skills)
    assert round(score, 2) == 0.67
    assert missing == {"docker"}


def test_skill_overlap_no_jd_skills():
    score, matched, missing = skill_overlap_score({"python"}, set())
    assert score == 0.0


def test_skill_overlap_zero_match():
    score, matched, missing = skill_overlap_score({"java"}, {"python"})
    assert score == 0.0
    assert missing == {"python"}


def test_text_similarity_identical_text():
    text = "Experienced Python developer with Flask and SQL background"
    score = text_similarity_score(text, text)
    assert score > 0.9


def test_text_similarity_unrelated_text():
    resume = "Experienced chef specializing in French pastry"
    jd = "Looking for a senior backend engineer with Kubernetes experience"
    score = text_similarity_score(resume, jd)
    assert score < 0.3


def test_text_similarity_empty_input():
    assert text_similarity_score("", "something") == 0.0
    assert text_similarity_score("something", "") == 0.0


def test_match_candidate_full_pipeline():
    resume = ParsedDocument(
        raw_text="Python developer with Flask, SQL and 3 years experience",
        name="Test Candidate",
        skills={"python", "flask", "sql"},
        experience_years=3,
    )
    jd = ParsedDocument(
        raw_text="Need a Python developer skilled in Flask and SQL",
        skills={"python", "flask", "sql"},
    )
    result = match_candidate(resume, jd)
    assert result["overall_score"] > 80
    assert set(result["matched_skills"]) == {"python", "flask", "sql"}
    assert result["missing_skills"] == []


def test_rank_candidates_orders_by_score():
    strong = ParsedDocument(
        raw_text="Python Flask SQL expert",
        name="Strong Candidate",
        skills={"python", "flask", "sql"},
    )
    weak = ParsedDocument(
        raw_text="Only knows PHP",
        name="Weak Candidate",
        skills={"php"},
    )
    jd = ParsedDocument(
        raw_text="Need Python Flask SQL developer",
        skills={"python", "flask", "sql"},
    )
    ranked = rank_candidates([(1, weak), (2, strong)], jd)
    assert ranked[0]["name"] == "Strong Candidate"
    assert ranked[0]["overall_score"] > ranked[1]["overall_score"]
