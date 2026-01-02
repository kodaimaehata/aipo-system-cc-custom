---
name: aipo-core
description: Core schemas, directory layout, and operating rules for the AIPO (AI Product Owner) workflow in Claude Code. Use with the phase skills (aipo-sense/aipo-focus/aipo-discover/aipo-deliver).
---

# AIPO Core Skill

## Description
Provides the core definitions, file structures, and data schemas for the AIPO (AI Product Owner) system. This skill is foundational and should be referenced by other AIPO skills.

## Core Concepts

### 1. Fractal Decomposition
AIPO operates on a recursive structure where every objective is treated as a **Layer**.
- **Root Layer**: The top-level project.
- **SubLayer**: A complex sub-goal that requires its own context and breakdown.
- **Task**: An atomic unit of work that can be executed directly within the current layer.

### 2. File Structure Standard
In this repository, AIPO artifacts MUST be created under `programs/{project_name}/` (not `Flow/`).

All layers must strictly follow this directory structure:

```
programs/
└── [project_name]/                 <-- Root Layer Root (= Program Root)
    ├── README.md                   <-- Optional
    ├── .gitignore                  <-- Optional
    ├── layer.yaml                  <-- Definition
    ├── context.yaml                <-- Context Index
    ├── tasks.yaml                  <-- Execution Plan (created/updated in Focus phase)
    ├── variables.yaml              <-- Optional (Abstract mode only)
    ├── context/                    <-- Context Documents
    │   ├── 01_team.md
    │   ├── 02_resources.md
    │   └── ...
    ├── documents/                  <-- Generated Documents / Deliverables
    ├── commands/                   <-- Execution commands (created in Discover phase)
    └── sublayers/                  <-- Child Layers
        ├── [SubLayer1]/
        └── [SubLayer2]/
```

### 3. Data Schemas

#### layer.yaml
`layer.yaml` / `context.yaml` / `tasks.yaml` should be written as **JSON-compatible YAML (= pure JSON)** for compatibility with `.claude/scripts/validate_program.py`.

```json
{
  "version": "1.0",
  "project_name": "example-project",
  "layer_id": "L001",
  "layer_name": "Root",
  "workflow_preset": "general",
  "goal": {
    "description": "Main Goal",
    "success_criteria": []
  },
  "mode": "concrete",
  "owner": "User Name",
  "deadline": null,
  "parent_layer_id": null,
  "created_at": "YYYY-MM-DD",
  "updated_at": "YYYY-MM-DD"
}
```

#### context.yaml
```json
{
  "version": "1.1",
  "project_name": "example-project",
  "layer_id": "L001",
  "generated_at": "YYYY-MM-DD",
  "parent_context_dir": null,
  "context_collection": {
    "methods": ["local_workspace", "web_search", "external_paths"],
    "local_workspace_config": {
      "priority_folders": [],
      "perspectives": []
    },
    "web_search_config": {
      "prefer_primary_sources": true,
      "keywords": []
    },
    "external_paths_config": {
      "paths": []
    },
    "collected_at": "YYYY-MM-DD",
    "confirmed_by": "user"
  },
  "context_documents": [
    {
      "name": "Team",
      "path": "context/01_team.md",
      "summary": "Who is involved and roles",
      "source_method": "local_workspace"
    }
  ]
}
```

**`context_collection` Field (Optional):**
- `methods`: Array of collection method IDs (`local_workspace`, `web_search`, `external_paths`)
- `*_config`: Configuration for each selected method
- `confirmed_by`: Who confirmed the selection (`user`, `ai`, or `cli`)

**`source_method` in context_documents (Optional):**
- Tracks which collection method produced each document

#### tasks.yaml
```json
{
  "version": "2.2",
  "project_name": "example-project",
  "layer_id": "L001",
  "generated_at": "YYYY-MM-DD",
  "decomposition_type": "recursive",
  "focus_strategy": "generic",
  "focus_strategy_reason": "Why this decomposition strategy fits the goal",
  "focus_strategy_confirmed_by": "ai",
  "sublayers": [
    {
      "id": "SG1",
      "goal": "Sub Goal",
      "priority": "P0",
      "status": "pending_init",
      "mode": "concrete",
      "path": "sublayers/SG1_subgoal"
    }
  ],
  "tasks": [
    {
      "id": "T001",
      "name": "Task Name",
      "type": "research",
      "status": "pending",
      "estimate": "4h",
      "command": "T001_Task_Name",
      "command_template_ref": null,
      "notes": ""
    }
  ],
  "command_generation": {
    "enabled": true,
    "target_dir": "commands",
    "naming_pattern": "{task_id}_{task_name}.md"
  }
}
```

## Rules
- **Context Inheritance**: SubLayers MUST reference their parent's context.
- **Atomic Tasks**: If a task is complex, turn it into a SubLayer.
- **Self-Contained**: Each layer contains everything needed to execute it.

## Layer Directory Resolution (Rule)
When a phase skill needs a target layer directory:
1. If the user provides a layer path, use it (must contain `layer.yaml`).
2. Else if the current working directory contains `layer.yaml`, treat it as the layer root.
3. Else search under `programs/` for candidate `layer.yaml` files (including nested `sublayers/`).
4. If multiple candidates match, ask the user to choose.
5. Treat `Flow/` as legacy/not supported in this repo unless the user explicitly asks to use it.
