"""Keep ``.codex/skills/<name>/`` in sync with its ``.claude/`` canonical copy.

Policy: ``.claude/skills/`` is the single editable source of truth. The
``.codex/`` variant is a derived mirror. Every office-anonymizer wrapper run
calls ``--check`` at startup so drift fails loudly.

Usage:
    python .claude/scripts/sync_skills.py --check
    python .claude/scripts/sync_skills.py --write

Exit codes:
    0 — .codex matches .claude (check) or write succeeded.
    1 — drift detected (check) or copy refused (write without --force on existing diff).
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
# Skills that carry a `.codex/` mirror. Expand the list as new skills are added.
_MIRRORED_SKILLS = (
    "office-anonymizer",
)


def collect_mirror_pairs(skill_name: str) -> list[tuple[Path, Path]]:
    """Return (claude_path, codex_path) pairs for every file under a skill."""
    claude_root = REPO_ROOT / ".claude" / "skills" / skill_name
    codex_root = REPO_ROOT / ".codex" / "skills" / skill_name
    if not claude_root.exists():
        raise FileNotFoundError(f".claude skill dir missing: {claude_root}")

    pairs: list[tuple[Path, Path]] = []
    for path in claude_root.rglob("*"):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(claude_root)
        pairs.append((path, codex_root / rel))
    return pairs


def check(skill_name: str) -> list[Path]:
    """Return relative paths that differ or are missing in the codex mirror."""
    drift: list[Path] = []
    for claude_path, codex_path in collect_mirror_pairs(skill_name):
        rel = claude_path.relative_to(REPO_ROOT / ".claude" / "skills" / skill_name)
        if not codex_path.exists():
            drift.append(rel)
            continue
        if not filecmp.cmp(claude_path, codex_path, shallow=False):
            drift.append(rel)
    # Also report codex-side orphans.
    codex_root = REPO_ROOT / ".codex" / "skills" / skill_name
    if codex_root.exists():
        claude_root = REPO_ROOT / ".claude" / "skills" / skill_name
        claude_rels = {
            p.relative_to(claude_root)
            for p in claude_root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        }
        for orphan in codex_root.rglob("*"):
            if orphan.is_dir() or "__pycache__" in orphan.parts:
                continue
            rel = orphan.relative_to(codex_root)
            if rel not in claude_rels and rel not in drift:
                drift.append(rel)
    return drift


def write(skill_name: str) -> None:
    """Copy every .claude file to the .codex mirror, preserving mtime."""
    for claude_path, codex_path in collect_mirror_pairs(skill_name):
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_path, codex_path)
    # Remove codex-side orphans.
    codex_root = REPO_ROOT / ".codex" / "skills" / skill_name
    claude_root = REPO_ROOT / ".claude" / "skills" / skill_name
    if not codex_root.exists():
        return
    claude_rels = {
        p.relative_to(claude_root)
        for p in claude_root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    for path in list(codex_root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(codex_root)
        if rel not in claude_rels:
            path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift between .claude and .codex. Exit 1 if any.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Copy .claude files to the .codex mirror (one-way).",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=None,
        help="Optional: limit to specific skill name(s). Defaults to all mirrored skills.",
    )
    args = parser.parse_args(argv)

    if args.check == args.write:
        parser.error("pass exactly one of --check or --write")

    skills = args.skill or list(_MIRRORED_SKILLS)
    exit_code = 0
    for skill_name in skills:
        if args.check:
            drift = check(skill_name)
            if drift:
                exit_code = 1
                print(f"[drift] {skill_name}:")
                for rel in drift:
                    print(f"  {rel}")
            else:
                print(f"[ok]    {skill_name}")
        else:
            write(skill_name)
            print(f"[sync]  {skill_name} -> .codex")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
