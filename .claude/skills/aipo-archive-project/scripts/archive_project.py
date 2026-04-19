#!/usr/bin/env python3
"""Archive an AIPO project and record metadata into programs/archived_projects.md."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sys


DONE_STATUSES = {"completed", "verified", "done"}

TABLE_HEADER = """# Archived AIPO Projects
| archived_at | project_name | purpose | activities | source_path | archive_path | summary | note |
| --- | --- | --- | --- | --- | --- | --- | --- |
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move an AIPO project to programs/archived and append metadata to "
            "programs/archived_projects.md."
        )
    )
    parser.add_argument(
        "project",
        help="Project directory path or folder name under the base directory.",
    )
    parser.add_argument(
        "--base-dir",
        default="programs",
        help="Base directory containing projects (default: programs).",
    )
    parser.add_argument(
        "--archive-dir",
        help="Destination directory for archived projects. Defaults to <base-dir>/archived.",
    )
    parser.add_argument(
        "--record-file",
        help="Archive metadata file. Defaults to <base-dir>/archived_projects.md.",
    )
    parser.add_argument("--note", default="", help="Optional memo to write to record file.")
    parser.add_argument("--purpose", default="", help="Project purpose to record in archive.")
    parser.add_argument(
        "--activities",
        default="",
        help="Description of what was done in the project to record in archive.",
    )
    return parser.parse_args()


def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json_or_none(path: Path):
    if not path.exists():
        return None
    text = _read_text(path).lstrip()
    if not text.startswith("{") and not text.startswith("["):
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
        return value[1:-1]
    return value


def resolve_project_path(base_dir: Path, project: str) -> Path:
    explicit = Path(project).expanduser()
    if explicit.exists():
        return explicit.resolve()

    if not base_dir.exists():
        raise FileNotFoundError(f"Base directory does not exist: {base_dir}")

    candidates = [p for p in base_dir.iterdir() if p.is_dir()]
    exact = [p for p in candidates if p.name == project]
    if len(exact) == 1:
        return exact[0].resolve()

    lower = [p for p in candidates if p.name.lower() == project.lower()]
    if len(lower) == 1:
        return lower[0].resolve()

    contains = [p for p in candidates if project.lower() in p.name.lower()]
    if len(contains) == 1:
        return contains[0].resolve()
    if contains:
        raise RuntimeError(
            "Multiple matching projects found: "
            + ", ".join(sorted(p.name for p in contains))
        )

    if exact:
        raise RuntimeError("Multiple exact matching projects found.")

    raise FileNotFoundError(
        f"Project not found in {base_dir}: {project}. "
        "Pass the full path or a unique folder name."
    )


def infer_purpose(project_dir: Path) -> str:
    layer = project_dir / "layer.yaml"

    data = _load_json_or_none(layer)
    if isinstance(data, dict):
        goal = data.get("goal")
        if isinstance(goal, dict):
            for key in ("description", "statement", "purpose", "summary", "objective"):
                value = goal.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(goal, str) and goal.strip():
            return goal.strip()

    if layer.exists():
        in_goal = False
        goal_indent = 0
        for line in _read_text(layer).splitlines():
            if re.match(r"^\s*goal\s*:\s*$", line):
                in_goal = True
                goal_indent = len(line) - len(line.lstrip(" "))
                continue
            if not in_goal:
                continue
            if line.strip() == "":
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= goal_indent:
                in_goal = False
                continue
            m = re.match(r"^\s*description\s*:\s*(.+)\s*$", line)
            if m:
                return _strip_quotes(m.group(1))

    for candidate in (
        project_dir / "context/01_overview.md",
        project_dir / "README.md",
        project_dir / "readme.md",
    ):
        if not candidate.exists():
            continue
        for raw in _read_text(candidate).splitlines():
            text = raw.strip()
            if not text:
                continue
            if text.startswith("#"):
                text = text.lstrip("#").strip()
            if text:
                return text[:200]

    return "(目的未設定)"


def _extract_paths_from_text(text: str) -> list[str]:
    patterns = [
        r"(?i)\bdocuments/[A-Za-z0-9_./\-]+",
        r"(?i)\bcommands/[A-Za-z0-9_./\-]+",
        r"(?i)\bsite/[A-Za-z0-9_./\-]+",
        r"(?i)\bweekly_review/[A-Za-z0-9_./\-]+",
    ]
    found: list[str] = []
    for pat in patterns:
        found.extend(re.findall(pat, text))

    seen = set()
    out = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def infer_activities(project_dir: Path) -> str:
    tasks_path = project_dir / "tasks.yaml"

    deliverables: list[str] = []
    task_names: list[str] = []
    total = 0
    done = 0

    data = _load_json_or_none(tasks_path)
    if isinstance(data, dict):
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                total += 1
                status = str(t.get("status") or "").strip().lower()
                if status in DONE_STATUSES:
                    done += 1

                name = t.get("name")
                if isinstance(name, str) and name.strip():
                    task_names.append(name.strip())

                for key in ("deliverable", "deliverables", "output"):
                    val = t.get(key)
                    if isinstance(val, str) and val.strip():
                        deliverables.append(val.strip())
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, str) and item.strip():
                                deliverables.append(item.strip())

                notes = t.get("notes")
                if isinstance(notes, str) and notes.strip():
                    deliverables.extend(_extract_paths_from_text(notes))

        if not task_names:
            sublayers = data.get("sublayers")
            if isinstance(sublayers, list):
                for sg in sublayers[:6]:
                    if isinstance(sg, dict):
                        g = sg.get("goal")
                        if isinstance(g, str) and g.strip():
                            task_names.append(g.strip())

    elif tasks_path.exists():
        lines = _read_text(tasks_path).splitlines()
        in_tasks = False
        tasks_indent = 0
        current: dict[str, str] = {}

        def flush_current():
            nonlocal total, done
            if not current:
                return
            total += 1
            status = str(current.get("status") or "").strip().lower()
            if status in DONE_STATUSES:
                done += 1
            name = current.get("name")
            if name:
                task_names.append(name)
            if current.get("result"):
                deliverables.extend(_extract_paths_from_text(current["result"]))
            if current.get("notes"):
                deliverables.extend(_extract_paths_from_text(current["notes"]))

        for line in lines:
            if re.match(r"^\s*tasks\s*:\s*$", line):
                in_tasks = True
                tasks_indent = len(line) - len(line.lstrip(" "))
                continue
            if not in_tasks:
                continue
            if line.strip() == "":
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= tasks_indent:
                flush_current()
                current = {}
                in_tasks = False
                continue

            if re.match(r"^\s*-\s*id\s*:\s*", line):
                flush_current()
                current = {}
                continue

            m = re.match(r"^\s*name\s*:\s*(.+)\s*$", line)
            if m:
                current["name"] = _strip_quotes(m.group(1))
                continue
            m = re.match(r"^\s*status\s*:\s*(.+)\s*$", line)
            if m:
                current["status"] = _strip_quotes(m.group(1))
                continue
            m = re.match(r"^\s*(result|notes)\s*:\s*(.+)\s*$", line)
            if m:
                current[m.group(1)] = _strip_quotes(m.group(2))
                continue

        if in_tasks:
            flush_current()

    if total == 0 and not task_names:
        return "主要作業は tasks.yaml から推定できず"

    parts: list[str] = []
    if total:
        max_names = 6
        top = task_names[:max_names]
        rest = max(0, total - len(top))
        if top:
            names_s = "、".join(top)
            if rest:
                names_s += f" 他{rest}件"
            parts.append(f"タスク{total}件（完了{done}）。主な作業: {names_s}")
        else:
            parts.append(f"タスク{total}件（完了{done}）")
    else:
        parts.append("主な作業: " + "、".join(task_names[:6]))

    cleaned: list[str] = []
    seen = set()
    for d in deliverables:
        d = d.strip().strip(",").strip(".")
        if not d:
            continue
        if d not in seen:
            seen.add(d)
            cleaned.append(d)

    if cleaned:
        top = cleaned[:4]
        more = len(cleaned) - len(top)
        s = ", ".join(top)
        if more:
            s += f" (+{more})"
        candidate = "。".join(parts + ["成果物: " + s])
        if len(candidate) <= 420:
            return candidate

    out = "。".join(parts)
    return out[:420].rstrip() + ("…" if len(out) > 420 else "")


def summarize_project(project_dir: Path) -> str:
    entries = [
        "layer.yaml",
        "context.yaml",
        "tasks.yaml",
        "context",
        "documents",
        "commands",
        "sublayers",
    ]
    parts: list[str] = []
    for name in entries:
        target = project_dir / name
        if target.is_file():
            parts.append(f"{name}(file)")
        elif target.is_dir():
            count = sum(1 for p in target.rglob("*") if p.is_file())
            parts.append(f"{name}(dir, {count} files)")

    if not parts:
        return "(no tracked AIPO artifacts found)"
    return "; ".join(parts)


def ensure_record_file(record_file: Path) -> None:
    record_file.parent.mkdir(parents=True, exist_ok=True)
    if not record_file.exists() or record_file.stat().st_size == 0:
        record_file.write_text(TABLE_HEADER, encoding="utf-8")
        return

    with record_file.open("r", encoding="utf-8") as fp:
        header_line = ""
        for _ in range(10):
            line = fp.readline()
            if not line:
                break
            if line.strip().startswith("|") and "archived_at" in line and "project_name" in line:
                header_line = line
                break

    if not header_line or "purpose" not in header_line or "activities" not in header_line or "summary" not in header_line:
        raise RuntimeError(
            f"Record file has unexpected columns: {record_file}. "
            "Run a backfill/migration so it matches the new format."
        )


def append_record(
    record_file: Path,
    archived_at: datetime,
    project_name: str,
    purpose: str,
    activities: str,
    source_path: Path,
    archive_path: Path,
    summary: str,
    note: str,
) -> None:
    ensure_record_file(record_file)

    row = [
        archived_at.strftime("%Y-%m-%d %H:%M:%S"),
        project_name,
        purpose,
        activities,
        str(source_path),
        str(archive_path),
        summary,
        note,
    ]

    with record_file.open("a", encoding="utf-8") as fp:
        fp.write("| " + " | ".join(escape_md_cell(c) for c in row) + " |\n")


def archive_project(
    project_dir: Path,
    archive_dir: Path,
    record_file: Path,
    purpose: str,
    activities: str,
    note: str,
) -> None:
    archived_at = datetime.now()
    destination = archive_dir / project_dir.name
    if destination.exists():
        suffix = archived_at.strftime("%Y%m%d%H%M%S")
        destination = archive_dir / f"{project_dir.name}-{suffix}"

    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(project_dir), destination)

    inferred_purpose = purpose.strip() or infer_purpose(destination)
    inferred_activities = activities.strip() or infer_activities(destination)
    summary = summarize_project(destination)

    append_record(
        record_file=record_file,
        archived_at=archived_at,
        project_name=project_dir.name,
        purpose=inferred_purpose,
        activities=inferred_activities,
        source_path=project_dir,
        archive_path=destination,
        summary=summary,
        note=note or "",
    )

    print("Archive completed")
    print(f"source: {project_dir}")
    print(f"archive: {destination}")
    print(f"record: {record_file}")


def main() -> int:
    args = parse_args()

    base_dir = Path(args.base_dir).expanduser().resolve()
    archive_dir = (
        Path(args.archive_dir).expanduser().resolve() if args.archive_dir else base_dir / "archived"
    )
    record_file = (
        Path(args.record_file).expanduser().resolve() if args.record_file else base_dir / "archived_projects.md"
    )

    try:
        project_dir = resolve_project_path(base_dir, args.project)
        archive_project(
            project_dir=project_dir,
            archive_dir=archive_dir,
            record_file=record_file,
            purpose=args.purpose,
            activities=args.activities,
            note=args.note,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
