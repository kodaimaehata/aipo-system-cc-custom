#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


PROJECT_ID_PREFIX = "P"
PROJECT_ID_WIDTH = 4
PROJECT_ID_PATTERN = re.compile(rf"^{PROJECT_ID_PREFIX}\d{{{PROJECT_ID_WIDTH}}}$")
PROJECT_ID_PREFIX_PATTERN = re.compile(rf"^{PROJECT_ID_PREFIX}(\d{{{PROJECT_ID_WIDTH}}})_(.+)$")


@dataclass(frozen=True)
class CandidateProject:
    path: Path
    sort_key: tuple


def _read_json_yaml(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json_yaml(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_created_key(path: Path) -> tuple:
    layer = _read_json_yaml(path / "layer.yaml")
    created_at = None
    if isinstance(layer, dict):
        created_at = layer.get("created_at")
    if isinstance(created_at, str):
        return ("0", created_at, path.as_posix())
    # Missing created_at: fallback to mtime
    return ("1", "", str(path.stat().st_mtime_ns), path.as_posix())


def _existing_max_id(base_dir: Path) -> int:
    max_id = 0
    for child in base_dir.iterdir():
        if not child.is_dir():
            continue
        match = PROJECT_ID_PREFIX_PATTERN.match(child.name)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max_id


def _fmt_project_id(n: int) -> str:
    max_id = 10**PROJECT_ID_WIDTH - 1
    if n > max_id:
        raise ValueError(f"project id overflow: max {max_id} reached")
    return f"{PROJECT_ID_PREFIX}{n:0{PROJECT_ID_WIDTH}d}"


def _has_project_prefix(name: str) -> bool:
    return PROJECT_ID_PREFIX_PATTERN.match(name) is not None


def _base_slug(path: Path) -> str:
    match = PROJECT_ID_PREFIX_PATTERN.match(path.name)
    if match:
        return match.group(2)
    return path.name


def _collect_candidates(base_dir: Path, *, include_prefixed: bool) -> list[CandidateProject]:
    candidates: list[CandidateProject] = []
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not include_prefixed and _has_project_prefix(child.name):
            continue
        candidates.append(CandidateProject(path=child, sort_key=_extract_created_key(child)))
    candidates.sort(key=lambda c: c.sort_key)
    return candidates


def _iter_aipo_yaml_files(project_dir: Path) -> list[Path]:
    targets: list[Path] = []
    for name in ("layer.yaml", "context.yaml", "tasks.yaml"):
        targets.extend(project_dir.rglob(name))
    targets = [path for path in targets if path.is_file()]
    targets.sort(key=lambda p: p.as_posix())
    return targets


def _migrate_project_id_fields(project_dir: Path, *, project_id: str, dry_run: bool) -> tuple[int, int, int]:
    changed = 0
    total = 0
    skipped = 0
    for path in _iter_aipo_yaml_files(project_dir):
        total += 1
        payload = _read_json_yaml(path)
        if not isinstance(payload, dict):
            skipped += 1
            print(f"[WARN] invalid json-compatible yaml, skip project_id update: {path}")
            continue

        if payload.get("project_id") == project_id:
            continue

        payload["project_id"] = project_id
        changed += 1
        if dry_run:
            print(f"[DRY-RUN] update project_id: {path} -> {project_id}")
            continue
        _write_json_yaml(path, payload)
    return changed, total, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assign sequential project IDs to programs directory entries and update YAML project_id fields."
    )
    parser.add_argument(
        "--base-dir",
        default="programs",
        help="Target root directory containing programs (default: programs).",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=1,
        help="Project ID start number when assign (default: 1). Existing prefixed IDs are considered unless --overwrite-existing is used.",
    )
    parser.add_argument(
        "--include-prefixed",
        action="store_true",
        help="Also re-assign IDs for folders already prefixed with P####_.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned renames without applying them.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="If destination exists, overwrite by skipping if already assigned; otherwise fail (safety default).",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    if not base_dir.exists():
        raise SystemExit(f"error: base dir not found: {base_dir}")

    candidates = _collect_candidates(base_dir, include_prefixed=args.include_prefixed)
    if not candidates:
        print("[INFO] no targets found")
        return 0

    next_id = args.start_id
    if args.include_prefixed is False:
        next_id = max(next_id, _existing_max_id(base_dir) + 1)

    for idx, candidate in enumerate(candidates, start=1):
        target_id = _fmt_project_id(next_id + idx - 1)
        slug = _base_slug(candidate.path)
        new_name = f"{target_id}_{slug}"
        target_path = base_dir / new_name
        final_project_path = candidate.path
        if target_path.exists() and target_path != candidate.path:
            print(f"[WARN] destination exists, skip: {candidate.path.name} -> {new_name}")
            continue

        if args.dry_run:
            print(f"[DRY-RUN] {candidate.path.name} -> {new_name}")
            if target_path == candidate.path:
                final_project_path = candidate.path
            else:
                final_project_path = candidate.path
        else:
            if target_path != candidate.path:
                try:
                    candidate.path.rename(target_path)
                except Exception as exc:
                    print(f"[ERROR] failed rename: {candidate.path.name} -> {new_name}: {exc}")
                    return 1
                print(f"[OK] renamed: {candidate.path.name} -> {new_name}")
                final_project_path = target_path
            else:
                if args.overwrite_existing:
                    print(f"[OK] already assigned: {candidate.path.name}")

        changed, total, skipped = _migrate_project_id_fields(
            final_project_path,
            project_id=target_id,
            dry_run=args.dry_run,
        )
        prefix = "[DRY-RUN]" if args.dry_run else "[OK]"
        print(
            f"{prefix} project_id sync: dir={final_project_path} "
            f"updated={changed} scanned={total} skipped_invalid={skipped}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
