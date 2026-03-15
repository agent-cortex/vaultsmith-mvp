"""Obsidian markdown writing helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .config import CATEGORY_DIRS, MEMORY_DIR, ensure_vault_dirs, normalize_entity_name, safe_note_filename, wikilink
from .models import ExtractionResult, MemoryCandidate, TaskItem


def _path_wikilink(path: Path, vault_root: Path) -> str:
    rel = path.relative_to(vault_root).with_suffix("")
    return f"[[{rel.as_posix()}]]"


def _unique_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        normalized = normalize_entity_name(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _unique_tasks(tasks: Iterable[TaskItem]) -> List[TaskItem]:
    seen = set()
    out: List[TaskItem] = []
    for task in tasks:
        normalized_text = normalize_entity_name(task.text)
        if not normalized_text:
            continue
        key = (normalized_text, task.completed)
        if key in seen:
            continue
        seen.add(key)
        out.append(TaskItem(text=normalized_text, completed=task.completed))
    return out


def _unique_memory_candidates(candidates: Iterable[MemoryCandidate]) -> List[MemoryCandidate]:
    seen = set()
    out: List[MemoryCandidate] = []
    for candidate in candidates:
        category = normalize_entity_name(candidate.category).lower()
        text = normalize_entity_name(candidate.text)
        if not category or not text:
            continue
        key = (category, text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(MemoryCandidate(category=category, text=text))
    return out


def _append_section_if_needed(note_path: Path, title: str, run_id: str, section: str) -> bool:
    marker = f"<!-- run_id:{run_id} -->"
    existing = ""
    if note_path.exists():
        existing = note_path.read_text(encoding="utf-8")
        if marker in existing:
            return False

    if existing:
        content = existing.rstrip() + "\n\n" + section.rstrip() + "\n"
    else:
        header = f"# {title}\n\n"
        content = header + section.rstrip() + "\n"

    note_path.write_text(content, encoding="utf-8")
    return True


def write_inbox_note(vault_path: Path, source_text: str, extraction: ExtractionResult, run_id: str, now: datetime) -> Path:
    ensure_vault_dirs(vault_path)
    stamp = now.strftime("%Y%m%d-%H%M%S-%f")
    run_token = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})[:24] or "run"
    inbox_name = f"ingest-{stamp}-{run_token}.md"
    inbox_path = vault_path / "00 Inbox" / inbox_name

    projects = _unique_preserve_order(sorted(extraction.projects))
    people = _unique_preserve_order(sorted(extraction.people))
    concepts = _unique_preserve_order(sorted(extraction.concepts))
    decisions = _unique_preserve_order(extraction.decisions)
    tasks = _unique_tasks(extraction.tasks)
    memory_candidates = _unique_memory_candidates(extraction.memory_candidates)

    lines: List[str] = []
    lines.append(f"# Inbox Capture {stamp}")
    lines.append("")
    lines.append(f"- Run ID: `{run_id}`")
    lines.append(f"- Captured: {now.isoformat(timespec='seconds')}")
    lines.append("")

    lines.append("## Summary")
    for bullet in extraction.summary_bullets:
        lines.append(f"- {bullet}")
    if not extraction.summary_bullets:
        lines.append("- (No meaningful lines found)")
    lines.append("")

    lines.append("## Extracted Entities")
    lines.append(f"- Projects: {', '.join(wikilink(p) for p in projects) if projects else '(none)'}")
    lines.append(f"- People: {', '.join(wikilink(p) for p in people) if people else '(none)'}")
    lines.append(f"- Concepts: {', '.join(wikilink(c) for c in concepts) if concepts else '(none)'}")
    lines.append(f"- Decisions: {', '.join(wikilink(d) for d in decisions) if decisions else '(none)'}")
    lines.append("")

    lines.append("## Memory Candidates")
    if memory_candidates:
        for candidate in memory_candidates:
            lines.append(f"- [{candidate.category}] {candidate.text}")
    else:
        lines.append("- (none)")
    lines.append("")

    if tasks:
        lines.append("## Tasks")
        for task in tasks:
            checkbox = "x" if task.completed else " "
            lines.append(f"- [{checkbox}] {task.text}")
        lines.append("")

    lines.append("## Raw Source")
    lines.append("```")
    lines.append(source_text.rstrip())
    lines.append("```")
    lines.append("")

    inbox_path.write_text("\n".join(lines), encoding="utf-8")
    return inbox_path


def write_entity_notes(vault_path: Path, extraction: ExtractionResult, run_id: str, inbox_note_path: Path, now: datetime) -> None:
    ensure_vault_dirs(vault_path)

    projects = _unique_preserve_order(sorted(extraction.projects))
    people = _unique_preserve_order(sorted(extraction.people))
    concepts = _unique_preserve_order(sorted(extraction.concepts))
    decisions = _unique_preserve_order(extraction.decisions)
    tasks = _unique_tasks(extraction.tasks)

    all_entities = {
        "projects": projects,
        "people": people,
        "concepts": concepts,
        "decisions": decisions,
    }

    source_link = _path_wikilink(inbox_note_path, vault_path)
    when_label = now.strftime("%Y-%m-%d %H:%M:%S")

    for category, names in all_entities.items():
        category_dir = vault_path / CATEGORY_DIRS[category]
        for name in names:
            note_path = category_dir / safe_note_filename(name)
            related: List[str] = []
            for other_cat, other_names in all_entities.items():
                if other_cat == category:
                    related.extend([n for n in other_names if n != name])
                else:
                    related.extend(other_names)

            related_links = ", ".join(wikilink(item) for item in _unique_preserve_order(related))
            section_lines = [
                f"## Update {when_label}",
                f"<!-- run_id:{run_id} -->",
                f"- Source: {source_link}",
            ]
            if related_links:
                section_lines.append(f"- Related: {related_links}")

            if category == "decisions":
                section_lines.append(f"- Decision: {name}")
                if tasks:
                    section_lines.append("- Follow-up tasks:")
                    for task in tasks:
                        checkbox = "x" if task.completed else " "
                        section_lines.append(f"  - [{checkbox}] {task.text}")

            section = "\n".join(section_lines)
            _append_section_if_needed(note_path, title=name, run_id=run_id, section=section)


def write_memory_notes(vault_path: Path, extraction: ExtractionResult, run_id: str, inbox_note_path: Path, now: datetime) -> None:
    ensure_vault_dirs(vault_path)
    candidates = _unique_memory_candidates(extraction.memory_candidates)
    if not candidates:
        return

    memory_note_path = vault_path / MEMORY_DIR / "Agent Memory Candidates.md"
    source_link = _path_wikilink(inbox_note_path, vault_path)
    when_label = now.strftime("%Y-%m-%d %H:%M:%S")

    grouped: dict[str, List[str]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.category, []).append(candidate.text)

    section_lines = [
        f"## Update {when_label}",
        f"<!-- run_id:{run_id} -->",
        f"- Source: {source_link}",
        "- Promote to persistent memory only if stable/repeated over time.",
        "",
    ]

    for category in sorted(grouped):
        section_lines.append(f"### {category.title()}")
        for text in grouped[category]:
            section_lines.append(f"- [ ] {text}")
        section_lines.append("")

    section = "\n".join(section_lines).rstrip()
    _append_section_if_needed(
        note_path=memory_note_path,
        title="Agent Memory Candidates",
        run_id=run_id,
        section=section,
    )
