"""End-to-end ingestion pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .extract import extract_entities
from .models import IngestResult
from .writer import write_entity_notes, write_inbox_note


class IngestError(RuntimeError):
    """Friendly exception raised for expected ingest failures."""


def ingest_file(input_path: Path, vault_path: Path, run_id: Optional[str] = None) -> IngestResult:
    if not input_path.exists():
        raise IngestError(f"Input file not found: {input_path}")

    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise IngestError(f"Input file must be UTF-8 text: {input_path}") from exc
    except PermissionError as exc:
        raise IngestError(f"Permission denied while reading input file: {input_path}") from exc
    except FileNotFoundError as exc:
        raise IngestError(f"Input file not found: {input_path}") from exc

    extraction = extract_entities(text)

    now = datetime.now()
    effective_run_id = run_id or f"run-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"

    try:
        inbox_note = write_inbox_note(
            vault_path=vault_path,
            source_text=text,
            extraction=extraction,
            run_id=effective_run_id,
            now=now,
        )

        write_entity_notes(
            vault_path=vault_path,
            extraction=extraction,
            run_id=effective_run_id,
            inbox_note_path=inbox_note,
            now=now,
        )
    except PermissionError as exc:
        raise IngestError(f"Permission denied while writing to vault: {vault_path}") from exc
    except FileNotFoundError as exc:
        raise IngestError(f"Vault path not found or inaccessible: {vault_path}") from exc

    return IngestResult(
        run_id=effective_run_id,
        inbox_note_path=str(inbox_note),
        projects=sorted(extraction.projects),
        people=sorted(extraction.people),
        concepts=sorted(extraction.concepts),
        decisions=extraction.decisions,
        tasks=extraction.tasks,
    )
