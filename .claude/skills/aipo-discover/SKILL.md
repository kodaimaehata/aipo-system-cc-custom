---
name: aipo-discover
description: AIPO Discover phase for Claude Code. Read `tasks.yaml` and generate per-task execution command files under `commands/` (HITL-integrated), using `command_template_ref` when available. Triggers: /discover, generate commands, turn tasks into executable steps.
---

# AIPO Discover Skill

## Description
Implements the **Discover** phase. Generates detailed execution plans (Commands) for each task defined in `tasks.yaml`. Corresponds to `CMD_aipo_03_discover`.

## Usage
Run this after `focus`.
**Triggers**: `/discover`, "Generate commands"

## Instructions

### Phase 1: Analysis
1. Resolve the target layer directory (see `aipo-core` “Layer Directory Resolution”).
2. Read `tasks.yaml` in the target layer directory.
3. Identify tasks that need execution (excluding simple management tasks if command is null).
4. Identify the `command_template_ref` if present.

### Phase 2: Command Generation
For each identified task:
1. **Create Directory**: Ensure `commands/` exists in the layer (or use `tasks.yaml.command_generation.target_dir`).
2. **Generate File**: Create `commands/{task.command}.md`.
3. **Content Structure** (HITL Integrated):
   - **Header**: Goal, Type (HITL), Estimate.
   - **Phase 1 (AI)**: Automated steps (research, drafting).
   - **HITL Phase (Human)**: Verification, decision, approval.
   - **Phase 2 (AI)**: Finalization, output generation.
   - **Instructions**: Specific instructions for `aipo-deliver` to execute this command.
4. If `command_template_ref` is set, open the referenced template (prefer local files under `src/aipo (AI-PO) system/CTX_command_templates/`) and adapt it for the task and layer context.

### Phase 3: Reporting
- Detail which command files were created/updated.
- Advise running `/deliver` to execute them.
