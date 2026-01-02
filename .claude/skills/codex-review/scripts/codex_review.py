#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class CodexReviewError(Exception):
    pass


def _today_iso() -> str:
    return date.today().isoformat()


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
        "too large (>1MB)": "大きすぎる（>1MB）",
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


def _is_git_repo(repo_dir: Path) -> bool:
    try:
        _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_dir)
        return True
    except CodexReviewError:
        return False


def _git_uncommitted_paths(repo_dir: Path) -> list[str]:
    out: set[str] = set()
    for cmd in [
        ["git", "diff", "--name-only", "-z"],
        ["git", "diff", "--name-only", "--cached", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ]:
        raw = _run(cmd, cwd=repo_dir)
        for p in raw.split("\0"):
            p = p.strip()
            if p:
                out.add(p)
    return sorted(out)


def _is_probably_binary(path: Path) -> bool:
    try:
        data = path.read_bytes()[:2048]
    except FileNotFoundError:
        return False
    if b"\x00" in data:
        return True
    # Heuristic: too many non-text bytes
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


CODE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".swift",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".lua",
    ".sql",
    ".html",
    ".css",
    ".scss",
}

DOC_EXTS = {
    ".md",
    ".txt",
    ".rst",
    ".adoc",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
}

CODE_FILENAMES = {
    "Makefile",
    "Dockerfile",
}

DOC_FILENAMES = {
    ".gitignore",
    ".gitattributes",
}

SECRET_EXTS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".crt",
    ".cer",
    ".der",
    ".jks",
    ".kdb",
}

DB_EXTS = {
    ".sqlite",
    ".sqlite3",
    ".db",
}

CREDENTIAL_FILENAMES = {
    ".npmrc",
    ".netrc",
}

SSH_KEY_FILENAMES = {
    "id_rsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
}

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
    if not text:
        return text
    out = _PRIVATE_KEY_BLOCK_RE.sub("<REDACTED_PRIVATE_KEY>", text)
    for pat in _TOKEN_PATTERNS:
        out = pat.sub("<REDACTED_TOKEN>", out)
    return out


def _is_code_path(rel_path: str) -> bool:
    p = Path(rel_path)
    if p.name in CODE_FILENAMES:
        return True
    ext = p.suffix.lower()
    if ext in CODE_EXTS:
        return True
    return False


def _is_doc_path(rel_path: str) -> bool:
    p = Path(rel_path)
    if p.name in DOC_FILENAMES:
        return True
    ext = p.suffix.lower()
    return ext in DOC_EXTS


def _is_excluded_path(rel_path: str) -> tuple[bool, str]:
    # Hard excludes (safety)
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
    # Large/binary handled later
    return (False, "")


@dataclass(frozen=True)
class ChangeSummary:
    code_paths: tuple[str, ...]
    doc_paths: tuple[str, ...]
    other_paths: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]  # (path, reason)


def _summarize_changes(repo_dir: Path, rel_paths: list[str]) -> ChangeSummary:
    code: list[str] = []
    docs: list[str] = []
    other: list[str] = []
    excluded: list[tuple[str, str]] = []

    for rp in rel_paths:
        is_excl, reason = _is_excluded_path(rp)
        if is_excl:
            excluded.append((rp, reason))
            continue

        abs_path = (repo_dir / rp)
        if abs_path.exists() and abs_path.is_file():
            if _is_probably_binary(abs_path):
                excluded.append((rp, "binary/non-utf8"))
                continue
            if abs_path.stat().st_size > 1024 * 1024:
                excluded.append((rp, "too large (>1MB)"))
                continue

        if _is_code_path(rp):
            code.append(rp)
        elif _is_doc_path(rp):
            docs.append(rp)
        else:
            other.append(rp)

    return ChangeSummary(
        code_paths=tuple(sorted(code)),
        doc_paths=tuple(sorted(docs)),
        other_paths=tuple(sorted(other)),
        excluded=tuple(sorted(excluded)),
    )


def _review_prompt(lang: str, *, changed: ChangeSummary, method: str) -> str:
    if lang == "ja":
        required = (
            "## 概要\n"
            "## P0（必ず修正）\n"
            "## P1（修正推奨）\n"
            "## 質問\n"
            "## 次のアクション（提案）\n"
        )
        return (
            "あなたはシニアレビュアーです。\n"
            "以下の変更をレビューし、Markdownで出力してください。\n\n"
            "必須フォーマット:\n"
            f"{required}\n"
            "ルール:\n"
            "- 指摘には対象ファイルパスを必ず含める\n"
            "- 機密情報/個人情報を推測・再掲しない\n"
            "- 可能なら具体的な修正案（文章案/設計案/手順）を提示する\n\n"
            f"選択された方式: {method}\n"
            f"変更ファイル（コード）: {', '.join(changed.code_paths) if changed.code_paths else '—'}\n"
            f"変更ファイル（ドキュメント等）: {', '.join(changed.doc_paths) if changed.doc_paths else '—'}\n"
            f"変更ファイル（その他）: {', '.join(changed.other_paths) if changed.other_paths else '—'}\n"
            f"除外（送信しない）: {', '.join([f'{p}({r})' for p, r in changed.excluded]) if changed.excluded else '—'}\n"
        )
    return (
        "You are a senior reviewer.\n"
        "Review the changes below and output in Markdown.\n\n"
        "Required format:\n"
        "## Summary\n"
        "## P0 (Must Fix)\n"
        "## P1 (Should Fix)\n"
        "## Questions\n"
        "## Suggested Next Actions\n\n"
        "Rules:\n"
        "- Include file paths in every finding\n"
        "- Do not infer or repeat secrets/PII\n"
        "- Provide concrete fix suggestions when possible\n\n"
        f"Chosen method: {method}\n"
        f"Changed files (code): {', '.join(changed.code_paths) if changed.code_paths else '—'}\n"
        f"Changed files (docs): {', '.join(changed.doc_paths) if changed.doc_paths else '—'}\n"
        f"Changed files (other): {', '.join(changed.other_paths) if changed.other_paths else '—'}\n"
        f"Excluded (not sent): {', '.join([f'{p}({r})' for p, r in changed.excluded]) if changed.excluded else '—'}\n"
    )

def _failure_body(lang: str, *, cause: str) -> str:
    if lang == "ja":
        return (
            "## 概要\n\n"
            f"- Codex 実行に失敗しました（{cause}）。\n\n"
            "## P0（必ず修正）\n\n"
            "- —\n\n"
            "## P1（修正推奨）\n\n"
            "- —\n\n"
            "## 質問\n\n"
            "- —\n\n"
            "## 次のアクション（提案）\n\n"
            "- `--dry-run` で方式/除外を確認する\n"
            "- `--method prompt|review` を指定して再実行する\n"
            "- 対象が大きい場合は分割して複数レポートにする\n"
            "- `codex login` 状態を確認する\n\n"
        )
    return (
        "## Summary\n\n"
        f"- Codex execution failed ({cause}).\n\n"
        "## P0 (Must Fix)\n\n"
        "- —\n\n"
        "## P1 (Should Fix)\n\n"
        "- —\n\n"
        "## Questions\n\n"
        "- —\n\n"
        "## Suggested Next Actions\n\n"
        "- Run with `--dry-run` to confirm method/exclusions\n"
        "- Retry with `--method prompt|review`\n"
        "- If the input is too large, split the review into multiple runs\n"
        "- Check `codex login` status\n\n"
    )


def _extract_codex_agent_message(jsonl: str) -> str:
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


def _build_prompt_based_input(repo_dir: Path, *, changed: ChangeSummary, lang: str) -> str:
    safe_paths = list(changed.code_paths) + list(changed.doc_paths) + list(changed.other_paths)
    prompt_method = "プロンプト入力（対象絞り込み）" if lang == "ja" else "prompt (targeted input)"
    header = _review_prompt(lang, changed=changed, method=prompt_method)

    if not safe_paths:
        return header + ("\n\n変更が見つかりませんでした。\n" if lang == "ja" else "\n\nNo changes found.\n")

    staged_label = "### Staged Diff" if lang != "ja" else "### ステージ済み差分"
    unstaged_label = "### Unstaged Diff" if lang != "ja" else "### 未ステージ差分"
    untracked_label = "### Untracked File: " if lang != "ja" else "### 未追跡ファイル: "

    diff_parts: list[str] = []
    if safe_paths:
        diff_unstaged = _redact_text(_run(["git", "diff", "--no-color", "--", *safe_paths], cwd=repo_dir))
        diff_staged = _redact_text(_run(["git", "diff", "--cached", "--no-color", "--", *safe_paths], cwd=repo_dir))
        if diff_staged.strip():
            diff_parts.append(staged_label + "\n```diff\n" + diff_staged.rstrip() + "\n```")
        if diff_unstaged.strip():
            diff_parts.append(unstaged_label + "\n```diff\n" + diff_unstaged.rstrip() + "\n```")

    # Untracked files: include content (if safe) because git diff won't show them.
    untracked_raw = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo_dir)
    untracked = [p for p in untracked_raw.split("\0") if p.strip()]
    untracked_safe: list[str] = []
    for rp in untracked:
        if rp in safe_paths:
            untracked_safe.append(rp)
    if untracked_safe:
        blocks: list[str] = []
        for rp in untracked_safe[:20]:
            abs_path = repo_dir / rp
            try:
                text = _redact_text(abs_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            blocks.append(f"{untracked_label}{rp}\n```text\n{text.rstrip()}\n```")
        if blocks:
            diff_parts.append("\n".join(blocks))

    body = "\n\n".join(diff_parts) if diff_parts else ("(diff empty)" if lang != "ja" else "（diffなし）")
    return header + "\n\n" + body


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


def _format_excluded(excluded: tuple[tuple[str, str], ...], *, lang: str) -> str:
    if not excluded:
        return "—"
    parts: list[str] = []
    for path, reason in excluded:
        parts.append(f"{path}({_i18n_exclude_reason(reason, lang=lang)})")
    return ", ".join(parts)


def _report_preamble(
    lang: str,
    *,
    repo_dir: Path,
    method_cmd: str,
    method_note: str,
    review_mode: str,
    scope: str,
    excluded: tuple[tuple[str, str], ...],
) -> str:
    today = _today_iso()
    excluded_text = _format_excluded(excluded, lang=lang)
    if lang == "ja":
        note = f"（{method_note}）" if method_note else ""
        return (
            f"# Codex レビュー ({today})\n\n"
            f"- 日付: `{today}`\n"
            f"- 対象: `{repo_dir}`\n"
            f"- 方式: `{method_cmd}`{note}\n"
            f"- レビューモード: `{review_mode}`\n"
            f"- スコープ: `{scope}`\n"
            f"- 除外: {excluded_text}\n\n"
        )
    note = f" ({method_note})" if method_note else ""
    return (
        f"# Codex Review ({today})\n\n"
        f"- date: `{today}`\n"
        f"- repo/layer: `{repo_dir}`\n"
        f"- method: `{method_cmd}`{note}\n"
        f"- review_mode: `{review_mode}`\n"
        f"- scope: `{scope}`\n"
        f"- excluded: {excluded_text}\n\n"
    )


def _runlog_section(lang: str, entries: list[tuple[str, str | None]]) -> str:
    if not entries:
        return ""
    title = "## 実行ログ" if lang == "ja" else "## Execution Log"
    lines: list[str] = [title, ""]
    for label, err in entries:
        if err:
            if lang == "ja":
                lines.append(f"- {label}: 失敗")
                lines.append(f"  - エラー: {err}")
            else:
                lines.append(f"- {label}: failed")
                lines.append(f"  - error: {err}")
        else:
            lines.append(f"- {label}: {'成功' if lang == 'ja' else 'ok'}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex review and save report (auto method selection).")
    parser.add_argument("--path", default=".", help="Target repo/layer directory (default: current dir).")
    parser.add_argument("--lang", default="auto", help="ja|en|auto (default: auto via env; prefer explicit).")
    parser.add_argument("--mode", choices=["uncommitted"], default="uncommitted", help="Review mode (default: uncommitted).")
    parser.add_argument(
        "--method",
        choices=["auto", "review", "prompt"],
        default="auto",
        help="Force method. auto=choose based on changed file types.",
    )
    parser.add_argument("--keep-tmp", action="store_true", help="Keep temp working directory for prompt-based exec (debug).")
    parser.add_argument("--timeout", type=float, default=None, help="Timeout seconds for Codex CLI execution (optional).")
    parser.add_argument("--dry-run", action="store_true", help="Print chosen method and exit.")
    args = parser.parse_args()

    repo_dir = Path(args.path)
    if not repo_dir.exists():
        raise SystemExit(f"[ERROR] path not found: {repo_dir}")
    repo_dir = repo_dir.resolve()

    if not _is_git_repo(repo_dir):
        raise SystemExit(f"[ERROR] not a git repository: {repo_dir}")

    rel_paths = _git_uncommitted_paths(repo_dir)
    changed = _summarize_changes(repo_dir, rel_paths)

    sample_parts: list[str] = []
    if rel_paths:
        sample_parts.append("\n".join(rel_paths))
    layer_yaml = repo_dir / "layer.yaml"
    if layer_yaml.exists():
        try:
            sample_parts.append(layer_yaml.read_text(encoding="utf-8")[:5000])
        except Exception:
            pass
    lang = _pick_lang(args.lang, sample="\n".join(sample_parts))

    if args.method == "review":
        chosen = "review"
    elif args.method == "prompt":
        chosen = "prompt"
    else:
        chosen = "review" if changed.code_paths else "prompt"
        # Safety: if excluded files exist, avoid codex review (cannot exclude them).
        if chosen == "review" and changed.excluded:
            chosen = "prompt"

    if args.dry_run:
        print(f"[INFO] repo: {repo_dir}")
        print(f"[INFO] lang: {lang}")
        print(f"[INFO] mode: {args.mode}")
        print(f"[INFO] chosen method: {chosen}")
        print(f"[INFO] code: {len(changed.code_paths)} docs: {len(changed.doc_paths)} other: {len(changed.other_paths)} excluded: {len(changed.excluded)}")
        return 0

    out_dir = _output_dir(repo_dir)
    out_path = _unique_output_path(out_dir, stem=f"codex_review_{_today_iso()}")

    runlog: list[tuple[str, str | None]] = []

    def write_report(method_cmd: str, method_note: str, body: str) -> None:
        report = _report_preamble(
            lang,
            repo_dir=repo_dir,
            method_cmd=method_cmd,
            method_note=method_note,
            review_mode=args.mode,
            scope=str(repo_dir),
            excluded=changed.excluded,
        )
        report += _runlog_section(lang, runlog)
        report += body
        out_path.write_text(report, encoding="utf-8")

    def run_review() -> tuple[str, str, str]:
        method_cmd = "codex exec（差分レビュー）" if lang == "ja" else "codex exec (diff review)"
        method_note = "差分レビュー" if lang == "ja" else "diff-based review"
        prompt_method = "差分レビュー（git差分を参照）" if lang == "ja" else "diff review (via git)"
        prompt = _review_prompt(lang, changed=changed, method=prompt_method)
        if lang == "ja":
            prompt += (
                "\n\n追加指示:\n"
                "- このリポジトリの未コミット差分（staged/unstaged/untracked）をレビュー対象とする\n"
                "- `git status --short` と `git diff --no-color` / `git diff --cached --no-color` を参照する\n"
                "- ファイルの書き換えや破壊的コマンドは実行しない\n"
            )
        else:
            prompt += (
                "\n\nAdditional instructions:\n"
                "- Review the current uncommitted changes (staged/unstaged/untracked)\n"
                "- Use `git status --short`, `git diff --no-color`, and `git diff --cached --no-color`\n"
                "- Do not modify files or run destructive commands\n"
            )
        out = _run(
            ["codex", "-s", "read-only", "-a", "never", "exec", "--json", "-"],
            cwd=repo_dir,
            input_text=prompt,
            timeout_s=args.timeout,
        )
        return (method_cmd, method_note, _extract_codex_agent_message(out))

    def run_prompt() -> tuple[str, str, str]:
        method_cmd = "codex exec"
        method_note = "プロンプト入力（対象絞り込み）" if lang == "ja" else "prompt-based (targeted input)"
        prompt = _build_prompt_based_input(repo_dir, changed=changed, lang=lang)

        def run_in_tmp(tmp: Path) -> str:
            out = _run(
                ["codex", "-s", "read-only", "-a", "never", "exec", "--json", "--skip-git-repo-check", "-C", str(tmp), "-"],
                cwd=repo_dir,
                input_text=prompt,
                timeout_s=args.timeout,
            )
            return _extract_codex_agent_message(out)

        if args.keep_tmp:
            tmp_dir = out_dir / ".tmp_codex_review"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            text = run_in_tmp(tmp_dir)
        else:
            with tempfile.TemporaryDirectory(prefix="tmp_codex_review_", dir=str(out_dir)) as tmp_name:
                text = run_in_tmp(Path(tmp_name))

        return (method_cmd, method_note, text)

    def attempt(method: str) -> tuple[str, str, str]:
        return run_review() if method == "review" else run_prompt()

    try:
        method_cmd, method_note, text = attempt(chosen)
        write_report(method_cmd, method_note, text)
        print(f"[OK] Wrote: {out_path}")
        return 0
    except CodexReviewError as e:
        runlog.append((f"attempt: {chosen}", str(e)))
    except KeyboardInterrupt:
        runlog.append((f"attempt: {chosen}", "interrupted"))
        write_report("interrupted", "", _failure_body(lang, cause="interrupted"))
        print(f"[ERROR] Interrupted; wrote report: {out_path}")
        return 130

    # If the user forced a method, stop here (but keep the report).
    if args.method != "auto":
        write_report("error", "", _failure_body(lang, cause="error"))
        print(f"[ERROR] Review failed; wrote report: {out_path}")
        return 1

    # Fallback (auto only)
    fallback = "prompt" if chosen == "review" else "review"
    if fallback == "review" and changed.excluded:
        # Cannot safely exclude paths with codex review.
        write_report("error", "", _failure_body(lang, cause="error"))
        print(f"[ERROR] Review failed; wrote report: {out_path}")
        return 1

    try:
        method_cmd, method_note, text = attempt(fallback)
        runlog.append((f"fallback: {fallback}", None))
        write_report(method_cmd, method_note, text)
        print(f"[OK] Wrote: {out_path}")
        return 0
    except CodexReviewError as e:
        runlog.append((f"fallback: {fallback}", str(e)))
        write_report("error", "", _failure_body(lang, cause="error"))
        print(f"[ERROR] Review failed; wrote report: {out_path}")
        return 1
    except KeyboardInterrupt:
        runlog.append((f"fallback: {fallback}", "interrupted"))
        write_report("interrupted", "", _failure_body(lang, cause="interrupted"))
        print(f"[ERROR] Interrupted; wrote report: {out_path}")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
