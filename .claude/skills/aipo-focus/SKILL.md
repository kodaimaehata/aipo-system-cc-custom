---
name: aipo-focus
description: AIPO Focus phase for Claude Code. Decompose a layer goal into SubLayers and Tasks, select a `focus_strategy`, and generate/update `tasks.yaml` plus `sublayers/*` placeholders and `documents/*` summaries. Triggers: /focus, break down goal, plan tasks.
---

# AIPO Focus Skill

## Description
Implements the **Focus** phase of the AIPO system. This skill handles Goal Decomposition, identifying SubLayers vs Tasks, and generating the Execution Plan (`tasks.yaml`). It corresponds to `CMD_aipo_02_focus`.

## Usage
Run this skill after `sense` to break down the goal.
**Triggers**: `/focus`, "Decompose goal", "Plan tasks"

## Instructions

### Phase 1: Context Loading
1. Resolve the target layer directory (see `aipo-core` “Layer Directory Resolution”).
2. Read the layer’s `layer.yaml` and `context.yaml`. Understand the Goal and Constraints.
3. If `context.yaml.parent_context_dir` is set, load the parent context as needed (inheritance).

### Phase 1.5: Focus Strategy (Required)
Select and record a `focus_strategy` for this decomposition:
- `product_manager` (product discovery/roadmap)
- `system_architect` (systems/platform/build)
- `content_strategist` (content/editorial)
- `generic` (fallback)
If unclear, propose one with a 1–2 line reason and ask the user to confirm.

### Phase 2: Decomposition (The AIPO Logic)
Analyze the Goal and break it down. Apply the **Fractal Decomposition** principle:

**Create a SubLayer (SG) if:**
- The item is complex and requires its own context.
- It involves multiple sub-tasks.
- It can be delegated to a specific role/person (e.g., "Design Phase").

**Create a Task (T) if:**
- It is an atomic unit of work (1-2 days).
- It is a management/verification task.
- It is a specific terminal command execution.

### Phase 3: Proposal
Present the proposed breakdown to the user:
- **SubLayers**: List ID, Goal, Priority.
- **Tasks**: List ID, Name, Type.
Ask for approval before writing files.

### Phase 4: Generation
Upon approval:

1. **Update `tasks.yaml`**:
   - Write the full plan using the schema from `aipo-core`.
   - Record `focus_strategy`, `focus_strategy_reason`, and `focus_strategy_confirmed_by`.
   - Use JSON-compatible YAML (= pure JSON) for compatibility with the validator script.
   - **CRITICAL**: For every non-management task, set a `command` name (e.g., `T001_Research`).
   - Only `management` / `coordination` / `verification` tasks may use `command: null`.
   - Ensure `command_generation.target_dir` matches the repo convention (`commands`).
   
2. **Create SubLayer Folders**:
   - `sublayers/[SG1_Name]/` (Empty, ready for `/sense` within that directory).
   - `sublayers/[SG2_Name]/`

3. **Generate Documents**:
   - Create summary documents in `documents/` based on successful decomposition analysis.
   - Focus-phase analysis documents (e.g., `strategic_analysis.md`) are not tied to a specific task and may use semantic names.
   - If any document is associated with a task, use the `T{ID}_description.md` naming convention (see aipo-core "Document Naming Convention").

### Phase 5: Next Steps
- Advise the user to run `/sense` on the high-priority SubLayers (Recursive Step).
- Advise the user to run `/discover` (or just execute) for atomic Tasks.
