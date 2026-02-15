#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class ValidationError(Exception):
    pass


def _read_json_yaml(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValidationError(f"missing file: {path}")
    except json.JSONDecodeError as e:
        raise ValidationError(f"invalid JSON-compatible YAML in {path}: {e}")


def _require(mapping: dict, key: str, *, path: str) -> Any:
    if key not in mapping:
        raise ValidationError(f"missing key '{path}{key}'")
    return mapping[key]


PROJECT_ID_PATTERN = re.compile(r"^P\d{4}$")


def _validate_project_id(value: Any, path: str) -> None:
    if not isinstance(value, str) or not PROJECT_ID_PATTERN.match(value):
        raise ValidationError(f"{path} must be 'P' + 4 digits (e.g. P0001)")


def _find_project_id_in_ancestors(base_dir: Path) -> str | None:
    # Legacy sublayers may not have project_id in local files.
    # Walk parents and reuse the first valid project_id found.
    for parent in [base_dir, *base_dir.parents]:
        for filename in ("layer.yaml", "context.yaml", "tasks.yaml"):
            candidate_path = parent / filename
            if not candidate_path.exists():
                continue
            try:
                payload = _read_json_yaml(candidate_path)
            except ValidationError:
                continue
            if not isinstance(payload, dict):
                continue
            project_id = payload.get("project_id")
            if isinstance(project_id, str) and PROJECT_ID_PATTERN.match(project_id):
                return project_id
    return None


def _resolve_expected_project_id(base_dir: Path, layer: dict, context: dict, tasks: dict) -> str:
    found: dict[str, str] = {}
    for scope, payload in (("layer", layer), ("context", context), ("tasks", tasks)):
        if "project_id" in payload:
            value = payload.get("project_id")
            _validate_project_id(value, path=f"{scope}.project_id")
            found[scope] = value

    unique_values = set(found.values())
    if len(unique_values) > 1:
        raise ValidationError(
            "project_id mismatch across files: "
            + ", ".join(f"{scope}={value}" for scope, value in found.items())
        )
    if len(unique_values) == 1:
        return next(iter(unique_values))

    inherited = _find_project_id_in_ancestors(base_dir.parent)
    if inherited is not None:
        return inherited

    raise ValidationError(
        "missing project_id in layer/context/tasks and no ancestor project_id found "
        f"(base={base_dir})"
    )


def _is_safe_relative_path(path_str: str) -> bool:
    p = Path(path_str)
    if p.is_absolute():
        return False
    if not p.parts:
        return False
    if ".." in p.parts:
        return False
    return True


def _validate_layer(layer: dict, *, expected_project_id: str) -> None:
    for key in [
        "version",
        "project_name",
        "layer_id",
        "layer_name",
        "workflow_preset",
        "goal",
        "mode",
        "owner",
    ]:
        _require(layer, key, path="layer.")
    if "project_id" in layer:
        _validate_project_id(layer["project_id"], path="layer.project_id")
        if layer["project_id"] != expected_project_id:
            raise ValidationError(
                f"layer.project_id mismatch: expected {expected_project_id}, got {layer['project_id']}"
            )
    goal = _require(layer, "goal", path="layer.")
    if not isinstance(goal, dict) or "description" not in goal:
        raise ValidationError("layer.goal.description is required")


def _validate_context(context: dict, *, expected_project_id: str) -> None:
    for key in ["version", "project_name", "layer_id", "generated_at", "context_documents"]:
        _require(context, key, path="context.")
    if "project_id" in context:
        _validate_project_id(context["project_id"], path="context.project_id")
        if context["project_id"] != expected_project_id:
            raise ValidationError(
                f"context.project_id mismatch: expected {expected_project_id}, got {context['project_id']}"
            )
    docs = context["context_documents"]
    if not isinstance(docs, list):
        raise ValidationError("context.context_documents must be a list")
    for i, doc in enumerate(docs):
        if not isinstance(doc, dict):
            raise ValidationError(f"context.context_documents[{i}] must be an object")
        for key in ["name", "path", "summary"]:
            if key not in doc:
                raise ValidationError(f"context.context_documents[{i}].{key} is required")


def _validate_tasks(tasks: dict, *, expected_project_id: str) -> None:
    required = [
        "version",
        "project_name",
        "layer_id",
        "generated_at",
        "decomposition_type",
        "focus_strategy",
        "focus_strategy_reason",
        "focus_strategy_confirmed_by",
        "sublayers",
        "tasks",
        "command_generation",
    ]
    for key in required:
        _require(tasks, key, path="tasks.")
    if "project_id" in tasks:
        _validate_project_id(tasks["project_id"], path="tasks.project_id")
        if tasks["project_id"] != expected_project_id:
            raise ValidationError(
                f"tasks.project_id mismatch: expected {expected_project_id}, got {tasks['project_id']}"
            )

    if tasks["focus_strategy_confirmed_by"] not in {"user", "ai"}:
        raise ValidationError("tasks.focus_strategy_confirmed_by must be 'user' or 'ai'")

    if not isinstance(tasks["sublayers"], list):
        raise ValidationError("tasks.sublayers must be a list")

    if not isinstance(tasks["tasks"], list):
        raise ValidationError("tasks.tasks must be a list")

    cmd_gen = tasks["command_generation"]
    if not isinstance(cmd_gen, dict):
        raise ValidationError("tasks.command_generation must be an object")
    if cmd_gen.get("enabled") not in {True, False}:
        raise ValidationError("tasks.command_generation.enabled must be a boolean")

    for i, sublayer in enumerate(tasks["sublayers"]):
        if not isinstance(sublayer, dict):
            raise ValidationError(f"tasks.sublayers[{i}] must be an object")
        for key in ["id", "goal"]:
            if key not in sublayer:
                raise ValidationError(f"tasks.sublayers[{i}].{key} is required")
        if not isinstance(sublayer["id"], str) or not sublayer["id"].strip():
            raise ValidationError(f"tasks.sublayers[{i}].id must be a non-empty string")
        if not isinstance(sublayer["goal"], str) or not sublayer["goal"].strip():
            raise ValidationError(f"tasks.sublayers[{i}].goal must be a non-empty string")

        mode = sublayer.get("mode")
        if mode is not None and mode not in {"concrete", "abstract"}:
            raise ValidationError(f"tasks.sublayers[{i}].mode must be 'concrete' or 'abstract' when set")

        path_value = sublayer.get("path")
        if path_value is not None:
            if not isinstance(path_value, str) or not path_value.strip():
                raise ValidationError(f"tasks.sublayers[{i}].path must be a non-empty string when set")
            if not _is_safe_relative_path(path_value.strip()):
                raise ValidationError(f"tasks.sublayers[{i}].path must be a safe relative path")

    for i, task in enumerate(tasks["tasks"]):
        if not isinstance(task, dict):
            raise ValidationError(f"tasks.tasks[{i}] must be an object")
        for key in ["id", "name", "type", "status", "command", "command_template_ref"]:
            if key not in task:
                raise ValidationError(f"tasks.tasks[{i}].{key} is required")

        task_type = task["type"]
        command = task["command"]
        if task_type in {"management", "coordination", "verification"}:
            if command is not None:
                raise ValidationError(f"tasks.tasks[{i}].command must be null for management/coordination/verification")
        else:
            if not isinstance(command, str) or not command.strip():
                raise ValidationError(f"tasks.tasks[{i}].command is required for type={task_type}")

        template_ref = task["command_template_ref"]
        if template_ref is not None and not isinstance(template_ref, str):
            raise ValidationError(f"tasks.tasks[{i}].command_template_ref must be a string or null")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AIPO program folder (JSON-compatible YAML).")
    parser.add_argument("--project", help="Project directory name under programs/.")
    parser.add_argument("--path", help="Direct path to the program folder (overrides --project).")
    args = parser.parse_args()

    if args.path:
        base_dir = Path(args.path)
    elif args.project:
        base_dir = Path("programs") / args.project
    else:
        raise SystemExit("error: provide --project or --path")

    errors: list[str] = []
    try:
        layer = _read_json_yaml(base_dir / "layer.yaml")
        context = _read_json_yaml(base_dir / "context.yaml")
        tasks = _read_json_yaml(base_dir / "tasks.yaml")

        if not isinstance(layer, dict) or not isinstance(context, dict) or not isinstance(tasks, dict):
            raise ValidationError("layer/context/tasks files must each contain a JSON object at the top level")

        expected_project_id = _resolve_expected_project_id(base_dir, layer, context, tasks)
        _validate_layer(layer, expected_project_id=expected_project_id)
        _validate_context(context, expected_project_id=expected_project_id)
        _validate_tasks(tasks, expected_project_id=expected_project_id)
    except ValidationError as e:
        errors.append(str(e))

    if errors:
        for err in errors:
            print(f"[ERROR] {err}")
        return 1

    print(f"[OK] Valid: {base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
