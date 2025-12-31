#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class CommandGenError(Exception):
    pass


def _read_json_yaml(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CommandGenError(f"missing file: {path}")
    except json.JSONDecodeError as e:
        raise CommandGenError(f"invalid JSON-compatible YAML in {path}: {e}")


def _safe_filename(value: str) -> str:
    value = value.strip()
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^\w\-\.\u0080-\uffff]+", "", value)
    value = re.sub(r"_{2,}", "_", value).strip("_").strip(".")
    if not value or value in {".", ".."}:
        return "task"
    return value


def _is_safe_relative_path(path_str: str) -> bool:
    """Check if path is safe (no traversal, no absolute)."""
    p = Path(path_str)
    if p.is_absolute():
        return False
    if not p.parts:
        return False
    if ".." in p.parts or "." in p.parts:
        return False
    return True


def _is_within_base(base_dir: Path, target_path: Path) -> bool:
    """Check if target_path is within base_dir."""
    try:
        target_path.resolve().relative_to(base_dir.resolve())
        return True
    except ValueError:
        return False


def _render_command_md(task: dict) -> str:
    task_id = task.get("id", "")
    task_name = task.get("name", "")
    template_ref = task.get("command_template_ref")

    template_line = f"- command_template_ref: `{template_ref}`" if template_ref else "- command_template_ref: `null`"
    return (
        f"# {task_id}: {task_name}\n\n"
        "## Goal\n"
        "- （このタスクで達成したいことを1〜2行で）\n\n"
        "## Done (Acceptance Criteria)\n"
        "- （完了条件を箇条書きで）\n\n"
        "## Inputs\n"
        "- （必要な前提情報・参照ファイル・URLなど）\n\n"
        "## Steps\n"
        "1. \n"
        "2. \n\n"
        "## Outputs\n"
        "- （作成/更新するファイル、成果物の場所）\n\n"
        "## Notes\n"
        f"{template_line}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate commands/*.md from tasks.yaml (JSON-compatible YAML).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="Project directory name under programs/.")
    group.add_argument("--path", help="Direct path to the layer folder (overrides --project).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing command files.")
    parser.add_argument("--include-management", action="store_true", help="Also generate commands for command=null tasks.")
    args = parser.parse_args()

    if args.path:
        base_dir = Path(args.path)
    else:
        base_dir = Path("programs") / args.project
    tasks_path = base_dir / "tasks.yaml"
    tasks = _read_json_yaml(tasks_path)
    if not isinstance(tasks, dict):
        raise SystemExit("[ERROR] tasks.yaml must be a JSON object")

    cmd_cfg = tasks.get("command_generation") or {}
    target_dir = cmd_cfg.get("target_dir") or "commands"
    naming_pattern = cmd_cfg.get("naming_pattern") or "{task_id}_{task_name}.md"

    # Validate target_dir for path traversal
    if not _is_safe_relative_path(target_dir):
        raise SystemExit(f"[ERROR] command_generation.target_dir is unsafe: {target_dir!r}")

    tasks_list = tasks.get("tasks")
    if not isinstance(tasks_list, list):
        raise SystemExit("[ERROR] tasks.tasks must be a list")

    generated = 0
    for task in tasks_list:
        if not isinstance(task, dict):
            continue
        if task.get("command") is None and not args.include_management:
            continue

        task_id = str(task.get("id", "")).strip()
        task_name = str(task.get("name", "")).strip()
        filename = naming_pattern.format(task_id=_safe_filename(task_id), task_name=_safe_filename(task_name))
        out_path = base_dir / target_dir / filename

        # Verify output path is within base_dir
        if not _is_within_base(base_dir, out_path):
            raise SystemExit(f"[ERROR] Generated path escapes base directory: {out_path}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not args.overwrite:
            continue

        out_path.write_text(_render_command_md(task), encoding="utf-8")
        generated += 1

    print(f"[OK] Generated {generated} command file(s) under {base_dir / target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
