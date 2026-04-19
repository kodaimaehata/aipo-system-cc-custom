---
name: aipo-archive-project
description: Archive an AIPO project by moving a project folder under programs/archived and recording purpose + activities (and artifact summary) into programs/archived_projects.md.
version: 1.0.0
author: Hermes Agent
license: MIT
---

# AIPO Project Archive

Use this skill when the user wants to archive, retire, suspend, or close a project under `programs/`.

## What this skill does

- Moves the target project directory into `programs/archived/`
- Appends a summary row to `programs/archived_projects.md`
- Records `purpose`, `activities`, source path, archive path, artifact summary, and an optional note

## Preconditions

Before running the archive script:

1. Confirm you are in the target repository root, or pass `--base-dir` explicitly.
2. Resolve the target project uniquely.
3. If the user provided a partial name and it is ambiguous, ask which project to archive.
4. Because this operation moves directories, confirm intent if the target is not explicit.

## Command

Run from the repository root:

```bash
python3 ~/.hermes/skills/aipo-archive-project/scripts/archive_project.py "<project-or-path>"
```

Options:

- `--base-dir "programs"`: project search root (default: `programs`)
- `--archive-dir "programs/archived"`: archive destination (default: `--base-dir/archived`)
- `--record-file "programs/archived_projects.md"`: archive metadata file (default)
- `--note "..."`: optional memo
- `--purpose "..."`: project purpose to record; inferred from `layer.yaml` or docs if omitted
- `--activities "..."`: activity summary to record; inferred from `tasks.yaml` and artifacts if omitted

## Procedure

1. Resolve the target from either:
   - a full existing directory path, or
   - a unique folder name under `programs/`
2. Run:

```bash
python3 ~/.hermes/skills/aipo-archive-project/scripts/archive_project.py "<project-or-path>"
```

3. The script moves the project to `programs/archived/`.
4. The script appends a row to `programs/archived_projects.md` with:
   - `archived_at`
   - `project_name`
   - `purpose`
   - `activities`
   - `source_path`
   - `archive_path`
   - `summary`
   - `note`
5. Report the resulting source path, archive path, and record file to the user.

## Notes

- This skill assumes the repository uses the AIPO `programs/` layout.
- If the repository root is not the current working directory, either `cd` there first or pass `--base-dir` and related paths explicitly.
- `programs/archived_projects.md` can later be used by AIPO sense/discovery workflows as historical context.
