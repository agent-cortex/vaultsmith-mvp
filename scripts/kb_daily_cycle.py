#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vaultsmith.kb import answer_query, compile_sources, improve_kb, lint_kb


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run VaultSmith KB daily cycle (phases 3-6)")
    p.add_argument("--vault", required=True, help="Path to pilot vault")
    p.add_argument("--query", required=True, help="Daily Q&A query")
    p.add_argument("--output", default="report", choices=["report", "slides", "plot"])
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--min-evidence", type=int, default=1)
    p.add_argument("--max-outputs", type=int, default=20)
    p.add_argument("--log-file", default="90 Reviews/kb-weekly-pilot-log.md")
    p.add_argument("--compiled-sources-state", default="{}", help="JSON dict of source path -> content hash")
    return p


def append_log(vault: Path, log_rel: str, *, compiled, linted, qa, improve_path: Path) -> Path:
    now = datetime.now()
    log_path = vault / log_rel
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8").rstrip()
    else:
        existing = "# KB Weekly Pilot Log\n"

    section = [
        "",
        f"## {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Compiled pages: {compiled.compiled_pages}",
        f"- Sources skipped (unchanged): {compiled.sources_skipped}",
        f"- Indexes updated: {compiled.updated_indexes}",
        f"- Broken links: {linted.broken_links}",
        f"- Orphan pages: {linted.orphan_pages}",
        f"- Missing citations: {linted.missing_citations}",
        f"- Stale pages: {linted.stale_pages}",
        f"- Duplicate aliases: {linted.duplicate_aliases}",
        f"- QA artifact: [[{Path(qa.artifact_path).relative_to(vault).with_suffix('').as_posix()}]]",
        f"- Evidence count: {qa.evidence_count}",
        f"- Confidence: {qa.confidence}",
        f"- Improvement suggestions: [[{improve_path.relative_to(vault).with_suffix('').as_posix()}]]",
    ]

    log_path.write_text(existing + "\n" + "\n".join(section) + "\n", encoding="utf-8")
    return log_path


def main() -> int:
    import json
    args = build_parser().parse_args()
    vault = Path(args.vault)
    compiled_sources_state = json.loads(args.compiled_sources_state)

    compiled = compile_sources(vault_path=vault, limit=200, compiled_sources=compiled_sources_state)
    linted = lint_kb(vault_path=vault)
    qa = answer_query(
        vault_path=vault,
        query=args.query,
        output_type=args.output,
        top_k=args.top_k,
        min_evidence=args.min_evidence,
    )
    improve_path = improve_kb(vault_path=vault, max_outputs=args.max_outputs)

    log_path = append_log(vault, args.log_file, compiled=compiled, linted=linted, qa=qa, improve_path=improve_path)

    print("VaultSmith KB daily cycle complete")
    print(f"vault={vault}")
    print(f"log={log_path}")
    print(
        "summary="
        f"compiled={compiled.compiled_pages} "
        f"sources_skipped={compiled.sources_skipped} "
        f"broken_links={linted.broken_links} "
        f"orphan_pages={linted.orphan_pages} "
        f"qa_confidence={qa.confidence} "
        f"qa_evidence={qa.evidence_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
