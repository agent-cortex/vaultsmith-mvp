VaultSmith (MVP+)

VaultSmith is a lightweight Python CLI that turns plain text into an Obsidian-compatible, cross-session knowledge graph.

It is designed to work with agent memory workflows out of the box:
- Small, durable persistent memory (stable facts/preferences)
- Large, expandable vault graph (sessions/projects/people/concepts/decisions)

This keeps memory compact while allowing unlimited long-term expansion in the vault.

What changed in this version
- Added `init` command to bootstrap an agent-ready vault layout
- Added memory-candidate extraction from plain text prefixes:
  - `Preference:`
  - `Environment:`
  - `Convention:`
  - `Profile:`
  - `Memory:`
- Added automatic `05 Memory/Agent Memory Candidates.md` updates during ingest
- Added `memory_candidates` count to ingest output
- Added reusable `99 System/AGENT-PLAYBOOK.md` and capture template for any copied agent setup

MVP pipeline
1. Ingest plaintext input
2. Extract entities with deterministic heuristics (no external API)
3. Write/update Obsidian notes with wikilinks
4. Capture candidate durable facts for promotion into persistent memory

Project structure
- cli.py
- requirements.txt
- sample_input.txt
- vaultsmith/
  - __init__.py
  - bootstrap.py
  - config.py
  - models.py
  - extract.py
  - writer.py
  - pipeline.py
  - review.py

Extraction rules
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
- Memory candidates:
  - lines starting with `Preference:` / `Environment:` / `Convention:` / `Profile:` / `Memory:`

Vault folders
- `00 Inbox`
- `05 Memory`
- `10 Projects`
- `20 People`
- `30 Concepts`
- `40 Decisions`
- `90 Reviews`
- `99 System`

Quickstart
1) From project root:
```bash
cd /home/home/vaultsmith
```

2) Bootstrap vault once (required for out-of-box agent compatibility):
```bash
python cli.py init --vault /home/home/obsidian-vault --agent-label "Any Agent"
```

3) Ingest session/plaintext:
```bash
python cli.py ingest --input sample_input.txt --vault /home/home/obsidian-vault
```

4) Run auto-linker (recommended before review):
```bash
python cli.py link --vault /home/home/obsidian-vault --limit 25 --min-shared-terms 2
```

5) Generate weekly review:
```bash
python cli.py review --vault /home/home/obsidian-vault
```

Expected artifacts
- New inbox capture note (always created):
  - `/home/home/obsidian-vault/00 Inbox/ingest-YYYYMMDD-HHMMSS-<run_id>.md`
- Entity notes (created/appended idempotently):
  - `/10 Projects/<name>--<hash>.md`
  - `/20 People/<name>--<hash>.md`
  - `/30 Concepts/<name>--<hash>.md`
  - `/40 Decisions/<name>--<hash>.md`
- Memory notes:
  - `/05 Memory/Agent Memory Candidates.md` (append-on-run-id)
  - `/05 Memory/Persistent Memory Schema.md` (created by init)
- Agent system notes:
  - `/99 System/AGENT-PLAYBOOK.md` (created by init)
- Auto-link updates:
  - recent `00 Inbox/ingest-*.md` notes get appended `## Auto Links ...` sections with related wikilinks
- Weekly review note:
  - `/90 Reviews/weekly-review-YYYY-Www.md`

Idempotency behavior
- Entity notes append a dated section at most once per `run_id`.
- Memory-candidate note also appends at most once per `run_id`.
- Inbox capture in `00 Inbox` is always a new file for each run.
- Without `--run-id`, VaultSmith auto-generates one.

Input encoding and error behavior
- Input files must be UTF-8 text.
- Missing/unreadable input or unwritable vault path returns concise stderr error and exit code `1`.

Weekly review includes
- Top Themes
- Open Loops
- Recent Decisions
- Suggested Next 3 Actions
- Stale Projects (>14 days)

Agent-copy compatibility contract (Waltz/VaultSmith)
If another agent copies this setup, it should follow:
1. Run `init` once in target vault.
2. Feed each session through `ingest`.
3. Use memory prefixes in source text when candidate durable facts appear.
4. Promote only stable/repeated facts from `05 Memory/Agent Memory Candidates.md` to `05 Memory/Persistent Memory Schema.md`.
5. Run `link` on a recurring cadence (before review) to grow cross-session interlinks.
6. Run `review` on a recurring cadence.

Example ingest with explicit run id
```bash
python cli.py ingest --input sample_input.txt --vault /home/home/obsidian-vault --run-id demo-001
```

Example linker run with explicit run id
```bash
python cli.py link --vault /home/home/obsidian-vault --limit 25 --min-shared-terms 2 --run-id link-001
```

Example input snippet for memory compatibility
```text
Project: VaultSmith
Concept: Knowledge Graph
Decision: Keep deterministic extraction for MVP
TODO: Add weekly linker pass

Preference: User prefers concise action-status labels.
Environment: Obsidian vault path is /home/home/obsidian-vault.
Convention: Promote to persistent memory only after repetition.
Profile: Preferred name is Megabyte.
Memory: Quiet hours are 23:00-06:00 unless urgent.
```
