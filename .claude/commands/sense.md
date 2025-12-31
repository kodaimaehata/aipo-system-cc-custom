---
description: Initialize a new project or sublayer (AIPO Sense).
---

# /sense

**Usage**:
- New program: `/sense "<Goal>" "<project_name>"`
- New sublayer (run inside parent layer dir): `/sense "<Goal>" "<sublayer_name>"`

Loads the **AIPO Sense Skill** to initialize a project or sublayer.

## Inputs
- Goal (required)
- Project name (required for new program; creates `programs/{project_name}/`)
- Sublayer name (required for new sublayer; creates under `sublayers/`)
- Optional: parent layer path (for sublayer creation), mode (`concrete|abstract`), owner, deadline

## Execution
1. Read `.claude/skills/aipo-core/SKILL.md` and follow its rules.
2. Read `.claude/skills/aipo-sense/SKILL.md` and execute its instructions.
