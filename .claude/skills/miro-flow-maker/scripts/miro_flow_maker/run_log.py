"""run log モジュール。

実行結果を JSON ファイルとして永続化する。
SG2 (create) / SG3 (update/append) 共通で使用する。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RunLog dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunLog:
    """1 実行単位の run log。JSON ファイルとして書き出す。"""

    run_id: str
    timestamp: str
    """ISO 8601 形式のタイムスタンプ"""

    mode: str
    """'create', 'update', 'append' のいずれか"""

    board_id: str | None
    frame_id: str | None
    flow_group_id: str
    dry_run: bool

    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int

    stop_reasons: list[str]
    duration_ms: int
    errors: list[str]

    item_results: list[dict[str, object]] = field(default_factory=list)
    """ItemResult + metadata を dict 化したもの"""

    partial_success: bool = False
    """SG3 追加: ExecutionResult.partial_success の転記。"""

    stopped_stage: str | None = None
    """SG3 追加: ExecutionResult.stopped_stage の転記。"""

    rerun_eligible: bool = True
    """SG3 追加: ExecutionResult.rerun_eligible の転記。"""


# ---------------------------------------------------------------------------
# build_run_log
# ---------------------------------------------------------------------------

def build_run_log(
    result: object,
    metadata_map: dict[str, dict[str, str]],
    duration_ms: int,
) -> RunLog:
    """ExecutionResult と metadata_map から RunLog を組み立てる。

    Args:
        result: ExecutionResult インスタンス。
        metadata_map: plan item id -> metadata dict のマッピング。
        duration_ms: 実行時間 (ミリ秒)。

    Returns:
        RunLog インスタンス。
    """
    # ExecutionResult の属性を直接参照する
    # (型ヒントを避けて循環インポートを回避)
    from miro_flow_maker.models import ExecutionResult

    assert isinstance(result, ExecutionResult)

    timestamp = datetime.now(timezone.utc).isoformat()

    # item_results を dict 化し、metadata 情報を付加
    item_dicts: list[dict[str, object]] = []
    for ir in result.item_results:
        item_dict: dict[str, object] = {
            "stable_item_id": ir.stable_item_id,
            "semantic_type": ir.semantic_type,
            "semantic_id": ir.semantic_id,
            "render_role": ir.render_role,
            "action": ir.action,
            "result": ir.result,
        }
        if ir.reason is not None:
            item_dict["reason"] = ir.reason
        # SG3: miro_item_id は値がある場合のみ書き出す（後方互換）
        if ir.miro_item_id is not None:
            item_dict["miro_item_id"] = ir.miro_item_id

        # metadata_map から追加情報を探す
        # stable_item_id -> plan item id の逆引きは metadata_map の値を走査
        for _plan_id, meta in metadata_map.items():
            if meta.get("stable_item_id") == ir.stable_item_id:
                # metadata の追加フィールドをマージ
                for key in (
                    "managed_by",
                    "project_id",
                    "layer_id",
                    "document_set_id",
                    "flow_group_id",
                    "update_mode",
                    "confirmation_packet_ref",
                ):
                    if key in meta:
                        item_dict[key] = meta[key]
                break

        item_dicts.append(item_dict)

    # errors: failed item の reason を収集
    errors: list[str] = []
    for ir in result.item_results:
        if ir.result == "failed" and ir.reason:
            errors.append(ir.reason)

    return RunLog(
        run_id=result.run_id,
        timestamp=timestamp,
        mode=result.mode,
        board_id=result.board_id,
        frame_id=result.frame_id,
        flow_group_id=result.flow_group_id,
        dry_run=result.dry_run,
        created_count=result.created_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        stop_reasons=list(result.stop_reasons),
        duration_ms=duration_ms,
        errors=errors,
        item_results=item_dicts,
        partial_success=result.partial_success,
        stopped_stage=result.stopped_stage,
        rerun_eligible=result.rerun_eligible,
    )


# ---------------------------------------------------------------------------
# write_run_log
# ---------------------------------------------------------------------------

def write_run_log(log: RunLog, log_dir: str) -> str:
    """RunLog を JSON ファイルに書き出す。

    ファイル名: ``{log_dir}/run_{run_id}_{timestamp}.json``
    ディレクトリが存在しない場合は自動作成する。

    Args:
        log: 書き出す RunLog。
        log_dir: 書き出し先ディレクトリ。

    Returns:
        書き出したファイルの絶対パス。
    """
    os.makedirs(log_dir, exist_ok=True)

    # ファイル名に使えない文字を置換 (ISO 8601 の ':' と '+')
    safe_ts = log.timestamp.replace(":", "").replace("+", "p")
    filename = f"run_{log.run_id}_{safe_ts}.json"
    filepath = os.path.join(log_dir, filename)

    log_dict = asdict(log)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(log_dict, f, ensure_ascii=False, indent=2)

    return os.path.abspath(filepath)


# ---------------------------------------------------------------------------
# load_run_log
# ---------------------------------------------------------------------------

def load_run_log(log_path: str) -> RunLog:
    """JSON ファイルから RunLog を復元する。

    SG2 既存 run log（miro_item_id / partial_success / stopped_stage /
    rerun_eligible が無い形式）との後方互換性を持つ。
    存在しないフィールドにはデフォルト値を適用する。

    NOTE: SG2 既存 run log には miro_item_id が無い。
    T003 reconciler の backfill_miro_item_ids() で
    board item 一覧から content 照合により補完する。

    Args:
        log_path: run log JSON ファイルへのパス。

    Returns:
        復元された RunLog インスタンス。
    """
    with open(log_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # item_results は dict のリストなのでそのまま読み込む
    item_results = data.get("item_results", [])
    if not isinstance(item_results, list):
        item_results = []

    return RunLog(
        run_id=data["run_id"],
        timestamp=data["timestamp"],
        mode=data["mode"],
        board_id=data.get("board_id"),
        frame_id=data.get("frame_id"),
        flow_group_id=data["flow_group_id"],
        dry_run=bool(data.get("dry_run", False)),
        created_count=int(data.get("created_count", 0)),
        updated_count=int(data.get("updated_count", 0)),
        skipped_count=int(data.get("skipped_count", 0)),
        failed_count=int(data.get("failed_count", 0)),
        stop_reasons=list(data.get("stop_reasons", []) or []),
        duration_ms=int(data.get("duration_ms", 0)),
        errors=list(data.get("errors", []) or []),
        item_results=list(item_results),
        # SG3 追加フィールド: 存在しない場合はデフォルト値を適用
        partial_success=bool(data.get("partial_success", False)),
        stopped_stage=data.get("stopped_stage"),
        rerun_eligible=bool(data.get("rerun_eligible", True)),
    )


# ---------------------------------------------------------------------------
# build_id_mapping_from_run_log
# ---------------------------------------------------------------------------

def find_latest_run_log(
    log_dir: str,
    board_id: str,
    frame_id: str,
    flow_group_id: str,
) -> RunLog | None:
    """log_dir 配下の run log を走査し、board_id / frame_id / flow_group_id
    が一致する最新の RunLog を返す。

    SG3 で update_handler と append_handler の両方から利用する共通関数
    （旧 ``_find_latest_run_log`` を統合）。

    仕様:
    - ファイル名規約: ``run_*.json``
    - mode は問わない（create / update / append の全てが対象）
    - timestamp は ISO 8601 文字列として文字列比較する
      （書式上、降順比較で最新を取得できる）
    - 読み込み失敗したファイル・形式不正なファイルは静かに無視する
    - ``log_dir`` が存在しない場合は None を返す

    Args:
        log_dir: run log ディレクトリのパス。
        board_id: 対象 board ID。
        frame_id: 対象 frame ID。
        flow_group_id: 対象 flow_group ID。

    Returns:
        最新の RunLog、該当が無ければ None。
    """
    if not os.path.isdir(log_dir):
        return None

    candidates: list[RunLog] = []
    for name in os.listdir(log_dir):
        if not name.startswith("run_") or not name.endswith(".json"):
            continue
        path = os.path.join(log_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            logger.debug("run log 読込失敗: %s", path)
            continue
        if not isinstance(data, dict):
            continue
        if data.get("board_id") != board_id:
            continue
        if data.get("frame_id") != frame_id:
            continue
        if data.get("flow_group_id") != flow_group_id:
            continue
        try:
            log = load_run_log(path)
        except Exception:
            logger.debug("run log load_run_log 失敗: %s", path)
            continue
        candidates.append(log)

    if not candidates:
        return None

    candidates.sort(key=lambda log: log.timestamp, reverse=True)
    return candidates[0]


def build_id_mapping_from_run_log(log: RunLog) -> dict[str, str]:
    """run log の item_results から stable_item_id -> miro_item_id のマッピングを構築する。

    miro_item_id が None / 欠落している item はスキップする。
    stable_item_id が空文字列の item もスキップする。

    NOTE: SG2 既存 run log には miro_item_id が無いため、このマッピングは空になる。
    T003 reconciler の backfill_miro_item_ids() で
    board item 一覧から content 照合により補完する想定。

    Args:
        log: RunLog インスタンス。

    Returns:
        stable_item_id -> miro_item_id の dict。miro_item_id が無い item は含まない。
    """
    mapping: dict[str, str] = {}
    for item in log.item_results:
        if not isinstance(item, dict):
            continue
        stable_id = item.get("stable_item_id")
        miro_id = item.get("miro_item_id")
        if not stable_id or not miro_id:
            continue
        if not isinstance(stable_id, str) or not isinstance(miro_id, str):
            continue
        mapping[stable_id] = miro_id
    return mapping
