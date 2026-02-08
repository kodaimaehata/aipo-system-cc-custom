---
name: aipo-deliver
description: AIPO Deliver phase for Claude Code. Execute a selected task from `tasks.yaml`, using a generated `commands/{task.command}.md` when available, and update task status plus deliverables. Triggers: /deliver, execute task, implement/research work item.
---

# AIPO Deliver Skill

## Description
Implements the **Deliver** phase. Executes tasks and produces outcomes. Corresponds to `CMD_aipo_04_deliver`.

## Usage
Run this to execute a task.
**Triggers**: `/deliver`, "Execute task"

## Instructions

### Phase 1: Task Selection
1. Resolve the target layer directory (see `aipo-core` “Layer Directory Resolution”).
2. Read `tasks.yaml` in the target layer directory.
3. List "pending" tasks.
3. If no Task ID is provided in input, ask user to select one.

### Phase 2: Context Collection (Auto-Research)
Before executing the core task:
1. Search the workspace for information relevant to the task (e.g., team members, tech stack, existing docs).
2. Use web research only if available and approved.
2. Save this as `context/T[ID]_[Subject].md`.
3. Link it in `context.yaml`.

### Phase 3: Execution
1. Check if a Command file exists (`commands/{task.command}.md`).
2. If yes, read and **follow its instructions** (Phased execution).
3. If no:
   - If `command_template_ref` is set on the task, open it and adapt a task-specific execution plan.
   - Otherwise propose a minimal execution plan, ask for confirmation if it changes files, then execute.

### Phase 3.5: Save Deliverables
When saving deliverables to `documents/`:
1. Name files using `T{ID}_description.md` format (e.g., `T001_findings.md`).
2. If a task produces multiple deliverables, distinguish by the description part (e.g., `T001_findings.md`, `T001_appendix.md`).
3. See aipo-core "Document Naming Convention" for full rules.

### Phase 4: Feedback
1. Update `tasks.yaml`: Mark task as `completed`.
2. Report deliverables to the user.
