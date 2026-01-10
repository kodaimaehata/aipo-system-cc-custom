#!/usr/bin/env python3
"""Codex Review Script - Execute Codex CLI review with custom prompt and file list.

Claude Code generates the review prompt and specifies target files.
This script validates files, reads content, calls Codex, and saves the report.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class CodexReviewError(Exception):
    pass


def _now_iso() -> str:
    """Return current datetime in YYYY-MM-DD_HH-MM-SS format (filesystem safe)."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _pick_lang(lang_arg: str, *, sample: str) -> str:
    lang = (lang_arg or "").strip().lower()
    if lang in {"ja", "en"}:
        return lang
    env_lang = (os.environ.get("AIPO_REVIEW_LANG") or os.environ.get("AIPO_LANG") or "").strip().lower()
    if env_lang in {"ja", "en"}:
        return env_lang
    return "ja" if _contains_japanese(sample) else "en"


def _i18n_exclude_reason(reason: str, *, lang: str) -> str:
    if lang != "ja":
        return reason
    mapping = {
        "secrets/env": "機密/環境変数",
        "secrets dir": "機密ディレクトリ",
        "local settings": "ローカル設定",
        "credentials file": "認証設定ファイル",
        "name suggests secret": "ファイル名が機密を示唆",
        "secret file extension": "機密拡張子",
        "database file": "DBファイル",
        "terraform state": "Terraform state",
        "ssh key": "SSH鍵",
        "git internals": "Git内部",
        "generated/deps": "生成物/依存",
        "binary/non-utf8": "バイナリ/非UTF-8",
        "too large (>10MB)": "大きすぎる（>10MB）",
        "not found": "ファイルなし",
    }
    return mapping.get(reason, reason)


def _kill_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _run(cmd: list[str], *, cwd: Path, input_text: str | None = None, timeout_s: float | None = None) -> str:
    try:
        with subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as proc:
            try:
                stdout, stderr = proc.communicate(input_text, timeout=timeout_s)
            except subprocess.TimeoutExpired as e:
                _kill_process_group(proc)
                stdout, stderr = proc.communicate()
                msg = f"command timed out ({timeout_s}s): {' '.join(cmd)}"
                if (stderr or "").strip():
                    msg += f"\n{stderr.strip()}"
                raise CodexReviewError(msg) from e
            except KeyboardInterrupt:
                _kill_process_group(proc)
                raise
    except FileNotFoundError as e:
        raise CodexReviewError(f"command not found: {cmd[0]}") from e

    if proc.returncode != 0:
        msg = f"command failed ({proc.returncode}): {' '.join(cmd)}"
        if (stderr or "").strip():
            msg += f"\n{stderr.strip()}"
        raise CodexReviewError(msg)
    return stdout


def _is_probably_binary(path: Path) -> bool:
    """Check if file is binary by looking for null bytes."""
    try:
        data = path.read_bytes()[:8192]
    except FileNotFoundError:
        return False
    # Null byte is a strong indicator of binary
    return b"\x00" in data


def _read_text_file(path: Path) -> str | None:
    """Read text file with encoding detection. Returns None if unreadable."""
    # Try common encodings in order of likelihood
    encodings = ["utf-8", "utf-8-sig", "shift_jis", "cp932", "euc-jp", "iso-8859-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


# File classification constants
SECRET_EXTS = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der", ".jks", ".kdb"}
DB_EXTS = {".sqlite", ".sqlite3", ".db"}
CREDENTIAL_FILENAMES = {".npmrc", ".netrc"}
SSH_KEY_FILENAMES = {"id_rsa", "id_ed25519", "authorized_keys", "known_hosts"}

_SECRET_NAME_RE = re.compile(
    r"(^|[._-])(secret|secrets|token|tokens|credential|credentials|apikey|api_key|private|key|keys)($|[._-])",
    flags=re.IGNORECASE,
)

_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    flags=re.DOTALL,
)

_TOKEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{10,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{10,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z\\-_]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)Bearer\\s+[A-Za-z0-9._\\-]{10,}"),
)


def _redact_text(text: str) -> str:
    """Mask sensitive values in text."""
    if not text:
        return text
    out = _PRIVATE_KEY_BLOCK_RE.sub("<REDACTED_PRIVATE_KEY>", text)
    for pat in _TOKEN_PATTERNS:
        out = pat.sub("<REDACTED_TOKEN>", out)
    return out


def _is_excluded_path(rel_path: str) -> tuple[bool, str]:
    """Check if a file path should be excluded for security reasons."""
    p = Path(rel_path)
    parts_lower = [x.lower() for x in p.parts]
    name = p.name.lower()
    ext = p.suffix.lower()

    if name.startswith(".env") or name.startswith(".secrets"):
        return (True, "secrets/env")
    if "secrets" in parts_lower or ".secrets" in parts_lower:
        return (True, "secrets dir")
    if name in {"settings.local.json"}:
        return (True, "local settings")
    if name in CREDENTIAL_FILENAMES:
        return (True, "credentials file")
    if ext in SECRET_EXTS:
        return (True, "secret file extension")
    if ext in DB_EXTS:
        return (True, "database file")
    if name.endswith(".tfstate") or name.endswith(".tfstate.backup"):
        return (True, "terraform state")
    if name in SSH_KEY_FILENAMES or any(name.startswith(f"{x}.") for x in SSH_KEY_FILENAMES):
        return (True, "ssh key")
    if _SECRET_NAME_RE.search(name):
        return (True, "name suggests secret")
    if ".git" in parts_lower:
        return (True, "git internals")
    if any(x in parts_lower for x in ["node_modules", "dist", "build", ".venv"]):
        return (True, "generated/deps")

    return (False, "")


@dataclass(frozen=True)
class ValidationResult:
    safe_files: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]  # (path, reason)


def _read_custom_prompt(prompt_arg: str) -> str:
    """Read custom prompt from argument or stdin."""
    if prompt_arg == "-":
        return sys.stdin.read()
    return prompt_arg


def _validate_files(repo_dir: Path, files: list[str]) -> ValidationResult:
    """Validate file list and return safe files and excluded files."""
    safe: list[str] = []
    excluded: list[tuple[str, str]] = []

    for f in files:
        # Security check
        is_excl, reason = _is_excluded_path(f)
        if is_excl:
            excluded.append((f, reason))
            continue

        abs_path = repo_dir / f
        if not abs_path.exists():
            excluded.append((f, "not found"))
            continue
        if not abs_path.is_file():
            excluded.append((f, "not a file"))
            continue
        if _is_probably_binary(abs_path):
            excluded.append((f, "binary/non-utf8"))
            continue
        if abs_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
            excluded.append((f, "too large (>10MB)"))
            continue

        safe.append(f)

    return ValidationResult(
        safe_files=tuple(sorted(safe)),
        excluded=tuple(sorted(excluded)),
    )


def _build_file_contents_section(repo_dir: Path, files: tuple[str, ...], lang: str) -> str:
    """Read file contents and build a section for the prompt."""
    parts: list[str] = []
    label = "ファイル内容" if lang == "ja" else "File Contents"

    for f in files:
        abs_path = repo_dir / f
        content = _read_text_file(abs_path)
        if content is not None:
            content = _redact_text(content)
            ext = abs_path.suffix.lstrip(".") or "text"
            parts.append(f"### {f}\n```{ext}\n{content.rstrip()}\n```")
        else:
            error_msg = "読み込み不可（エンコーディング不明）" if lang == "ja" else "unreadable (unknown encoding)"
            parts.append(f"### {f}\n({error_msg})")

    return f"## {label}\n\n" + "\n\n".join(parts) if parts else ""


def _build_excluded_section(excluded: tuple[tuple[str, str], ...], lang: str) -> str:
    """Build excluded files section."""
    if not excluded:
        return ""

    label = "除外ファイル" if lang == "ja" else "Excluded Files"
    parts: list[str] = []
    for path, reason in excluded:
        localized_reason = _i18n_exclude_reason(reason, lang=lang)
        parts.append(f"- {path} ({localized_reason})")

    return f"## {label}\n\n" + "\n".join(parts)


def _extract_codex_agent_message(jsonl: str) -> str:
    """Extract the final agent message from Codex JSON output."""
    last: str | None = None
    for line in (jsonl or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "item.completed":
            continue
        item = obj.get("item") or {}
        if not isinstance(item, dict):
            continue
        if item.get("type") not in {"agent_message", "assistant_message"}:
            continue
        text = item.get("text")
        if isinstance(text, str):
            last = text
    if last is None:
        raise CodexReviewError("no agent_message found in codex --json output")
    return last


def _output_dir(repo_dir: Path) -> Path:
    return repo_dir / "codex_review"


def _unique_output_path(out_dir: Path, *, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{stem}.md"
    if not base.exists():
        return base
    for i in range(2, 1000):
        cand = out_dir / f"{stem}_{i}.md"
        if not cand.exists():
            return cand
    raise CodexReviewError("too many existing review files")


def _report_preamble(
    lang: str,
    *,
    repo_dir: Path,
    timestamp: str,
    file_count: int,
    excluded_count: int,
) -> str:
    if lang == "ja":
        return (
            f"# Codex レビュー ({timestamp})\n\n"
            f"- 日時: `{timestamp}`\n"
            f"- 対象: `{repo_dir}`\n"
            f"- ファイル数: {file_count}\n"
            f"- 除外: {excluded_count}\n\n"
        )
    return (
        f"# Codex Review ({timestamp})\n\n"
        f"- datetime: `{timestamp}`\n"
        f"- repo/layer: `{repo_dir}`\n"
        f"- files: {file_count}\n"
        f"- excluded: {excluded_count}\n\n"
    )


def _failure_body(lang: str, *, cause: str) -> str:
    if lang == "ja":
        return (
            "## 概要\n\n"
            f"- Codex 実行に失敗しました（{cause}）。\n\n"
            "## 次のアクション（提案）\n\n"
            "- `--dry-run` でファイル検証を確認する\n"
            "- 対象ファイルが正しいか確認する\n"
            "- `codex login` 状態を確認する\n\n"
        )
    return (
        "## Summary\n\n"
        f"- Codex execution failed ({cause}).\n\n"
        "## Suggested Next Actions\n\n"
        "- Run with `--dry-run` to check file validation\n"
        "- Verify target files are correct\n"
        "- Check `codex login` status\n\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Codex review with custom prompt and file list."
    )
    parser.add_argument("--path", default=".", help="Target directory (default: current dir).")
    parser.add_argument("--lang", default="auto", help="ja|en|auto (default: auto).")
    parser.add_argument("--prompt", required=True, help="Review prompt (use '-' to read from stdin).")
    parser.add_argument("--files", nargs="+", required=True, help="Files to review (relative to --path).")
    parser.add_argument("--keep-tmp", action="store_true", help="Keep temp directory (debug).")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout seconds for Codex CLI.")
    parser.add_argument("--dry-run", action="store_true", help="Validate files and exit (no Codex run).")
    args = parser.parse_args()

    repo_dir = Path(args.path)
    if not repo_dir.exists():
        raise SystemExit(f"[ERROR] path not found: {repo_dir}")
    repo_dir = repo_dir.resolve()

    # Read custom prompt
    custom_prompt = _read_custom_prompt(args.prompt)

    # Validate files
    validation = _validate_files(repo_dir, args.files)

    # Determine language
    sample = custom_prompt + "\n".join(validation.safe_files)
    lang = _pick_lang(args.lang, sample=sample)

    # Dry run: show validation results
    if args.dry_run:
        print(f"[INFO] repo: {repo_dir}")
        print(f"[INFO] lang: {lang}")
        print(f"[INFO] safe files: {len(validation.safe_files)}")
        for f in validation.safe_files:
            print(f"  - {f}")
        print(f"[INFO] excluded: {len(validation.excluded)}")
        for f, reason in validation.excluded:
            print(f"  - {f} ({_i18n_exclude_reason(reason, lang=lang)})")
        return 0

    # Check if we have files to review
    if not validation.safe_files:
        error_msg = "レビュー対象のファイルがありません" if lang == "ja" else "No files to review"
        if validation.excluded:
            error_msg += f" ({len(validation.excluded)} excluded)"
        raise SystemExit(f"[ERROR] {error_msg}")

    # Build final prompt
    file_contents = _build_file_contents_section(repo_dir, validation.safe_files, lang)
    excluded_section = _build_excluded_section(validation.excluded, lang)

    final_prompt = custom_prompt
    if file_contents:
        final_prompt += "\n\n" + file_contents
    if excluded_section:
        final_prompt += "\n\n" + excluded_section

    # Prepare output
    out_dir = _output_dir(repo_dir)
    timestamp = _now_iso()
    out_path = _unique_output_path(out_dir, stem=f"codex_review_{timestamp}")

    def write_report(body: str) -> None:
        report = _report_preamble(
            lang,
            repo_dir=repo_dir,
            timestamp=timestamp,
            file_count=len(validation.safe_files),
            excluded_count=len(validation.excluded),
        )
        report += body
        out_path.write_text(report, encoding="utf-8")

    # Execute Codex
    try:
        if args.keep_tmp:
            tmp_dir = out_dir / ".tmp_codex_review"
            tmp_dir.mkdir(parents=True, exist_ok=True)
        else:
            tmp_ctx = tempfile.TemporaryDirectory(prefix="tmp_codex_review_", dir=str(out_dir))
            tmp_dir = Path(tmp_ctx.__enter__())

        try:
            out = _run(
                ["codex", "-s", "read-only", "-a", "never", "exec", "--json", "--skip-git-repo-check", "-C", str(tmp_dir), "-"],
                cwd=repo_dir,
                input_text=final_prompt,
                timeout_s=args.timeout,
            )
            review_body = _extract_codex_agent_message(out)
            write_report(review_body)
            print(f"[OK] Wrote: {out_path}")
            return 0
        finally:
            if not args.keep_tmp and "tmp_ctx" in locals():
                tmp_ctx.__exit__(None, None, None)

    except CodexReviewError as e:
        write_report(_failure_body(lang, cause=str(e)))
        print(f"[ERROR] Review failed; wrote report: {out_path}")
        return 1
    except KeyboardInterrupt:
        write_report(_failure_body(lang, cause="interrupted"))
        print(f"[ERROR] Interrupted; wrote report: {out_path}")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
