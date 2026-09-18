"""
parser.py
---------
Extracts structured information from resumes (PDF, DOCX, TXT) and job
descriptions (plain text).

This module is intentionally kept independent of Flask, the database, and
the matching engine so it can be unit tested in isolation.
"""

import re
import os

import pdfplumber
import docx


# A curated skills dictionary. Extend this list to widen what the parser
# can recognise. Keeping it as a flat set makes lookups O(1) and keeps the
# matching logic simple and transparent (no black-box ML skill extraction).
SKILLS_DB = {
    "python", "java", "c++", "c", "c#", "javascript", "typescript", "sql",
    "html", "css", "react", "angular", "vue", "node.js", "django", "flask",
    "fastapi", "spring", "express", "pandas", "numpy", "scikit-learn",
    "tensorflow", "pytorch", "keras", "machine learning", "deep learning",
    "nlp", "computer vision", "data analysis", "data visualization",
    "matplotlib", "power bi", "tableau", "excel", "aws", "azure", "gcp",
    "docker", "kubernetes", "git", "github", "linux", "bash", "rest api",
    "graphql", "mongodb", "postgresql", "mysql", "sqlite", "redis",
    "microservices", "agile", "scrum", "ci/cd", "jenkins", "testing",
    "pytest", "unit testing", "selenium", "figma", "ui/ux", "project management",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
EXPERIENCE_RE = re.compile(r"(\d+)\+?\s*(?:years|yrs)\s*(?:of)?\s*experience", re.IGNORECASE)


class ParsedDocument:
    """Container for the fields extracted from a resume or job description."""

    def __init__(self, raw_text, name=None, email=None, phone=None,
                 skills=None, experience_years=0):
        self.raw_text = raw_text
        self.name = name
        self.email = email
        self.phone = phone
        self.skills = skills or set()
        self.experience_years = experience_years

    def to_dict(self):
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "skills": sorted(self.skills),
            "experience_years": self.experience_years,
        }


def extract_text_from_file(file_path):
    """Return raw text from a .pdf, .docx, or .txt file."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        text_chunks = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)
        return "\n".join(text_chunks)

    if ext == ".docx":
        document = docx.Document(file_path)
        return "\n".join(p.text for p in document.paragraphs)

    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    raise ValueError(f"Unsupported file type: {ext}")


def extract_email(text):
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def extract_phone(text):
    match = PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def extract_skills(text):
    """Match known skills against the text. Case-insensitive, whole-phrase."""
    text_lower = text.lower()
    found = set()
    for skill in SKILLS_DB:
        # Word-boundary-ish match so "java" doesn't match inside "javascript"
        pattern = r"(?<![a-zA-Z0-9+#])" + re.escape(skill) + r"(?![a-zA-Z0-9+#])"
        if re.search(pattern, text_lower):
            found.add(skill)
    return found


def extract_experience_years(text):
    """Look for explicit 'X years of experience' phrasing; default to 0."""
    match = EXPERIENCE_RE.search(text)
    if match:
        return int(match.group(1))
    return 0


def extract_name(text):
    """
    Heuristic: assume the candidate's name is the first non-empty line
    that doesn't look like an email, phone number, or section header.
    This is a best-effort guess, not a guarantee -- flagged in guidelines.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        if len(line.split()) <= 5 and len(line) < 60:
            return line
        break
    return "Unknown Candidate"


def parse_resume(file_path):
    """Parse a resume file into a ParsedDocument."""
    text = extract_text_from_file(file_path)
    return ParsedDocument(
        raw_text=text,
        name=extract_name(text),
        email=extract_email(text),
        phone=extract_phone(text),
        skills=extract_skills(text),
        experience_years=extract_experience_years(text),
    )


def parse_job_description(text):
    """Parse a pasted job description string into a ParsedDocument."""
    return ParsedDocument(
        raw_text=text,
        skills=extract_skills(text),
        experience_years=extract_experience_years(text),
    )
