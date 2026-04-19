"""create モード用ハンドラー。

ConfirmedInput から DrawingPlan を生成し、Miro API 経由で
board / frame / shape / connector を新規作成する。
"""

from __future__ import annotations

import logging
import sys
import time
import uuid

from miro_flow_maker._render_helpers import (
    ACTOR_LANE_STYLE as _ACTOR_LANE_STYLE,
    BACK_EDGE_CONNECTOR_STYLE as _BACK_EDGE_CONNECTOR_STYLE,
    CONNECTOR_STYLE as _CONNECTOR_STYLE,
    ENDPOINT_STYLE as _ENDPOINT_STYLE,
    LANE_BOLD_WRAP as _LANE_BOLD_WRAP,
    NODE_SHAPE_MAP as _NODE_SHAPE_MAP,
    NODE_STYLE_BASE as _NODE_STYLE_BASE,
    NODE_STYLES as _NODE_STYLES,
    SYSTEM_LABEL_STYLE as _SYSTEM_LABEL_STYLE,
    SYSTEM_LANE_STYLE as _SYSTEM_LANE_STYLE,
    node_shape as _node_shape,
    to_center as _to_center,
    to_frame_local_center as _to_frame_local_center,
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
from miro_flow_maker.run_log import build_run_log, write_run_log

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 座標変換ヘルパー・スタイル定数
# ---------------------------------------------------------------------------
# create_handler.py / update_handler.py の共通定義は _render_helpers.py に集約。
# 既存の公開シグネチャ維持のため、ここではモジュール内の private 別名として
# 再エクスポートするだけにしている。

__all__ = ["CreateHandler"]


# ---------------------------------------------------------------------------
# CreateHandler
# ---------------------------------------------------------------------------


class CreateHandler:
    """create モードの ModeHandler 実装。

    ModeHandler Protocol に準拠する。
    全 item を新規作成する（既存 item の再利用はしない）。
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
        """create モードの実行。

        処理順 (P0004 create 契約に準拠):
        1. build_drawing_plan
        2. build_plan_metadata_map
        3. dry-run チェック (拡充: plan 表示 + item_results 生成)
        4. ensure_board
        5. ensure_flow_frame
        6. create_lane_items
        7. create_node_items
        8. create_system_label_items
        9. create_endpoint_items
        10. create_connector_items
        11. run log 書き出し
        12. ExecutionResult を返す
        """
        start_ms = time.monotonic_ns() // 1_000_000
        run_id = str(uuid.uuid4())
        board_name = context.board_name or confirmed_input.flow_group_id

        # 1. 描画計画を生成
        plan = build_drawing_plan(confirmed_input, board_name)

        # 2. metadata マップを事前生成（run log 用）
        metadata_map = build_plan_metadata_map(confirmed_input, plan)

        # 結果コンテナを初期化
        result = ExecutionResult(
            run_id=run_id,
            mode="create",
            success=False,
            board_id=None,
            frame_id=None,
            flow_group_id=confirmed_input.flow_group_id,
            dry_run=context.dry_run,
        )

        # 3. dry-run チェック
        if context.dry_run:
            self._dry_run_output(plan, metadata_map)
            self._dry_run_generate_item_results(plan, metadata_map, result)
            result.success = True
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        # plan_id -> miro_item_id マッピング
        id_map: dict[str, str] = {}

        # 4. ensure_board
        board_id = self._ensure_board(plan.board_name, result)
        if board_id is None:
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        result.board_id = board_id

        # 5. ensure_flow_frame
        frame_id = self._ensure_frame(board_id, plan, result, metadata_map)
        if frame_id is None:
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        result.frame_id = frame_id

        # 6. create_lane_items
        self._create_lane_items(board_id, frame_id, plan, result, metadata_map, id_map)

        # 7. create_node_items
        self._create_node_items(board_id, frame_id, plan, result, metadata_map, id_map)

        # 8. create_system_label_items
        self._create_system_label_items(board_id, frame_id, plan, result, metadata_map, id_map)

        # 9. create_endpoint_items
        self._create_endpoint_items(board_id, frame_id, plan, result, metadata_map, id_map)

        # 10. create_connector_items
        stopped = self._create_connector_items(
            board_id, plan, result, metadata_map, id_map
        )
        if stopped:
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        # 11. 成功
        result.success = result.failed_count == 0 and len(result.stop_reasons) == 0

        # 12. run log 書き出し
        self._write_run_log(result, metadata_map, start_ms, config)
        return result

    # ------------------------------------------------------------------
    # dry-run helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dry_run_output(
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
    ) -> None:
        """DrawingPlan の内容を stderr に人間が読める形式で出力する。"""
        w = sys.stderr.write

        w("=" * 60 + "\n")
        w("[DRY-RUN] create mode — Drawing Plan Summary\n")
        w("=" * 60 + "\n")

        # board
        w(f"\nBoard: {plan.board_name}\n")

        # frame
        f = plan.frame
        w(f"Frame: {f.title} (x={f.x}, y={f.y}, w={f.width}, h={f.height})\n")

        # lanes
        w(f"\nLanes ({len(plan.lanes)}):\n")
        for lane in plan.lanes:
            w(f"  - {lane.id} [{lane.type}] \"{lane.label}\" "
              f"(x={lane.x}, y={lane.y}, w={lane.width}, h={lane.height})\n")

        # nodes
        w(f"\nNodes ({len(plan.nodes)}):\n")
        for node in plan.nodes:
            w(f"  - {node.id} [{node.type}] \"{node.label}\" "
              f"lane={node.lane_id} (x={node.x}, y={node.y})\n")

        # system_labels
        w(f"\nSystemLabels ({len(plan.system_labels)}):\n")
        for sl in plan.system_labels:
            w(f"  - {sl.id} \"{sl.label}\" node={sl.node_id} system={sl.system_id} "
              f"(x={sl.x}, y={sl.y})\n")

        # endpoints
        w(f"\nEndpoints ({len(plan.endpoints)}):\n")
        for ep in plan.endpoints:
            w(f"  - {ep.id} \"{ep.label}\" system={ep.system_id} "
              f"(x={ep.x}, y={ep.y})\n")

        # connectors
        w(f"\nConnectors ({len(plan.connectors)}):\n")
        for conn in plan.connectors:
            label_str = f" \"{conn.label}\"" if conn.label else ""
            back_str = " (back_edge)" if conn.is_back_edge else ""
            w(f"  - {conn.id}: {conn.from_plan_id} -> {conn.to_plan_id} "
              f"[{conn.type}]{label_str}{back_str}\n")

        # item totals
        total = (
            1  # frame
            + len(plan.lanes)
            + len(plan.nodes)
            + len(plan.system_labels)
            + len(plan.endpoints)
            + len(plan.connectors)
        )
        w(f"\nTotal items: {total}\n")

        # metadata sample
        if metadata_map:
            first_key = next(iter(metadata_map))
            first_meta = metadata_map[first_key]
            w(f"\nMetadata sample (plan_id={first_key}):\n")
            for k, v in first_meta.items():
                w(f"  {k}: {v}\n")

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
                action="create",
                result="dry_run_skipped",
            ))
            result.skipped_count += 1

        # frame
        _add("frame", "flow_group", plan.frame.title, "frame")

        # lanes
        for lane in plan.lanes:
            _add(lane.id, "lane", lane.semantic_id, "lane_shape")

        # nodes
        for node in plan.nodes:
            _add(node.id, "node", node.semantic_id, "shape")

        # system_labels
        for sl in plan.system_labels:
            _add(sl.id, "system_endpoint", sl.system_id, "system_label")

        # endpoints
        for ep in plan.endpoints:
            _add(ep.id, "endpoint", ep.semantic_id, "endpoint_shape")

        # connectors
        for conn in plan.connectors:
            _add(conn.id, "connector", conn.id, "connector_line")

    # ------------------------------------------------------------------
    # run log helper
    # ------------------------------------------------------------------

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
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_board(
        self,
        board_name: str,
        result: ExecutionResult,
    ) -> str | None:
        """board を作成し、board_id を返す。失敗時は None。"""
        try:
            resp = self._client.create_board(board_name)
        except ExecutionError as exc:
            reason = f"board 作成失敗: {exc}"
            result.stop_reasons.append(reason)
            logger.error(reason)
            return None
        board_id = resp.get("id")
        if not board_id:
            reason = "board 作成レスポンスに id が含まれていない"
            result.stop_reasons.append(reason)
            logger.error(reason)
            return None
        logger.info("board 作成完了: %s", board_id)
        return str(board_id)

    def _ensure_frame(
        self,
        board_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
    ) -> str | None:
        """frame を作成し、frame_id を返す。失敗時は None。"""
        frame = plan.frame
        frame_cx, frame_cy = _to_center(frame.x, frame.y, frame.width, frame.height)
        try:
            resp = self._client.create_frame(
                board_id=board_id,
                title=frame.title,
                x=frame_cx,
                y=frame_cy,
                width=frame.width,
                height=frame.height,
            )
        except ExecutionError as exc:
            reason = f"frame 作成失敗: {exc}"
            result.stop_reasons.append(reason)
            logger.error(reason)
            return None
        frame_id = resp.get("id")
        if not frame_id:
            reason = "frame 作成レスポンスに id が含まれていない"
            result.stop_reasons.append(reason)
            logger.error(reason)
            return None

        frame_id = str(frame_id)

        # frame の ItemResult を記録
        meta = metadata_map.get("frame", {})
        result.item_results.append(ItemResult(
            stable_item_id=meta.get("stable_item_id", ""),
            semantic_type=meta.get("semantic_type", "flow_group"),
            semantic_id=meta.get("semantic_id", ""),
            render_role=meta.get("render_role", "frame"),
            action="create",
            result="success",
            miro_item_id=frame_id,
        ))
        result.created_count += 1
        logger.info("frame 作成完了: %s", frame_id)
        return frame_id

    def _create_lane_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """lane shape を作成する。"""
        for lane in plan.lanes:
            meta = metadata_map.get(lane.id, {})
            lx, ly = _to_frame_local_center(plan.frame, lane.x, lane.y, lane.width, lane.height)
            style = _ACTOR_LANE_STYLE if lane.type == "actor_lane" else _SYSTEM_LANE_STYLE
            lane_content = f"<b>{lane.label}</b>" if _LANE_BOLD_WRAP else lane.label
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape="rectangle",
                    content=lane_content,
                    x=lx,
                    y=ly,
                    width=lane.width,
                    height=lane.height,
                    style=style,
                    parent_id=frame_id,
                )
                miro_id = resp.get("id")
                if not miro_id:
                    reason = f"lane {lane.id} 作成レスポンスに id が含まれていない"
                    result.item_results.append(ItemResult(
                        stable_item_id=meta.get("stable_item_id", ""),
                        semantic_type=meta.get("semantic_type", lane.type),
                        semantic_id=meta.get("semantic_id", lane.semantic_id),
                        render_role=meta.get("render_role", "lane_container"),
                        action="create",
                        result="failed",
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                miro_id = str(miro_id)
                id_map[lane.id] = miro_id
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", lane.type),
                    semantic_id=meta.get("semantic_id", lane.semantic_id),
                    render_role=meta.get("render_role", "lane_container"),
                    action="create",
                    result="success",
                    miro_item_id=miro_id,
                ))
                result.created_count += 1
                logger.info("lane 作成完了: %s -> %s", lane.id, miro_id)
            except ExecutionError as exc:
                reason = f"lane {lane.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", lane.type),
                    semantic_id=meta.get("semantic_id", lane.semantic_id),
                    render_role=meta.get("render_role", "lane_container"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)

    def _create_node_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """node shape を作成する。"""
        for node in plan.nodes:
            meta = metadata_map.get(node.id, {})
            shape = _node_shape(node.type)
            node_style = _NODE_STYLES.get(node.type, _NODE_STYLE_BASE)
            lx, ly = _to_frame_local_center(plan.frame, node.x, node.y, node.width, node.height)
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape=shape,
                    content=node.label,
                    x=lx,
                    y=ly,
                    width=node.width,
                    height=node.height,
                    style=node_style,
                    parent_id=frame_id,
                )
                miro_id = resp.get("id")
                if not miro_id:
                    reason = f"node {node.id} 作成レスポンスに id が含まれていない"
                    result.item_results.append(ItemResult(
                        stable_item_id=meta.get("stable_item_id", ""),
                        semantic_type=meta.get("semantic_type", "node"),
                        semantic_id=meta.get("semantic_id", node.semantic_id),
                        render_role=meta.get("render_role", "node_shape"),
                        action="create",
                        result="failed",
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                miro_id = str(miro_id)
                id_map[node.id] = miro_id
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "node"),
                    semantic_id=meta.get("semantic_id", node.semantic_id),
                    render_role=meta.get("render_role", "node_shape"),
                    action="create",
                    result="success",
                    miro_item_id=miro_id,
                ))
                result.created_count += 1
                logger.info("node 作成完了: %s -> %s", node.id, miro_id)
            except ExecutionError as exc:
                reason = f"node {node.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "node"),
                    semantic_id=meta.get("semantic_id", node.semantic_id),
                    render_role=meta.get("render_role", "node_shape"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)

    def _create_system_label_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """system_label shape を作成する。"""
        for sl_plan in plan.system_labels:
            meta = metadata_map.get(sl_plan.id, {})
            lx, ly = _to_frame_local_center(
                plan.frame, sl_plan.x, sl_plan.y, sl_plan.width, sl_plan.height,
            )
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape="round_rectangle",
                    content=sl_plan.label,
                    x=lx,
                    y=ly,
                    width=sl_plan.width,
                    height=sl_plan.height,
                    style=_SYSTEM_LABEL_STYLE,
                    parent_id=frame_id,
                )
                miro_id = resp.get("id")
                if not miro_id:
                    reason = f"system_label {sl_plan.id} 作成レスポンスに id が含まれていない"
                    result.item_results.append(ItemResult(
                        stable_item_id=meta.get("stable_item_id", ""),
                        semantic_type=meta.get("semantic_type", "system_endpoint"),
                        semantic_id=meta.get("semantic_id", sl_plan.system_id),
                        render_role=meta.get("render_role", "system_label"),
                        action="create",
                        result="failed",
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                miro_id = str(miro_id)
                id_map[sl_plan.id] = miro_id
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", sl_plan.system_id),
                    render_role=meta.get("render_role", "system_label"),
                    action="create",
                    result="success",
                    miro_item_id=miro_id,
                ))
                result.created_count += 1
                logger.info("system_label 作成完了: %s -> %s", sl_plan.id, miro_id)
            except ExecutionError as exc:
                reason = f"system_label {sl_plan.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", sl_plan.system_id),
                    render_role=meta.get("render_role", "system_label"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)

    def _create_endpoint_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """endpoint shape を作成する。"""
        for ep in plan.endpoints:
            meta = metadata_map.get(ep.id, {})
            lx, ly = _to_frame_local_center(
                plan.frame, ep.x, ep.y, ep.width, ep.height,
            )
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape="rectangle",
                    content=ep.label,
                    x=lx,
                    y=ly,
                    width=ep.width,
                    height=ep.height,
                    style=_ENDPOINT_STYLE,
                    parent_id=frame_id,
                )
                miro_id = resp.get("id")
                if not miro_id:
                    reason = f"endpoint {ep.id} 作成レスポンスに id が含まれていない"
                    result.item_results.append(ItemResult(
                        stable_item_id=meta.get("stable_item_id", ""),
                        semantic_type=meta.get("semantic_type", "system_endpoint"),
                        semantic_id=meta.get("semantic_id", ep.semantic_id),
                        render_role=meta.get("render_role", "endpoint_shape"),
                        action="create",
                        result="failed",
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                miro_id = str(miro_id)
                id_map[ep.id] = miro_id
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", ep.semantic_id),
                    render_role=meta.get("render_role", "endpoint_shape"),
                    action="create",
                    result="success",
                    miro_item_id=miro_id,
                ))
                result.created_count += 1
                logger.info("endpoint 作成完了: %s -> %s", ep.id, miro_id)
            except ExecutionError as exc:
                reason = f"endpoint {ep.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", ep.semantic_id),
                    render_role=meta.get("render_role", "endpoint_shape"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)

    def _create_connector_items(
        self,
        board_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> bool:
        """connector を作成する。

        Returns:
            True の場合、接続先未解決による停止が発生した。
        """
        for conn in plan.connectors:
            # system_access connector はスキップ（SystemLabel に矢印は不要）
            if conn.type == "system_access":
                meta = metadata_map.get(conn.id, {})
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action="create",
                    result="skipped",
                    reason="system_access connector は SystemLabel で代替",
                ))
                result.skipped_count += 1
                continue

            meta = metadata_map.get(conn.id, {})

            # plan_id -> miro_item_id を解決
            from_miro_id = id_map.get(conn.from_plan_id)
            to_miro_id = id_map.get(conn.to_plan_id)

            if from_miro_id is None or to_miro_id is None:
                # P0004 停止条件: 接続先未解決 → 即停止
                missing_parts = []
                if from_miro_id is None:
                    missing_parts.append(f"from={conn.from_plan_id}")
                if to_miro_id is None:
                    missing_parts.append(f"to={conn.to_plan_id}")
                reason = (
                    f"connector {conn.id} 接続先未解決: "
                    f"{', '.join(missing_parts)}"
                )
                # P1-1: connector 未解決時に ItemResult を残す
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                result.stop_reasons.append(reason)
                logger.error(reason)
                return True

            captions = None
            if conn.label:
                captions = [{"content": conn.label}]

            if conn.is_back_edge:
                # 差戻し: 下から出て上に入る
                start_item = {"id": from_miro_id, "position": {"x": "50%", "y": "0%"}}
                end_item = {"id": to_miro_id, "position": {"x": "50%", "y": "0%"}}
                connector_style = _BACK_EDGE_CONNECTOR_STYLE
            else:
                # 通常: 右端→左端
                start_item = {"id": from_miro_id, "position": {"x": "100%", "y": "50%"}}
                end_item = {"id": to_miro_id, "position": {"x": "0%", "y": "50%"}}
                connector_style = _CONNECTOR_STYLE

            try:
                resp = self._client.create_connector(
                    board_id=board_id,
                    start_item=start_item,
                    end_item=end_item,
                    shape="elbowed",
                    style=connector_style,
                    captions=captions,
                )
                conn_miro_id = resp.get("id")
                if not conn_miro_id:
                    reason = f"connector {conn.id} 作成レスポンスに id が含まれていない"
                    result.item_results.append(ItemResult(
                        stable_item_id=meta.get("stable_item_id", ""),
                        semantic_type=meta.get("semantic_type", conn.type),
                        semantic_id=meta.get("semantic_id", conn.id),
                        render_role=meta.get("render_role", "edge_connector"),
                        action="create",
                        result="failed",
                        reason=reason,
                    ))
                    result.failed_count += 1
                    logger.warning(reason)
                    continue
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action="create",
                    result="success",
                    miro_item_id=str(conn_miro_id),
                ))
                result.created_count += 1
                logger.info("connector 作成完了: %s", conn.id)
            except ExecutionError as exc:
                reason = f"connector {conn.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action="create",
                    result="failed",
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)

        return False
