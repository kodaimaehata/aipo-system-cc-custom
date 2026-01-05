---
name: aipo-sense
description: AIPO Sense phase for Claude Code. Initialize a new root layer (program) or sublayer and generate `layer.yaml`, `context.yaml`, and initial `context/*.md` under `programs/{project_name}/`. Triggers: /sense, initialize project/layer, add sublayer, collect context.
---

# AIPO Sense Skill

## Description
Implements the **Sense** phase of the AIPO system. This skill handles Project Initialization, Layer Creation, and Context Collection. It corresponds to `CMD_aipo_01_sense`.

## Usage
Run this skill when starting a new project or adding a new SubLayer.
**Triggers**: `/sense`, "Initialize project", "Add sublayer"

## Instructions

### Phase 0: Mode Determination
Determine the operation mode based on the user's input and current directory context:
1. **New Project**: If no parent layer is specified and starting fresh.
2. **SubLayer Creation**: If a parent layer is specified or implied.
3. **Re-Initialization**: If the layer already exists.

### Phase 1: Information Gathering
Ensure you have the following information. If missing, ask the user:
- **Project Name (directory)**: e.g., `my-project` (used as `programs/{project_name}/`)
- **Layer Name**: e.g., "Performance Improvement" (default: "Root" for a new program)
- **Goal**: What needs to be achieved.
- **Owner**: (Default to current user)
- **Mode**: "concrete" (default) or "abstract".
- **Parent Layer (optional)**: A path to the parent layer directory (must contain `layer.yaml`) for SubLayer creation.
  - For a program root layer, this is typically `programs/{project_name}`.

### Phase 2: Structure Creation
1. **Resolve the target layer directory** (see `aipo-core` "Layer Directory Resolution"):
   - **Root Layer (Program Root)**: `programs/[project_name]/`
   - **SubLayer**: `[ParentLayerDir]/sublayers/[LayerName]/`
2. If the target directory already exists, **ask before modifying/overwriting**.
3. **Subdirectories**: `sublayers/`, `documents/`, `context/`, `commands/`.
4. **(Recommended) Initialize via script** (run from repo root):
   ```bash
   python3 .claude/scripts/init_program.py --project "{project_name}" --goal "{goal}" --preset general
   ```
   - **Git initialization**: The script runs `git init` by default (to treat `programs/{project_name}/` as an independent repository).
   - To skip Git initialization, add `--no-git-init`.
   - The parent repository's `.gitignore` excludes `programs/*`, which helps prevent accidentally committing nested repositories.

### Phase 3: Layer Initialization
Create the following files in the layer directory:

#### 3a. layer.yaml
Follow the schema in `aipo-core`.
- Generate a unique `layer_id`.
- Functionally describe the Goal.
- If this is a SubLayer, read the parent `layer.yaml` and set `parent_layer_id` accordingly.
- Use JSON-compatible YAML (= pure JSON) for compatibility with the validator script.

#### 3b. Context Collection (Auto-Research)
Use local workspace search/read tools (e.g., `ls`, `rg`) to gather context relevant to the Goal. Use web research only if available and approved.
- **Team Structure**: Who is involved?
- **Existing Resources**: Related code, docs, rules.
- **Constraints**: Deadlines, tech stack.

**Action**: Create markdown files in `context/`:
- `01_team.md`
- `02_resources.md`
- `03_constraints.md`

#### 3c. context.yaml
Create an index file referencing the collected context documents.
- If this is a SubLayer, MUST reference the parent context via `parent_context_dir`.
  - Prefer a repo-root-relative path to the parent `context/` directory (e.g., `programs/.../context`).

### Phase 4: Reports
- Confirm the created structure to the user.
- Suggest running `/focus` (AIPO Focus) as the next step.
