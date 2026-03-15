"""Cross-note auto-linking for session continuity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Dict, List, Sequence, Set, Tuple
from uuid import uuid4

from .config import CONCEPTS_DIR, DECISIONS_DIR, INBOX_DIR, PEOPLE_DIR, PROJECTS_DIR, ensure_vault_dirs

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

STOPWORDS = {
    "about", "after", "again", "also", "and", "because", "been", "before", "between", "could",
    "from", "have", "into", "just", "more", "note", "notes", "over", "project", "review", "that",
    "their", "there", "these", "they", "this", "those", "update", "using", "with", "weekly", "what",
    "where", "while", "will", "would", "your", "generated", "source", "capture", "inbox",
}


@dataclass
class LinkResult:
    run_id: str
    processed_notes: int
    updated_notes: int
    suggested_links: int


class LinkError(RuntimeError):
    """Friendly exception raised for expected linker failures."""


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


def _path_wikilink(path: Path, vault_root: Path) -> str:
    rel = path.relative_to(vault_root).with_suffix("")
    return f"[[{rel.as_posix()}]]"


def _normalize_link_target(raw: str) -> Set[str]:
    base = raw.split("|", 1)[0].split("#", 1)[0].strip()
    if not base:
        return set()
    base_l = base.lower()
    out = {base_l}
    if "/" in base_l:
        out.add(base_l.rsplit("/", 1)[-1])
    return out


def _extract_existing_link_targets(text: str) -> Set[str]:
    targets: Set[str] = set()
    for match in WIKILINK_RE.findall(text):
        targets.update(_normalize_link_target(match))
    return targets


def _tokenize(text: str) -> Set[str]:
    out: Set[str] = set()
    for token in WORD_RE.findall(text.lower()):
        if len(token) < 4:
            continue
        if token in STOPWORDS:
            continue
        out.add(token)
    return out


def _note_terms(path: Path) -> Set[str]:
    stem = path.stem.replace("_", " ")
    text = _read_text(path)
    terms = _tokenize(stem)
    terms.update(_tokenize(text))
    return terms


def _append_section_if_needed(note_path: Path, run_id: str, section: str) -> bool:
    marker = f"<!-- linker_run_id:{run_id} -->"
    existing = ""
    if note_path.exists():
        existing = _read_text(note_path)
        if marker in existing:
            return False

    if existing:
        content = existing.rstrip() + "\n\n" + section.rstrip() + "\n"
    else:
        content = section.rstrip() + "\n"

    note_path.write_text(content, encoding="utf-8")
    return True


def auto_link_sessions(
    vault_path: Path,
    limit: int = 25,
    min_shared_terms: int = 2,
    run_id: str | None = None,
) -> LinkResult:
    try:
        ensure_vault_dirs(vault_path)
    except PermissionError as exc:
        raise LinkError(f"Permission denied while preparing vault: {vault_path}") from exc

    if not vault_path.exists() or not vault_path.is_dir():
        raise LinkError(f"Vault path not found or inaccessible: {vault_path}")

    if limit < 1:
        raise LinkError("--limit must be >= 1")
    if min_shared_terms < 1:
        raise LinkError("--min-shared-terms must be >= 1")

    effective_run_id = run_id or f"link-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"

    inbox_notes = [
        note for note in _iter_markdown_files(vault_path / INBOX_DIR)
        if note.name.startswith("ingest-")
    ]
    target_notes = inbox_notes[:limit]

    candidate_notes = (
        _iter_markdown_files(vault_path / PROJECTS_DIR)
        + _iter_markdown_files(vault_path / PEOPLE_DIR)
        + _iter_markdown_files(vault_path / CONCEPTS_DIR)
        + _iter_markdown_files(vault_path / DECISIONS_DIR)
        + inbox_notes
    )

    term_cache: Dict[Path, Set[str]] = {}

    def terms_for(path: Path) -> Set[str]:
        if path not in term_cache:
            term_cache[path] = _note_terms(path)
        return term_cache[path]

    now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_notes = 0
    suggested_links = 0

    for note in target_notes:
        note_text = _read_text(note)
        existing_targets = _extract_existing_link_targets(note_text)
        source_terms = terms_for(note)
        if not source_terms:
            continue

        scored: List[Tuple[int, float, Path, List[str], str]] = []

        for candidate in candidate_notes:
            if candidate == note:
                continue

            rel_target = candidate.relative_to(vault_path).with_suffix("").as_posix().lower()
            stem_target = candidate.stem.lower()
            if rel_target in existing_targets or stem_target in existing_targets:
                continue

            candidate_terms = terms_for(candidate)
            shared = sorted(source_terms.intersection(candidate_terms))
            if len(shared) < min_shared_terms:
                continue

            link = _path_wikilink(candidate, vault_path)
            scored.append((len(shared), candidate.stat().st_mtime, candidate, shared[:4], link))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        top = scored[:5]
        if not top:
            continue

        section_lines = [
            f"## Auto Links {now_label}",
            f"<!-- linker_run_id:{effective_run_id} -->",
            "- Suggested related notes based on shared terms:",
        ]

        for score, _, _, shared, link in top:
            section_lines.append(f"  - {link} — shared_terms={score} ({', '.join(shared)})")

        section = "\n".join(section_lines)
        if _append_section_if_needed(note, effective_run_id, section):
            updated_notes += 1
            suggested_links += len(top)

    return LinkResult(
        run_id=effective_run_id,
        processed_notes=len(target_notes),
        updated_notes=updated_notes,
        suggested_links=suggested_links,
    )
