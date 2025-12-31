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


def _validate_single_skill(skill_dir: Path, *, strict: bool = False) -> list[str]:
    """Validate a single skill directory. Returns list of errors."""
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        errors.append(f"missing: {skill_md}")
        return errors

    try:
        fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except SkillValidationError as e:
        errors.append(str(e))
        return errors

    name = fm.get("name", "").strip()
    desc = fm.get("description", "").strip()
    if not name:
        errors.append("frontmatter 'name' is required")
    if not desc or "TODO" in desc:
        errors.append("frontmatter 'description' must be filled (no TODO)")

    expected = skill_dir.name
    if name and name != expected:
        errors.append(f"frontmatter name '{name}' must match folder name '{expected}'")

    # Check optional/required directories
    for rel in ["scripts", "references"]:
        p = skill_dir / rel
        if p.is_dir():
            print(f"  [INFO] {skill_dir.name}: Found directory: {rel}")
        elif strict:
            errors.append(f"missing required directory: {rel} (strict mode)")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Claude Code skill(s).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--skill-dir", help="Path to a single skill directory to validate.")
    group.add_argument("--all", action="store_true", help="Validate all skills under .claude/skills/")
    parser.add_argument("--skills-root", default=".claude/skills", help="Root directory for --all (default: .claude/skills)")
    parser.add_argument("--strict", action="store_true", help="Require scripts/ and references/ directories.")
    args = parser.parse_args()

    all_errors: dict[str, list[str]] = {}

    if args.all:
        skills_root = Path(args.skills_root)
        if not skills_root.is_dir():
            raise SystemExit(f"[ERROR] Skills root not found: {skills_root}")
        skill_dirs = [d for d in skills_root.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
        if not skill_dirs:
            raise SystemExit(f"[ERROR] No skills found under {skills_root}")
        for skill_dir in sorted(skill_dirs):
            errors = _validate_single_skill(skill_dir, strict=args.strict)
            if errors:
                all_errors[str(skill_dir)] = errors
            else:
                print(f"[OK] {skill_dir.name}")
    else:
        skill_dir = Path(args.skill_dir)
        errors = _validate_single_skill(skill_dir, strict=args.strict)
        if errors:
            all_errors[str(skill_dir)] = errors
        else:
            print(f"[OK] Skill looks valid: {skill_dir}")

    if all_errors:
        print("\n[ERRORS]")
        for path, errs in all_errors.items():
            for e in errs:
                print(f"  {path}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

