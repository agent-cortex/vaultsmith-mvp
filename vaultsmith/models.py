"""Data models used by extraction and writing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set


@dataclass(frozen=True)
class TaskItem:
    text: str
    completed: bool = False


@dataclass
class ExtractionResult:
    projects: Set[str] = field(default_factory=set)
    people: Set[str] = field(default_factory=set)
    concepts: Set[str] = field(default_factory=set)
    decisions: List[str] = field(default_factory=list)
    tasks: List[TaskItem] = field(default_factory=list)
    summary_bullets: List[str] = field(default_factory=list)


@dataclass
class IngestResult:
    run_id: str
    inbox_note_path: str
    projects: List[str]
    people: List[str]
    concepts: List[str]
    decisions: List[str]
    tasks: List[TaskItem]
