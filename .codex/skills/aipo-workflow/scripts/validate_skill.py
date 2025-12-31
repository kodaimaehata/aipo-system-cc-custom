#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


class SkillValidationError(Exception):
    pass


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise SkillValidationError("SKILL.md must start with YAML frontmatter (---)")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SkillValidationError("SKILL.md frontmatter must end with '---'")
    fm = text[4:end].strip().splitlines()
    out: dict[str, str] = {}
    for line in fm:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)\s*$", line)
        if not m:
            raise SkillValidationError(f"unsupported frontmatter line: {line!r}")
        key, value = m.group(1), m.group(2)
        out[key] = value
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal validator for this skill (no PyYAML required).")
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise SystemExit(f"[ERROR] missing: {skill_md}")

    fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()
    if not name:
        raise SystemExit("[ERROR] frontmatter 'name' is required")
    if not desc or "TODO" in desc:
        raise SystemExit("[ERROR] frontmatter 'description' must be filled (no TODO)")

    expected = skill_dir.name
    if name != expected:
        raise SystemExit(f"[ERROR] frontmatter name '{name}' must match folder name '{expected}'")

    for rel in ["scripts", "references"]:
        p = skill_dir / rel
        if not p.is_dir():
            raise SystemExit(f"[ERROR] missing directory: {p}")

    print(f"[OK] Skill looks valid: {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

