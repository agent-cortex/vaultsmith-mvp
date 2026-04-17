"""LLM-knowledge-base style workflows for VaultSmith.

This module implements a deterministic, local-first version of the workflow:
raw sources -> compiled wiki -> lint/health -> Q&A artifacts -> continuous improvement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Sequence, Tuple

from .config import ensure_vault_dirs, normalize_entity_name, safe_note_filename

SOURCES_DIR = "01 Sources"
WIKI_DIR = "11 Wiki"
CONCEPTS2_DIR = "12 Concepts"
ENTITIES2_DIR = "13 Entities"
METHODS_DIR = "14 Methods"
QUESTIONS_DIR = "15 Open Questions"
OUTPUTS_DIR = "70 Outputs"
INDEX_DIR = "95 Index"
CONTROL_DIR = "99 Control"
REVIEWS_DIR = "90 Reviews"

KB_REQUIRED_DIRS = [
    SOURCES_DIR,
    WIKI_DIR,
    CONCEPTS2_DIR,
    ENTITIES2_DIR,
    METHODS_DIR,
    QUESTIONS_DIR,
    OUTPUTS_DIR,
    INDEX_DIR,
    CONTROL_DIR,
]

SOURCE_FIELDS = {
    "title",
    "source_type",
    "author",
    "origin",
    "source_date",
    "captured_at",
    "tags",
    "reliability_score",
    "domain",
    "source_id",
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = {
    "about", "after", "again", "also", "and", "because", "been", "before", "between", "could",
    "from", "have", "into", "just", "more", "note", "notes", "over", "project", "review", "that",
    "their", "there", "these", "they", "this", "those", "update", "using", "with", "weekly", "what",
    "where", "while", "will", "would", "your", "source", "sources", "query", "knowledge", "wiki",
    "compilation", "compiled", "question", "questions", "answer", "answers", "research", "paper",
}

LOW_SIGNAL_TERMS = {
    "use", "build", "content", "open", "how", "which", "ask", "core", "method", "design", "goals", "pilot",
}


@dataclass
class KbCompileResult:
    compiled_pages: int
    updated_indexes: int
    concepts_created: int
    entities_created: int
    methods_created: int
    questions_created: int
    sources_skipped: int


@dataclass
class KbLintResult:
    report_path: str
    broken_links: int
    orphan_pages: int
    missing_citations: int
    stale_pages: int
    duplicate_aliases: int


@dataclass
class KbQaResult:
    artifact_path: str
    evidence_count: int
    confidence: str


class KBError(RuntimeError):
    """Friendly exception for expected KB failures."""


def _slugify(value: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    if not cleaned:
        cleaned = "item"
    return cleaned[:max_len].strip("-") or "item"


def _tokenize(text: str) -> List[str]:
    out: List[str] = []
    for t in WORD_RE.findall(text.lower()):
        if len(t) < 4 or t in STOPWORDS:
            continue
        out.append(t)
    return out


def _titlecase_candidates(text: str, min_count: int = 2) -> List[str]:
    counts: Dict[str, int] = {}
    for token in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", text):
        if token.lower() in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = [k for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if v >= min_count]
    return ranked[:12]


def _is_low_signal_term(term: str) -> bool:
    cleaned = normalize_entity_name(term)
    if not cleaned:
        return True
    tokens = [t for t in re.split(r"\s+", cleaned) if t]
    if len(tokens) == 1 and tokens[0].lower() in LOW_SIGNAL_TERMS:
        return True
    if len(cleaned) < 4:
        return True
    if cleaned.lower().startswith(("open question", "todo", "unknown")):
        return True
    return False


def _dedupe_terms(terms: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = normalize_entity_name(term)
        if _is_low_signal_term(cleaned):
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _method_candidates(text: str) -> List[str]:
    methods: List[str] = []
    patterns = [
        r"\b(method|approach|workflow|pipeline|algorithm):\s*([^\n.]{4,120})",
        r"\b(use|using)\s+([A-Za-z][A-Za-z0-9\- ]{3,80})",
    ]
    for p in patterns:
        for m in re.finditer(p, text, flags=re.IGNORECASE):
            cand = normalize_entity_name(m.group(2))
            if cand and cand.lower() not in {x.lower() for x in methods}:
                methods.append(cand)
    methods = [m for m in _dedupe_terms(methods) if len(m.split()) >= 2]
    return methods[:8]


def _question_candidates(text: str) -> List[str]:
    found: List[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.endswith("?"):
            found.append(s)
            continue
        if s.lower().startswith(("open question:", "unknown:", "todo:")):
            found.append(s)
    # ensure uniqueness preserving order
    uniq: List[str] = []
    seen = set()
    for q in found:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(q)
    return uniq[:12]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _iter_md(folder: Path) -> List[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    files = [p for p in folder.rglob("*.md") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _ensure_kb_dirs(vault_path: Path) -> None:
    ensure_vault_dirs(vault_path)
    for folder in KB_REQUIRED_DIRS:
        (vault_path / folder).mkdir(parents=True, exist_ok=True)


def init_kb_layout(vault_path: Path) -> List[Path]:
    _ensure_kb_dirs(vault_path)
    created: List[Path] = []

    control_docs = {
        "KB-SCHEMA.md": """# KB Schema

## Canonical structure
- 01 Sources/ => immutable source captures with metadata
- 11 Wiki/ => compiled topic pages
- 12 Concepts/ => concept nodes with source evidence
- 13 Entities/ => people/org/product/entity nodes
- 14 Methods/ => workflows and methods
- 15 Open Questions/ => unresolved questions
- 70 Outputs/ => generated answer artifacts
- 95 Index/ => machine-friendly indexes and backlinks

## Naming rules
- Keep one canonical page per concept/entity/method.
- Prefer stable filenames and source IDs.
- Always include `## Sources` section on compiled pages.
""",
        "COMPILER-RULES.md": """# Compiler Rules

1. Never alter raw source files in 01 Sources.
2. Compiled wiki pages must include:
   - What it is
   - Why it matters
   - Key claims
   - Evidence / Sources
   - Open questions
3. Every claim should map to at least one source link.
4. Preserve prior context by appending incremental updates.
5. If confidence is low, emit explicit uncertainty notes.
""",
        "SOURCE-PRIORITY.md": """# Source Priority

Default reliability policy (editable):
- 0.9-1.0: primary papers, official docs, first-party repos
- 0.7-0.89: trusted articles, engineering blogs
- 0.5-0.69: social posts and summaries
- <0.5: unverified claims

When conflicts occur, higher reliability wins unless newer primary evidence exists.
""",
    }

    for filename, body in control_docs.items():
        p = vault_path / CONTROL_DIR / filename
        if not p.exists():
            p.write_text(body.strip() + "\n", encoding="utf-8")
            created.append(p)

    return created


def _append_op_log(vault_path: Path, op_type: str, title: str, details: Sequence[str]) -> Path:
    index_dir = vault_path / INDEX_DIR
    index_dir.mkdir(parents=True, exist_ok=True)
    log_path = index_dir / "log.md"
    now = datetime.now()

    if log_path.exists():
        existing = _read_text(log_path).rstrip()
    else:
        existing = "# KB Operation Log\n"

    lines = [f"## [{now.strftime('%Y-%m-%d %H:%M:%S')}] {op_type} | {title}"]
    lines.extend(f"- {item}" for item in details)
    lines.append("")

    log_path.write_text(existing + "\n\n" + "\n".join(lines), encoding="utf-8")
    return log_path


def _write_aliases_index(vault_path: Path, alias_map: Dict[str, List[str]]) -> Path:
    out = vault_path / INDEX_DIR / "aliases.md"
    lines = ["# Canonical Aliases", "", f"Updated: {datetime.now().isoformat(timespec='seconds')}", ""]
    for alias, paths in sorted(alias_map.items()):
        if len(paths) <= 1:
            continue
        lines.append(f"## {alias}")
        canonical = sorted(paths)[0]
        lines.append(f"- Canonical: [[{Path(canonical).with_suffix('').as_posix()}]]")
        for p in sorted(paths):
            if p == canonical:
                continue
            lines.append(f"- Alias: [[{Path(p).with_suffix('').as_posix()}]]")
        lines.append("")

    if len(lines) <= 4:
        lines.append("- No duplicate aliases detected.")

    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _write_contradictions(vault_path: Path, claim_entries: Sequence[Tuple[str, str, str]]) -> Path:
    out = vault_path / INDEX_DIR / "contradictions.md"
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for key, polarity, page_rel in claim_entries:
        bucket = grouped.setdefault(key, {"positive": [], "negative": []})
        bucket[polarity].append(page_rel)

    lines = ["# Contradiction Tracker", "", f"Updated: {datetime.now().isoformat(timespec='seconds')}", ""]
    found = 0
    for key, bucket in sorted(grouped.items()):
        if not bucket["positive"] or not bucket["negative"]:
            continue
        found += 1
        lines.append(f"## Claim: {key}")
        lines.append("- Positive evidence pages:")
        for rel in sorted(set(bucket["positive"])):
            lines.append(f"  - [[{Path(rel).with_suffix('').as_posix()}]]")
        lines.append("- Negative evidence pages:")
        for rel in sorted(set(bucket["negative"])):
            lines.append(f"  - [[{Path(rel).with_suffix('').as_posix()}]]")
        lines.append("")

    if found == 0:
        lines.append("- No contradictions detected by heuristic pass.")

    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _metadata_frontmatter(meta: Dict[str, object]) -> str:
    lines = ["---"]
    for key in [
        "title", "source_type", "author", "origin", "source_date", "captured_at", "tags", "reliability_score", "domain", "source_id"
    ]:
        value = meta.get(key, "")
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def ingest_source(
    vault_path: Path,
    input_path: Path,
    *,
    source_type: str,
    title: str,
    origin: str = "",
    author: str = "",
    source_date: str = "",
    tags: Sequence[str] | None = None,
    reliability_score: float = 0.6,
    domain: str = "general",
) -> Path:
    if not input_path.exists():
        raise KBError(f"Input source not found: {input_path}")

    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise KBError(f"Input source must be UTF-8 text: {input_path}") from exc

    _ensure_kb_dirs(vault_path)

    tags = [normalize_entity_name(t) for t in (tags or []) if normalize_entity_name(t)]
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    source_seed = f"{source_type}|{title}|{origin}|{stamp}"
    source_id = hashlib.sha1(source_seed.encode("utf-8")).hexdigest()[:10]

    folder = vault_path / SOURCES_DIR / _slugify(source_type, max_len=24)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y%m%d')}-{_slugify(title, max_len=72)}--{source_id}.md"
    path = folder / filename

    meta = {
        "title": title,
        "source_type": source_type,
        "author": author,
        "origin": origin,
        "source_date": source_date,
        "captured_at": now.isoformat(timespec="seconds"),
        "tags": list(tags),
        "reliability_score": reliability_score,
        "domain": domain,
        "source_id": source_id,
    }

    content = [
        _metadata_frontmatter(meta),
        "",
        "## Source Content",
        "",
        text.rstrip(),
        "",
    ]
    path.write_text("\n".join(content), encoding="utf-8")
    _append_op_log(
        vault_path,
        "ingest",
        title,
        [
            f"source_id={source_id}",
            f"source_type={source_type}",
            f"source_note=[[{path.relative_to(vault_path).with_suffix('').as_posix()}]]",
            f"reliability={reliability_score}",
        ],
    )
    return path


def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    head = text[4:end]
    body = text[end + 5 :]
    meta: Dict[str, str] = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, body


def _write_index_files(vault_path: Path, source_to_wiki: Dict[str, str], backlinks: Dict[str, List[str]]) -> int:
    index_dir = vault_path / INDEX_DIR
    index_dir.mkdir(parents=True, exist_ok=True)

    status_path = index_dir / "source-status.json"
    status_path.write_text(json.dumps(source_to_wiki, indent=2, sort_keys=True), encoding="utf-8")

    wiki_index_path = index_dir / "wiki-index.md"
    lines = ["# Wiki Index", "", f"Updated: {datetime.now().isoformat(timespec='seconds')}", ""]
    for sid, wpath in sorted(source_to_wiki.items()):
        rel = Path(wpath)
        lines.append(f"- `{sid}` -> [[{rel.with_suffix('').as_posix()}]]")
    wiki_index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    backlinks_path = index_dir / "backlinks.md"
    bl = ["# Backlinks", "", f"Updated: {datetime.now().isoformat(timespec='seconds')}", ""]
    for page, refs in sorted(backlinks.items()):
        bl.append(f"## [[{page}]]")
        if refs:
            for r in sorted(set(refs)):
                bl.append(f"- [[{r}]]")
        else:
            bl.append("- (none)")
        bl.append("")
    backlinks_path.write_text("\n".join(bl).rstrip() + "\n", encoding="utf-8")

    return 3


def compile_sources(
    vault_path: Path,
    limit: int = 200,
    compiled_sources: Dict[str, str] | None = None,
) -> KbCompileResult:
    _ensure_kb_dirs(vault_path)

    sources = _iter_md(vault_path / SOURCES_DIR)[:limit]
    if not sources:
        return KbCompileResult(0, 0, 0, 0, 0, 0, 0)

    known: Dict[str, str] = compiled_sources if compiled_sources is not None else {}

    # Compute content signatures; skip sources already compiled with same content
    sources_to_process: List[Path] = []
    sources_skipped = 0
    for src in sources:
        sig = hashlib.sha1(_read_text(src).encode()).hexdigest()[:12]
        key = str(src.resolve())
        if known.get(key) == sig:
            sources_skipped += 1
        else:
            sources_to_process.append(src)

    # If everything is known, skip compilation entirely
    if not sources_to_process:
        return KbCompileResult(0, 0, 0, 0, 0, 0, sources_skipped)

    source_to_wiki: Dict[str, str] = {}
    backlinks: Dict[str, List[str]] = {}

    concepts_created = 0
    entities_created = 0
    methods_created = 0
    questions_created = 0
    compiled_pages = 0

    touched_created: List[str] = []
    touched_updated: List[str] = []
    claim_entries: List[Tuple[str, str, str]] = []
    alias_map: Dict[str, List[str]] = {}

    def _record_alias(path: Path) -> None:
        alias = re.sub(r"--[0-9a-f]{8}$", "", path.stem).lower()
        alias_map.setdefault(alias, []).append(path.relative_to(vault_path).as_posix())

    def _claim_signature(claim: str) -> Tuple[str, str]:
        lower = f" {claim.lower()} "
        polarity = "negative" if any(tok in lower for tok in [" not ", " no ", " without ", " never ", " cannot ", " can't "]) else "positive"
        normalized = re.sub(r"\b(not|no|without|never|cannot|can't)\b", "", claim.lower())
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized[:120], polarity

    for src in sources_to_process:
        raw = _read_text(src)
        meta, body = _parse_frontmatter(raw)
        source_id = meta.get("source_id") or hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:10]
        title = meta.get("title") or src.stem

        bullets = [s.strip() for s in SENTENCE_RE.split(body) if len(s.strip()) > 30][:6]
        concepts = _dedupe_terms(_titlecase_candidates(body))[:5]
        entities = _dedupe_terms(_titlecase_candidates((meta.get("author", "") + "\n" + body), min_count=1))[:5]
        methods = _method_candidates(body)
        questions = _question_candidates(body)

        wiki_name = safe_note_filename(f"{title} {source_id}")
        wiki_path = vault_path / WIKI_DIR / wiki_name
        existed = wiki_path.exists()

        source_link = f"[[{src.relative_to(vault_path).with_suffix('').as_posix()}]]"
        lines = [
            f"# {normalize_entity_name(title)}",
            "",
            f"- Source ID: `{source_id}`",
            f"- Compiled At: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## What it is",
            f"- {bullets[0] if bullets else 'Compiled source page.'}",
            "",
            "## Why it matters",
            f"- {bullets[1] if len(bullets) > 1 else 'Potentially useful for this domain knowledge base.'}",
            "",
            "## Key claims",
        ]
        if bullets:
            for b in bullets:
                lines.append(f"- {b}")
                claim_key, polarity = _claim_signature(b)
                if claim_key:
                    claim_entries.append((claim_key, polarity, wiki_path.relative_to(vault_path).as_posix()))
        else:
            lines.append("- (No claims extracted)")

        lines.extend(["", "## Open questions"])
        if questions:
            for q in questions[:8]:
                lines.append(f"- {q}")
        else:
            lines.append("- What should be verified next?")

        lines.extend(["", "## Sources", f"- {source_link}", ""])
        wiki_path.write_text("\n".join(lines), encoding="utf-8")
        compiled_pages += 1
        _record_alias(wiki_path)
        if existed:
            touched_updated.append(wiki_path.relative_to(vault_path).as_posix())
        else:
            touched_created.append(wiki_path.relative_to(vault_path).as_posix())

        wiki_rel = wiki_path.relative_to(vault_path).with_suffix("").as_posix()
        source_to_wiki[source_id] = str(wiki_path.relative_to(vault_path))
        backlinks.setdefault(wiki_rel, []).append(src.relative_to(vault_path).with_suffix("").as_posix())

        wiki_link = f"[[{wiki_rel}]]"

        for concept in concepts:
            p = vault_path / CONCEPTS2_DIR / safe_note_filename(concept)
            if not p.exists():
                concepts_created += 1
                p.write_text(f"# {concept}\n\n## Sources\n- {wiki_link}\n", encoding="utf-8")
                touched_created.append(p.relative_to(vault_path).as_posix())
            _record_alias(p)
            backlinks.setdefault(p.relative_to(vault_path).with_suffix("").as_posix(), []).append(wiki_rel)

        for ent in entities:
            p = vault_path / ENTITIES2_DIR / safe_note_filename(ent)
            if not p.exists():
                entities_created += 1
                p.write_text(f"# {ent}\n\n## Sources\n- {wiki_link}\n", encoding="utf-8")
                touched_created.append(p.relative_to(vault_path).as_posix())
            _record_alias(p)
            backlinks.setdefault(p.relative_to(vault_path).with_suffix("").as_posix(), []).append(wiki_rel)

        for method in methods:
            p = vault_path / METHODS_DIR / safe_note_filename(method)
            if not p.exists():
                methods_created += 1
                p.write_text(f"# {method}\n\n## Sources\n- {wiki_link}\n", encoding="utf-8")
                touched_created.append(p.relative_to(vault_path).as_posix())
            _record_alias(p)
            backlinks.setdefault(p.relative_to(vault_path).with_suffix("").as_posix(), []).append(wiki_rel)

        for question in questions:
            qtitle = question[:80].rstrip("?")
            p = vault_path / QUESTIONS_DIR / safe_note_filename(qtitle)
            if not p.exists():
                questions_created += 1
                p.write_text(f"# {question}\n\n## Raised By\n- {wiki_link}\n", encoding="utf-8")
                touched_created.append(p.relative_to(vault_path).as_posix())
            _record_alias(p)
            backlinks.setdefault(p.relative_to(vault_path).with_suffix("").as_posix(), []).append(wiki_rel)

    auto_linked_nodes = _auto_link_low_degree_nodes(vault_path, max_nodes=300, min_shared_terms=1)
    wiki_wiki_links = _auto_link_wiki_to_wiki(vault_path, max_pairs=200, min_shared_terms=2)
    # Second pass to catch newly-linked nodes that can now be linked further
    auto_linked_nodes_2 = _auto_link_low_degree_nodes(vault_path, max_nodes=300, min_shared_terms=1)
    auto_linked_nodes_total = auto_linked_nodes + auto_linked_nodes_2

    updated_indexes = _write_index_files(vault_path, source_to_wiki, backlinks)
    aliases_path = _write_aliases_index(vault_path, alias_map)
    contradictions_path = _write_contradictions(vault_path, claim_entries)

    report_path = vault_path / INDEX_DIR / f"compile-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    report_lines = [
        "# Compile Update Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Sources processed: {len(sources)}",
        f"- Wiki pages compiled: {compiled_pages}",
        f"- Created pages: {len(touched_created)}",
        f"- Updated pages: {len(touched_updated)}",
        f"- Auto-linked low-degree nodes: {auto_linked_nodes_total} (2 passes: {auto_linked_nodes} + {auto_linked_nodes_2})",
        f"- Wiki-to-wiki auto-links: {wiki_wiki_links}",
        "",
        "## Created pages",
    ]
    if touched_created:
        report_lines.extend(f"- [[{Path(p).with_suffix('').as_posix()}]]" for p in sorted(set(touched_created))[:300])
    else:
        report_lines.append("- (none)")
    report_lines.extend(["", "## Updated pages"])
    if touched_updated:
        report_lines.extend(f"- [[{Path(p).with_suffix('').as_posix()}]]" for p in sorted(set(touched_updated))[:300])
    else:
        report_lines.append("- (none)")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    _append_op_log(
        vault_path,
        "compile",
        f"processed={len(sources)}",
        [
            f"compiled_pages={compiled_pages}",
            f"created_pages={len(set(touched_created))}",
            f"updated_pages={len(set(touched_updated))}",
            f"auto_linked_nodes={auto_linked_nodes_total}",
            f"wiki_wiki_links={wiki_wiki_links}",
            f"compile_report=[[{report_path.relative_to(vault_path).with_suffix('').as_posix()}]]",
            f"aliases=[[{aliases_path.relative_to(vault_path).with_suffix('').as_posix()}]]",
            f"contradictions=[[{contradictions_path.relative_to(vault_path).with_suffix('').as_posix()}]]",
        ],
    )

    return KbCompileResult(
        compiled_pages=compiled_pages,
        updated_indexes=updated_indexes,
        concepts_created=concepts_created,
        entities_created=entities_created,
        methods_created=methods_created,
        questions_created=questions_created,
        sources_skipped=sources_skipped,
    )


def _extract_wikilinks(text: str) -> List[str]:
    out: List[str] = []
    for match in WIKILINK_RE.findall(text):
        target = match.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            out.append(target)
    return out


def _ensure_section_link(path: Path, section_title: str, bullet_line: str) -> bool:
    text = _read_text(path)
    if bullet_line in text:
        return False

    if f"## {section_title}" in text:
        updated = text.rstrip() + "\n" + bullet_line + "\n"
    else:
        updated = text.rstrip() + f"\n\n## {section_title}\n{bullet_line}\n"
    path.write_text(updated, encoding="utf-8")
    return True


def _compute_kb_ref_counts(vault_path: Path, kb_pages: Sequence[Path]) -> Dict[str, int]:
    page_set = {
        p.relative_to(vault_path).with_suffix("").as_posix().lower(): p
        for p in kb_pages
    }
    ref_count: Dict[str, int] = {k: 0 for k in page_set}

    for page in kb_pages:
        txt = _read_text(page)
        for link in _extract_wikilinks(txt):
            cand = link.lower()
            if cand in page_set:
                ref_count[cand] += 1
                continue
            base = cand.rsplit("/", 1)[-1]
            matched = [k for k in page_set if k.endswith("/" + base) or k == base]
            if matched:
                ref_count[matched[0]] += 1

    return ref_count


def _auto_link_wiki_to_wiki(vault_path: Path, max_pairs: int = 200, min_shared_terms: int = 2) -> int:
    """
    Token-match wiki pages against each other and add bidirectional links.
    This gives wiki pages incoming links so lint_kb no longer counts them as orphans.

    Returns the number of new links created (bidirectional pairs).
    """
    wiki_pages = _iter_md(vault_path / WIKI_DIR)
    if len(wiki_pages) < 2:
        return 0

    # Build token cache for all wiki pages (first 3000 chars for speed)
    wiki_token_cache: Dict[Path, set[str]] = {}
    for w in wiki_pages:
        txt = _read_text(w)[:3000]
        wiki_token_cache[w] = set(_tokenize(txt))

    # Build existing link map so we skip already-linked pairs.
    # Normalize all targets to lowercase basename for consistent comparison,
    # mirroring how _compute_kb_ref_counts and lint_kb do basename fallback.
    existing_links: Set[Tuple[str, str]] = set()
    for w in wiki_pages:
        txt = _read_text(w)
        page_key = w.relative_to(vault_path).with_suffix("").as_posix().lower()
        for link in _extract_wikilinks(txt):
            link_lower = link.lower()
            # Store both full-path and basename forms so lookups always match
            existing_links.add((page_key, link_lower))
            base = link_lower.rsplit("/", 1)[-1]
            if base != link_lower:
                existing_links.add((page_key, base))

    linked = 0

    for i, page_a in enumerate(wiki_pages):
        terms_a = wiki_token_cache[page_a]
        if not terms_a:
            continue

        best_score = 0
        best_page: Path | None = None

        for page_b in wiki_pages[i + 1:]:
            terms_b = wiki_token_cache.get(page_b)
            if not terms_b:
                continue

            score = len(terms_a & terms_b)
            if score > best_score:
                best_score = score
                best_page = page_b

        if not best_page or best_score < min_shared_terms:
            continue

        key_a = page_a.relative_to(vault_path).with_suffix("").as_posix()
        key_b = best_page.relative_to(vault_path).with_suffix("").as_posix()
        key_a_lower = key_a.lower()
        key_b_lower = key_b.lower()
        key_a_base = key_a_lower.rsplit("/", 1)[-1]
        key_b_base = key_b_lower.rsplit("/", 1)[-1]

        # Skip if already linked in either direction (check both full-path and basename forms)
        if (
            (key_a_lower, key_b_lower) in existing_links
            or (key_b_lower, key_a_lower) in existing_links
            or (key_a_lower, key_b_base) in existing_links
            or (key_b_lower, key_a_base) in existing_links
        ):
            continue

        # Add A → B link
        changed_a = _ensure_section_link(page_a, "Auto Links", f"- [[{key_b}]]")
        # Add B → A link (bidirectional)
        changed_b = _ensure_section_link(best_page, "Auto Links", f"- [[{key_a}]]")

        if changed_a or changed_b:
            linked += 1
            existing_links.add((key_a.lower(), key_b.lower()))
            existing_links.add((key_b.lower(), key_a.lower()))

        if linked >= max_pairs:
            break

    return linked


def _auto_link_low_degree_nodes(vault_path: Path, max_nodes: int = 300, min_shared_terms: int = 1) -> int:
    wiki_pages = _iter_md(vault_path / WIKI_DIR)
    if not wiki_pages:
        return 0

    kb_pages: List[Path] = []
    for d in [WIKI_DIR, CONCEPTS2_DIR, ENTITIES2_DIR, METHODS_DIR, QUESTIONS_DIR, OUTPUTS_DIR]:
        kb_pages.extend(_iter_md(vault_path / d))

    ref_count = _compute_kb_ref_counts(vault_path, kb_pages)

    node_pages: List[Path] = []
    for d in [CONCEPTS2_DIR, ENTITIES2_DIR, METHODS_DIR, QUESTIONS_DIR]:
        node_pages.extend(_iter_md(vault_path / d))

    orphan_nodes = [
        p for p in node_pages
        if ref_count.get(p.relative_to(vault_path).with_suffix("").as_posix().lower(), 0) == 0
    ][:max_nodes]

    linked = 0
    wiki_token_cache: Dict[Path, set[str]] = {
        w: set(_tokenize(_read_text(w)[:4000]))
        for w in wiki_pages
    }

    for node in orphan_nodes:
        node_terms = set(_tokenize(re.sub(r"--[0-9a-f]{8}$", "", node.stem)))
        if not node_terms:
            continue

        best_page: Path | None = None
        best_score = 0
        for w in wiki_pages:
            score = len(node_terms & wiki_token_cache[w])
            if score > best_score:
                best_score = score
                best_page = w

        if not best_page or best_score < min_shared_terms:
            continue

        node_rel = node.relative_to(vault_path).with_suffix("").as_posix()
        wiki_rel = best_page.relative_to(vault_path).with_suffix("").as_posix()

        changed_node = _ensure_section_link(node, "Auto Links", f"- [[{wiki_rel}]]")
        changed_wiki = _ensure_section_link(best_page, "Related Nodes (auto)", f"- [[{node_rel}]]")
        if changed_node or changed_wiki:
            linked += 1

    return linked


def lint_kb(vault_path: Path) -> KbLintResult:
    _ensure_kb_dirs(vault_path)
    kb_pages = []
    for d in [WIKI_DIR, CONCEPTS2_DIR, ENTITIES2_DIR, METHODS_DIR, QUESTIONS_DIR, OUTPUTS_DIR]:
        kb_pages.extend(_iter_md(vault_path / d))

    source_pages = _iter_md(vault_path / SOURCES_DIR)

    # KB pages are scored for orphan/citation metrics.
    kb_page_set = {
        p.relative_to(vault_path).with_suffix("").as_posix().lower(): p
        for p in kb_pages
    }
    # Valid link targets include both compiled KB pages and source notes.
    valid_target_set = {
        p.relative_to(vault_path).with_suffix("").as_posix().lower(): p
        for p in [*kb_pages, *source_pages]
    }

    ref_count: Dict[str, int] = {k: 0 for k in kb_page_set}
    broken_links = 0
    missing_citations = 0
    alias_map: Dict[str, List[str]] = {}

    citation_required_dirs = {WIKI_DIR, CONCEPTS2_DIR, ENTITIES2_DIR, METHODS_DIR}

    for page in kb_pages:
        txt = _read_text(page)
        if page.parent.name in citation_required_dirs and "## Sources" not in txt:
            missing_citations += 1

        alias = re.sub(r"--[0-9a-f]{8}$", "", page.stem).lower()
        alias_map.setdefault(alias, []).append(page.relative_to(vault_path).as_posix())

        for link in _extract_wikilinks(txt):
            cand = link.lower()
            if cand in valid_target_set:
                if cand in ref_count:
                    ref_count[cand] += 1
                continue
            # fallback on basename lookup
            base = cand.rsplit("/", 1)[-1]
            matched = [k for k in valid_target_set if k.endswith("/" + base) or k == base]
            if matched:
                if matched[0] in ref_count:
                    ref_count[matched[0]] += 1
            else:
                broken_links += 1

    orphan_pages = sum(1 for k, v in ref_count.items() if v == 0 and "/70 outputs/" not in k)

    # stale if source newer than wiki based on source-status map
    stale_pages = 0
    source_status_path = vault_path / INDEX_DIR / "source-status.json"
    if source_status_path.exists():
        try:
            mapping = json.loads(_read_text(source_status_path))
        except json.JSONDecodeError:
            mapping = {}
        for _, wiki_rel in mapping.items():
            wiki_path = vault_path / wiki_rel
            if not wiki_path.exists():
                stale_pages += 1
                continue
            wiki_mtime = wiki_path.stat().st_mtime
            # recover source id from wiki file content
            wiki_text = _read_text(wiki_path)
            src_match = re.search(r"\[\[(01 Sources/[^\]]+)\]\]", wiki_text)
            if not src_match:
                continue
            src_path = vault_path / (src_match.group(1) + ".md")
            if src_path.exists() and src_path.stat().st_mtime > wiki_mtime:
                stale_pages += 1

    duplicate_aliases = sum(1 for _, paths in alias_map.items() if len(paths) > 1)

    now = datetime.now()
    report = vault_path / REVIEWS_DIR / f"knowledge-health-{now.strftime('%Y-%m-%d')}.md"
    lines = [
        f"# Knowledge Health {now.strftime('%Y-%m-%d')}",
        "",
        f"Generated: {now.isoformat(timespec='seconds')}",
        "",
        "## Summary",
        f"- Broken links: {broken_links}",
        f"- Orphan pages: {orphan_pages}",
        f"- Missing citations: {missing_citations}",
        f"- Stale pages: {stale_pages}",
        f"- Duplicate aliases: {duplicate_aliases}",
        "",
        "## Suggested fixes",
        "- Repair broken wikilinks and regenerate index.",
        "- Add sources section to pages missing citations.",
        "- Recompile stale pages where sources changed.",
        "- Merge duplicate canonical aliases.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _write_aliases_index(vault_path, alias_map)
    _append_op_log(
        vault_path,
        "lint",
        "knowledge-health",
        [
            f"report=[[{report.relative_to(vault_path).with_suffix('').as_posix()}]]",
            f"broken_links={broken_links}",
            f"orphan_pages={orphan_pages}",
            f"missing_citations={missing_citations}",
            f"stale_pages={stale_pages}",
            f"duplicate_aliases={duplicate_aliases}",
        ],
    )

    return KbLintResult(
        report_path=str(report),
        broken_links=broken_links,
        orphan_pages=orphan_pages,
        missing_citations=missing_citations,
        stale_pages=stale_pages,
        duplicate_aliases=duplicate_aliases,
    )


def _score_page_for_query(page: Path, query_tokens: Sequence[str]) -> int:
    text = _read_text(page).lower()
    score = 0
    for t in query_tokens:
        score += text.count(t)
    return score


def answer_query(
    vault_path: Path,
    query: str,
    output_type: str = "report",
    top_k: int = 8,
    min_evidence: int = 1,
) -> KbQaResult:
    _ensure_kb_dirs(vault_path)
    if not query.strip():
        raise KBError("Query must not be empty")

    query_tokens = _tokenize(query)
    candidates = _iter_md(vault_path / WIKI_DIR)
    if not candidates:
        raise KBError("No compiled wiki pages found. Run compile first.")

    scored = []
    for p in candidates:
        s = _score_page_for_query(p, query_tokens)
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda item: item[0], reverse=True)
    top = [p for _, p in scored[:top_k]] or candidates[: min(top_k, len(candidates))]

    evidence_links = [f"[[{p.relative_to(vault_path).with_suffix('').as_posix()}]]" for p in top]
    if len(evidence_links) < max(min_evidence, 1):
        raise KBError(
            f"Insufficient evidence for QA output: have {len(evidence_links)}, require {max(min_evidence, 1)}"
        )

    synthesis: List[str] = []
    for page in top[:5]:
        text = _read_text(page)
        for line in text.splitlines():
            s = line.strip("- ").strip()
            if not s or s.startswith("#") or s.startswith("["):
                continue
            synthesis.append(s)
            if len(synthesis) >= 8:
                break
        if len(synthesis) >= 8:
            break

    confidence = "high" if len(top) >= 5 else "medium" if len(top) >= 2 else "low"

    now = datetime.now()
    stem = _slugify(query, max_len=60)
    ext = "md"
    artifact = vault_path / OUTPUTS_DIR / f"{now.strftime('%Y%m%d-%H%M%S')}-{stem}.{ext}"

    lines = [
        f"# Q&A Artifact: {query}",
        "",
        f"Generated: {now.isoformat(timespec='seconds')}",
        f"Output Type: {output_type}",
        "",
        "## Answer",
    ]
    if synthesis:
        for item in synthesis:
            lines.append(f"- {item}")
    else:
        lines.append("- No strong evidence found in current wiki.")

    lines.extend(["", "## Evidence used"])
    for ev in evidence_links:
        lines.append(f"- {ev}")

    lines.extend(["", "## Confidence", f"- {confidence}", ""])
    artifact.write_text("\n".join(lines), encoding="utf-8")

    # feedback loop: append to question candidates
    questions_index = vault_path / INDEX_DIR / "question-candidates.md"
    q_lines = [
        f"## {now.isoformat(timespec='seconds')}",
        f"- Query: {query}",
        f"- Artifact: [[{artifact.relative_to(vault_path).with_suffix('').as_posix()}]]",
        f"- Confidence: {confidence}",
        f"- Evidence count: {len(evidence_links)}",
        "",
    ]
    existing = questions_index.read_text(encoding="utf-8") if questions_index.exists() else "# Question Candidates\n\n"
    questions_index.write_text(existing.rstrip() + "\n\n" + "\n".join(q_lines), encoding="utf-8")

    _append_op_log(
        vault_path,
        "query",
        query,
        [
            f"output_type={output_type}",
            f"evidence_count={len(evidence_links)}",
            f"confidence={confidence}",
            f"artifact=[[{artifact.relative_to(vault_path).with_suffix('').as_posix()}]]",
        ],
    )

    return KbQaResult(artifact_path=str(artifact), evidence_count=len(evidence_links), confidence=confidence)


def improve_kb(vault_path: Path, max_outputs: int = 20) -> Path:
    """Continuous-improvement pass: suggest new question prompts from recent outputs."""
    _ensure_kb_dirs(vault_path)
    outputs = _iter_md(vault_path / OUTPUTS_DIR)[:max_outputs]

    now = datetime.now()
    out = vault_path / INDEX_DIR / "improvement-suggestions.md"
    lines = [
        "# Improvement Suggestions",
        "",
        f"Generated: {now.isoformat(timespec='seconds')}",
        "",
        "## Suggested next research directions",
    ]

    if not outputs:
        lines.append("- No output artifacts found yet. Run `qa` first.")
    else:
        for p in outputs:
            txt = _read_text(p)
            conf_match = re.search(r"## Confidence\n-\s*(\w+)", txt)
            conf = conf_match.group(1).lower() if conf_match else "unknown"
            query_line = next((ln for ln in txt.splitlines() if ln.startswith("# Q&A Artifact:")), "")
            query = query_line.replace("# Q&A Artifact:", "").strip() or p.stem
            if conf in {"low", "unknown"}:
                lines.append(f"- Deepen evidence for: {query}")
            else:
                lines.append(f"- Extend adjacent concepts from: {query}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _append_op_log(
        vault_path,
        "improve",
        "improvement-suggestions",
        [
            f"outputs_scanned={len(outputs)}",
            f"suggestions=[[{out.relative_to(vault_path).with_suffix('').as_posix()}]]",
        ],
    )
    return out
