---
description: Run Codex CLI as a reviewer and save a review report.
---

# /codex_review

**Usage**: `/codex_review [RepoOrLayerPath] [lang: ja|en]`

Claude Code がレビュープロンプトを生成し、対象ファイルを指定して Codex CLI でレビューを実行します。

## Execution

1. Read `.claude/skills/codex-review/SKILL.md`
2. Analyze the changes made in this session
3. Identify target files for review
4. Generate a review prompt describing:
   - Intent of the changes
   - Specific review focus areas
   - Expected output format
5. Execute the script with `--prompt` and `--files` parameters

## Inputs

- Optional: repo/layer path (default: current working directory)
- Optional: `lang: ja|en` (recommended; otherwise auto-detected)
