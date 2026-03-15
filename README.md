# VaultSmith (MVP+)

VaultSmith is a lightweight Python CLI that converts plain text into an Obsidian-compatible, cross-session knowledge graph.

It is designed for a two-layer memory model:
- Small, durable persistent memory (stable preferences/facts)
- Large, expandable vault graph (sessions/projects/people/concepts/decisions)

This keeps persistent memory compact while vault knowledge can grow indefinitely.

## What's New

- Added `init` command to bootstrap an agent-ready vault layout
- Added memory-candidate extraction from text prefixes:
  - `Preference:`
  - `Environment:`
  - `Convention:`
  - `Profile:`
  - `Memory:`
- Added automatic updates to `05 Memory/Agent Memory Candidates.md` during ingest
- Added `memory_candidates` count to ingest output
- Added reusable `99 System/AGENT-PLAYBOOK.md` and capture template
- Added `link` command for deterministic cross-note auto-linking

## Pipeline

1. Ingest plaintext input
2. Extract entities with deterministic heuristics (no external APIs)
3. Write/update Obsidian notes with wikilinks
4. Capture candidate durable facts for persistent memory promotion
5. Auto-link recent ingest notes based on shared terms
6. Generate weekly review synthesis

## Project Structure

```text
.
├── cli.py
├── requirements.txt
├── sample_input.txt
├── SKILL.md
└── vaultsmith/
    ├── __init__.py
    ├── bootstrap.py
    ├── config.py
    ├── extract.py
    ├── linker.py
    ├── models.py
    ├── pipeline.py
    ├── review.py
    └── writer.py
```

## Extraction Rules

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

## Vault Layout

- `00 Inbox`
- `05 Memory`
- `10 Projects`
- `20 People`
- `30 Concepts`
- `40 Decisions`
- `90 Reviews`
- `99 System`

## Quickstart (Portable)

1) Set environment-specific paths:

```bash
export VAULTSMITH_DIR="/absolute/path/to/vaultsmith"
export OBSIDIAN_VAULT_PATH="/absolute/path/to/your-obsidian-vault"
```

2) Bootstrap vault once:

```bash
cd "$VAULTSMITH_DIR"
python cli.py init --vault "$OBSIDIAN_VAULT_PATH" --agent-label "Any Agent"
```

3) Ingest a session/plaintext file:

```bash
python cli.py ingest --input sample_input.txt --vault "$OBSIDIAN_VAULT_PATH"
```

4) Auto-link recent ingest notes:

```bash
python cli.py link --vault "$OBSIDIAN_VAULT_PATH" --limit 25 --min-shared-terms 2
```

5) Generate weekly review:

```bash
python cli.py review --vault "$OBSIDIAN_VAULT_PATH"
```

Optional: auto-close standard verification loops when artifacts exist (ingest note, auto links, review generation):

```bash
python cli.py review --vault "$OBSIDIAN_VAULT_PATH" --close-verified
```

## Optional Daily Helper Script

```bash
~/.hermes/skills/note-taking/vaultsmith/scripts/run_daily_cycle.sh \
  --vaultsmith-dir "$VAULTSMITH_DIR" \
  --vault "$OBSIDIAN_VAULT_PATH" \
  --input /absolute/path/to/session_input.txt \
  --run-id day-001
```

The script also supports environment-variable-only mode and legacy positional args.

## Expected Artifacts

- New inbox capture note (always created):
  - `00 Inbox/ingest-YYYYMMDD-HHMMSS-<run_id>.md`
- Entity notes (created/appended idempotently):
  - `10 Projects/<name>--<hash>.md`
  - `20 People/<name>--<hash>.md`
  - `30 Concepts/<name>--<hash>.md`
  - `40 Decisions/<name>--<hash>.md`
- Memory notes:
  - `05 Memory/Agent Memory Candidates.md`
  - `05 Memory/Persistent Memory Schema.md`
- System note:
  - `99 System/AGENT-PLAYBOOK.md`
- Auto-link updates:
  - appended `## Auto Links ...` sections in recent `00 Inbox/ingest-*.md`
- Weekly review:
  - `90 Reviews/weekly-review-YYYY-Www.md`

## Idempotency

- Entity notes append at most once per `run_id`.
- Memory-candidate note appends at most once per `run_id`.
- Linker auto-link section appends at most once per linker `run_id`.
- Inbox capture is always a new file per ingest run.
- If `--run-id` is omitted, VaultSmith auto-generates one.

## Error Behavior

- Input files must be UTF-8 text.
- Missing/unreadable input or unwritable vault path returns concise stderr errors with exit code `1`.

## Weekly Review Includes

- Top Themes
- Open Loops
- Recent Decisions
- Suggested Next 3 Actions
- Stale Projects (>14 days)

## Agent-Copy Compatibility Contract

Any agent/environment should follow:

1. Run `init` once in the target vault.
2. Feed each meaningful session through `ingest`.
3. Use memory prefixes when candidate durable facts appear.
4. Promote only stable/repeated facts from `05 Memory/Agent Memory Candidates.md` to `05 Memory/Persistent Memory Schema.md`.
5. Run `link` regularly (before review) to grow interlinks.
6. Run `review` on a recurring cadence.

## Examples

Ingest with explicit run id:

```bash
python cli.py ingest --input sample_input.txt --vault "$OBSIDIAN_VAULT_PATH" --run-id demo-001
```

Link with explicit run id:

```bash
python cli.py link --vault "$OBSIDIAN_VAULT_PATH" --limit 25 --min-shared-terms 2 --run-id link-001
```

Memory-compatible input snippet:

```text
Project: VaultSmith
Concept: Knowledge Graph
Decision: Keep deterministic extraction for MVP
TODO: Add weekly linker pass

Preference: User prefers concise action-status labels.
Environment: Obsidian vault path is /absolute/path/to/your-obsidian-vault.
Convention: Promote to persistent memory only after repetition.
Profile: Preferred name is Megabyte.
Memory: Quiet hours are 23:00-06:00 unless urgent.
```
