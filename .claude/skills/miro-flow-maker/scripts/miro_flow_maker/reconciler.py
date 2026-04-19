"""再調停（reconciliation）モジュール。

前回 run log と board 上の item 一覧を照合し、DrawingPlan の各 item に対して
update / create / skip / stop / orphaned の判定を行う。

UpdateHandler / AppendHandler の前提モジュール。Miro API は直接呼ばない
（board_items / board_connectors は呼び出し側で事前取得して渡す設計）。

設計方針:
- run log を唯一の metadata 源泉とする（P0-2）
- system lane は使わず SystemLabel を利用する（P0-1）
- MVP では自動削除しない。confirmed から消えた managed item は orphaned として記録（P1-3）
- frame 内 item のみを対象とする（P1-2）
- connector の接続先解決は reconciler の責務外（handler が実行時に解決）
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from miro_flow_maker._constants import (
    ItemAction,
    SkipReason,
    UpdateMode,
)
from miro_flow_maker.layout import DrawingPlan
from miro_flow_maker.run_log import RunLog, build_id_mapping_from_run_log

logger = logging.getLogger(__name__)

__all__ = [
    "ReconcileAction",
    "ReconcileResult",
    "reconcile",
    "backfill_miro_item_ids",
]


# ---------------------------------------------------------------------------
# データ型定義
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileAction:
    """item 単位の再調停判定結果。"""

    stable_item_id: str
    plan_id: str
    """DrawingPlan 内の item id。handler が plan item を特定するために使用する。"""
    render_role: str
    """'lane_container', 'node_shape', 'system_label', 'edge_connector' 等。"""
    action: str
    """'update', 'create', 'skip', 'stop', 'orphaned' のいずれか。"""
    miro_item_id: str | None
    """既存 item の場合の Miro ID。create / orphaned / skip の場合は None も可。"""
    reason: str | None
    """判定理由。ユーザや後段 handler 向けの説明文。"""
    update_mode: str
    """'managed', 'manual_detached', 'unmanaged' のいずれか。"""
    skip_reason: str | None = None
    """skip 判定の構造化ラベル（``SkipReason`` 値）。skip 以外は None。

    P2 指摘（2 回目）への対応。従来の reason 文字列マッチによる分類は文言
    変更に脆弱だったため、reconciler 側で構造化ラベルを設定し、
    ``update_handler._classify_skip_status`` はこのフィールドを参照する。
    後方互換のためデフォルト値 ``None`` を与え、既存の位置引数構築箇所は
    そのまま動作する。
    """


@dataclass(frozen=True)
class ReconcileResult:
    """再調停の全体結果。"""

    actions: list[ReconcileAction]
    stop_reasons: list[str]
    orphaned_items: list[ReconcileAction]
    """confirmed から消えた managed item。自動削除せず記録のみ行う。"""
    stopped: bool


# ---------------------------------------------------------------------------
# 内部ヘルパ
# ---------------------------------------------------------------------------


def _iter_plan_items(drawing_plan: DrawingPlan):
    """DrawingPlan 内の item を (plan_id, render_role, label) のタプルで列挙する。

    Returns:
        yield 形式で (plan_id, render_role, label | None) を返す。
        label は backfill 時の content 照合に用いる。connector は label 照合対象外。
    """
    # frame は特別: plan_id = "frame"
    yield ("frame", "frame", drawing_plan.frame.title)
    for lane in drawing_plan.lanes:
        yield (lane.id, "lane_container", lane.label)
    for node in drawing_plan.nodes:
        yield (node.id, "node_shape", node.label)
    for sl in drawing_plan.system_labels:
        yield (sl.id, "system_label", sl.label)
    for ep in drawing_plan.endpoints:
        yield (ep.id, "endpoint_shape", ep.label)
    for conn in drawing_plan.connectors:
        yield (conn.id, "edge_connector", None)


def _build_stable_to_run_log_entries(
    prev_run_log: RunLog | None,
) -> dict[str, list[dict[str, object]]]:
    """run log の item_results を stable_item_id ごとにグルーピングする。

    stable_item_id が重複している場合の検出（stop 判定）に利用する。
    """
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    if prev_run_log is None:
        return grouped
    for item in prev_run_log.item_results:
        if not isinstance(item, dict):
            continue
        stable_id = item.get("stable_item_id")
        if not isinstance(stable_id, str) or not stable_id:
            continue
        grouped[stable_id].append(item)
    return grouped


def _get_update_mode(entries: list[dict[str, object]]) -> str:
    """run log item エントリ群から update_mode を決定する。

    複数エントリがある場合は先頭の値を採用（重複 stop 判定は別途行う）。
    update_mode 欄が欠落している（SG2 既存形式）場合は 'managed' 扱い。
    """
    if not entries:
        return UpdateMode.MANAGED
    raw = entries[0].get("update_mode")
    if isinstance(raw, str) and raw:
        return raw
    return UpdateMode.MANAGED


def _get_run_log_flow_group_id(entries: list[dict[str, object]]) -> str | None:
    """run log item エントリから flow_group_id を取り出す。"""
    if not entries:
        return None
    raw = entries[0].get("flow_group_id")
    if isinstance(raw, str) and raw:
        return raw
    return None


def _collect_board_item_ids(board_items: list[dict[str, Any]]) -> set[str]:
    """board item id の集合を返す（stale 検出用）。"""
    ids: set[str] = set()
    for item in board_items:
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            ids.add(item_id)
    return ids


def _collect_frame_scoped_item_ids(
    board_items: list[dict[str, Any]],
    frame_id: str,
) -> set[str]:
    """frame の子 item（parent.id == frame_id）の id 集合を返す。

    Miro API v2 の item レスポンスでは parent は ``{"id": "..."}`` または ``parent_id`` の
    いずれかで表現される可能性があるため両方を確認する。
    """
    ids: set[str] = set()
    for item in board_items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        parent_obj = item.get("parent")
        parent_id: str | None = None
        if isinstance(parent_obj, dict):
            pid = parent_obj.get("id")
            if isinstance(pid, str):
                parent_id = pid
        if parent_id is None:
            raw = item.get("parent_id")
            if isinstance(raw, str):
                parent_id = raw
        if parent_id == frame_id:
            ids.add(item_id)
    return ids


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def reconcile(
    drawing_plan: DrawingPlan,
    metadata_map: dict[str, dict[str, str]],
    prev_run_log: RunLog | None,
    board_items: list[dict[str, Any]],
    board_connectors: list[dict[str, Any]],
    frame_id: str,
) -> ReconcileResult:
    """DrawingPlan と前回 run log / board 状態を照合して ReconcileAction を算出する。

    処理順序は仕様書 Step 1-8 に準拠する。

    Args:
        drawing_plan: confirmed 入力から生成した描画計画。
        metadata_map: plan item id -> metadata dict。stable_item_id / flow_group_id 等を保持。
        prev_run_log: 前回実行の run log。初回実行の場合は None。
        board_items: 現在の board 上の item 一覧（MiroClient.get_items_on_board の結果）。
        board_connectors: 現在の board 上の connector 一覧（stale 検出用）。
        frame_id: 対象 frame の Miro ID。frame 外の item は判定対象外。

    Returns:
        ReconcileResult: 各 item の判定結果、停止理由、orphaned リスト、停止フラグ。
    """
    # --- Step 1: 前回 run log からマッピングを復元 ---
    id_mapping = (
        build_id_mapping_from_run_log(prev_run_log) if prev_run_log is not None else {}
    )
    stable_to_entries = _build_stable_to_run_log_entries(prev_run_log)

    # --- Step 2: board 上の item id 集合を構築（stale 検出用） ---
    board_all_ids = _collect_board_item_ids(board_items)
    board_connector_ids = _collect_board_item_ids(board_connectors)
    # shape と connector を合わせた存在集合
    board_existing_ids: set[str] = board_all_ids | board_connector_ids

    # --- Step 3: frame 内 item の id 集合 ---
    frame_scoped_ids = _collect_frame_scoped_item_ids(board_items, frame_id)
    # connector は parent を持たないため frame 内判定から除外し、連携時は shape 側で判断する

    actions: list[ReconcileAction] = []
    stop_reasons: list[str] = []
    stopped = False

    # DrawingPlan に含まれる plan_id 集合（orphaned 判定用に先に構築）
    plan_ids_in_drawing: set[str] = set()
    plan_stable_ids: set[str] = set()

    # --- Step 6: DrawingPlan の各 item について判定 ---
    for plan_id, render_role, _label in _iter_plan_items(drawing_plan):
        plan_ids_in_drawing.add(plan_id)

        meta = metadata_map.get(plan_id, {})
        stable_id = meta.get("stable_item_id", "")
        plan_flow_group_id = meta.get("flow_group_id") or ""

        # metadata_map が未整備で stable_item_id が取れない場合は stop 理由に追加
        if not stable_id:
            reason = f"metadata_map に stable_item_id が無い: plan_id={plan_id}"
            actions.append(
                ReconcileAction(
                    stable_item_id="",
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.STOP,
                    miro_item_id=None,
                    reason=reason,
                    update_mode=UpdateMode.MANAGED,
                )
            )
            stop_reasons.append(reason)
            stopped = True
            continue

        plan_stable_ids.add(stable_id)

        # --- Step 8 (一部): flow_group_id 欠落チェック ---
        if not plan_flow_group_id:
            reason = (
                f"metadata_map に flow_group_id が無い: plan_id={plan_id} "
                f"stable_item_id={stable_id}"
            )
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.STOP,
                    miro_item_id=None,
                    reason=reason,
                    update_mode=UpdateMode.MANAGED,
                )
            )
            stop_reasons.append(reason)
            stopped = True
            continue

        # run log 側のエントリを取得（複数一致 / 0 一致 / 1 一致）
        run_log_entries = stable_to_entries.get(stable_id, [])

        # --- Step 6: stable_item_id 重複判定 → stop ---
        if len(run_log_entries) > 1:
            reason = (
                f"stable_item_id 重複: stable_item_id={stable_id} "
                f"(run log に {len(run_log_entries)} 件)"
            )
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.STOP,
                    miro_item_id=None,
                    reason=reason,
                    update_mode=UpdateMode.MANAGED,
                )
            )
            stop_reasons.append(reason)
            stopped = True
            continue

        # --- Step 4: update_mode 分類 ---
        update_mode = _get_update_mode(run_log_entries)

        # --- Step 5: flow_group_id 分離 ---
        run_log_flow_group_id = _get_run_log_flow_group_id(run_log_entries)
        if (
            run_log_flow_group_id is not None
            and run_log_flow_group_id != plan_flow_group_id
        ):
            # flow_group_id が異なるエントリは別 flow の item なので対象外扱い
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.SKIP,
                    miro_item_id=None,
                    reason=(
                        "flow_group_id が一致しない: "
                        f"plan={plan_flow_group_id} run_log={run_log_flow_group_id}"
                    ),
                    update_mode=update_mode,
                    skip_reason=SkipReason.FLOW_GROUP_MISMATCH,
                )
            )
            continue

        # --- Step 4 (続き): manual_detached / unmanaged は skip ---
        if update_mode == UpdateMode.MANUAL_DETACHED:
            miro_id = id_mapping.get(stable_id)
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.SKIP,
                    miro_item_id=miro_id,
                    reason="update_mode=manual_detached のため保護",
                    update_mode=update_mode,
                    skip_reason=SkipReason.MANUAL_DETACHED,
                )
            )
            continue
        if update_mode == UpdateMode.UNMANAGED:
            miro_id = id_mapping.get(stable_id)
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.SKIP,
                    miro_item_id=miro_id,
                    reason="update_mode=unmanaged のため保護",
                    update_mode=update_mode,
                    skip_reason=SkipReason.UNMANAGED,
                )
            )
            continue

        # --- Step 6 (続き): 1 件一致 / 0 件一致 判定 ---
        miro_id = id_mapping.get(stable_id)
        if miro_id is None:
            # 0 件一致 → create
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.CREATE,
                    miro_item_id=None,
                    reason="run log に miro_item_id が無い（新規作成対象）",
                    update_mode=update_mode,
                )
            )
            continue

        # --- Step 2 (遅延): stale miro_item_id 検出 → create 扱い ---
        if miro_id not in board_existing_ids:
            logger.warning(
                "stale miro_item_id: stable_item_id=%s miro_item_id=%s "
                "（board 上に存在しない）→ create 扱いに変更",
                stable_id,
                miro_id,
            )
            actions.append(
                ReconcileAction(
                    stable_item_id=stable_id,
                    plan_id=plan_id,
                    render_role=render_role,
                    action=ItemAction.CREATE,
                    miro_item_id=None,
                    reason="stale miro_item_id（board 上に存在しない）",
                    update_mode=update_mode,
                )
            )
            continue

        # --- Step 3 (遅延): frame 内 item 限定 ---
        # connector は frame 配下に属さないため shape のみ parent チェックする。
        # frame 自身は当然 frame の子ではないため判定対象から除外する。
        if render_role not in ("edge_connector", "frame"):
            if miro_id not in frame_scoped_ids:
                logger.warning(
                    "frame 外 item を検出: stable_item_id=%s miro_item_id=%s "
                    "frame_id=%s → skip 扱い",
                    stable_id,
                    miro_id,
                    frame_id,
                )
                actions.append(
                    ReconcileAction(
                        stable_item_id=stable_id,
                        plan_id=plan_id,
                        render_role=render_role,
                        action=ItemAction.SKIP,
                        miro_item_id=miro_id,
                        reason=f"frame_id={frame_id} の子ではないため対象外",
                        update_mode=update_mode,
                        skip_reason=SkipReason.FRAME_OUTSIDE,
                    )
                )
                continue

        # --- 1 件一致 → update ---
        actions.append(
            ReconcileAction(
                stable_item_id=stable_id,
                plan_id=plan_id,
                render_role=render_role,
                action=ItemAction.UPDATE,
                miro_item_id=miro_id,
                reason="run log の miro_item_id と 1:1 で一致",
                update_mode=update_mode,
            )
        )

    # --- Step 7: orphaned 検出 ---
    # run log に存在するが DrawingPlan に含まれない managed item。
    orphaned_items: list[ReconcileAction] = []
    for stable_id, entries in stable_to_entries.items():
        if stable_id in plan_stable_ids:
            continue
        update_mode = _get_update_mode(entries)
        if update_mode != "managed":
            # 非 managed は orphaned として扱わない（保護対象）
            continue
        # flow_group_id が現在の plan と異なる場合も orphaned ではなく対象外
        entry_flow_group_id = _get_run_log_flow_group_id(entries)
        # plan 側の flow_group_id は frame metadata に入っているはず
        frame_meta = metadata_map.get("frame", {})
        plan_flow_group_id = frame_meta.get("flow_group_id") or ""
        if entry_flow_group_id and plan_flow_group_id and entry_flow_group_id != plan_flow_group_id:
            continue
        render_role_raw = entries[0].get("render_role")
        render_role = (
            render_role_raw if isinstance(render_role_raw, str) and render_role_raw else "unknown"
        )
        miro_id = id_mapping.get(stable_id)
        orphaned_items.append(
            ReconcileAction(
                stable_item_id=stable_id,
                plan_id="",  # DrawingPlan に存在しない
                render_role=render_role,
                action=ItemAction.ORPHANED,
                miro_item_id=miro_id,
                reason="DrawingPlan に含まれないが run log 上は managed",
                update_mode=update_mode,
                skip_reason=SkipReason.ORPHANED,
            )
        )

    return ReconcileResult(
        actions=actions,
        stop_reasons=stop_reasons,
        orphaned_items=orphaned_items,
        stopped=stopped,
    )


# ---------------------------------------------------------------------------
# backfill_miro_item_ids
# ---------------------------------------------------------------------------


def _extract_content_text(item: dict[str, Any]) -> str | None:
    """board item の ``data.content`` からテキストを抽出する。

    Miro の content は HTML を含む場合があるためタグを単純除去する（厳密解析は行わない）。
    """
    data = item.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("content")
    if not isinstance(raw, str):
        # frame の title も data.title に入る場合があるため確認
        title = data.get("title")
        if isinstance(title, str):
            raw = title
        else:
            return None
    # 簡易な HTML タグ除去
    cleaned_parts: list[str] = []
    in_tag = False
    for ch in raw:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            cleaned_parts.append(ch)
    cleaned = "".join(cleaned_parts).strip()
    return cleaned or None


def _extract_connector_endpoints(conn: dict[str, Any]) -> tuple[str | None, str | None]:
    """board connector から startItem.id / endItem.id を抽出する。

    Miro API v2 の connector レスポンスでは、接続先は以下のいずれかの形式を取る:
    - ``{"startItem": {"id": "..."}, "endItem": {"id": "..."}}``
    - レガシー: ``{"data": {"startItem": {...}, "endItem": {...}}}``
    - key 名の揺れ (``start_item``) は Miro Web API では通常出ないが、
      呼び出し側テストの安全網として許容する。
    """
    def _id(obj: object) -> str | None:
        if isinstance(obj, dict):
            v = obj.get("id")
            if isinstance(v, str) and v:
                return v
        return None

    start = (
        _id(conn.get("startItem"))
        or _id(conn.get("start_item"))
    )
    end = (
        _id(conn.get("endItem"))
        or _id(conn.get("end_item"))
    )

    if start is None or end is None:
        data = conn.get("data")
        if isinstance(data, dict):
            if start is None:
                start = _id(data.get("startItem")) or _id(data.get("start_item"))
            if end is None:
                end = _id(data.get("endItem")) or _id(data.get("end_item"))

    return start, end


def backfill_miro_item_ids(
    run_log: RunLog,
    board_items: list[dict[str, Any]],
    board_connectors: list[dict[str, Any]],
    drawing_plan: DrawingPlan,
) -> dict[str, str]:
    """SG2 既存 run log（miro_item_id なし）を board 情報で補完する。

    shape の補完戦略:
    - board item の ``data.content`` と DrawingPlan の lane / node / system_label の
      label を照合し、1 件一致した場合のみマッピングに追加する
    - 複数一致 / 0 件一致は曖昧なのでスキップし、手動確認を促す

    connector の補完戦略（P0-B で追加）:
    1. run log entry の ``render_role`` が ``edge_connector`` (or ``semantic_type`` が
       ``business_flow`` / ``system_access``) のものを抽出
    2. entry の ``semantic_id`` を DrawingPlan の ConnectorPlan.id と照合し、
       ``from_plan_id`` / ``to_plan_id`` を取得
    3. DrawingPlan の plan_id → 既に補完済の stable_item_id → miro_item_id マッピング
       （lane / node / system_label）を逆引きし、board_connectors の
       ``startItem.id`` / ``endItem.id`` ペアと突き合わせる
    4. 1 件一致した場合のみマッピングに追加。複数一致 / 0 件一致はスキップ

    Args:
        run_log: 補完対象の RunLog（miro_item_id が欠落した SG2 形式想定）。
        board_items: 対象 board の item 一覧。
        board_connectors: 対象 board の connector 一覧。
        drawing_plan: 今回の実行で用いる DrawingPlan。

    Returns:
        補完後の stable_item_id -> miro_item_id マッピング。既にマッピングがある item は
        そのまま保持し、今回補完できた item のみ追加される。
    """
    # 既存マッピング（miro_item_id がすでに記録されている item）
    existing_mapping = build_id_mapping_from_run_log(run_log)

    # 補完対象: run log に stable_item_id はあるが miro_item_id が無い item
    missing_entries: list[dict[str, object]] = []
    for item in run_log.item_results:
        if not isinstance(item, dict):
            continue
        stable_id = item.get("stable_item_id")
        miro_id = item.get("miro_item_id")
        if not isinstance(stable_id, str) or not stable_id:
            continue
        if isinstance(miro_id, str) and miro_id:
            continue
        missing_entries.append(item)

    if not missing_entries:
        return dict(existing_mapping)

    # plan 側: stable_item_id -> label のマッピングを構築
    plan_labels_by_plan_id: dict[str, str] = {}
    plan_labels_by_plan_id["frame"] = drawing_plan.frame.title
    for lane in drawing_plan.lanes:
        plan_labels_by_plan_id[lane.id] = lane.label
    for node in drawing_plan.nodes:
        plan_labels_by_plan_id[node.id] = node.label
    for sl in drawing_plan.system_labels:
        plan_labels_by_plan_id[sl.id] = sl.label

    # connector plan 側: plan_id -> (from_plan_id, to_plan_id)
    connector_plan_map: dict[str, tuple[str, str]] = {
        conn.id: (conn.from_plan_id, conn.to_plan_id)
        for conn in drawing_plan.connectors
    }

    # board item を content テキストでグルーピング
    items_by_content: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in board_items:
        text = _extract_content_text(item)
        if not text:
            continue
        items_by_content[text].append(item)

    supplemented: dict[str, str] = dict(existing_mapping)

    # Pass 1: shape (non-connector) を先に補完する
    connector_entries: list[dict[str, object]] = []
    for entry in missing_entries:
        render_role = entry.get("render_role")
        semantic_type = entry.get("semantic_type")
        if render_role == "edge_connector" or semantic_type in (
            "business_flow",
            "system_access",
        ):
            connector_entries.append(entry)
            continue

        stable_id = entry.get("stable_item_id")
        if not isinstance(stable_id, str):
            continue

        # semantic_id を ヒントに plan 側 label を推定
        semantic_id_raw = entry.get("semantic_id")
        if not isinstance(semantic_id_raw, str) or not semantic_id_raw:
            logger.info(
                "backfill スキップ: semantic_id なし stable_item_id=%s",
                stable_id,
            )
            continue

        label = plan_labels_by_plan_id.get(semantic_id_raw)
        if label is None:
            logger.info(
                "backfill スキップ: DrawingPlan に一致する plan item なし "
                "stable_item_id=%s semantic_id=%s",
                stable_id,
                semantic_id_raw,
            )
            continue

        matches = items_by_content.get(label, [])
        if len(matches) == 1:
            miro_id = matches[0].get("id")
            if isinstance(miro_id, str) and miro_id:
                supplemented[stable_id] = miro_id
                logger.info(
                    "backfill 成功: stable_item_id=%s miro_item_id=%s (label=%r)",
                    stable_id,
                    miro_id,
                    label,
                )
            else:
                logger.info(
                    "backfill スキップ: board item の id が取得できない "
                    "stable_item_id=%s label=%r",
                    stable_id,
                    label,
                )
        elif len(matches) == 0:
            logger.info(
                "backfill スキップ (0 件一致): stable_item_id=%s label=%r "
                "（手動確認が必要）",
                stable_id,
                label,
            )
        else:
            logger.info(
                "backfill スキップ (複数一致 %d 件): stable_item_id=%s label=%r "
                "（手動確認が必要）",
                len(matches),
                stable_id,
                label,
            )

    # Pass 2: connector を補完する（P0-B）
    # Pass 1 で確定した shape の miro_item_id を使い、board_connectors の
    # startItem.id / endItem.id ペアから該当 connector を 1 件一致で特定する。
    if connector_entries and board_connectors:
        # plan_id -> miro_item_id（Pass 1 結果 + 既存マッピング）の逆引き辞書を
        # 作るために、run_log の (stable_item_id, plan_hint) から plan_id を引く
        # 方式は取らず、ConnectorPlan が保持する from/to plan_id をベースに
        # 直接比較する。そのため「plan_id -> miro_item_id」を求める必要がある。
        #
        # run_log entry には plan_id そのものは無いため、entry.semantic_id が
        # plan_id と一致する前提（metadata_helper の build_plan_metadata_map
        # が semantic_id = plan_id を設定している）を利用する。
        plan_id_to_miro: dict[str, str] = {}
        for entry in run_log.item_results:
            if not isinstance(entry, dict):
                continue
            stable_id_e = entry.get("stable_item_id")
            semantic_id_e = entry.get("semantic_id")
            if (
                not isinstance(stable_id_e, str)
                or not isinstance(semantic_id_e, str)
                or not stable_id_e
                or not semantic_id_e
            ):
                continue
            miro_id_e = supplemented.get(stable_id_e)
            if not miro_id_e:
                # 既存 entry の miro_item_id も許容（SG2 では欠落している想定）
                raw = entry.get("miro_item_id")
                if isinstance(raw, str) and raw:
                    miro_id_e = raw
            if miro_id_e:
                plan_id_to_miro[semantic_id_e] = miro_id_e

        # board connector の endpoint ペアを dict 化
        connectors_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(
            list
        )
        for conn in board_connectors:
            start_id, end_id = _extract_connector_endpoints(conn)
            if start_id and end_id:
                connectors_by_pair[(start_id, end_id)].append(conn)

        for entry in connector_entries:
            stable_id = entry.get("stable_item_id")
            if not isinstance(stable_id, str) or not stable_id:
                continue
            semantic_id_raw = entry.get("semantic_id")
            if not isinstance(semantic_id_raw, str) or not semantic_id_raw:
                logger.info(
                    "connector backfill スキップ: semantic_id なし "
                    "stable_item_id=%s",
                    stable_id,
                )
                continue

            plan_pair = connector_plan_map.get(semantic_id_raw)
            if plan_pair is None:
                logger.info(
                    "connector backfill スキップ: DrawingPlan に該当 ConnectorPlan なし "
                    "stable_item_id=%s semantic_id=%s",
                    stable_id,
                    semantic_id_raw,
                )
                continue

            from_plan_id, to_plan_id = plan_pair
            from_miro = plan_id_to_miro.get(from_plan_id)
            to_miro = plan_id_to_miro.get(to_plan_id)
            if not from_miro or not to_miro:
                logger.info(
                    "connector backfill スキップ: 接続先 shape の miro_item_id が "
                    "未解決 stable_item_id=%s from=%s to=%s",
                    stable_id,
                    from_plan_id,
                    to_plan_id,
                )
                continue

            matches = connectors_by_pair.get((from_miro, to_miro), [])
            if len(matches) == 1:
                conn_id = matches[0].get("id")
                if isinstance(conn_id, str) and conn_id:
                    supplemented[stable_id] = conn_id
                    logger.info(
                        "connector backfill 成功: stable_item_id=%s "
                        "miro_item_id=%s (from=%s -> to=%s)",
                        stable_id,
                        conn_id,
                        from_miro,
                        to_miro,
                    )
                else:
                    logger.info(
                        "connector backfill スキップ: connector id が取得できない "
                        "stable_item_id=%s",
                        stable_id,
                    )
            elif len(matches) == 0:
                logger.info(
                    "connector backfill スキップ (0 件一致): stable_item_id=%s "
                    "pair=(%s -> %s) （手動確認が必要）",
                    stable_id,
                    from_miro,
                    to_miro,
                )
            else:
                logger.info(
                    "connector backfill スキップ (複数一致 %d 件): "
                    "stable_item_id=%s pair=(%s -> %s) （手動確認が必要）",
                    len(matches),
                    stable_id,
                    from_miro,
                    to_miro,
                )

    return supplemented
