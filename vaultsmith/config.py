"""Configuration and naming helpers for VaultSmith."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re

INBOX_DIR = "00 Inbox"
PROJECTS_DIR = "10 Projects"
PEOPLE_DIR = "20 People"
CONCEPTS_DIR = "30 Concepts"
DECISIONS_DIR = "40 Decisions"
REVIEWS_DIR = "90 Reviews"
MEMORY_DIR = "05 Memory"
SYSTEM_DIR = "99 System"

CATEGORY_DIRS = {
    "projects": PROJECTS_DIR,
    "people": PEOPLE_DIR,
    "concepts": CONCEPTS_DIR,
    "decisions": DECISIONS_DIR,
}

VAULT_REQUIRED_DIRS = [
    INBOX_DIR,
    MEMORY_DIR,
    PROJECTS_DIR,
    PEOPLE_DIR,
    CONCEPTS_DIR,
    DECISIONS_DIR,
    REVIEWS_DIR,
    SYSTEM_DIR,
]
MAX_NOTE_BASENAME_LEN = 120


def ensure_vault_dirs(vault_path: Path) -> None:
    for folder in VAULT_REQUIRED_DIRS:
        (vault_path / folder).mkdir(parents=True, exist_ok=True)


def normalize_entity_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    return cleaned


def safe_note_filename(name: str) -> str:
    """Convert text to a filesystem-safe markdown filename."""
    raw = normalize_entity_name(name)
    cleaned = re.sub(r"[\\/:*?\"<>|#\[\]]+", "", raw)
    cleaned = cleaned.replace("..", ".")
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "Untitled"

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    base = cleaned[:MAX_NOTE_BASENAME_LEN].rstrip(" .")
    if not base:
        base = "Untitled"

    return f"{base}--{digest}.md"


def wikilink(name: str) -> str:
    return f"[[{normalize_entity_name(name)}]]"
