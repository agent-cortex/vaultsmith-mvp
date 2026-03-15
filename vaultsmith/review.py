"""Weekly review generation for VaultSmith."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Dict, List, Sequence, Set, Tuple

from .config import CONCEPTS_DIR, DECISIONS_DIR, INBOX_DIR, PEOPLE_DIR, PROJECTS_DIR, REVIEWS_DIR, ensure_vault_dirs

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(.+?)\s*$")
CHECKBOX_LINE_RE = re.compile(r"^(\s*[-*]\s*\[)( |x|X)(\]\s*)(.+?)\s*$")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
HASH_SUFFIX_RE = re.compile(r"--[0-9a-f]{8}$")

TASK_RUN_CYCLE = "Run regular VaultSmith cycle on dedicated vault."
TASK_CONFIRM_INGEST = "Confirm ingest output appears in 00 Inbox."
TASK_CONFIRM_LINKER = "Confirm linker annotates auto links."
TASK_CONFIRM_REVIEW = "Confirm weekly review is generated."

STOPWORDS = {
    "about", "after", "again", "also", "and", "because", "been", "before", "between", "could",
    "from", "have", "into", "just", "more", "note", "notes", "over", "project", "review", "that",
    "their", "there", "these", "they", "this", "those", "update", "using", "with", "weekly", "what",
    "where", "while", "will", "would", "your",
}


@dataclass
class ReviewResult:
    review_note_path: str
    open_loops_count: int
    stale_projects_count: int


class ReviewError(RuntimeError):
    """Friendly exception raised for expected review failures."""


def _path_wikilink(path: Path, vault_root: Path) -> str:
    rel = path.relative_to(vault_root).with_suffix("")
    return f"[[{rel.as_posix()}]]"


def _iter_markdown_files(folder: Path) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".md"]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _note_display_name(note_path: Path) -> str:
    stem = HASH_SUFFIX_RE.sub("", note_path.stem)
    return stem.replace("_", " ").strip() or note_path.stem


def _tokenize_words(text: str) -> List[str]:
    words: List[str] = []
    for token in WORD_RE.findall(text.lower()):
        if len(token) < 4:
            continue
        if token in STOPWORDS:
            continue
        words.append(token)
    return words


def _meaningful_snippet(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("```"):
            continue
        if stripped.startswith("<!--"):
            continue
        snippet = stripped
        if len(snippet) > 140:
            snippet = snippet[:137].rstrip() + "..."
        return snippet
    return fallback


def _extract_open_loops(notes: Sequence[Path], vault_path: Path) -> List[Tuple[str, str, float]]:
    loops: List[Tuple[str, str, float]] = []
    seen: Set[Tuple[str, str]] = set()

    for note in notes:
        text = _read_text(note)
        in_fence = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            match = CHECKBOX_RE.match(line)
            if not match:
                continue
            completed = match.group(1).lower() == "x"
            if completed:
                continue
            task_text = match.group(2).strip()
            if not task_text:
                continue
            source = _path_wikilink(note, vault_path)
            key = (task_text.lower(), source)
            if key in seen:
                continue
            seen.add(key)
            loops.append((task_text, source, note.stat().st_mtime))

    loops.sort(key=lambda item: item[2], reverse=True)
    return loops


def _build_top_themes(project_notes: Sequence[Path], concept_notes: Sequence[Path], vault_path: Path) -> List[Tuple[str, int, List[str]]]:
    theme_counts: Counter[str] = Counter()
    theme_sources: Dict[str, Set[str]] = defaultdict(set)

    for note in list(project_notes) + list(concept_notes):
        source_link = _path_wikilink(note, vault_path)
        display_name = _note_display_name(note)
        title_words = _tokenize_words(display_name)
        for word in title_words:
            theme_counts[word] += 2
            theme_sources[word].add(source_link)

        body = _read_text(note)
        body_words = _tokenize_words(body)
        for word in body_words[:300]:
            theme_counts[word] += 1
            theme_sources[word].add(source_link)

    ranked: List[Tuple[str, int, List[str]]] = []
    for theme, count in theme_counts.most_common(8):
        links = sorted(theme_sources[theme])[:4]
        ranked.append((theme, count, links))
    return ranked


def _mark_verified_tasks_in_text(text: str, completion_map: Dict[str, bool]) -> Tuple[str, bool]:
    lines = text.splitlines()
    out: List[str] = []
    changed = False
    in_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue

        if in_fence:
            out.append(line)
            continue

        match = CHECKBOX_LINE_RE.match(line)
        if not match:
            out.append(line)
            continue

        prefix, mark, suffix, task_text = match.groups()
        should_complete = completion_map.get(task_text.strip(), False)
        if should_complete and mark.lower() != "x":
            out.append(f"{prefix}x{suffix}{task_text}")
            changed = True
        else:
            out.append(line)

    rebuilt = "\n".join(out)
    if text.endswith("\n"):
        rebuilt += "\n"
    return rebuilt, changed


def _apply_verified_task_closures(notes: Sequence[Path], completion_map: Dict[str, bool]) -> int:
    changed_files = 0
    for note in notes:
        original = _read_text(note)
        updated, changed = _mark_verified_tasks_in_text(original, completion_map)
        if not changed:
            continue
        note.write_text(updated, encoding="utf-8")
        changed_files += 1
    return changed_files


def generate_weekly_review(vault_path: Path, close_verified: bool = False) -> ReviewResult:
    try:
        ensure_vault_dirs(vault_path)
    except PermissionError as exc:
        raise ReviewError(f"Permission denied while writing to vault: {vault_path}") from exc

    if not vault_path.exists() or not vault_path.is_dir():
        raise ReviewError(f"Vault path not found or inaccessible: {vault_path}")

    projects_dir = vault_path / PROJECTS_DIR
    people_dir = vault_path / PEOPLE_DIR
    concepts_dir = vault_path / CONCEPTS_DIR
    decisions_dir = vault_path / DECISIONS_DIR
    inbox_dir = vault_path / INBOX_DIR
    reviews_dir = vault_path / REVIEWS_DIR

    project_notes = _iter_markdown_files(projects_dir)
    people_notes = _iter_markdown_files(people_dir)
    concept_notes = _iter_markdown_files(concepts_dir)
    decision_notes = _iter_markdown_files(decisions_dir)
    inbox_notes = _iter_markdown_files(inbox_dir)
    existing_review_notes = _iter_markdown_files(reviews_dir)

    all_context_notes = list(project_notes) + list(people_notes) + list(concept_notes) + list(decision_notes) + list(inbox_notes)

    if close_verified:
        latest_inbox = inbox_notes[0] if inbox_notes else None
        latest_inbox_has_auto_links = False
        if latest_inbox is not None:
            latest_inbox_has_auto_links = "## Auto Links" in _read_text(latest_inbox)

        completion_map = {
            TASK_RUN_CYCLE: latest_inbox is not None,
            TASK_CONFIRM_INGEST: latest_inbox is not None,
            TASK_CONFIRM_LINKER: latest_inbox_has_auto_links,
            TASK_CONFIRM_REVIEW: True,
        }
        _apply_verified_task_closures(list(all_context_notes) + list(existing_review_notes), completion_map)

    themes = _build_top_themes(project_notes, concept_notes, vault_path)
    open_loops = _extract_open_loops(all_context_notes, vault_path)

    recent_decisions: List[Tuple[str, str]] = []
    for note in decision_notes[:5]:
        text = _read_text(note)
        link = _path_wikilink(note, vault_path)
        fallback = f"Decision note: {_note_display_name(note)}"
        recent_decisions.append((link, _meaningful_snippet(text, fallback)))

    now = datetime.now()
    stale_cutoff = now - timedelta(days=14)
    stale_projects: List[Tuple[Path, int]] = []
    for note in project_notes:
        modified = datetime.fromtimestamp(note.stat().st_mtime)
        if modified < stale_cutoff:
            age_days = (now - modified).days
            stale_projects.append((note, age_days))
    stale_projects.sort(key=lambda item: item[1], reverse=True)

    next_actions: List[str] = []
    for task_text, source, _ in open_loops:
        next_actions.append(f"Complete: {task_text} ({source})")
        if len(next_actions) >= 3:
            break

    if len(next_actions) < 3:
        for note in project_notes[:8]:
            link = _path_wikilink(note, vault_path)
            action = f"Review status and unblock {link}"
            if action not in next_actions:
                next_actions.append(action)
            if len(next_actions) >= 3:
                break

    if len(next_actions) < 3:
        for link, _ in recent_decisions:
            action = f"Capture follow-up for {link}"
            if action not in next_actions:
                next_actions.append(action)
            if len(next_actions) >= 3:
                break

    iso = now.isocalendar()
    filename = f"weekly-review-{iso.year}-W{iso.week:02d}.md"
    output_path = reviews_dir / filename

    lines: List[str] = []
    lines.append(f"# Weekly Review {iso.year}-W{iso.week:02d}")
    lines.append("")
    lines.append(f"Generated: {now.isoformat(timespec='seconds')}")
    lines.append("")

    lines.append("## Top Themes")
    if themes:
        for theme, count, links in themes:
            refs = f" — {', '.join(links)}" if links else ""
            lines.append(f"- {theme} ({count}){refs}")
    else:
        lines.append("- No dominant themes detected yet.")
    lines.append("")

    lines.append("## Open Loops")
    if open_loops:
        for task_text, source, _ in open_loops[:20]:
            lines.append(f"- [ ] {task_text} — from {source}")
    else:
        lines.append("- No open checkboxes found across scanned notes.")
    lines.append("")

    lines.append("## Recent Decisions")
    if recent_decisions:
        for link, snippet in recent_decisions:
            lines.append(f"- {link} — {snippet}")
    else:
        lines.append("- No decision notes found.")
    lines.append("")

    lines.append("## Suggested Next 3 Actions")
    if next_actions:
        for idx, action in enumerate(next_actions[:3], start=1):
            lines.append(f"{idx}. {action}")
    else:
        lines.append("1. Create a project note and capture at least one next action.")
        lines.append("2. Add decisions as they are made to build review context.")
        lines.append("3. Re-run weekly review after new activity.")
    lines.append("")

    lines.append("## Stale Projects")
    if stale_projects:
        for note, age_days in stale_projects:
            lines.append(f"- {_path_wikilink(note, vault_path)} — no updates for {age_days} days")
    else:
        lines.append("- No stale projects older than 14 days.")
    lines.append("")

    try:
        output_path.write_text("\n".join(lines), encoding="utf-8")
    except PermissionError as exc:
        raise ReviewError(f"Permission denied while writing review note: {output_path}") from exc

    return ReviewResult(
        review_note_path=str(output_path),
        open_loops_count=len(open_loops),
        stale_projects_count=len(stale_projects),
    )
