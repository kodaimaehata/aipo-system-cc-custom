---
description: Run Codex CLI as a reviewer and save a review report (auto-selects code vs document review).
---

# /codex_review

**Usage**: `/codex_review [RepoOrLayerPath] [lang: ja|en]`

Runs Codex CLI to review Claude Code’s recent changes and saves the result as a Markdown report.

## Behavior (auto)
- If code changes are detected (e.g., `*.py`, `*.ts`, `*.js`): runs a diff-based review (Codex reviews the current Git diff)
- Otherwise (docs/config/skill files): uses a prompt-based targeted review (`codex exec`) with explicit file scope and review criteria

## Inputs
- Optional: repo/layer path (default: current working directory)
- Optional: `lang: ja|en` (recommended; otherwise the skill chooses based on chat language)

## Execution
1. Read `.claude/skills/codex-review/SKILL.md` and execute its instructions.
