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
# Every entry here is the CANONICAL name -- the form matched_skills /
# missing_skills / the admin's skill list will use. See SKILL_ALIASES below
# for the different ways people actually write each one.
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

# ---------------------------------------------------------------------------
# Synonyms / aliases
# ---------------------------------------------------------------------------
# Different resumes (and job descriptions) refer to the same skill in
# different ways -- "React.js" vs "React", "JS" vs "JavaScript", "AWS" vs
# "Amazon Web Services". Without this map, extract_skills() would treat
# those as two unrelated skills and neither side would get credit for the
# match, even though they mean the same thing.
#
# Maps: canonical skill name (must exist in SKILLS_DB) -> list of
# alternate spellings / abbreviations / phrasings to also recognise.
# Whichever form the text uses, the result is recorded under the
# canonical name, so matching, storage, and the skill-demand chart all
# stay consistent regardless of how a given resume happened to phrase it.
SKILL_ALIASES = {
    "javascript": ["js", "java script", "es6", "ecmascript"],
    "typescript": ["ts"],
    "python": ["py"],
    "c++": ["cpp", "c plus plus"],
    "c#": ["c sharp", "csharp", ".net", "dotnet"],
    "node.js": ["nodejs", "node js", "node"],
    "react": ["react.js", "reactjs"],
    "angular": ["angular.js", "angularjs"],
    "vue": ["vue.js", "vuejs"],
    "django": ["django rest framework", "drf"],
    "flask": ["flask-restful"],
    "aws": ["amazon web services"],
    "azure": ["microsoft azure"],
    "gcp": ["google cloud platform", "google cloud"],
    "sql": ["structured query language"],
    "postgresql": ["postgres", "psql"],
    "mysql": ["my sql"],
    "mongodb": ["mongo db", "mongo"],
    "ci/cd": ["ci-cd", "cicd", "continuous integration", "continuous deployment"],
    "machine learning": ["ml"],
    "deep learning": ["dl"],
    "nlp": ["natural language processing"],
    "computer vision": ["cv"],
    "ui/ux": ["ui-ux", "ux/ui", "user interface design", "user experience design"],
    "scikit-learn": ["sklearn", "scikit learn"],
    "tensorflow": ["tf"],
    "rest api": ["restful api", "rest apis", "restful apis", "rest"],
    "power bi": ["powerbi"],
    "git": ["version control"],
    "kubernetes": ["k8s"],
    "project management": ["pm"],
    "unit testing": ["unittest"],
    "data analysis": ["data analytics"],
    "data visualization": ["data viz"],
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}")
EXPERIENCE_RE = re.compile(r"(\d+)\+?\s*(?:years|yrs)\s*(?:of)?\s*experience", re.IGNORECASE)

LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?", re.IGNORECASE)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_-]+/?", re.IGNORECASE)
PORTFOLIO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9_-]+\.(?:dev|me|io|com|net|org)(?:/[A-Za-z0-9_\-./]*)?",
    re.IGNORECASE,
)

# Section headers recognised while splitting a resume into structured parts.
# Keys are the canonical section name; values are the different ways
# resumes tend to spell that heading. Matched case-insensitively, on their
# own line (optionally followed by a colon).
SECTION_HEADERS = {
    "summary": ["summary", "objective", "professional summary", "profile", "about"],
    "experience": ["experience", "work experience", "professional experience", "employment history"],
    "education": ["education", "academic background", "qualifications"],
    "skills": ["skills", "technical skills", "core competencies", "key skills"],
    "projects": ["projects", "personal projects", "academic projects"],
    "certifications": ["certifications", "certificates", "licenses & certifications", "licenses"],
}

DEGREE_KEYWORDS = [
    "bachelor", "b.sc", "bsc", "b.tech", "btech", "b.e.", "be ", "bs ", "b.s.",
    "master", "m.sc", "msc", "m.tech", "mtech", "m.e.", "me ", "ms ", "m.s.",
    "phd", "ph.d", "doctorate", "associate degree", "diploma", "fsc", "matric",
    "intermediate", "high school",
]

YEAR_RE = re.compile(r"(19|20)\d{2}")


class ParsedDocument:
    """Container for the fields extracted from a resume or job description."""

    def __init__(self, raw_text, name=None, email=None, phone=None,
                 skills=None, experience_years=0, sections=None,
                 education=None, certifications=None, links=None):
        self.raw_text = raw_text
        self.name = name
        self.email = email
        self.phone = phone
        self.skills = skills or set()
        self.experience_years = experience_years
        # Structured fields (best-effort -- resumes have no fixed format,
        # so these are heuristics, not guarantees; see docstrings below).
        self.sections = sections or {}
        self.education = education or []
        self.certifications = certifications or []
        self.links = links or {}

    def to_dict(self):
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "skills": sorted(self.skills),
            "experience_years": self.experience_years,
            "education": self.education,
            "certifications": self.certifications,
            "links": self.links,
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


def extract_links(text):
    """
    Best-effort extraction of a LinkedIn profile, GitHub profile, and a
    generic portfolio/personal-site URL, when present in the text.
    """
    links = {}

    linkedin = LINKEDIN_RE.search(text)
    if linkedin:
        links["linkedin"] = linkedin.group(0)

    github = GITHUB_RE.search(text)
    if github:
        links["github"] = github.group(0)

    # Portfolio: any domain-looking URL that isn't LinkedIn/GitHub, and
    # isn't just the tail end of an email address (e.g. "email.com" from
    # "name@email.com" should NOT be picked up as a portfolio link).
    for match in PORTFOLIO_RE.finditer(text):
        url = match.group(0)
        low = url.lower()
        if "linkedin.com" in low or "github.com" in low:
            continue
        preceding_char = text[match.start() - 1] if match.start() > 0 else ""
        if preceding_char == "@":
            continue
        links["portfolio"] = url
        break

    return links


def _build_skill_patterns(skills):
    """
    For each canonical skill, compile one regex that matches either the
    canonical name itself or any of its known aliases (see SKILL_ALIASES).
    Returns a list of (canonical_name, compiled_pattern) pairs.
    """
    patterns = []
    for skill in skills:
        variants = [skill] + SKILL_ALIASES.get(skill, [])
        # Longest first so e.g. "amazon web services" isn't shadowed by a
        # shorter alias also being present in the alternation.
        variants = sorted(set(variants), key=len, reverse=True)
        alt = "|".join(re.escape(v) for v in variants)
        # Word-boundary-ish match so "java" doesn't match inside "javascript",
        # and multi-word aliases like "amazon web services" still work.
        pattern = re.compile(r"(?<![a-zA-Z0-9+#.])(?:" + alt + r")(?![a-zA-Z0-9+#])")
        patterns.append((skill, pattern))
    return patterns


def extract_skills(text, skills=None):
    """
    Match known skills (and their common synonyms/aliases -- see
    SKILL_ALIASES) against the text. Case-insensitive, whole-phrase.
    Whatever form is found in the text, it's recorded under the
    canonical skill name, so "React.js" and "React" both register as
    "react" and will match each other during scoring.

    `skills` lets the caller pass a custom/updated skill set (e.g. one
    fetched from the database, which admins can edit). Falls back to the
    built-in SKILLS_DB when not provided, so this stays independently
    testable without needing a database.
    """
    if skills is None:
        skills = SKILLS_DB

    text_lower = text.lower()
    found = set()
    for canonical, pattern in _build_skill_patterns(skills):
        if pattern.search(text_lower):
            found.add(canonical)
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


def _looks_like_header(line, header_words):
    """
    True if `line` on its own looks like a section heading -- short,
    matches one of the known header phrasings, optionally in caps or
    followed by a colon (e.g. "EDUCATION", "Work Experience:").
    """
    cleaned = line.strip().strip(":").strip().lower()
    if not cleaned or len(cleaned) > 40:
        return False
    return cleaned in header_words


def extract_sections(text):
    """
    Split resume text into labelled sections (summary, experience,
    education, skills, projects, certifications) using a heuristic line
    scan for common section headings.

    This is intentionally simple (no ML/layout analysis) so it stays
    fast and dependency-free, but it means unconventional resume layouts
    (creative/graphic-heavy formats, headings buried mid-paragraph,
    non-English headings) won't be split correctly -- see limitations
    in the matching write-up.
    """
    all_header_words = {
        word: canonical
        for canonical, words in SECTION_HEADERS.items()
        for word in words
    }

    sections = {}
    current = "summary"
    buffer = []

    for line in text.splitlines():
        matched_canonical = None
        for word, canonical in all_header_words.items():
            if _looks_like_header(line, {word}):
                matched_canonical = canonical
                break

        if matched_canonical:
            if buffer:
                sections[current] = sections.get(current, "") + "\n".join(buffer).strip() + "\n"
            current = matched_canonical
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections[current] = sections.get(current, "") + "\n".join(buffer).strip()

    return {k: v.strip() for k, v in sections.items() if v.strip()}


def extract_education(sections):
    """
    Best-effort structured education extraction from the "education"
    section (falls back to scanning the whole document if no education
    heading was found). For each line that mentions a degree keyword,
    returns a dict with the raw line, a guessed degree keyword, and a
    graduation year if one appears on that line.

    This is a heuristic over free text, not a real NER model -- it will
    miss unconventional phrasing and can occasionally misfire (see
    limitations).
    """
    text = sections.get("education", "")
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        degree = next((kw for kw in DEGREE_KEYWORDS if kw in low), None)
        if degree:
            year_match = YEAR_RE.search(line)
            entries.append({
                "raw": line,
                "degree_keyword": degree.strip(". "),
                "year": year_match.group(0) if year_match else None,
            })
    return entries


def extract_certifications(sections):
    """
    Line items from the "certifications" section, if the resume has one.
    Filters out empty/very short lines and contact-info lines (LinkedIn/
    GitHub/email/phone) that can end up trailing into the last section
    when a resume has no closing heading after its certifications list.
    """
    text = sections.get("certifications", "")
    items = []
    for line in text.splitlines():
        line = line.strip(" -•\t")
        if len(line) < 3:
            continue
        low = line.lower()
        if "linkedin.com" in low or "github.com" in low:
            continue
        if EMAIL_RE.search(line) or PHONE_RE.search(line):
            continue
        items.append(line)
    return items


def parse_resume(file_path, skills=None):
    """Parse a resume file into a ParsedDocument."""
    text = extract_text_from_file(file_path)
    sections = extract_sections(text)
    return ParsedDocument(
        raw_text=text,
        name=extract_name(text),
        email=extract_email(text),
        phone=extract_phone(text),
        skills=extract_skills(text, skills=skills),
        experience_years=extract_experience_years(text),
        sections=sections,
        education=extract_education(sections),
        certifications=extract_certifications(sections),
        links=extract_links(text),
    )


def parse_job_description(text, skills=None):
    """Parse a pasted job description string into a ParsedDocument."""
    return ParsedDocument(
        raw_text=text,
        skills=extract_skills(text, skills=skills),
        experience_years=extract_experience_years(text),
    )
