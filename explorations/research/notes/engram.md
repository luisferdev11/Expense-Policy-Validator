# Engram for cross-session memory: research (fetched 2026-10-08)

Research subagent output, condensed. Web research only.

## What it is

- `Gentleman-Programming/engram`: "Persistent memory system for AI coding agents".
  - One Go binary that acts as a CLI, an HTTP API, an MCP server and a TUI.
  - MIT license, about 7.1k stars.
  - Latest release v3.2.1, 2026-10-07. v3.0.0 (2026-10-01) was breaking, and v3.2.1 is a recovery release.
  - Sources: https://github.com/Gentleman-Programming/engram, https://github.com/Gentleman-Programming/engram/releases/tag/v3.2.1
- Other projects share the name (engram-rs, engram-mcp, claude-engram); none was evaluated.

## How it works

- **Storage:** local SQLite with FTS5 search in `~/.engram/engram.db`. Cloud sync is opt-in. Source: https://raw.githubusercontent.com/Gentleman-Programming/engram/main/DOCS.md
- **What it stores:** curated observations (decision, architecture, bugfix, pattern, config, discovery, learning, preference), each with a scope, plus session summaries and user prompts.
- **Interfaces:** 23 MCP tools (`mem_save`, `mem_search`, `mem_context`, `mem_session_summary`, …).
- **Claude Code wiring:** `engram setup claude-code` installs a user-scope plugin with hooks and the MCP server; there is also a bare-MCP option. Source: https://raw.githubusercontent.com/Gentleman-Programming/engram/main/docs/AGENT-SETUP.md
- **Plugin hooks:** at SessionStart they inject context from earlier sessions and auto-import `.engram/manifest.json`. At UserPromptSubmit they may capture prompts, and `capture_prompt` defaults to true. Source: https://raw.githubusercontent.com/Gentleman-Programming/engram/main/docs/PLUGINS.md

## Risks for this project

1. **Labels firewall.** A memory saved during an `eval/` session ("receipt X should flag rule Y") would be injected into later pipeline sessions automatically. That is a side channel around rule 1.
2. **Prompt capture is on by default.** Redaction needs manual `<private>` tags.
3. **Files inside the repo.** `engram init` and `engram sync` write `.engram/` into the repo, and sync exports every observation of the project. `.engram/` must be gitignored before anything else.
4. **Churn.** Three releases in a week, one breaking, with open issues about resuming sessions.
5. **Overlap.** CLAUDE.md, Claude Code auto-memory, and Spec Kit's `.specify/memory/` plus the spec files already cover most of what it would store.

## Recommendation

- **Not for the next three days.** Decisions live in committed ADRs, the spec and `AI_NOTES.md`, where reviewers can see them. Cross-session context lives in CLAUDE.md and auto-memory.
- **To evaluate it after delivery,** use the safest setup:
  - bare MCP only, with no plugin hooks;
  - `.engram/` gitignored, never `engram sync` or Cloud;
  - `ENGRAM_NO_UPDATE_CHECK=1`;
  - a CLAUDE.md rule never to store receipt IDs, labels, notes or eval outcomes in it, and never to use it in `eval/` sessions.
