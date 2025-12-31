#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any


class SubLayerSyncError(Exception):
    pass


def _today_iso() -> str:
    return date.today().isoformat()


def _read_json_yaml(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SubLayerSyncError(f"missing file: {path}")
    except json.JSONDecodeError as e:
        raise SubLayerSyncError(f"invalid JSON-compatible YAML in {path}: {e}")


def _write_json_yaml(path: Path, data: object, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _safe_slug(value: str, *, max_len: int = 64) -> str:
    value = value.strip()
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^\w\-\u0080-\uffff]+", "", value)
    value = re.sub(r"_{2,}", "_", value).strip("_")
    if not value:
        value = "sublayer"
    if len(value) > max_len:
        value = value[:max_len].rstrip("_")
    return value


def _is_safe_relative_path(path_str: str) -> bool:
    p = Path(path_str)
    if p.is_absolute():
        return False
    if not p.parts:
        return False
    if ".." in p.parts or "." in p.parts:
        return False
    return True


def _relpath(from_dir: Path, to_dir: Path) -> str:
    return os.path.relpath(str(to_dir), start=str(from_dir))


def _init_sublayer_folder(
    sublayer_dir: Path,
    *,
    project_name: str,
    layer_id: str,
    layer_name: str,
    goal: str,
    workflow_preset: str,
    mode: str,
    owner: str,
    deadline: str | None,
    parent_layer_id: str,
    parent_context_dir: str,
    overwrite: bool,
) -> None:
    (sublayer_dir / "commands").mkdir(parents=True, exist_ok=True)
    (sublayer_dir / "documents").mkdir(parents=True, exist_ok=True)
    (sublayer_dir / "sublayers").mkdir(parents=True, exist_ok=True)
    (sublayer_dir / "context").mkdir(parents=True, exist_ok=True)

    _write_text(
        sublayer_dir / "README.md",
        f"# {layer_name}\n\n"
        f"- layer_id: `{layer_id}`\n"
        f"- parent: `{parent_layer_id}`\n"
        f"- goal: {goal}\n",
        overwrite=overwrite,
    )

    layer_yaml = {
        "version": "1.0",
        "project_name": project_name,
        "layer_id": layer_id,
        "layer_name": layer_name,
        "workflow_preset": workflow_preset,
        "goal": {"description": goal, "success_criteria": []},
        "mode": mode,
        "owner": owner,
        "deadline": deadline,
        "parent_layer_id": parent_layer_id,
        "created_at": _today_iso(),
        "updated_at": _today_iso(),
    }
    _write_json_yaml(sublayer_dir / "layer.yaml", layer_yaml, overwrite=False)

    context_yaml = {
        "version": "1.0",
        "project_name": project_name,
        "layer_id": layer_id,
        "generated_at": _today_iso(),
        "parent_context_dir": parent_context_dir,
        "context_documents": [
            {
                "name": "Overview",
                "path": "context/01_overview.md",
                "summary": "背景・目的・スコープの要約（要更新）",
            },
            {
                "name": "Constraints",
                "path": "context/02_constraints.md",
                "summary": "制約（期限・予算・技術・法務など）（要更新）",
            },
        ],
    }
    _write_json_yaml(sublayer_dir / "context.yaml", context_yaml, overwrite=False)

    tasks_yaml = {
        "version": "2.2",
        "project_name": project_name,
        "layer_id": layer_id,
        "generated_at": _today_iso(),
        "decomposition_type": "recursive",
        "focus_strategy": "generic" if workflow_preset == "general" else "product_manager",
        "focus_strategy_reason": "サブレイヤー初期化のデフォルト（必要に応じて更新）",
        "focus_strategy_confirmed_by": "ai",
        "sublayers": [],
        "tasks": [],
        "command_generation": {
            "enabled": True,
            "target_dir": "commands",
            "naming_pattern": "{task_id}_{task_name}.md",
        },
        "summary": {"sublayer_count": 0, "task_count": 0, "next_action": "focus: tasks分解"},
    }
    _write_json_yaml(sublayer_dir / "tasks.yaml", tasks_yaml, overwrite=False)

    _write_text(
        sublayer_dir / "context" / "01_overview.md",
        "# Overview\n\n- 背景:\n- 目的:\n- スコープ:\n- 非スコープ:\n",
        overwrite=overwrite,
    )
    _write_text(
        sublayer_dir / "context" / "02_constraints.md",
        "# Constraints\n\n- 期限:\n- 予算:\n- 技術:\n- 法務/コンプライアンス:\n- 依存関係:\n",
        overwrite=overwrite,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create sublayer folders/files from a layer folder's tasks.yaml.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="Project directory name under programs/.")
    group.add_argument("--path", help="Direct path to the layer folder (overrides --project).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing sublayer files (README/context stubs).")
    parser.add_argument(
        "--write-back",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write back computed sublayer.path/mode into the layer's tasks.yaml.",
    )
    args = parser.parse_args()

    if args.path:
        base_dir = Path(args.path)
    else:
        base_dir = Path("programs") / args.project
    layer = _read_json_yaml(base_dir / "layer.yaml")
    tasks = _read_json_yaml(base_dir / "tasks.yaml")
    if not isinstance(layer, dict) or not isinstance(tasks, dict):
        raise SystemExit("[ERROR] layer.yaml and tasks.yaml must be JSON objects")

    project_name = str(layer.get("project_name") or args.project)
    parent_layer_id = str(layer.get("layer_id") or "L001")
    workflow_preset = str(layer.get("workflow_preset") or "general")
    mode = str(layer.get("mode") or "concrete")
    owner = str(layer.get("owner") or "owner")
    deadline = layer.get("deadline")

    sublayers = tasks.get("sublayers")
    if not isinstance(sublayers, list):
        raise SystemExit("[ERROR] tasks.yaml: 'sublayers' must be a list")

    updated = False
    created = 0
    for idx, item in enumerate(sublayers):
        if not isinstance(item, dict):
            continue

        sub_id = str(item.get("id") or "").strip()
        sub_goal = str(item.get("goal") or "").strip()
        if not sub_id or not sub_goal:
            raise SystemExit(f"[ERROR] sublayers[{idx}] requires 'id' and 'goal'")

        sub_mode = str(item.get("mode") or mode)
        sub_layer_id = f"{parent_layer_id}-{sub_id}"

        # Determine directory
        path_value = item.get("path")
        if isinstance(path_value, str) and path_value.strip():
            rel_path = path_value.strip()
            if not _is_safe_relative_path(rel_path):
                raise SystemExit(f"[ERROR] sublayers[{idx}].path is not a safe relative path: {rel_path!r}")
            sublayer_dir = base_dir / rel_path
        else:
            # Sanitize sub_id to prevent path traversal
            safe_sub_id = _safe_slug(sub_id, max_len=32)
            dir_name = f"{safe_sub_id}_{_safe_slug(sub_goal)}"
            rel_path = str(Path("sublayers") / dir_name)
            # Verify generated path is safe
            if not _is_safe_relative_path(rel_path):
                raise SystemExit(f"[ERROR] sublayers[{idx}]: generated path is unsafe: {rel_path!r}")
            sublayer_dir = base_dir / rel_path
            if args.write_back:
                item["path"] = rel_path
                updated = True

        if args.write_back and (item.get("mode") is None):
            item["mode"] = sub_mode
            updated = True

        parent_context_dir = _relpath(sublayer_dir, base_dir / "context")
        layer_name = f"{sub_id}_{_safe_slug(sub_goal, max_len=48)}"

        # Create if missing; always ensure folder skeleton exists.
        before = sublayer_dir.exists()
        _init_sublayer_folder(
            sublayer_dir,
            project_name=project_name,
            layer_id=sub_layer_id,
            layer_name=layer_name,
            goal=sub_goal,
            workflow_preset=workflow_preset,
            mode=sub_mode,
            owner=owner,
            deadline=deadline if isinstance(deadline, str) or deadline is None else None,
            parent_layer_id=parent_layer_id,
            parent_context_dir=parent_context_dir,
            overwrite=args.overwrite,
        )
        if not before:
            created += 1

    if args.write_back and updated:
        _write_json_yaml(base_dir / "tasks.yaml", tasks, overwrite=True)

    print(f"[OK] Sublayers synced. created={created} total={len(sublayers)} base={base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
