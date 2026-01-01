---
description: Generate a weekly review / inventory report for the current layer or a specified AIPO program/layer (AIPO Operation).
---

# /operation

**Usage**: `/operation [LayerPath|ProjectName] [lang: ja|en]`

Generates a weekly review report under `weekly_review/` for the target layer (root + nested sublayers).

## Inputs
- Optional: layer path (recommended when multiple layers exist), e.g. `programs/<project_name>` or `programs/<project_name>/sublayers/<sublayer_name>`
- Optional: project name, e.g. `FlyHigh2-Planning`
- Optional: `lang: ja|en`

## Execution
1. Read `.claude/skills/aipo-core/SKILL.md` and follow its rules.
2. Read `.claude/skills/aipo-operation/SKILL.md` and execute its instructions.

