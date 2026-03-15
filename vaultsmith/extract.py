"""Deterministic extraction heuristics for VaultSmith."""

from __future__ import annotations

from collections import Counter
import re
from typing import Iterable, List

from .models import ExtractionResult, MemoryCandidate, TaskItem

PROJECT_LINE_RE = re.compile(r"^\s*Project:\s*(.+?)\s*$", re.IGNORECASE)
HASHTAG_PROJECT_RE = re.compile(r"#project/([A-Za-z0-9][A-Za-z0-9_-]*)")
PEOPLE_RE = re.compile(r"(?<![\w.])@([A-Za-z][A-Za-z0-9_-]*)\b")
CONCEPT_LINE_RE = re.compile(r"^\s*Concept:\s*(.+?)\s*$", re.IGNORECASE)
DECISION_LINE_RE = re.compile(r"^\s*Decision:\s*(.+?)\s*$", re.IGNORECASE)
TODO_LINE_RE = re.compile(r"^\s*TODO:\s*(.+?)\s*$", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")
TITLECASE_WORD_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)*\b")

MEMORY_PREFIX_PATTERNS = [
    ("preference", re.compile(r"^\s*Preference:\s*(.+?)\s*$", re.IGNORECASE)),
    ("environment", re.compile(r"^\s*Environment:\s*(.+?)\s*$", re.IGNORECASE)),
    ("convention", re.compile(r"^\s*Convention:\s*(.+?)\s*$", re.IGNORECASE)),
    ("profile", re.compile(r"^\s*Profile:\s*(.+?)\s*$", re.IGNORECASE)),
    ("memory", re.compile(r"^\s*Memory:\s*(.+?)\s*$", re.IGNORECASE)),
]


STOP_TITLECASE_WORDS = {
    "Project",
    "Concept",
    "Decision",
    "TODO",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}


def _clean_list_field(raw: str) -> List[str]:
    parts = [p.strip() for p in re.split(r"[,;/]", raw) if p.strip()]
    return parts if parts else [raw.strip()]


def _meaningful_lines(lines: Iterable[str], limit: int = 5) -> List[str]:
    picked: List[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text in {"---", "***"}:
            continue
        picked.append(text)
        if len(picked) >= limit:
            break
    return picked


def _append_memory_candidate(result: ExtractionResult, category: str, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return

    key = (category.lower(), cleaned.lower())
    existing = {(item.category.lower(), item.text.lower()) for item in result.memory_candidates}
    if key in existing:
        return

    result.memory_candidates.append(MemoryCandidate(category=category.lower(), text=cleaned))


def extract_entities(text: str) -> ExtractionResult:
    result = ExtractionResult()
    lines = text.splitlines()

    titlecase_counter: Counter[str] = Counter()

    for line in lines:
        if not line.strip():
            continue

        match = PROJECT_LINE_RE.match(line)
        if match:
            for item in _clean_list_field(match.group(1)):
                result.projects.add(item)

        for proj in HASHTAG_PROJECT_RE.findall(line):
            result.projects.add(proj.replace("_", " ").replace("-", " ").strip())

        for person in PEOPLE_RE.findall(line):
            result.people.add(person)

        match = CONCEPT_LINE_RE.match(line)
        if match:
            for item in _clean_list_field(match.group(1)):
                result.concepts.add(item)

        match = DECISION_LINE_RE.match(line)
        if match:
            result.decisions.append(match.group(1).strip())

        for category, pattern in MEMORY_PREFIX_PATTERNS:
            match = pattern.match(line)
            if match:
                _append_memory_candidate(result, category, match.group(1))

        match = TODO_LINE_RE.match(line)
        if match:
            result.tasks.append(TaskItem(text=match.group(1).strip(), completed=False))

        match = CHECKBOX_RE.match(line)
        if match:
            result.tasks.append(TaskItem(text=match.group(2).strip(), completed=match.group(1).lower() == "x"))

        for token in TITLECASE_WORD_RE.findall(line):
            if token not in STOP_TITLECASE_WORDS and len(token) > 2:
                titlecase_counter[token] += 1

    for token, count in titlecase_counter.items():
        if count >= 2:
            result.concepts.add(token)

    result.summary_bullets = _meaningful_lines(lines, limit=5)

    return result
