from __future__ import annotations

import argparse
from pathlib import Path
import sys

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
    print(f"projects={len(result.projects)} people={len(result.people)} concepts={len(result.concepts)} decisions={len(result.decisions)} tasks={len(result.tasks)}")
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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "ingest":
        return cmd_ingest(args)

    if args.command == "review":
        return cmd_review(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
