"""
matcher.py
----------
Scores a candidate's resume against a job description using two signals:

1. Skill overlap  -- what fraction of the JD's required skills the
   candidate actually has. This is the interpretable, explainable part.
2. Text similarity -- TF-IDF + cosine similarity between the full resume
   text and the full JD text, to catch relevant experience that isn't
   captured by the fixed skills dictionary.

The final score is a weighted blend of both, favouring skill overlap
because it's more directly meaningful to a recruiter than raw text
similarity.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SKILL_WEIGHT = 0.7
TEXT_SIMILARITY_WEIGHT = 0.3


def skill_overlap_score(resume_skills, jd_skills):
    """Return (score 0-1, matched skills, missing skills)."""
    if not jd_skills:
        # No skills detected in the JD -- can't score on this signal.
        return 0.0, set(), set()

    matched = resume_skills & jd_skills
    missing = jd_skills - resume_skills
    score = len(matched) / len(jd_skills)
    return score, matched, missing


def text_similarity_score(resume_text, jd_text):
    """Return cosine similarity (0-1) between resume and JD text via TF-IDF."""
    if not resume_text.strip() or not jd_text.strip():
        return 0.0

    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        tfidf_matrix = vectorizer.fit_transform([resume_text, jd_text])
    except ValueError:
        # Happens if vocabulary is empty after stop-word removal
        return 0.0

    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])
    return float(similarity[0][0])


def match_candidate(resume, job_description):
    """
    Compare a parsed resume against a parsed job description.

    Args:
        resume: ParsedDocument for the candidate's resume.
        job_description: ParsedDocument for the job posting.

    Returns:
        dict with overall_score (0-100), skill_score, text_score,
        matched_skills, missing_skills.
    """
    skill_score, matched, missing = skill_overlap_score(
        resume.skills, job_description.skills
    )
    text_score = text_similarity_score(resume.raw_text, job_description.raw_text)

    overall = (skill_score * SKILL_WEIGHT) + (text_score * TEXT_SIMILARITY_WEIGHT)
    overall_percent = round(overall * 100, 1)

    return {
        "overall_score": overall_percent,
        "skill_score": round(skill_score * 100, 1),
        "text_score": round(text_score * 100, 1),
        "matched_skills": sorted(matched),
        "missing_skills": sorted(missing),
    }


def rank_candidates(resumes, job_description):
    """
    Score and rank a list of (candidate_id, ParsedDocument) tuples against
    a job description. Returns results sorted by overall_score descending.
    """
    results = []
    for candidate_id, resume in resumes:
        result = match_candidate(resume, job_description)
        result["candidate_id"] = candidate_id
        result["name"] = resume.name
        result["email"] = resume.email
        result["phone"] = resume.phone
        result["experience_years"] = resume.experience_years
        result["education"] = resume.education
        result["certifications"] = resume.certifications
        result["links"] = resume.links
        results.append(result)

    results.sort(key=lambda r: r["overall_score"], reverse=True)
    return results
