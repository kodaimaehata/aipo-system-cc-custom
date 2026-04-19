"""update モード用ハンドラー。

既存 board 上の managed item を stable_item_id で再識別し、
差分更新を実行する。reconciler の判定結果に従って
update / create / skip / stop を item ごとに適用する。
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from dataclasses import replace
from typing import Any

from miro_flow_maker._constants import (
    ItemAction,
    ItemResultStatus,
    SkipReason,
    StoppedStage,
    UpdateMode,
)
from miro_flow_maker._frame_helpers import extract_frame_id_from_link
from miro_flow_maker._render_helpers import (
    ACTOR_LANE_STYLE,
    BACK_EDGE_CONNECTOR_STYLE,
    CONNECTOR_STYLE,
    ENDPOINT_STYLE,
    LANE_BOLD_WRAP,
    NODE_STYLE_BASE,
    NODE_STYLES,
    SYSTEM_LABEL_STYLE,
    SYSTEM_LANE_STYLE,
    node_shape,
    to_frame_local_center,
)
from miro_flow_maker.exceptions import ExecutionError
from miro_flow_maker.layout import (
    ConnectorPlan,
    DrawingPlan,
    EndpointPlan,
    FramePlan,
    LanePlan,
    NodePlan,
    SystemLabelPlan,
    build_drawing_plan,
)
from miro_flow_maker.metadata_helper import build_plan_metadata_map
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.models import (
    AppConfig,
    ConfirmedInput,
    ExecutionResult,
    ItemResult,
    RequestContext,
)
from miro_flow_maker.reconciler import (
    ReconcileAction,
    ReconcileResult,
    backfill_miro_item_ids,
    reconcile,
)
from miro_flow_maker.run_log import (
    RunLog,
    build_run_log,
    find_latest_run_log,
    write_run_log,
)

logger = logging.getLogger(__name__)

__all__ = ["UpdateHandler"]


# ---------------------------------------------------------------------------
# UpdateHandler
# ---------------------------------------------------------------------------


class UpdateHandler:
    """update モードの ModeHandler 実装。

    既存 board 上の managed item を stable_item_id で再識別し、
    差分更新を実行する。ModeHandler Protocol に準拠する。
    """

    def __init__(self, client: MiroClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(
        self,
        confirmed_input: ConfirmedInput,
        context: RequestContext,
        config: AppConfig,
    ) -> ExecutionResult:
        """update モードの実行。

        処理順序:
        1. build_drawing_plan / build_plan_metadata_map
        2. ExecutionResult 初期化
        3. dry-run チェック
        4. Stage1 resolve_board
        5. Stage2 resolve_frame
        6. 前回 run log の読み込み（backfill 含む）
        7. Stage3 reconcile
        8. Stage4 upsert shapes（lane / node / system_label / endpoint）
        9. Stage5 upsert connectors
        10. orphaned の ItemResult 記録
        11. 成功判定と run log 書き出し
        """
        start_ms = time.monotonic_ns() // 1_000_000
        run_id = str(uuid.uuid4())

        # 1. 描画計画 / metadata マップ生成（update では board_name は未使用）
        plan = build_drawing_plan(confirmed_input, board_name="")
        metadata_map = build_plan_metadata_map(confirmed_input, plan)

        # 2. ExecutionResult 初期化
        result = ExecutionResult(
            run_id=run_id,
            mode="update",
            success=False,
            board_id=context.board_id,
            frame_id=context.frame_id,
            flow_group_id=confirmed_input.flow_group_id,
            dry_run=context.dry_run,
        )

        # 3. dry-run: 実 API は呼ばず DrawingPlan と reconcile 概要だけ出力
        if context.dry_run:
            self._dry_run_output(plan, metadata_map, context)
            self._dry_run_generate_item_results(plan, metadata_map, result)
            result.success = True
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        # 4. Stage 1: resolve_board
        board_id = context.board_id
        if not board_id:
            reason = "board_id が指定されていない"
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_BOARD
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        try:
            self._client.get_board(board_id)
        except ExecutionError as exc:
            reason = f"board 取得失敗: {exc}"
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_BOARD
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        # 5. Stage 2: resolve_frame
        frame_id = context.frame_id
        if not frame_id and context.frame_link:
            frame_id = extract_frame_id_from_link(context.frame_link)

        if not frame_id:
            reason = "frame_id / frame_link のいずれからも frame_id を解決できない"
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_FRAME
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        try:
            board_items = self._client.get_items_on_board(board_id)
            board_connectors = self._client.get_connectors_on_board(board_id)
        except ExecutionError as exc:
            reason = f"board item / connector 一覧取得失敗: {exc}"
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_FRAME
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        # frame_id が board 上に存在するか確認
        frame_exists = any(
            isinstance(item.get("id"), str) and item["id"] == frame_id
            for item in board_items
        )
        if not frame_exists:
            reason = f"frame_id={frame_id} が board 上に存在しない"
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_FRAME
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        result.frame_id = frame_id

        # 6. 前回 run log を検索し、SG2 形式なら backfill
        prev_run_log = find_latest_run_log(
            config.log_dir,
            board_id,
            frame_id,
            confirmed_input.flow_group_id,
        )
        if prev_run_log is not None:
            prev_run_log = _backfill_run_log_if_needed(
                prev_run_log, board_items, board_connectors, plan
            )

        # 7. Stage 3: reconcile
        reconcile_result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=frame_id,
        )

        if reconcile_result.stopped:
            for reason in reconcile_result.stop_reasons:
                if reason not in result.stop_reasons:
                    result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RECONCILE
            result.rerun_eligible = False
            logger.error(
                "reconcile 段階で停止: reasons=%s", reconcile_result.stop_reasons
            )
            # orphaned も ItemResult に残す
            self._record_orphaned(reconcile_result, metadata_map, result)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        if reconcile_result.orphaned_items:
            for o in reconcile_result.orphaned_items:
                logger.warning(
                    "orphaned item 検出: stable_item_id=%s miro_item_id=%s "
                    "(DrawingPlan 対象外)",
                    o.stable_item_id,
                    o.miro_item_id,
                )

        # 8. Stage 4: upsert shapes
        id_map: dict[str, str] = {}
        # P0-C: skip された shape の plan_id を追跡し、connector 段階で
        # 接続先が skip されたかどうかを判定できるようにする。
        skipped_plan_ids: set[str] = set()
        stopped = self._upsert_shapes(
            board_id=board_id,
            frame_id=frame_id,
            plan=plan,
            metadata_map=metadata_map,
            actions=reconcile_result.actions,
            result=result,
            id_map=id_map,
            skipped_plan_ids=skipped_plan_ids,
        )
        if stopped:
            result.stopped_stage = StoppedStage.UPSERT_SHAPES
            # reconciler 由来の stop は rerun_eligible=False。
            # それ以外の API 失敗（transient）は handler 側で判断する。
            if result.rerun_eligible is None:
                result.rerun_eligible = False
            self._finalize(result, reconcile_result, metadata_map, start_ms, config)
            return result

        # 9. Stage 5: upsert connectors
        connector_stopped = self._upsert_connectors(
            board_id=board_id,
            plan=plan,
            metadata_map=metadata_map,
            actions=reconcile_result.actions,
            result=result,
            id_map=id_map,
            skipped_plan_ids=skipped_plan_ids,
        )
        if connector_stopped:
            result.stopped_stage = StoppedStage.UPSERT_CONNECTORS
            result.rerun_eligible = True
            self._finalize(result, reconcile_result, metadata_map, start_ms, config)
            return result

        # 10. orphaned を ItemResult に記録
        self._record_orphaned(reconcile_result, metadata_map, result)

        # 11. 成功判定 + run log 書き出し
        self._finalize(result, reconcile_result, metadata_map, start_ms, config)
        return result

    # ------------------------------------------------------------------
    # finalize / run log
    # ------------------------------------------------------------------

    def _finalize(
        self,
        result: ExecutionResult,
        reconcile_result: ReconcileResult,
        metadata_map: dict[str, dict[str, str]],
        start_ms: int,
        config: AppConfig,
    ) -> None:
        """成功判定・partial_success フラグ設定・run log 書き出しをまとめる。"""
        applied_count = result.created_count + result.updated_count
        stopped = result.stopped_stage is not None or len(result.stop_reasons) > 0

        result.success = result.failed_count == 0 and len(result.stop_reasons) == 0
        result.partial_success = applied_count > 0 and (
            result.failed_count > 0 or stopped
        )

        self._write_run_log(result, metadata_map, start_ms, config)

    @staticmethod
    def _write_run_log(
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        start_ms: int,
        config: AppConfig,
    ) -> None:
        """run log を書き出す。成功・失敗問わず呼ぶ。"""
        duration_ms = time.monotonic_ns() // 1_000_000 - start_ms
        log_dir = config.log_dir
        try:
            log = build_run_log(result, metadata_map, duration_ms)
            path = write_run_log(log, log_dir)
            logger.info("run log 書き出し完了: %s", path)
        except Exception:
            logger.exception("run log 書き出し失敗")

    # ------------------------------------------------------------------
    # dry-run helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_output(
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        context: RequestContext,
    ) -> None:
        """DrawingPlan / reconcile プレビューを stderr に出力する。"""
        w = sys.stderr.write
        w("=" * 60 + "\n")
        w("[DRY-RUN] update mode — Drawing Plan Summary\n")
        w("=" * 60 + "\n")
        w(f"\nBoard ID: {context.board_id}\n")
        w(f"Frame ID: {context.frame_id}\n")
        f = plan.frame
        w(f"Frame: {f.title} (x={f.x}, y={f.y}, w={f.width}, h={f.height})\n")
        w(f"\nLanes ({len(plan.lanes)}):\n")
        for lane in plan.lanes:
            w(f"  - {lane.id} [{lane.type}] \"{lane.label}\"\n")
        w(f"\nNodes ({len(plan.nodes)}):\n")
        for node in plan.nodes:
            w(f"  - {node.id} [{node.type}] \"{node.label}\" lane={node.lane_id}\n")
        w(f"\nSystemLabels ({len(plan.system_labels)}):\n")
        for sl in plan.system_labels:
            w(f"  - {sl.id} \"{sl.label}\" node={sl.node_id}\n")
        w(f"\nConnectors ({len(plan.connectors)}):\n")
        for conn in plan.connectors:
            label_str = f" \"{conn.label}\"" if conn.label else ""
            back_str = " (back_edge)" if conn.is_back_edge else ""
            w(f"  - {conn.id}: {conn.from_plan_id} -> {conn.to_plan_id}"
              f" [{conn.type}]{label_str}{back_str}\n")
        total = (
            1
            + len(plan.lanes)
            + len(plan.nodes)
            + len(plan.system_labels)
            + len(plan.endpoints)
            + len(plan.connectors)
        )
        w(f"\nTotal items: {total}\n")
        if metadata_map:
            first_key = next(iter(metadata_map))
            first_meta = metadata_map[first_key]
            w(f"\nMetadata sample (plan_id={first_key}):\n")
            for k, v in first_meta.items():
                w(f"  {k}: {v}\n")
        w(
            "\nReconcile preview: skipped — board state is not fetched in dry-run.\n"
        )
        w("=" * 60 + "\n")
        sys.stderr.flush()

    @staticmethod
    def _dry_run_generate_item_results(
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
    ) -> None:
        """dry-run 時に全 item の ItemResult を dry_run_skipped で生成する。"""

        def _add(plan_id: str, fallback_type: str, fallback_id: str, fallback_role: str) -> None:
            meta = metadata_map.get(plan_id, {})
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", fallback_type),
                semantic_id=meta.get("semantic_id", fallback_id),
                render_role=meta.get("render_role", fallback_role),
                action=ItemAction.UPDATE,
                result=ItemResultStatus.DRY_RUN_SKIPPED,
            ))
            result.skipped_count += 1

        _add("frame", "flow_group", plan.frame.title, "frame")
        for lane in plan.lanes:
            _add(lane.id, "lane", lane.semantic_id, "lane_container")
        for node in plan.nodes:
            _add(node.id, "node", node.semantic_id, "node_shape")
        for sl in plan.system_labels:
            _add(sl.id, "system_endpoint", sl.system_id, "system_label")
        for ep in plan.endpoints:
            _add(ep.id, "endpoint", ep.semantic_id, "endpoint_shape")
        for conn in plan.connectors:
            _add(conn.id, "connector", conn.id, "edge_connector")

    # ------------------------------------------------------------------
    # Stage 4: upsert shapes
    # ------------------------------------------------------------------

    def _upsert_shapes(
        self,
        *,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        actions: list[ReconcileAction],
        result: ExecutionResult,
        id_map: dict[str, str],
        skipped_plan_ids: set[str] | None = None,
    ) -> bool:
        """lane / node / system_label / endpoint の update / create / skip を処理。

        Args:
            skipped_plan_ids: skip 扱いとなった shape の plan_id を追記する set。
                connector 段階で「接続先が skip された」ことを判定するために使う。

        Returns:
            True の場合、action='stop' による停止が発生した。
        """
        # plan_id -> plan 要素の lookup を構築
        lane_map: dict[str, LanePlan] = {lp.id: lp for lp in plan.lanes}
        node_map: dict[str, NodePlan] = {np_.id: np_ for np_ in plan.nodes}
        sl_map: dict[str, SystemLabelPlan] = {sl.id: sl for sl in plan.system_labels}
        ep_map: dict[str, EndpointPlan] = {ep.id: ep for ep in plan.endpoints}

        for action in actions:
            plan_id = action.plan_id

            # shape 系ではない plan_id はここではスキップ
            # （connector / frame は別処理）
            if action.render_role == "edge_connector":
                continue

            if action.action == ItemAction.STOP:
                reason = action.reason or f"reconcile が停止: plan_id={plan_id}"
                if reason not in result.stop_reasons:
                    result.stop_reasons.append(reason)
                # ItemResult: stop は failed に記録する（再実行時は reconcile からやり直し）
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=metadata_map.get(plan_id, {}).get("semantic_type", ""),
                    semantic_id=metadata_map.get(plan_id, {}).get("semantic_id", ""),
                    render_role=action.render_role,
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                # rerun_eligible は reconciler 判定ベース
                result.rerun_eligible = False
                return True

            if action.action == ItemAction.SKIP:
                # P1-C: skip 理由の粒度を拡張し、ReconcileAction の update_mode / reason
                # から適切な ItemResultStatus に分類する。
                ir_result = _classify_skip_status(action)
                reason = action.reason or "reconciler により skip 判定"
                meta = metadata_map.get(plan_id, {})
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", ""),
                    semantic_id=meta.get("semantic_id", ""),
                    render_role=action.render_role,
                    action=ItemAction.UPDATE,
                    result=ir_result,
                    reason=reason,
                    miro_item_id=action.miro_item_id,
                ))
                result.skipped_count += 1

                # 保護系 skip（manual_detached / unmanaged）と
                # 隔離系 skip（frame_outside / flow_group_mismatch 等）で
                # connector 段への伝播を分岐する。
                #
                # - 保護系（manual_detached / unmanaged）:
                #     仕様 Q1: 既存 shape はそのまま保護するが、接続 connector は
                #     更新を許可する。そのため miro_item_id を id_map に登録し、
                #     かつ skipped_plan_ids には入れない。こうすることで
                #     _upsert_connectors は「接続先が id_map にあり、skip 依存でも
                #     ない」と判断し、通常の update / create 経路に進む。
                # - 隔離系（frame_outside / flow_group_mismatch / その他）:
                #     接続先として使うと frame 外 item や別 flow の item を
                #     connector 経由で復活させてしまうため、id_map には
                #     登録せず skipped_plan_ids に追加する。これにより
                #     _upsert_connectors は skipped_connector_dependency として
                #     skip する。
                protective_statuses = (
                    ItemResultStatus.SKIPPED_MANUAL_DETACHED,
                    ItemResultStatus.SKIPPED_UNMANAGED,
                )
                if ir_result in protective_statuses:
                    if action.miro_item_id:
                        id_map[plan_id] = action.miro_item_id
                    # 保護系は connector 更新を許可するため skipped_plan_ids には
                    # 追加しない（Q1: connector 側は通常通り update / create する）
                else:
                    # 隔離系 skip: connector の接続先として使わせない
                    if skipped_plan_ids is not None:
                        skipped_plan_ids.add(plan_id)
                continue

            # frame は update 対象外（frame の更新は P0004 で未定義）
            if action.render_role == "frame":
                if action.miro_item_id:
                    id_map["frame"] = action.miro_item_id
                continue

            # action == "update" or "create"
            if plan_id in lane_map:
                self._upsert_lane(
                    board_id=board_id,
                    frame_id=frame_id,
                    frame_plan=plan.frame,
                    lane=lane_map[plan_id],
                    action=action,
                    metadata_map=metadata_map,
                    result=result,
                    id_map=id_map,
                )
            elif plan_id in node_map:
                self._upsert_node(
                    board_id=board_id,
                    frame_id=frame_id,
                    frame_plan=plan.frame,
                    node=node_map[plan_id],
                    action=action,
                    metadata_map=metadata_map,
                    result=result,
                    id_map=id_map,
                )
            elif plan_id in sl_map:
                self._upsert_system_label(
                    board_id=board_id,
                    frame_id=frame_id,
                    frame_plan=plan.frame,
                    sl=sl_map[plan_id],
                    action=action,
                    metadata_map=metadata_map,
                    result=result,
                    id_map=id_map,
                )
            elif plan_id in ep_map:
                self._upsert_endpoint(
                    board_id=board_id,
                    frame_id=frame_id,
                    frame_plan=plan.frame,
                    ep=ep_map[plan_id],
                    action=action,
                    metadata_map=metadata_map,
                    result=result,
                    id_map=id_map,
                )
            # それ以外（未知）は無視

        return False

    # ------------------------------------------------------------------
    # Upsert helpers: lane / node / system_label / endpoint
    # ------------------------------------------------------------------

    def _upsert_lane(
        self,
        *,
        board_id: str,
        frame_id: str,
        frame_plan: FramePlan,
        lane: LanePlan,
        action: ReconcileAction,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
        id_map: dict[str, str],
    ) -> None:
        meta = metadata_map.get(lane.id, {})
        cx, cy = to_frame_local_center(
            frame_plan, lane.x, lane.y, lane.width, lane.height
        )
        style = ACTOR_LANE_STYLE if lane.type == "actor_lane" else SYSTEM_LANE_STYLE
        content = f"<b>{lane.label}</b>" if LANE_BOLD_WRAP else lane.label

        self._run_shape_upsert(
            board_id=board_id,
            frame_id=frame_id,
            action=action,
            plan_id=lane.id,
            shape="rectangle",
            content=content,
            cx=cx,
            cy=cy,
            width=lane.width,
            height=lane.height,
            style=style,
            meta=meta,
            render_role_default="lane_container",
            semantic_type_default=lane.type,
            semantic_id_default=lane.semantic_id,
            result=result,
            id_map=id_map,
        )

    def _upsert_node(
        self,
        *,
        board_id: str,
        frame_id: str,
        frame_plan: FramePlan,
        node: NodePlan,
        action: ReconcileAction,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
        id_map: dict[str, str],
    ) -> None:
        meta = metadata_map.get(node.id, {})
        cx, cy = to_frame_local_center(
            frame_plan, node.x, node.y, node.width, node.height
        )
        shape = node_shape(node.type)
        style = NODE_STYLES.get(node.type, NODE_STYLE_BASE)

        self._run_shape_upsert(
            board_id=board_id,
            frame_id=frame_id,
            action=action,
            plan_id=node.id,
            shape=shape,
            content=node.label,
            cx=cx,
            cy=cy,
            width=node.width,
            height=node.height,
            style=style,
            meta=meta,
            render_role_default="node_shape",
            semantic_type_default="node",
            semantic_id_default=node.semantic_id,
            result=result,
            id_map=id_map,
        )

    def _upsert_system_label(
        self,
        *,
        board_id: str,
        frame_id: str,
        frame_plan: FramePlan,
        sl: SystemLabelPlan,
        action: ReconcileAction,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
        id_map: dict[str, str],
    ) -> None:
        meta = metadata_map.get(sl.id, {})
        cx, cy = to_frame_local_center(
            frame_plan, sl.x, sl.y, sl.width, sl.height
        )
        self._run_shape_upsert(
            board_id=board_id,
            frame_id=frame_id,
            action=action,
            plan_id=sl.id,
            shape="round_rectangle",
            content=sl.label,
            cx=cx,
            cy=cy,
            width=sl.width,
            height=sl.height,
            style=SYSTEM_LABEL_STYLE,
            meta=meta,
            render_role_default="system_label",
            semantic_type_default="system_endpoint",
            semantic_id_default=sl.id,
            result=result,
            id_map=id_map,
        )

    def _upsert_endpoint(
        self,
        *,
        board_id: str,
        frame_id: str,
        frame_plan: FramePlan,
        ep: EndpointPlan,
        action: ReconcileAction,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
        id_map: dict[str, str],
    ) -> None:
        meta = metadata_map.get(ep.id, {})
        cx, cy = to_frame_local_center(
            frame_plan, ep.x, ep.y, ep.width, ep.height
        )
        self._run_shape_upsert(
            board_id=board_id,
            frame_id=frame_id,
            action=action,
            plan_id=ep.id,
            shape="rectangle",
            content=ep.label,
            cx=cx,
            cy=cy,
            width=ep.width,
            height=ep.height,
            style=ENDPOINT_STYLE,
            meta=meta,
            render_role_default="endpoint_shape",
            semantic_type_default="system_endpoint",
            semantic_id_default=ep.semantic_id,
            result=result,
            id_map=id_map,
        )

    def _run_shape_upsert(
        self,
        *,
        board_id: str,
        frame_id: str,
        action: ReconcileAction,
        plan_id: str,
        shape: str,
        content: str,
        cx: float,
        cy: float,
        width: float,
        height: float,
        style: dict[str, Any],
        meta: dict[str, str],
        render_role_default: str,
        semantic_type_default: str,
        semantic_id_default: str,
        result: ExecutionResult,
        id_map: dict[str, str],
    ) -> None:
        """shape の update / create を実行し、ItemResult を記録する。"""
        stable_id = action.stable_item_id
        semantic_type = meta.get("semantic_type", semantic_type_default)
        semantic_id = meta.get("semantic_id", semantic_id_default)
        render_role = meta.get("render_role", render_role_default)

        if action.action == ItemAction.UPDATE:
            miro_id = action.miro_item_id
            if not miro_id:
                reason = (
                    f"update action だが miro_item_id が無い: plan_id={plan_id}"
                )
                result.item_results.append(ItemResult(
                    stable_item_id=stable_id,
                    semantic_type=semantic_type,
                    semantic_id=semantic_id,
                    render_role=render_role,
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                return
            try:
                self._client.update_shape(
                    board_id,
                    miro_id,
                    data={"shape": shape, "content": content},
                    position={"x": cx, "y": cy},
                    geometry={"width": width, "height": height},
                    style=style,
                )
            except ExecutionError as exc:
                reason = f"{render_role_default} {plan_id} 更新失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=stable_id,
                    semantic_type=semantic_type,
                    semantic_id=semantic_id,
                    render_role=render_role,
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                    miro_item_id=miro_id,
                ))
                result.failed_count += 1
                logger.warning(reason)
                return

            id_map[plan_id] = miro_id
            result.item_results.append(ItemResult(
                stable_item_id=stable_id,
                semantic_type=semantic_type,
                semantic_id=semantic_id,
                render_role=render_role,
                action=ItemAction.UPDATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=miro_id,
            ))
            result.updated_count += 1
            logger.info("%s 更新完了: %s -> %s", render_role_default, plan_id, miro_id)
            return

        # action == "create"
        try:
            resp = self._client.create_shape(
                board_id=board_id,
                shape=shape,
                content=content,
                x=cx,
                y=cy,
                width=width,
                height=height,
                style=style,
                parent_id=frame_id,
            )
        except ExecutionError as exc:
            reason = f"{render_role_default} {plan_id} 作成失敗: {exc}"
            result.item_results.append(ItemResult(
                stable_item_id=stable_id,
                semantic_type=semantic_type,
                semantic_id=semantic_id,
                render_role=render_role,
                action=ItemAction.CREATE,
                result=ItemResultStatus.FAILED,
                reason=reason,
            ))
            result.failed_count += 1
            logger.warning(reason)
            return

        miro_id = resp.get("id") if isinstance(resp, dict) else None
        if not miro_id or not isinstance(miro_id, str):
            reason = (
                f"{render_role_default} {plan_id} 作成レスポンスに id が含まれていない"
            )
            result.item_results.append(ItemResult(
                stable_item_id=stable_id,
                semantic_type=semantic_type,
                semantic_id=semantic_id,
                render_role=render_role,
                action=ItemAction.CREATE,
                result=ItemResultStatus.FAILED,
                reason=reason,
            ))
            result.failed_count += 1
            logger.warning(reason)
            return

        id_map[plan_id] = miro_id
        result.item_results.append(ItemResult(
            stable_item_id=stable_id,
            semantic_type=semantic_type,
            semantic_id=semantic_id,
            render_role=render_role,
            action=ItemAction.CREATE,
            result=ItemResultStatus.SUCCESS,
            miro_item_id=miro_id,
        ))
        result.created_count += 1
        logger.info("%s 作成完了: %s -> %s", render_role_default, plan_id, miro_id)

    # ------------------------------------------------------------------
    # Stage 5: upsert connectors
    # ------------------------------------------------------------------

    def _upsert_connectors(
        self,
        *,
        board_id: str,
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        actions: list[ReconcileAction],
        result: ExecutionResult,
        id_map: dict[str, str],
        skipped_plan_ids: set[str] | None = None,
    ) -> bool:
        """connector の update / create を実行する。

        Args:
            skipped_plan_ids: shape 段階で skip された plan_id の集合。
                connector の from/to がこの集合に含まれる場合、connector も
                skip し（P0-C）、``skipped_connector_dependency`` として記録する。

        Returns:
            True の場合、接続先未解決で停止した（= stop）。
        """
        if skipped_plan_ids is None:
            skipped_plan_ids = set()
        action_by_plan_id: dict[str, ReconcileAction] = {
            a.plan_id: a for a in actions if a.render_role == "edge_connector"
        }

        for conn in plan.connectors:
            meta = metadata_map.get(conn.id, {})

            # system_access は create 時と同様に ItemResult を skipped で残す
            if conn.type == "system_access":
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.SKIPPED,
                    reason="system_access connector は SystemLabel で代替",
                ))
                result.skipped_count += 1
                continue

            action = action_by_plan_id.get(conn.id)
            if action is None:
                # reconciler 結果に含まれない場合は create 相当として扱う
                action = ReconcileAction(
                    stable_item_id=meta.get("stable_item_id", ""),
                    plan_id=conn.id,
                    render_role="edge_connector",
                    action=ItemAction.CREATE,
                    miro_item_id=None,
                    reason="reconcile 対象外 → 新規作成",
                    update_mode=UpdateMode.MANAGED,
                )

            # skip の場合は skipped として記録して次へ
            if action.action == ItemAction.SKIP:
                ir_result = _classify_skip_status(action)
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=ItemAction.UPDATE,
                    result=ir_result,
                    reason=action.reason,
                    miro_item_id=action.miro_item_id,
                ))
                result.skipped_count += 1
                continue

            # P0-C: 接続先 shape が skip 扱いなら connector も skip する。
            # 接続先が create 失敗 / 単純未解決の場合は従来通り stop する。
            dep_skipped_parts: list[str] = []
            if conn.from_plan_id in skipped_plan_ids:
                dep_skipped_parts.append(f"from={conn.from_plan_id}")
            if conn.to_plan_id in skipped_plan_ids:
                dep_skipped_parts.append(f"to={conn.to_plan_id}")

            if dep_skipped_parts:
                reason = (
                    f"connector {conn.id} 接続先 shape が skip 扱いのためスキップ: "
                    f"{', '.join(dep_skipped_parts)}"
                )
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.SKIPPED_CONNECTOR_DEPENDENCY,
                    reason=reason,
                    miro_item_id=action.miro_item_id,
                ))
                result.skipped_count += 1
                logger.warning(reason)
                continue

            # 接続先を id_map から解決
            from_miro_id = id_map.get(conn.from_plan_id)
            to_miro_id = id_map.get(conn.to_plan_id)

            if from_miro_id is None or to_miro_id is None:
                missing_parts: list[str] = []
                if from_miro_id is None:
                    missing_parts.append(f"from={conn.from_plan_id}")
                if to_miro_id is None:
                    missing_parts.append(f"to={conn.to_plan_id}")
                reason = (
                    f"connector {conn.id} 接続先未解決: "
                    f"{', '.join(missing_parts)}"
                )
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=action.action,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                result.stop_reasons.append(reason)
                logger.error(reason)
                return True

            captions = [{"content": conn.label}] if conn.label else None

            if conn.is_back_edge:
                start_item = {"id": from_miro_id, "position": {"x": "50%", "y": "0%"}}
                end_item = {"id": to_miro_id, "position": {"x": "50%", "y": "0%"}}
                style = BACK_EDGE_CONNECTOR_STYLE
            else:
                start_item = {"id": from_miro_id, "position": {"x": "100%", "y": "50%"}}
                end_item = {"id": to_miro_id, "position": {"x": "0%", "y": "50%"}}
                style = CONNECTOR_STYLE

            if action.action == ItemAction.UPDATE:
                miro_id = action.miro_item_id
                if not miro_id:
                    reason = (
                        f"connector {conn.id} update action だが miro_item_id が無い"
                    )
                    result.item_results.append(ItemResult(
                        stable_item_id=action.stable_item_id,
                        semantic_type=meta.get("semantic_type", conn.type),
                        semantic_id=meta.get("semantic_id", conn.id),
                        render_role="edge_connector",
                        action=ItemAction.UPDATE,
                        result=ItemResultStatus.FAILED,
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                try:
                    self._client.update_connector(
                        board_id,
                        miro_id,
                        start_item=start_item,
                        end_item=end_item,
                        style=style,
                        captions=captions,
                        shape="elbowed",
                    )
                except ExecutionError as exc:
                    reason = f"connector {conn.id} 更新失敗: {exc}"
                    result.item_results.append(ItemResult(
                        stable_item_id=action.stable_item_id,
                        semantic_type=meta.get("semantic_type", conn.type),
                        semantic_id=meta.get("semantic_id", conn.id),
                        render_role="edge_connector",
                        action=ItemAction.UPDATE,
                        result=ItemResultStatus.FAILED,
                        reason=reason,
                        miro_item_id=miro_id,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue

                id_map[conn.id] = miro_id
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=ItemAction.UPDATE,
                    result=ItemResultStatus.SUCCESS,
                    miro_item_id=miro_id,
                ))
                result.updated_count += 1
                logger.info("connector 更新完了: %s -> %s", conn.id, miro_id)
                continue

            # action == "create"
            try:
                resp = self._client.create_connector(
                    board_id=board_id,
                    start_item=start_item,
                    end_item=end_item,
                    shape="elbowed",
                    style=style,
                    captions=captions,
                )
            except ExecutionError as exc:
                reason = f"connector {conn.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            conn_miro_id = resp.get("id") if isinstance(resp, dict) else None
            if not conn_miro_id or not isinstance(conn_miro_id, str):
                reason = f"connector {conn.id} 作成レスポンスに id が含まれていない"
                result.item_results.append(ItemResult(
                    stable_item_id=action.stable_item_id,
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role="edge_connector",
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[conn.id] = conn_miro_id
            result.item_results.append(ItemResult(
                stable_item_id=action.stable_item_id,
                semantic_type=meta.get("semantic_type", conn.type),
                semantic_id=meta.get("semantic_id", conn.id),
                render_role="edge_connector",
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=conn_miro_id,
            ))
            result.created_count += 1
            logger.info("connector 作成完了: %s -> %s", conn.id, conn_miro_id)

        return False

    # ------------------------------------------------------------------
    # Orphaned 記録
    # ------------------------------------------------------------------

    @staticmethod
    def _record_orphaned(
        reconcile_result: ReconcileResult,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
    ) -> None:
        """orphaned item を ItemResult として run log に残す。"""
        seen_stable_ids = {ir.stable_item_id for ir in result.item_results}
        for o in reconcile_result.orphaned_items:
            if o.stable_item_id in seen_stable_ids:
                continue
            result.item_results.append(ItemResult(
                stable_item_id=o.stable_item_id,
                semantic_type="",
                semantic_id="",
                render_role=o.render_role,
                action=ItemAction.ORPHANED,
                result=ItemResultStatus.SKIPPED_ORPHANED,
                reason=o.reason,
                miro_item_id=o.miro_item_id,
            ))
            result.skipped_count += 1


# ---------------------------------------------------------------------------
# skip 理由分類ヘルパー（P1-C）
# ---------------------------------------------------------------------------


def _classify_skip_status(action: ReconcileAction) -> str:
    """ReconcileAction (action='skip') を ItemResultStatus 値に分類する。

    P2 指摘（2 回目）への対応:
    - 旧実装は ``action.reason`` の部分文字列 (``frame_id=`` / ``flow_group_id``)
      を見て分類しており、reconciler 側のメッセージ文言が変わると silently
      誤分類する問題があった
    - 現在は reconciler が ``ReconcileAction.skip_reason`` に構造化ラベル
      （``SkipReason`` 値）を設定しているため、本関数ではそれを参照する
    - 既存 run log との後方互換のため、``skip_reason`` が欠落している
      （旧形式の） action に対しては ``update_mode`` からのフォールバック
      分類のみ行う

    判定順:
    1. ``action.skip_reason`` が設定されていれば対応する ItemResultStatus を返す
    2. 未設定の場合は ``update_mode`` を見て manual_detached / unmanaged を判定
    3. それ以外 → SKIPPED_MANUAL_DETACHED（保守的に保護扱い。既存動作との互換）
    """
    if action.skip_reason is not None:
        if action.skip_reason == SkipReason.MANUAL_DETACHED:
            return ItemResultStatus.SKIPPED_MANUAL_DETACHED
        if action.skip_reason == SkipReason.UNMANAGED:
            return ItemResultStatus.SKIPPED_UNMANAGED
        if action.skip_reason == SkipReason.FRAME_OUTSIDE:
            return ItemResultStatus.SKIPPED_FRAME_OUTSIDE
        if action.skip_reason == SkipReason.FLOW_GROUP_MISMATCH:
            return ItemResultStatus.SKIPPED_FLOW_GROUP_MISMATCH
        if action.skip_reason == SkipReason.ORPHANED:
            return ItemResultStatus.SKIPPED_ORPHANED
        # 未知の skip_reason 値 → 保護扱い
        return ItemResultStatus.SKIPPED_MANUAL_DETACHED

    # skip_reason が未設定 → update_mode から推定（旧 run log 互換）
    if action.update_mode == UpdateMode.MANUAL_DETACHED:
        return ItemResultStatus.SKIPPED_MANUAL_DETACHED
    if action.update_mode == UpdateMode.UNMANAGED:
        return ItemResultStatus.SKIPPED_UNMANAGED

    # 未分類 → 保護扱い（既存動作との互換性維持）
    return ItemResultStatus.SKIPPED_MANUAL_DETACHED


# ---------------------------------------------------------------------------
# backfill 必要判定 + 実施
# ---------------------------------------------------------------------------


def _backfill_run_log_if_needed(
    run_log: RunLog,
    board_items: list[dict[str, Any]],
    board_connectors: list[dict[str, Any]],
    drawing_plan: DrawingPlan,
) -> RunLog:
    """SG2 形式（miro_item_id 欠落）の run log を board 情報で補完する。

    shape（lane / node / system_label）と connector の両方を補完する（P0-B）。
    補完内容を反映した新しい RunLog を返す。元の run_log は変更しない。
    補完不要な場合は同じ RunLog を返す。
    """
    missing = any(
        isinstance(item, dict)
        and isinstance(item.get("stable_item_id"), str)
        and item["stable_item_id"]
        and not item.get("miro_item_id")
        for item in run_log.item_results
    )
    if not missing:
        return run_log

    mapping = backfill_miro_item_ids(
        run_log, board_items, board_connectors, drawing_plan
    )
    if not mapping:
        return run_log

    new_items: list[dict[str, object]] = []
    for item in run_log.item_results:
        if not isinstance(item, dict):
            new_items.append(item)
            continue
        stable_id = item.get("stable_item_id")
        miro_id = item.get("miro_item_id")
        if (
            isinstance(stable_id, str)
            and stable_id
            and (not miro_id)
            and stable_id in mapping
        ):
            new_item = dict(item)
            new_item["miro_item_id"] = mapping[stable_id]
            new_items.append(new_item)
        else:
            new_items.append(item)

    return replace(run_log, item_results=new_items)
