from pathlib import Path

from vaultsmith.config import ensure_vault_dirs
from vaultsmith.review import generate_weekly_review


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _seed_common_notes(vault: Path, include_auto_links: bool) -> None:
    ensure_vault_dirs(vault)

    inbox = """
# Inbox Capture

## Tasks
- [ ] Run regular VaultSmith cycle on dedicated vault.
- [ ] Confirm ingest output appears in 00 Inbox.
- [ ] Confirm linker annotates auto links.
- [ ] Confirm weekly review is generated.

## Raw Source
```
- [ ] Confirm ingest output appears in 00 Inbox.
- [ ] Confirm linker annotates auto links.
- [ ] Confirm weekly review is generated.
```
"""

    if include_auto_links:
        inbox += "\n## Auto Links 2026-03-15 18:24:13\n- suggested\n"

    _write(vault / "00 Inbox" / "ingest-1.md", inbox)

    decision = """
# Decision Note

## Update
- Follow-up tasks:
  - [ ] Run regular VaultSmith cycle on dedicated vault.
  - [ ] Confirm ingest output appears in 00 Inbox.
  - [ ] Confirm linker annotates auto links.
  - [ ] Confirm weekly review is generated.
"""
    _write(vault / "40 Decisions" / "decision.md", decision)


def test_review_close_verified_marks_tasks_and_leaves_raw_source_unchanged(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _seed_common_notes(vault, include_auto_links=True)

    result = generate_weekly_review(vault_path=vault, close_verified=True)
    assert result.open_loops_count >= 0

    inbox_text = (vault / "00 Inbox" / "ingest-1.md").read_text(encoding="utf-8")
    assert "- [x] Run regular VaultSmith cycle on dedicated vault." in inbox_text
    assert "- [x] Confirm ingest output appears in 00 Inbox." in inbox_text
    assert "- [x] Confirm linker annotates auto links." in inbox_text
    assert "- [x] Confirm weekly review is generated." in inbox_text

    # Raw source block should stay historical and unchanged.
    assert "## Raw Source" in inbox_text
    assert "```\n- [ ] Confirm ingest output appears in 00 Inbox." in inbox_text


def test_review_close_verified_requires_auto_links_for_linker_confirmation(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _seed_common_notes(vault, include_auto_links=False)

    generate_weekly_review(vault_path=vault, close_verified=True)

    inbox_text = (vault / "00 Inbox" / "ingest-1.md").read_text(encoding="utf-8")
    assert "- [x] Run regular VaultSmith cycle on dedicated vault." in inbox_text
    assert "- [x] Confirm ingest output appears in 00 Inbox." in inbox_text
    assert "- [ ] Confirm linker annotates auto links." in inbox_text
    assert "- [x] Confirm weekly review is generated." in inbox_text


def test_review_open_loops_ignore_raw_source_checkboxes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _seed_common_notes(vault, include_auto_links=True)

    result = generate_weekly_review(vault_path=vault, close_verified=True)

    assert result.open_loops_count == 0
