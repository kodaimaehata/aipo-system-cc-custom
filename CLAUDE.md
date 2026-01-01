# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIPO System (AI Product Owner) - A workflow management system for AI-assisted project execution. Originally created by みやっちさん (@miyatti) as a Notion-based system, adapted here for Claude Code and Codex CLI.

The system uses **fractal decomposition**: Goals → SubLayers (complex sub-goals) → Tasks (atomic work units).

## Commands

This repository is documentation-focused with helper Python scripts. No build/test toolchain.

```bash
# Initialize a new AIPO project
python3 .claude/scripts/init_program.py --project "<name>" --goal "<goal>" --preset general

# Validate project YAML files
python3 .claude/scripts/validate_program.py --project "<name>"

# Generate task command files from tasks.yaml
python3 .claude/scripts/generate_commands.py --project "<name>"

# Search content (paths contain spaces)
rg "pattern" "src/aipo (AI-PO) system"
```

## AIPO Workflow Phases

Use slash commands to execute each phase:

| Command | Skill | Purpose |
|---------|-------|---------|
| `/sense` | aipo-sense | Initialize project/sublayer, gather context |
| `/focus` | aipo-focus | Decompose goal into SubLayers and Tasks |
| `/discover` | aipo-discover | Generate execution commands for tasks |
| `/deliver` | aipo-deliver | Execute task and update status |
| `/operation` | aipo-operation | Weekly review and inventory reports |

## Architecture

### Dual Implementation
- `.claude/` - Claude Code skills with slash commands
- `.codex/` - Codex CLI skills (parallel implementation)

Both share the same core schemas (aipo-core) and produce compatible artifacts.

### Key Directories
- `.claude/skills/` - Phase skills (aipo-core, aipo-sense, aipo-focus, aipo-discover, aipo-deliver, aipo-operation)
- `.claude/commands/` - Slash command definitions
- `.claude/scripts/` - Python helper utilities
- `programs/` - Individual project directories (each is its own Git repo, not tracked by parent)
- `src/aipo (AI-PO) system/` - Original AIPO documentation source

### Core Data Files (per layer)
All YAML files must be **JSON-compatible** (no YAML-specific features like anchors):
- `layer.yaml` - Layer metadata (goal, owner, deadline)
- `context.yaml` - Context document index
- `tasks.yaml` - Execution plan with sublayers and tasks

### Layer Structure
```
programs/{project}/
├── layer.yaml
├── context.yaml
├── tasks.yaml
├── context/           # Gathered context documents
├── documents/         # Generated deliverables
├── commands/          # Task execution commands
└── sublayers/         # Nested layers (recursive)
```

## Conventions

- Quote paths with spaces in shell commands
- Keep files UTF-8
- Use Conventional Commits: `docs:`, `feat:`, `fix:`
- Avoid renaming files (breaks internal links with URL-encoded filenames)
- New docs follow prefixes: `CMD_<area>_*` for commands, `CTX_<topic>_*` for context
