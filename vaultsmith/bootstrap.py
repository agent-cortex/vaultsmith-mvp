"""Vault bootstrap helpers for out-of-box multi-agent compatibility."""

from __future__ import annotations

from pathlib import Path

from .config import MEMORY_DIR, SYSTEM_DIR, ensure_vault_dirs


class BootstrapError(RuntimeError):
    """Friendly exception raised for expected bootstrap failures."""


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return True


def bootstrap_vault(vault_path: Path, agent_label: str = "Any Agent") -> list[Path]:
    try:
        ensure_vault_dirs(vault_path)
    except PermissionError as exc:
        raise BootstrapError(f"Permission denied while creating vault folders: {vault_path}") from exc

    created: list[Path] = []

    memory_schema = vault_path / MEMORY_DIR / "Persistent Memory Schema.md"
    if _write_if_missing(
        memory_schema,
        """
# Persistent Memory Schema

Use this file to keep stable, durable facts that should survive across sessions.

## Rules
- Store only durable, high-signal facts.
- Do NOT store temporary task progress.
- Promote facts from `Agent Memory Candidates.md` only after repetition or explicit confirmation.

## Sections
### User Profile
- name/preferred-address
- timezone
- communication style
- recurring preferences

### Environment Facts
- machine/tooling details that are unlikely to change often

### Workflow Conventions
- stable commands/process rules used across sessions

### Agent Routing Hints
- which indexes/notes to check first for common task types
""",
    ):
        created.append(memory_schema)

    playbook = vault_path / SYSTEM_DIR / "AGENT-PLAYBOOK.md"
    if _write_if_missing(
        playbook,
        f"""
# Agent Playbook ({agent_label})

This vault is designed for cross-session continuity.

## Required behavior per session
1. Create/append one inbox capture via VaultSmith ingest.
2. Link extracted entities into Projects/People/Concepts/Decisions.
3. Add candidate durable facts using `Preference:`, `Environment:`, `Convention:`, `Profile:`, or `Memory:` prefixes in source text.
4. Promote only stable/repeated facts from `05 Memory/Agent Memory Candidates.md` into `05 Memory/Persistent Memory Schema.md`.

## Interlinking policy
- Always use wikilinks for extracted entities.
- Reuse existing note names when possible (avoid duplicates).
- Keep one canonical note per entity and append updates with run_id markers.

## Expansion policy
- Prefer adding new linked notes over expanding one giant note.
- Use weekly reviews to identify stale projects and open loops.
""",
    ):
        created.append(playbook)

    capture_template = vault_path / "00 Inbox" / "capture-template.md"
    if _write_if_missing(
        capture_template,
        """
# Session Capture Template

Project: 
Concept: 
Decision: 
TODO: 

Preference: 
Environment: 
Convention: 
Profile: 
Memory: 

Notes:
""",
    ):
        created.append(capture_template)

    return created
