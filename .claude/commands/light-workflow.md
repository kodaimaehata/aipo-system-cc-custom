---
description: Orchestrate a lightweight mini-project under mini-projects/.
---

# /light-workflow

**Usage**: `/light-workflow [goal_or_run_path]`

Loads the lightweight workflow skill for small tools, small apps, PoCs, and document deliverables managed under `mini-projects/`.

## Inputs
- Optional: goal, title, or short natural-language brief
- Optional: existing run path such as `mini-projects/active/<date>_<slug>`
- Optional: desired slug or title for a new run

## Execution
1. Read `.claude/skills/light-workflow/SKILL.md` and execute its instructions.
2. If needed, also read companion skills under `.claude/skills/light-planning/` and `.claude/skills/light-delivery/`.
