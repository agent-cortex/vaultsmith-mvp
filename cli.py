from __future__ import annotations

import argparse
from pathlib import Path
import sys

from vaultsmith.bootstrap import BootstrapError, bootstrap_vault
from vaultsmith.linker import LinkError, auto_link_sessions
from vaultsmith.pipeline import IngestError, ingest_file
from vaultsmith.review import ReviewError, generate_weekly_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VaultSmith CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest plaintext and write Obsidian notes")
    ingest.add_argument("--input", required=True, help="Path to input text file")
    ingest.add_argument("--vault", required=True, help="Path to Obsidian vault")
    ingest.add_argument("--run-id", required=False, help="Optional run id for idempotent append behavior")

    review = subparsers.add_parser("review", help="Generate weekly review from vault notes")
    review.add_argument("--vault", required=True, help="Path to Obsidian vault")

    init_cmd = subparsers.add_parser("init", help="Bootstrap vault files for cross-session multi-agent usage")
    init_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    init_cmd.add_argument("--agent-label", required=False, default="Any Agent", help="Label shown in AGENT-PLAYBOOK")

    link_cmd = subparsers.add_parser("link", help="Auto-link recent inbox notes to related notes")
    link_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    link_cmd.add_argument("--limit", type=int, default=25, help="Number of recent inbox notes to process")
    link_cmd.add_argument("--min-shared-terms", type=int, default=2, help="Minimum shared terms for link suggestions")
    link_cmd.add_argument("--run-id", required=False, help="Optional run id for idempotent linker sections")

    return parser


def cmd_ingest(args: argparse.Namespace) -> int:
    try:
        result = ingest_file(
            input_path=Path(args.input),
            vault_path=Path(args.vault),
            run_id=args.run_id,
        )
    except IngestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("VaultSmith ingest complete")
    print(f"run_id={result.run_id}")
    print(f"inbox_note={result.inbox_note_path}")
    print(
        "projects="
        f"{len(result.projects)} "
        f"people={len(result.people)} "
        f"concepts={len(result.concepts)} "
        f"decisions={len(result.decisions)} "
        f"tasks={len(result.tasks)} "
        f"memory_candidates={len(result.memory_candidates)}"
    )
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    try:
        result = generate_weekly_review(vault_path=Path(args.vault))
    except ReviewError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("VaultSmith weekly review generated")
    print(f"review_note={result.review_note_path}")
    print(f"open_loops={result.open_loops_count} stale_projects={result.stale_projects_count}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    try:
        created = bootstrap_vault(vault_path=Path(args.vault), agent_label=args.agent_label)
    except BootstrapError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("VaultSmith init complete")
    if created:
        print("created_files=")
        for path in created:
            print(f"- {path}")
    else:
        print("created_files=(none; all bootstrap files already existed)")
    return 0


def cmd_link(args: argparse.Namespace) -> int:
    try:
        result = auto_link_sessions(
            vault_path=Path(args.vault),
            limit=args.limit,
            min_shared_terms=args.min_shared_terms,
            run_id=args.run_id,
        )
    except LinkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("VaultSmith linker complete")
    print(f"run_id={result.run_id}")
    print(f"processed_notes={result.processed_notes}")
    print(f"updated_notes={result.updated_notes}")
    print(f"suggested_links={result.suggested_links}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        return cmd_ingest(args)

    if args.command == "review":
        return cmd_review(args)

    if args.command == "init":
        return cmd_init(args)

    if args.command == "link":
        return cmd_link(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
