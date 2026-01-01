#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


class WeeklyReviewError(Exception):
    pass


def _today_iso() -> str:
    return date.today().isoformat()


def _strip_yaml_comment(line: str) -> str:
    # Remove trailing YAML comment markers while keeping quoted strings intact.
    in_single = False
    in_double = False
    out: list[str] = []
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_yaml_scalar(value: str) -> Any:
    s = value.strip()
    if not s:
        return ""
    if s.startswith('"'):
        # Use JSON parser for JSON-compatible string escapes.
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s.strip('"')
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        inner = s[1:-1]
        return inner.replace("''", "'")
    low = s.lower()
    if low in {"null", "~"}:
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return s
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _parse_simple_yaml(text: str, *, path: Path) -> Any:
    """
    Minimal YAML parser for the subset used in legacy AIPO artifacts:
    - mappings (key: value, key: <nested>)
    - lists (- item, - key: value)
    - scalars (quoted strings, numbers, true/false/null)
    This is intentionally limited (no anchors, no multiline blocks).
    """

    lines = text.splitlines()

    def next_nonempty(i: int) -> tuple[int, int, str] | None:
        j = i
        while j < len(lines):
            raw = _strip_yaml_comment(lines[j])
            if raw.strip():
                indent = len(raw) - len(raw.lstrip(" "))
                return (j, indent, raw.lstrip(" "))
            j += 1
        return None

    root: Any = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    i = 0
    while i < len(lines):
        raw = _strip_yaml_comment(lines[i])
        i += 1
        if not raw.strip():
            continue
        if "\t" in raw:
            raise WeeklyReviewError(f"unsupported YAML (tabs) in {path}")

        indent = len(raw) - len(raw.lstrip(" "))
        content = raw.lstrip(" ")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise WeeklyReviewError(f"invalid indentation in {path}")
        container = stack[-1][1]

        # List item
        if content.startswith("- "):
            if not isinstance(container, list):
                raise WeeklyReviewError(f"unexpected list item at indent={indent} in {path}")
            item_text = content[2:].strip()
            if not item_text:
                # "-": decide next container type
                nxt = next_nonempty(i)
                child: Any = [] if (nxt and nxt[2].startswith("- ")) else {}
                container.append(child)
                if nxt:
                    stack.append((nxt[1] - 1, child))
                continue

            if ":" in item_text:
                k, v = item_text.split(":", 1)
                k = k.strip()
                v = v.strip()
                item: dict[str, Any] = {}
                if v:
                    item[k] = _parse_yaml_scalar(v)
                else:
                    nxt = next_nonempty(i)
                    child: Any = [] if (nxt and nxt[2].startswith("- ")) else {}
                    item[k] = child
                    if nxt:
                        stack.append((nxt[1] - 1, child))
                container.append(item)
                # Push this dict for further keys of the same list item.
                stack.append((indent, item))
                continue

            container.append(_parse_yaml_scalar(item_text))
            continue

        # Mapping entry
        if ":" not in content:
            raise WeeklyReviewError(f"unsupported YAML line in {path}: {content!r}")
        key, rest = content.split(":", 1)
        key = key.strip()
        rest = rest.strip()

        if not isinstance(container, dict):
            raise WeeklyReviewError(f"unexpected mapping entry under list at indent={indent} in {path}")

        if rest:
            container[key] = _parse_yaml_scalar(rest)
            continue

        # key: (nested)
        nxt = next_nonempty(i)
        child: Any
        if nxt and nxt[2].startswith("- "):
            child = []
        else:
            child = {}
        container[key] = child
        if nxt:
            stack.append((nxt[1] - 1, child))

    return root


def _read_structured_data(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WeeklyReviewError(f"missing file: {path}")

    # First try JSON (JSON-compatible YAML).
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback to a minimal YAML subset (legacy artifacts).
        return _parse_simple_yaml(text, path=path)


def _safe_filename(value: str) -> str:
    value = value.strip()
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^\w\-\.\u0080-\uffff]+", "", value)
    value = re.sub(r"_{2,}", "_", value).strip("_")
    return value or "item"


def _is_safe_relative_path(path_str: str) -> bool:
    p = Path(path_str)
    if p.is_absolute():
        return False
    if not p.parts:
        return False
    if ".." in p.parts:
        return False
    return True


def _relpath(from_dir: Path, to_path: Path) -> str:
    return os.path.relpath(str(to_path), start=str(from_dir))


def _parse_estimate_to_hours(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s:
        return None

    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|h|d)", s)
    if not m:
        return None

    qty = float(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return qty / 60.0
    if unit == "h":
        return qty
    if unit == "d":
        # AIPOの想定稼働（簡易）：1d=8h
        return qty * 8.0
    return None


def _z_90() -> float:
    # two-sided 90% CI -> z ~ 1.645
    return 1.645


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _pick_lang(lang_arg: str, *, sample: str) -> str:
    lang = (lang_arg or "").strip().lower()
    if lang in {"ja", "en"}:
        return lang
    # Allow environment override for manual runs.
    env_lang = (os.environ.get("AIPO_OPERATION_LANG") or os.environ.get("AIPO_LANG") or "").strip().lower()
    if env_lang in {"ja", "en"}:
        return env_lang
    # auto: choose based on presence of Japanese characters
    return "ja" if _contains_japanese(sample) else "en"


def _i18n(lang: str) -> dict[str, str]:
    if lang == "en":
        return {
            "title": "Weekly Review",
            "project_goal": "Project Goal",
            "project_structure": "Project Structure",
            "progress": "Progress",
            "eta": "Project ETA (90%)",
            "eta_missing": "ETA: — (cannot compute because estimates are missing)",
            "eta_label": "ETA: {eta}",
            "coverage_label": "Estimate coverage: {coverage}",
            "coverage_note": "Note: Some tasks are missing estimates; ETA precision is reduced.",
            "layer_table_header": "| Depth | Layer | Purpose | Work Summary | Final Deliverable | Path |",
            "layer_table_sep": "|---:|---|---|---|---|---|",
            "tasks_table_header": "| Task | Type | Status | Estimate | Command | Deliverables |",
            "tasks_table_sep": "|---|---|---|---|---|---|",
            "dash": "—",
            "work_empty": "—",
        }
    return {
        "title": "週次レビュー",
        "project_goal": "プロジェクトのゴール",
        "project_structure": "プロジェクトの全体構造",
        "progress": "プロジェクトの進捗",
        "eta": "プロジェクトのETA（90%）",
        "eta_missing": "ETA: —（estimate が不足しているため算出不可）",
        "eta_label": "ETA: {eta}",
        "coverage_label": "信頼係数（estimate coverage）: {coverage}",
        "coverage_note": "注: estimate が未設定のタスクがあるため、レンジの精度は低下します。",
        "layer_table_header": "| 階層 | レイヤー | 目的 | 作業概要 | 最終成果物 | パス |",
        "layer_table_sep": "|---:|---|---|---|---|---|",
        "tasks_table_header": "| タスク | 種別 | ステータス | 見積 | コマンド | 成果物 |",
        "tasks_table_sep": "|---|---|---|---|---|---|",
        "dash": "—",
        "work_empty": "—",
    }


def _normalize_task_type(value: str, lang: str) -> str:
    v = value.strip()
    if not v:
        return v
    if lang != "ja":
        return v
    mapping = {
        "research": "調査",
        "implementation": "実装",
        "verification": "検証",
        "coordination": "調整",
        "management": "管理",
        "decision": "意思決定",
        "design": "設計",
        "content": "コンテンツ",
        "planning": "計画",
        "deployment": "デプロイ",
        "review": "レビュー",
    }
    return mapping.get(v.lower(), v)


def _normalize_status(value: str, lang: str) -> str:
    v = value.strip()
    if not v:
        return v
    if lang != "ja":
        return v
    mapping = {
        "pending": "未着手",
        "in_progress": "進行中",
        "completed": "完了",
        "verified": "検証済",
        "ready": "準備完了",
        "pending_init": "初期化待ち",
    }
    return mapping.get(v.lower(), v)


def _status_bucket(status_raw: str) -> str:
    s = status_raw.strip().lower()
    if _task_status_is_done(s):
        return "done"
    if s in {"pending", "pending_init"}:
        return "pending"
    if s in {"in_progress"}:
        return "in_progress"
    return "other"


def _short_task_name(name: str, *, max_len: int = 48) -> str:
    s = name.strip()
    if not s:
        return s
    s = re.sub(r"^\s*(Deep Research:|Research:|Verification:)\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _infer_work_categories(layer: "LayerInfo", *, lang: str) -> list[str]:
    # Infer high-level work categories from task types and names (no translation).
    # Output is localized labels.
    labels = {
        "research": ("調査・分析", "Research & analysis"),
        "requirements": ("要件整理・仕様策定", "Requirements & specs"),
        "planning": ("計画・意思決定", "Planning & decisions"),
        "design": ("設計", "Design"),
        "implementation": ("実装・構築", "Implementation"),
        "verification": ("検証・レビュー", "Verification"),
        "content": ("コンテンツ制作", "Content creation"),
        "coordination": ("調整", "Coordination"),
        "ops": ("運用・リリース", "Ops & release"),
    }
    priority = [
        "requirements",
        "research",
        "design",
        "implementation",
        "content",
        "verification",
        "planning",
        "ops",
        "coordination",
    ]
    prio_idx = {k: i for i, k in enumerate(priority)}

    counts: dict[str, int] = {}

    for t in layer.tasks:
        matched: set[str] = set()

        ttype = (t.task_type or "").strip().lower()
        if ttype in {"research"}:
            matched.add("research")
        if ttype in {"planning", "management", "decision"}:
            matched.add("planning")
        if ttype in {"design"}:
            matched.add("design")
        if ttype in {"implementation", "deployment"}:
            matched.add("implementation")
        if ttype in {"verification", "review"}:
            matched.add("verification")
        if ttype in {"content"}:
            matched.add("content")
        if ttype in {"coordination"}:
            matched.add("coordination")

        name = (t.name or "").strip()
        low = name.lower()
        if name:
            if re.search(r"(調査|リサーチ|分析|ヒアリング|インタビュー|競合|市場)", name) or re.search(
                r"\b(research|analy[sz]e|analysis|interview|survey|competitor|market)\b", low
            ):
                matched.add("research")
            if re.search(r"(要件|仕様|要約|整理|課題|仮説|KPI|OKR|ゴール)", name) or re.search(
                r"\b(requirements?|specs?|specification|scope|kpi|okr|goal)\b", low
            ):
                matched.add("requirements")
            if re.search(r"(設計|デザイン|ワイヤ|UX|UI|情報設計)", name) or re.search(
                r"\b(design|ux|ui|wireframe|architecture)\b", low
            ):
                matched.add("design")
            if re.search(r"(実装|開発|構築|作成|作る|生成|コーディング)", name) or re.search(
                r"\b(implement|build|develop|coding|prototype)\b", low
            ):
                matched.add("implementation")
            if re.search(r"(検証|テスト|確認|レビュー|QA)", name) or re.search(
                r"\b(test|verify|review|qa|validate)\b", low
            ):
                matched.add("verification")
            if re.search(r"(執筆|記事|ライティング|コンテンツ|コピー|文章)", name) or re.search(
                r"\b(content|copy|write|writing|article)\b", low
            ):
                matched.add("content")
            if re.search(r"(運用|リリース|公開|配信|デプロイ)", name) or re.search(
                r"\b(deploy|release|launch|publish|operations?)\b", low
            ):
                matched.add("ops")
            if re.search(r"(調整|連携|合意|依頼|問い合わせ)", name) or re.search(
                r"\b(coordination|align|sync|stakeholder)\b", low
            ):
                matched.add("coordination")

        for k in matched:
            counts[k] = counts.get(k, 0) + 1

    keys = sorted(counts.keys(), key=lambda k: (-counts[k], prio_idx.get(k, 999), k))
    top = keys[:2]
    out: list[str] = []
    for k in top:
        ja, en = labels.get(k, (k, k))
        out.append(ja if lang == "ja" else en)
    return out


def _summarize_layer_tasks(layer: LayerInfo, *, lang: str, labels: dict[str, str]) -> str:
    if not layer.tasks:
        return labels["work_empty"]

    cats = _infer_work_categories(layer, lang=lang)
    if cats:
        if len(cats) == 1:
            if lang == "ja":
                sentence = f"{cats[0]}を進め、目的に沿った成果物を整える。"
            else:
                sentence = f"Advance {cats[0]} to produce the outputs needed for this layer’s goal."
        else:
            if lang == "ja":
                sentence = f"{cats[0]}を軸に、{cats[1]}まで進めて成果物を整える。"
            else:
                sentence = f"Advance {cats[0]} and {cats[1]} to produce the outputs needed for this layer’s goal."
    else:
        # Fallback: mention one concrete task as an example, without listing.
        example = ""
        for t in layer.tasks:
            n = _short_task_name(t.name or "")
            if n:
                example = n
                break
        if lang == "ja":
            sentence = f"{example}などを進め、目的達成に必要な作業を具体化する。" if example else "目的達成に必要な作業を具体化する。"
        else:
            sentence = f"Progress items like {example} to clarify the work needed for this layer’s goal." if example else "Clarify the work needed for this layer’s goal."

    # Keep cells compact.
    max_len = 140
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rstrip() + "…"
    return sentence


def _format_tree_prefix(ancestor_last: list[bool], *, is_last: bool, include_connector: bool) -> str:
    # Use HTML non-breaking spaces so indentation is preserved inside tables.
    parts: list[str] = []
    for last in ancestor_last:
        if last:
            parts.append("&nbsp;&nbsp;&nbsp;")
        else:
            parts.append("│&nbsp;&nbsp;")
    if include_connector:
        parts.append(("└─&nbsp;" if is_last else "├─&nbsp;"))
    return "".join(parts)


def _build_tree(
    layers: list[LayerInfo],
) -> tuple[list[LayerInfo], dict[Path, list[LayerInfo]], dict[Path, Path | None]]:
    by_id: dict[str, LayerInfo] = {}
    for li in layers:
        if li.layer_id and li.layer_id not in by_id:
            by_id[li.layer_id] = li

    # Parent mapping: prefer explicit parent id, else infer by closest ancestor path.
    parent_by_path: dict[Path, Path | None] = {}
    layer_paths = [li.path for li in layers]
    layer_paths_set = set(layer_paths)
    for li in layers:
        parent: Path | None = None
        if li.parent_layer_id and li.parent_layer_id in by_id:
            parent = by_id[li.parent_layer_id].path
        else:
            # infer: closest ancestor directory that is also a layer dir
            candidates = [p for p in li.path.parents if p in layer_paths_set]
            if candidates:
                parent = max(candidates, key=lambda p: len(p.as_posix()))
        parent_by_path[li.path] = parent

    children: dict[Path, list[LayerInfo]] = {li.path: [] for li in layers}
    roots: list[LayerInfo] = []
    for li in layers:
        parent = parent_by_path[li.path]
        if parent is None:
            roots.append(li)
        else:
            children.setdefault(parent, []).append(li)

    def sort_key(x: LayerInfo) -> tuple[str, str]:
        return (x.layer_id, x.path.as_posix())

    roots.sort(key=sort_key)
    for p in list(children.keys()):
        children[p].sort(key=sort_key)

    return roots, children, parent_by_path


def _layer_work_summary(from_dir: Path, layer: LayerInfo, *, lang: str, labels: dict[str, str]) -> str:
    # Summarize task contents ("what we do to achieve the goal"), not progress.
    return _summarize_layer_tasks(layer, lang=lang, labels=labels)

@dataclass(frozen=True)
class TaskRow:
    layer_path: Path
    task_id: str
    name: str
    task_type: str
    status: str
    estimate_raw: str | None
    estimate_hours: float | None
    command_path: Path | None
    deliverable_paths: tuple[Path, ...]


@dataclass(frozen=True)
class LayerInfo:
    path: Path
    project_name: str
    layer_id: str
    layer_name: str
    goal_desc: str
    goal_deliverable: str | None
    parent_layer_id: str | None
    tasks_path: Path | None
    tasks: tuple[TaskRow, ...]
    documents_dir: Path | None
    documents: tuple[Path, ...]


def _find_layer_dirs(base_dir: Path) -> list[Path]:
    layer_paths = sorted(base_dir.rglob("layer.yaml"))
    return [p.parent for p in layer_paths]


def _read_layer(layer_dir: Path) -> dict[str, Any]:
    layer = _read_structured_data(layer_dir / "layer.yaml")
    if not isinstance(layer, dict):
        raise WeeklyReviewError(f"layer.yaml must be a JSON object: {layer_dir}")
    return layer


def _read_tasks(layer_dir: Path) -> dict[str, Any] | None:
    p = layer_dir / "tasks.yaml"
    if not p.exists():
        return None
    tasks = _read_structured_data(p)
    if not isinstance(tasks, dict):
        raise WeeklyReviewError(f"tasks.yaml must be a JSON object: {layer_dir}")
    return tasks


def _pick_existing_dir(layer_dir: Path, candidates: list[str]) -> Path | None:
    # Prefer exact directory names present in the filesystem (important on case-insensitive FS).
    try:
        entries = {p.name: p for p in layer_dir.iterdir() if p.is_dir()}
    except FileNotFoundError:
        entries = {}
    for name in candidates:
        if name in entries:
            return entries[name]
    for name in candidates:
        p = layer_dir / name
        if p.is_dir():
            return p
    return None


def _list_documents(layer_dir: Path) -> tuple[Path | None, list[Path]]:
    docs_dir = _pick_existing_dir(layer_dir, ["documents", "Documents"])
    if not docs_dir:
        return (None, [])
    out: list[Path] = []
    for p in docs_dir.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            out.append(p.resolve())
    out.sort(key=lambda x: (x.parent.as_posix(), x.name))
    return (docs_dir.resolve(), out)


def _extract_outputs_from_command(command_md: Path) -> list[str]:
    try:
        text = command_md.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    # Very small, robust parser: find a "## Outputs" section and capture bullet-ish lines until next "## "
    m = re.search(r"(?m)^\s*##\s*Outputs\s*$", text)
    if not m:
        return []
    rest = text[m.end() :]
    stop = re.search(r"(?m)^\s*##\s+", rest)
    block = rest if not stop else rest[: stop.start()]

    outputs: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("-", "*")):
            item = line.lstrip("-*").strip()
            if item:
                outputs.append(item)
    return outputs


def _extract_path_candidates(text: str) -> list[str]:
    candidates: list[str] = []

    # 1) Common AIPO-relative path prefixes (robust against Japanese punctuation adjacency).
    prefixes = r"(?:@)?(?:Documents|documents|sublayers|site|Context|context|Commands|commands|weekly_review)"
    for m in re.finditer(rf"(?P<p>{prefixes}/[^\s`\"'()\[\]{{}}<>]+)", text):
        p = m.group("p").strip().strip(").,、。:;")
        if p.startswith("@"):
            p = p[1:]
        candidates.append(p)

    # 2) Fallback: permissive token that contains at least one slash.
    for m in re.finditer(r"(?P<p>[^\s`]+/[^\s`]+)", text):
        p = m.group("p").strip().strip(").,、。:;")
        if p.startswith(("http://", "https://")):
            continue
        if p.startswith("@"):
            p = p[1:]
        candidates.append(p)

    # Dedup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in candidates:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _resolve_task_command_path(layer_dir: Path, tasks_cfg: dict[str, Any] | None, task: dict[str, Any]) -> Path | None:
    cmd_dir = "commands"
    # Prefer existing command directory in the layer (legacy may use "Commands")
    existing_cmd_dir = _pick_existing_dir(layer_dir, ["commands", "Commands"])
    if existing_cmd_dir is not None:
        cmd_dir = existing_cmd_dir.name
    naming_pattern = "{task_id}_{task_name}.md"
    if isinstance(tasks_cfg, dict):
        cmd_cfg = tasks_cfg.get("command_generation")
        if isinstance(cmd_cfg, dict):
            if isinstance(cmd_cfg.get("target_dir"), str) and cmd_cfg["target_dir"].strip():
                cmd_dir = cmd_cfg["target_dir"].strip()
            if isinstance(cmd_cfg.get("naming_pattern"), str) and cmd_cfg["naming_pattern"].strip():
                naming_pattern = cmd_cfg["naming_pattern"].strip()

    candidates: list[Path] = []
    command_value = task.get("command")
    if isinstance(command_value, str) and command_value.strip():
        candidates.append(layer_dir / cmd_dir / f"{command_value.strip()}.md")

    task_id = str(task.get("id") or "").strip()
    task_name = str(task.get("name") or "").strip()
    if task_id and task_name:
        rendered = naming_pattern.format(task_id=_safe_filename(task_id), task_name=_safe_filename(task_name))
        candidates.append(layer_dir / cmd_dir / rendered)

    for p in candidates:
        if p.exists():
            return p
    return None


def _infer_task_deliverables(layer_dir: Path, task: dict[str, Any], command_path: Path | None) -> list[Path]:
    deliverables: list[Path] = []

    task_id = str(task.get("id") or "").strip()
    command_value = task.get("command")
    command_value = command_value.strip() if isinstance(command_value, str) else ""

    # 1) files in documents/ whose name contains task id or command
    _, docs = _list_documents(layer_dir)
    for p in docs:
        name = p.name
        if task_id and task_id in name:
            deliverables.append(p)
        elif command_value and command_value in name:
            deliverables.append(p)

    # 2) parse Outputs section of command file and treat path-like tokens as deliverables
    if command_path is not None and command_path.exists():
        for line in _extract_outputs_from_command(command_path):
            for cand in _extract_path_candidates(line):
                if not _is_safe_relative_path(cand):
                    continue
                resolved = (layer_dir / cand).resolve()
                # ensure it stays within layer_dir to avoid leaking outside by crafted text
                try:
                    resolved.relative_to(layer_dir.resolve())
                except ValueError:
                    continue
                if resolved.exists() and resolved.is_file():
                    deliverables.append(resolved.resolve())

    # 3) legacy fields (result/output/description/notes) often embed "Documents/..." paths
    for field in ["output", "result", "deliverables", "description", "notes"]:
        v = task.get(field)
        texts: list[str] = []
        if isinstance(v, str):
            texts = [v]
        elif isinstance(v, list):
            texts = [str(x) for x in v if isinstance(x, str)]
        elif isinstance(v, dict):
            texts = [json.dumps(v, ensure_ascii=False)]
        for text in texts:
            for cand in _extract_path_candidates(text):
                if not _is_safe_relative_path(cand):
                    continue
                resolved = (layer_dir / cand).resolve()
                try:
                    resolved.relative_to(layer_dir.resolve())
                except ValueError:
                    continue
                if resolved.exists() and resolved.is_file():
                    deliverables.append(resolved.resolve())

    # Dedup while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for p in deliverables:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _task_status_is_done(status: str) -> bool:
    # Status values vary by program. Treat these as "done" for ETA purposes.
    # - completed: finished
    # - verified: finished + reviewed/verified (common in some programs)
    return status.strip().lower() in {"completed", "verified"}


def _build_layer_info(base_dir: Path, layer_dir: Path) -> LayerInfo:
    layer = _read_layer(layer_dir)
    tasks_cfg = _read_tasks(layer_dir)

    project_name = str(layer.get("project_name") or base_dir.name)
    layer_id = str(layer.get("layer_id") or "").strip() or "UNKNOWN"
    layer_name = str(layer.get("layer_name") or layer_dir.name).strip()
    parent_layer_id_raw = layer.get("parent_layer_id")
    if parent_layer_id_raw is None:
        parent_layer_id_raw = layer.get("parent_layer")
    parent_layer_id = str(parent_layer_id_raw).strip() if isinstance(parent_layer_id_raw, str) and parent_layer_id_raw else None

    goal = layer.get("goal") if isinstance(layer.get("goal"), dict) else {}
    goal_desc = str(goal.get("description") or "").strip()
    goal_deliverable = str(goal.get("deliverable")).strip() if isinstance(goal.get("deliverable"), str) else None

    docs_dir, docs = _list_documents(layer_dir)

    task_rows: list[TaskRow] = []
    tasks_path: Path | None = (layer_dir / "tasks.yaml") if (layer_dir / "tasks.yaml").exists() else None
    if tasks_cfg is not None:
        tasks_list = tasks_cfg.get("tasks")
        if isinstance(tasks_list, list):
            for t in tasks_list:
                if not isinstance(t, dict):
                    continue
                task_id = str(t.get("id") or "").strip()
                name = str(t.get("name") or "").strip()
                task_type = str(t.get("type") or "").strip()
                status = str(t.get("status") or "").strip()
                estimate_raw = t.get("estimate")
                estimate_raw_s = str(estimate_raw).strip() if isinstance(estimate_raw, str) and estimate_raw.strip() else None
                estimate_hours = _parse_estimate_to_hours(estimate_raw_s) if estimate_raw_s else None
                command_path = _resolve_task_command_path(layer_dir, tasks_cfg, t)
                deliverables = tuple(_infer_task_deliverables(layer_dir, t, command_path))
                task_rows.append(
                    TaskRow(
                        layer_path=layer_dir,
                        task_id=task_id,
                        name=name,
                        task_type=task_type,
                        status=status,
                        estimate_raw=estimate_raw_s,
                        estimate_hours=estimate_hours,
                        command_path=command_path,
                        deliverable_paths=deliverables,
                    )
                )

    return LayerInfo(
        path=layer_dir,
        project_name=project_name,
        layer_id=layer_id,
        layer_name=layer_name,
        goal_desc=goal_desc,
        goal_deliverable=goal_deliverable,
        parent_layer_id=parent_layer_id,
        tasks_path=tasks_path,
        tasks=tuple(task_rows),
        documents_dir=docs_dir,
        documents=tuple(docs),
    )


def _md_link(label: str, rel_path: str) -> str:
    return f"[{label}]({rel_path})"


def _fmt_paths_as_links(from_dir: Path, paths: Iterable[Path]) -> str:
    items: list[str] = []
    for p in paths:
        rel = _relpath(from_dir, p)
        items.append(_md_link(p.name, rel))
    return "<br>".join(items) if items else "—"


def _render_layer_structure_table(from_dir: Path, layers: list[LayerInfo], labels: dict[str, str], *, lang: str) -> str:
    roots, children, _ = _build_tree(layers)

    lines: list[str] = []
    lines.append(labels["layer_table_header"])
    lines.append(labels["layer_table_sep"])

    def walk(node: LayerInfo, ancestor_last: list[bool]) -> None:
        # Determine this node's own last-flag from ancestor_last context is handled by caller.
        depth = len(ancestor_last)

        purpose = node.goal_desc or labels["dash"]
        deliverable_parts: list[str] = []
        if node.goal_deliverable:
            deliverable_parts.append(node.goal_deliverable)
        if node.documents:
            # Keep it short: show up to 3 file links, plus a link to the documents dir.
            doc_links = _fmt_paths_as_links(from_dir, node.documents[:3])
            deliverable_parts.append(f"docs: {doc_links}")
            if node.documents_dir is not None and node.documents_dir.is_dir():
                rel_docs_dir = _relpath(from_dir, node.documents_dir)
                deliverable_parts.append(f"dir: {_md_link(rel_docs_dir, rel_docs_dir)}")

        deliverable = "<br>".join(deliverable_parts) if deliverable_parts else labels["dash"]
        rel = _relpath(from_dir, node.path)
        path_link = _md_link(rel, rel)
        work = _layer_work_summary(from_dir, node, lang=lang, labels=labels)

        # Keep the label simple: identifier + name only (hierarchy is shown via Depth).
        layer_label = f"`{node.layer_id}` {node.layer_name}".strip() if (node.layer_id or node.layer_name) else labels["dash"]
        lines.append(f"| {depth} | {layer_label} | {purpose} | {work} | {deliverable} | {path_link} |")

        # Walk children
        kids = children.get(node.path, [])
        for idx, child in enumerate(kids):
            child_is_last = idx == (len(kids) - 1)
            walk(child, ancestor_last + [child_is_last])

    for ridx, root in enumerate(roots):
        # For root, ancestor_last is empty; children last-flag is decided in walk.
        walk(root, [])

    return "\n".join(lines)


def _render_tasks_table(from_dir: Path, layer: LayerInfo, labels: dict[str, str], *, lang: str) -> str:
    lines: list[str] = []
    lines.append(labels["tasks_table_header"])
    lines.append(labels["tasks_table_sep"])
    if not layer.tasks:
        dash = labels["dash"]
        lines.append(f"| {dash} | {dash} | {dash} | {dash} | {dash} | {dash} |")
        return "\n".join(lines)

    for t in layer.tasks:
        task_label = f"`{t.task_id}` {t.name}".strip() if t.task_id or t.name else labels["dash"]
        cmd = _md_link(t.command_path.name, _relpath(from_dir, t.command_path)) if t.command_path else labels["dash"]
        est = t.estimate_raw or labels["dash"]
        deliverables = _fmt_paths_as_links(from_dir, t.deliverable_paths)
        lines.append(
            f"| {task_label} | {_normalize_task_type(t.task_type or labels['dash'], lang)} | {_normalize_status(t.status or labels['dash'], lang)} | {est} | {cmd} | {deliverables} |"
        )
    return "\n".join(lines)


def _collect_all_tasks(layers: list[LayerInfo]) -> list[TaskRow]:
    out: list[TaskRow] = []
    for li in layers:
        out.extend(li.tasks)
    return out


def _compute_eta_90(tasks: list[TaskRow]) -> tuple[str, float] | None:
    remaining: list[TaskRow] = [t for t in tasks if not _task_status_is_done(t.status)]
    if not remaining:
        return ("0h (no remaining tasks)", 1.0)

    known = [t for t in remaining if isinstance(t.estimate_hours, (int, float))]
    coverage = len(known) / len(remaining) if remaining else 1.0
    if not known:
        return None

    # PERT-style: optimistic=0.7M, pessimistic=1.6M
    means: list[float] = []
    variances: list[float] = []
    for t in known:
        m = float(t.estimate_hours)  # type: ignore[arg-type]
        o = 0.7 * m
        p = 1.6 * m
        mean = (o + 4 * m + p) / 6.0
        std = (p - o) / 6.0
        means.append(mean)
        variances.append(std * std)

    total_mean = sum(means)
    total_std = (sum(variances) ** 0.5) if variances else 0.0
    z = _z_90()
    low = max(0.0, total_mean - z * total_std)
    high = max(0.0, total_mean + z * total_std)

    def fmt_hours(h: float) -> str:
        if h >= 16:
            return f"{h/8.0:.1f}d ({h:.1f}h)"
        return f"{h:.1f}h"

    return (f"{fmt_hours(low)} – {fmt_hours(high)} (90% interval)", coverage)


def _render_report(base_dir: Path, layers: list[LayerInfo], *, lang: str) -> str:
    root = layers[0] if layers else None
    project_name = root.project_name if root else base_dir.name
    goal = root.goal_desc if root and root.goal_desc else "—"
    labels = _i18n(lang)

    lines: list[str] = []
    lines.append(f"# {labels['title']} ({_today_iso()}) - {project_name}")
    lines.append("")
    lines.append(f"## {labels['project_goal']}")
    lines.append(f"- {goal}")
    lines.append("")

    lines.append(f"## {labels['project_structure']}")
    lines.append(_render_layer_structure_table(base_dir, layers, labels, lang=lang))
    lines.append("")

    lines.append(f"## {labels['progress']}")
    for li in layers:
        rel = _relpath(base_dir, li.path)
        lines.append(f"### `{li.layer_id}` {li.layer_name} ({_md_link(rel, rel)})")
        lines.append(_render_tasks_table(base_dir, li, labels, lang=lang))
        lines.append("")

    lines.append(f"## {labels['eta']}")
    eta = _compute_eta_90(_collect_all_tasks(layers))
    if eta is None:
        lines.append(f"- {labels['eta_missing']}")
    else:
        eta_str, coverage = eta
        coverage_str = f"{coverage:.0%}"
        lines.append(f"- {labels['eta_label'].format(eta=eta_str)}")
        lines.append(f"- {labels['coverage_label'].format(coverage=coverage_str)}")
        if coverage < 1.0:
            lines.append(f"- {labels['coverage_note']}")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate weekly review report for an AIPO program (Operation phase).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="Project directory name under programs/.")
    group.add_argument("--path", help="Direct path to a layer/program folder (must contain layer.yaml).")
    parser.add_argument(
        "--lang",
        choices=["ja", "en", "auto"],
        default="auto",
        help="Report language for headings/labels (default: auto; does not auto-translate free text fields).",
    )
    parser.add_argument(
        "--out",
        help="Output path (default: <layer_dir>/weekly_review/weekly_review_YYYY-MM-DD.md)",
    )
    args = parser.parse_args()

    if args.project:
        base_dir = Path("programs") / args.project
    else:
        base_dir = Path(args.path)

    if not (base_dir / "layer.yaml").exists():
        raise SystemExit(f"[ERROR] layer.yaml not found under: {base_dir}")

    layer_dirs = _find_layer_dirs(base_dir)
    if not layer_dirs:
        raise SystemExit(f"[ERROR] no layer.yaml found under: {base_dir}")

    layers = [_build_layer_info(base_dir, d) for d in layer_dirs]
    # Sort: root first (no parent), then by path for stable ordering
    layers.sort(key=lambda li: (0 if li.parent_layer_id is None else 1, li.path.as_posix()))

    out_path = Path(args.out) if args.out else (base_dir / "weekly_review" / f"weekly_review_{_today_iso()}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample = (layers[0].goal_desc if layers and layers[0].goal_desc else "") + " " + (layers[0].layer_name if layers else "")
    lang = _pick_lang(args.lang, sample=sample)
    out_path.write_text(_render_report(base_dir, layers, lang=lang), encoding="utf-8")

    print(f"[OK] Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
