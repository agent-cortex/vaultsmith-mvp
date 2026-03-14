VaultSmith (MVP)

VaultSmith is a lightweight Python CLI for ingesting plain text and turning it into Obsidian-friendly notes.

MVP pipeline:
1. Ingest plaintext input
2. Extract entities with deterministic heuristics (no external API)
3. Write/update notes in Obsidian folders with wikilinks

Project structure
- cli.py
- requirements.txt
- sample_input.txt
- vaultsmith/
  - __init__.py
  - config.py
  - models.py
  - extract.py
  - writer.py
  - pipeline.py
  - review.py

Heuristic extraction rules
- Projects:
  - lines starting with `Project:`
  - hashtags like `#project/<name>`
- People:
  - `@name` tokens
- Concepts:
  - lines starting with `Concept:`
  - TitleCase words repeated at least 2 times
- Decisions:
  - lines starting with `Decision:`
- Tasks:
  - lines starting with `TODO:`
  - markdown checkboxes like `- [ ] task`

Obsidian output folders
- `00 Inbox`
- `10 Projects`
- `20 People`
- `30 Concepts`
- `40 Decisions`
- `90 Reviews`

Quickstart
1) From project root:
   cd /home/home/vaultsmith

2) Run ingest:
   python cli.py ingest --input sample_input.txt --vault /home/home/obsidian-vault

3) Generate weekly review:
   python cli.py review --vault /home/home/obsidian-vault

Expected artifacts after run
- New inbox capture note (always created):
  - `/home/home/obsidian-vault/00 Inbox/ingest-YYYYMMDD-HHMMSS-<run_id>.md`
- Project notes (created or appended):
  - `/home/home/obsidian-vault/10 Projects/<Project Name>.md`
- People notes:
  - `/home/home/obsidian-vault/20 People/<person>.md`
- Concept notes:
  - `/home/home/obsidian-vault/30 Concepts/<Concept>.md`
- Decision notes:
  - `/home/home/obsidian-vault/40 Decisions/<Decision text>.md`
- Weekly review note:
  - `/home/home/obsidian-vault/90 Reviews/weekly-review-YYYY-Www.md`

Idempotency behavior
- Entity notes (`10 Projects`, `20 People`, `30 Concepts`, `40 Decisions`) append a dated section at most once per `run_id`.
- If you rerun with the same `--run-id`, VaultSmith will not append duplicate entity sections.
- The inbox capture note in `00 Inbox` is always created as a new file for each run, even when `--run-id` is reused.
- Without `--run-id`, VaultSmith auto-generates one.

Input encoding and error behavior
- Input files are expected to be UTF-8 text.
- If the input file is missing, unreadable, non-UTF-8, or the vault path cannot be written, CLI prints a concise error to stderr and exits with code `1`.

Weekly review includes
- Title and generated timestamp
- Top Themes (frequency-based from concepts/projects)
- Open Loops (`- [ ]` tasks from scanned notes)
- Recent Decisions (latest snippets)
- Suggested Next 3 Actions
- Stale Projects (>14 days since modified)

Example command with explicit run id
python cli.py ingest --input sample_input.txt --vault /home/home/obsidian-vault --run-id demo-001
