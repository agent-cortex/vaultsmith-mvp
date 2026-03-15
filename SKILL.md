---
name: vaultsmith
description: Build and maintain a cross-session Obsidian knowledge graph with persistent-memory-compatible ingestion, auto-linking, and weekly review.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [obsidian, knowledge-graph, memory, notes, automation]
    category: note-taking
    requires_toolsets: [terminal, file]
---

# VaultSmith

## When to Use
Use this skill when you need to:
- Convert session/chat text into structured Obsidian notes.
- Keep continuity across separate sessions by interlinking related notes.
- Separate compact persistent memory from expandable long-form vault knowledge.
- Run recurring synthesis (open loops, stale projects, themes, decisions).

Typical triggers:
- User asks for "cross-session linking" or "second brain" behavior.
- A project has many chats and needs continuity over time.
- You want agent-copyable setup that works out of the box.

## Prerequisites
- VaultSmith repository exists locally.
- Python is available.
- An Obsidian vault path exists (or can be created).

Recommended variables (set per environment):
```bash
export VAULTSMITH_DIR="/absolute/path/to/vaultsmith"
export OBSIDIAN_VAULT_PATH="/absolute/path/to/your-obsidian-vault"
```

Notes:
- Do not assume fixed paths.
- If these env vars are set, scripts and commands can run without hardcoded machine-specific locations.

## Procedure

### 1) Initialize vault for agent-compatible operation (one-time)
```bash
cd "$VAULTSMITH_DIR"
python cli.py init --vault "$OBSIDIAN_VAULT_PATH" --agent-label "Any Agent"
```

This creates/ensures:
- `00 Inbox/`
- `05 Memory/`
- `10 Projects/`
- `20 People/`
- `30 Concepts/`
- `40 Decisions/`
- `90 Reviews/`
- `99 System/`
- `05 Memory/Persistent Memory Schema.md`
- `99 System/AGENT-PLAYBOOK.md`
- `00 Inbox/capture-template.md`

### 2) Ingest source text from a session
Create an input file (or reuse `sample_input.txt`) and run:
```bash
cd "$VAULTSMITH_DIR"
python cli.py ingest --input sample_input.txt --vault "$OBSIDIAN_VAULT_PATH"
```

For idempotent reruns:
```bash
python cli.py ingest --input sample_input.txt --vault "$OBSIDIAN_VAULT_PATH" --run-id session-001
```

### 3) Include memory-candidate prefixes in input text
When the text contains durable facts, prefix lines with one of:
- `Preference:`
- `Environment:`
- `Convention:`
- `Profile:`
- `Memory:`

These get captured into:
- Inbox note (`## Memory Candidates`)
- `05 Memory/Agent Memory Candidates.md`

### 4) Auto-link recent ingest notes
Run linker to grow cross-session interlinks:
```bash
cd "$VAULTSMITH_DIR"
python cli.py link --vault "$OBSIDIAN_VAULT_PATH" --limit 25 --min-shared-terms 2
```

Idempotent linker rerun:
```bash
python cli.py link --vault "$OBSIDIAN_VAULT_PATH" --limit 25 --min-shared-terms 2 --run-id link-001
```

### 5) Generate weekly synthesis
```bash
cd "$VAULTSMITH_DIR"
python cli.py review --vault "$OBSIDIAN_VAULT_PATH"
```

Optional (close standard verification loops when artifacts are present):
```bash
python cli.py review --vault "$OBSIDIAN_VAULT_PATH" --close-verified
```

Output includes:
- Top Themes
- Open Loops
- Recent Decisions
- Suggested Next 3 Actions
- Stale Projects

### 6) Promote stable facts to persistent schema
After repetition/confirmation, move only stable items from:
- `05 Memory/Agent Memory Candidates.md`
into:
- `05 Memory/Persistent Memory Schema.md`

Do not promote temporary task state.

## Operational Cadence
- Per session: ingest once.
- Daily or every few sessions: run linker.
- Weekly: run review and prune/advance open loops.
- Memory hygiene: promote only repeated/stable facts.

## Pitfalls
- Linking noise can increase if `--min-shared-terms` is too low.
  - Fix: raise to `3` for stricter similarity.
- Duplicate-looking entities can occur from naming variance.
  - Fix: normalize naming in source text and reuse canonical entity names.
- Persistent memory bloat if everything is promoted.
  - Fix: keep durable facts only; leave evolving details in vault notes.
- Non-UTF8 input causes ingest failure.
  - Fix: convert source text to UTF-8 before ingest.

## Verification
After running init + ingest + link + review, verify:

```bash
cd "$OBSIDIAN_VAULT_PATH"
```

Check expected files:
- New `00 Inbox/ingest-*.md`
- Updated entity notes in `10/20/30/40` folders
- `05 Memory/Agent Memory Candidates.md` has latest update section
- Ingest note contains `## Auto Links ...` after linker run
- `90 Reviews/weekly-review-YYYY-Www.md` exists

Quick CLI success markers:
- `VaultSmith ingest complete`
- `VaultSmith linker complete`
- `VaultSmith weekly review generated`

## Fallback / Recovery
If any command fails:
1. Re-run with explicit absolute paths.
2. Confirm vault path write permissions.
3. Re-run with explicit `--run-id` for deterministic troubleshooting.
4. Run commands step-by-step in order: `init` → `ingest` → `link` → `review`.
