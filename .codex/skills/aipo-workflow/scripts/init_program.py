#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _today_iso() -> str:
    return date.today().isoformat()


def _safe_dir_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("project name is required")
    value = value.replace("/", "-").replace("\\", "-")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if value in {".", ".."}:
        raise ValueError("invalid project name")
    return value


def _write_json_yaml(path: Path, data: object, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git_init(repo_dir: Path) -> None:
    if (repo_dir / ".git").exists():
        return
    try:
        subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("[WARN] git not found; skipping git init")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[WARN] git init failed; skipping ({stderr})")


@dataclass(frozen=True)
class InitArgs:
    project_name: str
    layer_name: str
    goal: str
    preset: str
    mode: str
    owner: str
    deadline: str | None
    overwrite: bool
    git_init: bool
    context_methods: list[str] | None
    priority_folders: list[str] | None
    external_paths: list[str] | None


def _build_layer_yaml(args: InitArgs, *, layer_id: str) -> dict:
    return {
        "version": "1.0",
        "project_name": args.project_name,
        "layer_id": layer_id,
        "layer_name": args.layer_name,
        "workflow_preset": args.preset,
        "goal": {"description": args.goal, "success_criteria": []},
        "mode": args.mode,
        "owner": args.owner,
        "deadline": args.deadline,
        "parent_layer_id": None,
        "created_at": _today_iso(),
        "updated_at": _today_iso(),
    }


def _build_context_yaml(args: InitArgs, *, layer_id: str) -> dict:
    base = {
        "version": "1.1",
        "project_name": args.project_name,
        "layer_id": layer_id,
        "generated_at": _today_iso(),
        "parent_context_dir": None,
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

    # Add context_collection if methods are specified
    if args.context_methods:
        context_collection: dict = {
            "methods": args.context_methods,
            "collected_at": None,
            "confirmed_by": "cli",
        }

        if "local_workspace" in args.context_methods:
            context_collection["local_workspace_config"] = {
                "priority_folders": args.priority_folders or [],
                "perspectives": [],
            }

        if "web_search" in args.context_methods:
            context_collection["web_search_config"] = {
                "prefer_primary_sources": True,
                "keywords": [],
            }

        if "external_paths" in args.context_methods:
            context_collection["external_paths_config"] = {
                "paths": args.external_paths or [],
            }

        base["context_collection"] = context_collection

    return base


def _build_tasks_yaml(args: InitArgs, *, layer_id: str) -> dict:
    if args.preset == "discovery":
        focus_strategy = "product_manager"
        focus_strategy_reason = "新規事業ディスカバリーのためPM視点でDiscovery→Deliveryを優先"
    else:
        focus_strategy = "generic"
        focus_strategy_reason = "汎用プリセットのためコンテキストに応じて柔軟に分解"

    return {
        "version": "2.2",
        "project_name": args.project_name,
        "layer_id": layer_id,
        "generated_at": _today_iso(),
        "decomposition_type": "recursive",
        "focus_strategy": focus_strategy,
        "focus_strategy_reason": focus_strategy_reason,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an AIPO program folder under programs/{project}.")
    parser.add_argument("--project", required=True, help="Project directory name (used under programs/).")
    parser.add_argument("--layer-name", default="Root", help="Root layer name.")
    parser.add_argument("--goal", required=True, help="One-line goal.")
    parser.add_argument("--preset", choices=["general", "discovery"], default="general")
    parser.add_argument("--mode", choices=["concrete", "abstract"], default="concrete")
    parser.add_argument("--owner", default="owner")
    parser.add_argument("--deadline", default=None, help="ISO date (YYYY-MM-DD) or omit.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    parser.add_argument(
        "--git-init",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Initialize a git repository under programs/{project}.",
    )
    parser.add_argument(
        "--context-methods",
        default=None,
        help="Comma-separated context collection methods: local_workspace,web_search,external_paths",
    )
    parser.add_argument(
        "--priority-folders",
        default=None,
        help="Comma-separated priority folders for local_workspace (e.g., 'src/,docs/')",
    )
    parser.add_argument(
        "--external-paths",
        default=None,
        help="Comma-separated external paths for external_paths method",
    )
    args_ns = parser.parse_args()

    project_name = _safe_dir_name(args_ns.project)

    # Parse comma-separated values
    context_methods = None
    if args_ns.context_methods:
        context_methods = [m.strip() for m in args_ns.context_methods.split(",") if m.strip()]

    priority_folders = None
    if args_ns.priority_folders:
        priority_folders = [f.strip() for f in args_ns.priority_folders.split(",") if f.strip()]

    external_paths = None
    if args_ns.external_paths:
        external_paths = [p.strip() for p in args_ns.external_paths.split(",") if p.strip()]

    args = InitArgs(
        project_name=project_name,
        layer_name=args_ns.layer_name,
        goal=args_ns.goal,
        preset=args_ns.preset,
        mode=args_ns.mode,
        owner=args_ns.owner,
        deadline=args_ns.deadline,
        overwrite=args_ns.overwrite,
        git_init=args_ns.git_init,
        context_methods=context_methods,
        priority_folders=priority_folders,
        external_paths=external_paths,
    )

    base_dir = Path("programs") / args.project_name
    layer_id = "L001"

    if args.git_init:
        base_dir.mkdir(parents=True, exist_ok=True)
        _git_init(base_dir)

    _write_text(
        base_dir / "README.md",
        f"# {args.project_name}\n\n"
        "AIPO（Codex CLI版）の成果物リポジトリ。\n\n"
        "## Structure\n"
        "- `layer.yaml`: Goal/モード/期限など\n"
        "- `context.yaml` + `context/`: 収集した前提情報（Index + 実体）\n"
        "- `tasks.yaml`: SubLayer/Task 分解と実行計画\n"
        "- `commands/`: タスク実行手順（Discoverで生成・調整）\n",
        overwrite=args.overwrite,
    )
    _write_text(
        base_dir / ".gitignore",
        ".DS_Store\n**/.DS_Store\n",
        overwrite=args.overwrite,
    )

    _write_json_yaml(base_dir / "layer.yaml", _build_layer_yaml(args, layer_id=layer_id), overwrite=args.overwrite)
    _write_json_yaml(base_dir / "context.yaml", _build_context_yaml(args, layer_id=layer_id), overwrite=args.overwrite)
    _write_json_yaml(base_dir / "tasks.yaml", _build_tasks_yaml(args, layer_id=layer_id), overwrite=args.overwrite)

    _write_text(
        base_dir / "context" / "01_overview.md",
        "# Overview\n\n- 背景:\n- 目的:\n- スコープ:\n- 非スコープ:\n",
        overwrite=args.overwrite,
    )
    _write_text(
        base_dir / "context" / "02_constraints.md",
        "# Constraints\n\n- 期限:\n- 予算:\n- 技術:\n- 法務/コンプライアンス:\n- 依存関係:\n",
        overwrite=args.overwrite,
    )

    (base_dir / "commands").mkdir(parents=True, exist_ok=True)
    (base_dir / "documents").mkdir(parents=True, exist_ok=True)
    (base_dir / "sublayers").mkdir(parents=True, exist_ok=True)

    print(f"[OK] Initialized: {base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
