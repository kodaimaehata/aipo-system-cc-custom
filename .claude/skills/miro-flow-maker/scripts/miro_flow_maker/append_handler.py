"""append モード用ハンドラー。

既存 board / frame 上に新しい flow_group の item 群を追加する。
create に近いが以下の点が異なる:
- board / frame は既存を再利用する（新規作成しない）
- 既存 flow_group_id への append は stable_item_id 衝突防止のため停止する
- frame 内の既存占有領域を計算し、その下に新しい flow_group を配置する
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
    StoppedStage,
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
    APPEND_GAP,
    FRAME_PADDING,
    DrawingPlan,
    build_drawing_plan,
    compute_required_append_frame_size,
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
from miro_flow_maker.run_log import (
    RunLog,
    build_run_log,
    find_latest_run_log,
    write_run_log,
)

logger = logging.getLogger(__name__)

__all__ = ["AppendHandler"]

# ---------------------------------------------------------------------------
# append レイアウト定数
# ---------------------------------------------------------------------------
# APPEND_GAP は layout.py を単一の source of truth とする（compute_required_append_frame_size
# と整合させるため）。ここでは再 import するだけで定義しない。

# Stage 3 auto-frame 用定数。既存 frame との水平マージン（論理座標）。
FRAME_MARGIN: float = 200.0


# ---------------------------------------------------------------------------
# AppendHandler
# ---------------------------------------------------------------------------


class AppendHandler:
    """append モードの ModeHandler 実装。

    既存 board / frame に新しい flow_group の item 群を追加する。
    ModeHandler Protocol に準拠する。
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
        """append モードの実行。

        処理順序:
        1. build_drawing_plan / build_plan_metadata_map
        2. ExecutionResult 初期化（mode='append'）
        3. dry-run チェック
        4. Stage1 resolve_board
        5. Stage2 resolve_frame（frame_id 必須）+ 既存占有領域計算
        6. 同一 flow_group_id 衝突チェック（run log 照合）
        7. DrawingPlan に座標オフセットを適用
        8. Stage3 item 作成（lanes → nodes → system_labels → endpoints → connectors）
        9. 成功判定 + run log 書き出し
        """
        start_ms = time.monotonic_ns() // 1_000_000
        run_id = str(uuid.uuid4())

        # 1. 描画計画 / metadata マップ（append では board_name は未使用）
        plan = build_drawing_plan(confirmed_input, board_name="")
        metadata_map = build_plan_metadata_map(confirmed_input, plan)

        # 2. ExecutionResult 初期化
        result = ExecutionResult(
            run_id=run_id,
            mode="append",
            success=False,
            board_id=context.board_id,
            frame_id=None,  # Stage2 で確定する
            flow_group_id=confirmed_input.flow_group_id,
            dry_run=context.dry_run,
        )

        # 以降の本体は run log 観察性を守るため try/except で包む。既存の
        # early-return パス（collision / resolve_board / resolve_frame /
        # upsert_connectors 停止など）は既に自前で _write_run_log + return
        # しているため二重書き出しは発生しない。ここでは「想定外例外」が
        # 上位まで抜ける場合だけ best-effort で run log を書き、例外は
        # そのまま raise し直す（P2-4 の ExecutionError 以外伝播仕様と整合）。
        try:
            return self._execute_body(
                confirmed_input, context, config,
                plan=plan,
                metadata_map=metadata_map,
                result=result,
                start_ms=start_ms,
            )
        except Exception as exc:
            logger.exception("append execute で想定外例外: %s", exc)
            try:
                result.stop_reasons.append(
                    f"uncaught exception: {type(exc).__name__}: {exc}"
                )
                if result.stopped_stage is None:
                    result.stopped_stage = StoppedStage.UPSERT_SHAPES
                result.rerun_eligible = True
                self._write_run_log(result, metadata_map, start_ms, config)
            except Exception:
                logger.exception("run log 書き出し失敗（例外 finally block）")
            raise

    def _execute_body(
        self,
        confirmed_input: ConfirmedInput,
        context: RequestContext,
        config: AppConfig,
        *,
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
        start_ms: int,
    ) -> ExecutionResult:
        """execute() の本体。例外観察性のため分離している。"""

        # 3. dry-run: 実 API は呼ばない
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

        # 5. Stage 2: resolve_frame + 既存占有領域計算
        # P1-A: append でも frame_link から frame_id を抽出できるようにする。
        # 従来は frame_id のみ参照しており、CLI で受け付けた --frame-link が
        # 利用者には通るように見えて必ず resolve_frame で止まっていた。
        frame_id = context.frame_id
        if not frame_id and context.frame_link:
            frame_id = extract_frame_id_from_link(context.frame_link)

        is_auto_created_frame = False

        # Stage 3: frame 未指定 + opt-in なら board 上に新規 frame を自動作成する。
        # board_items は placement 計算のために先に取得する（その後の occupied_bottom
        # 計算では新規 frame は空なのでスキップする）。
        if not frame_id and context.auto_frame:
            try:
                board_items = self._client.get_items_on_board(board_id)
                self._client.get_connectors_on_board(board_id)
            except ExecutionError as exc:
                reason = f"board item / connector 一覧取得失敗: {exc}"
                result.stop_reasons.append(reason)
                result.stopped_stage = StoppedStage.RESOLVE_FRAME
                result.rerun_eligible = True
                logger.error(reason)
                self._write_run_log(result, metadata_map, start_ms, config)
                return result

            new_cx, new_cy = _compute_auto_frame_placement(board_items, plan)
            try:
                created = self._client.create_frame(
                    board_id=board_id,
                    title=plan.frame.title,
                    x=new_cx,
                    y=new_cy,
                    width=plan.frame.width,
                    height=plan.frame.height,
                )
            except ExecutionError as exc:
                reason = f"auto-frame: frame 作成失敗: {exc}"
                result.stop_reasons.append(reason)
                result.stopped_stage = StoppedStage.RESOLVE_FRAME
                result.rerun_eligible = True
                logger.error(reason)
                self._write_run_log(result, metadata_map, start_ms, config)
                return result

            new_frame_id = created.get("id") if isinstance(created, dict) else None
            if not isinstance(new_frame_id, str) or not new_frame_id:
                reason = (
                    "auto-frame: create_frame レスポンスから frame_id を"
                    " 取得できませんでした"
                )
                result.stop_reasons.append(reason)
                result.stopped_stage = StoppedStage.RESOLVE_FRAME
                result.rerun_eligible = True
                logger.error(reason)
                self._write_run_log(result, metadata_map, start_ms, config)
                return result

            frame_id = new_frame_id
            is_auto_created_frame = True
            logger.info(
                "auto-frame: 新規 frame を作成 (id=%s, x=%.0f, y=%.0f, w=%.0f, h=%.0f)",
                frame_id, new_cx, new_cy, plan.frame.width, plan.frame.height,
            )

        if not frame_id:
            # frame_id 不在 + auto-frame 未指定 → 従来通り停止
            reason = (
                "append モードでは frame_id が必須です。"
                " --frame-id もしくは解析可能な --frame-link を指定してください"
                "（あるいは --auto-frame で新規 frame を自動作成）"
            )
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.RESOLVE_FRAME
            result.rerun_eligible = True
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result

        if is_auto_created_frame:
            # auto-frame 経由で既に board_items 取得済み。新規 frame は空なので
            # occupied_bottom=0 で進む。
            items_in_frame = []
            occupied_bottom = 0.0
        else:
            try:
                board_items = self._client.get_items_on_board(board_id)
                # connector 一覧は append では直接使わないが、取得可否の検証と
                # 今後の拡張（frame 内 connector 確認）のため呼び出しておく
                self._client.get_connectors_on_board(board_id)
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

            # frame 内 item を抽出し、既存占有領域の下端を計算
            items_in_frame = [
                item for item in board_items
                if _get_parent_id(item) == frame_id
            ]
            occupied_bottom = _calculate_occupied_bottom(items_in_frame)

        result.frame_id = frame_id

        # 6. 同一 flow_group_id 衝突チェック（P1-B / P0 2回目指摘）
        # collision 判定は「最新 run が既存 item を 1 件以上反映させているか」
        # を基準にする。単に ``created_count > 0`` だけを見ると、update-only の
        # 前回 run （created_count==0 / updated_count>0）をすり抜けてしまい、
        # 既存 item 上に重複 append が発生する。
        #
        # 判定ルール:
        #   - ``created_count > 0 OR updated_count > 0`` → collision として停止
        #   - 双方 0（完全失敗 run） → collision としない（既存仕様維持）
        # partial_success=True の場合のみ update mode への切替を促すメッセージを使う。
        prev_run_log = find_latest_run_log(
            config.log_dir,
            board_id,
            frame_id,
            confirmed_input.flow_group_id,
        )
        has_prev_effect = (
            prev_run_log is not None
            and (prev_run_log.created_count > 0 or prev_run_log.updated_count > 0)
        )
        if has_prev_effect:
            assert prev_run_log is not None  # 上の条件で保証（型チェック補助）
            if prev_run_log.partial_success:
                reason = (
                    "同一 flow_group_id の item が部分的に存在するため append 不可。"
                    " 前回 run は partial_success=True で停止しています。"
                    " update モードに切り替えて再実行してください"
                )
            else:
                reason = (
                    "同一 flow_group_id の item が既に存在するため append 不可。"
                    " update モードを使用するか、異なる flow_group_id で再試行してください"
                )
            result.stop_reasons.append(reason)
            result.stopped_stage = StoppedStage.FLOW_GROUP_COLLISION
            result.rerun_eligible = False
            logger.error(reason)
            self._write_run_log(result, metadata_map, start_ms, config)
            return result
        elif prev_run_log is not None:
            # 前回 run log は存在するが created_count == 0 かつ updated_count == 0
            # つまり「1 件も反映していない完全失敗 run」→ 再 append を許可
            logger.info(
                "前回 run log は created_count=0 / updated_count=0 の完全失敗のため "
                "collision 扱いとせず再 append を許可します: run_id=%s",
                prev_run_log.run_id,
            )

        # 6.5 Stage 2B: frame 自動リサイズ（default ON / opt-out で skip）
        # auto-frame で新規作成したばかりの frame は plan 寸法で作っており
        # 余計な再リサイズは不要なためスキップする。
        if context.auto_resize and not is_auto_created_frame:
            current_frame = next(
                (
                    it for it in board_items
                    if isinstance(it.get("id"), str) and it["id"] == frame_id
                ),
                None,
            )
            if current_frame is not None:
                try:
                    new_cx, new_cy, new_w, new_h = compute_required_append_frame_size(
                        plan, occupied_bottom, current_frame
                    )
                    cur_geom = current_frame.get("geometry") or {}
                    try:
                        cur_w = float(cur_geom.get("width", 0.0))
                        cur_h = float(cur_geom.get("height", 0.0))
                    except (TypeError, ValueError):
                        cur_w = 0.0
                        cur_h = 0.0
                    # 既存 size より大きい場合のみ resize
                    if new_w > cur_w or new_h > cur_h:
                        logger.info(
                            "auto-resize: frame (%.0fx%.0f) -> (%.0fx%.0f)",
                            cur_w, cur_h, new_w, new_h,
                        )
                        self._client.update_frame(
                            board_id=board_id,
                            frame_id=frame_id,
                            x=new_cx,
                            y=new_cy,
                            width=new_w,
                            height=new_h,
                        )
                except ExecutionError as exc:
                    # resize API 失敗はフォールバック: 従来通り append 試行
                    # （frame が小さい場合は後続 shape 作成で 400 する可能性あり）。
                    # InputError やその他の非 API 例外は上位バグの可能性が高い
                    # ため握りつぶさず伝播させる。
                    logger.warning(
                        "auto-resize API 失敗、既存サイズで続行: %s", exc
                    )

        # 7. DrawingPlan に座標オフセットを適用
        # offset_y は logical 座標系でのシフト量。render 時に to_frame_local_center
        # がさらに -frame.y (= +FRAME_PADDING) を足すため、FRAME_PADDING を差し引い
        # て existing bottom と new top の間を丁度 APPEND_GAP に揃える。
        #   miro_top = (lane.y + offset_y) - frame.y
        #            = 0 + (occupied_bottom + APPEND_GAP - FRAME_PADDING) + FRAME_PADDING
        #            = occupied_bottom + APPEND_GAP
        # なお以前は `- plan.frame.y` を引いて二重引き算による 100px バグを抱えて
        # いた。その修正後も render 段の +FRAME_PADDING が残存し 110px ズレ
        # (APPEND_GAP + FRAME_PADDING) していたため、ここで引き算する。
        # offset_x: 0（frame 左端基準で配置）
        if occupied_bottom > 0.0:
            offset_y = occupied_bottom + APPEND_GAP - FRAME_PADDING
        else:
            # 空 frame: plan の論理座標をそのまま使う（render 時の +FRAME_PADDING
            # で top = FRAME_PADDING に配置される）
            offset_y = 0.0
        offset_x = 0.0

        if offset_y != 0.0 or offset_x != 0.0:
            plan = _shift_plan(plan, offset_x, offset_y)
            logger.info(
                "append offset 適用: occupied_bottom=%.1f offset=(%.1f, %.1f)",
                occupied_bottom, offset_x, offset_y,
            )

        # 8. Stage 3: item 作成
        id_map: dict[str, str] = {}

        self._create_lane_items(board_id, frame_id, plan, result, metadata_map, id_map)
        self._create_node_items(board_id, frame_id, plan, result, metadata_map, id_map)
        self._create_system_label_items(
            board_id, frame_id, plan, result, metadata_map, id_map
        )
        self._create_endpoint_items(
            board_id, frame_id, plan, result, metadata_map, id_map
        )
        stopped = self._create_connector_items(
            board_id, plan, result, metadata_map, id_map
        )
        if stopped:
            result.stopped_stage = StoppedStage.UPSERT_CONNECTORS
            result.rerun_eligible = True
            self._finalize(result, metadata_map, start_ms, config)
            return result

        # 9. 成功判定 + run log 書き出し
        self._finalize(result, metadata_map, start_ms, config)
        return result

    # ------------------------------------------------------------------
    # finalize / run log
    # ------------------------------------------------------------------

    def _finalize(
        self,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        start_ms: int,
        config: AppConfig,
    ) -> None:
        """成功判定・partial_success フラグ設定・run log 書き出し。"""
        stopped = result.stopped_stage is not None or len(result.stop_reasons) > 0
        result.success = result.failed_count == 0 and len(result.stop_reasons) == 0
        result.partial_success = result.created_count > 0 and (
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
        """DrawingPlan と append 配置プレビューを stderr に出力する。"""
        w = sys.stderr.write
        w("=" * 60 + "\n")
        w("[DRY-RUN] append mode — Drawing Plan Summary\n")
        w("=" * 60 + "\n")
        w(f"\nBoard ID: {context.board_id}\n")
        w(f"Frame ID: {context.frame_id}\n")
        f = plan.frame
        w(f"Frame (既存再利用): {f.title} (plan x={f.x}, y={f.y}, w={f.width}, h={f.height})\n")
        w("  NOTE: append では frame は既存を再利用する。plan.frame の座標/寸法は"
          " 論理座標のまま保持され、実 frame は変更しない\n")
        w(f"  NOTE: 実際の配置オフセットは board 取得後の占有領域から算出（APPEND_GAP={APPEND_GAP}）\n")

        w(f"\nLanes ({len(plan.lanes)}):\n")
        for lane in plan.lanes:
            w(f"  - {lane.id} [{lane.type}] \"{lane.label}\"\n")
        w(f"\nNodes ({len(plan.nodes)}):\n")
        for node in plan.nodes:
            w(f"  - {node.id} [{node.type}] \"{node.label}\" lane={node.lane_id}\n")
        w(f"\nSystemLabels ({len(plan.system_labels)}):\n")
        for sl in plan.system_labels:
            w(f"  - {sl.id} \"{sl.label}\" node={sl.node_id}\n")
        w(f"\nEndpoints ({len(plan.endpoints)}):\n")
        for ep in plan.endpoints:
            w(f"  - {ep.id} \"{ep.label}\" system={ep.system_id}\n")
        w(f"\nConnectors ({len(plan.connectors)}):\n")
        for conn in plan.connectors:
            label_str = f" \"{conn.label}\"" if conn.label else ""
            back_str = " (back_edge)" if conn.is_back_edge else ""
            w(
                f"  - {conn.id}: {conn.from_plan_id} -> {conn.to_plan_id}"
                f" [{conn.type}]{label_str}{back_str}\n"
            )

        total = (
            1
            + len(plan.lanes)
            + len(plan.nodes)
            + len(plan.system_labels)
            + len(plan.endpoints)
            + len(plan.connectors)
        )
        w(f"\nTotal items (frame を含む論理総数): {total}\n")
        w(
            "\nAppend preview: 実占有領域は dry-run では取得しないためオフセット計算はスキップ。\n"
        )
        w("=" * 60 + "\n")
        sys.stderr.flush()

    @staticmethod
    def _dry_run_generate_item_results(
        plan: DrawingPlan,
        metadata_map: dict[str, dict[str, str]],
        result: ExecutionResult,
    ) -> None:
        """dry-run 時に全 item の ItemResult を dry_run_skipped で生成する。

        append では frame は既存を再利用するため、frame の ItemResult は
        action='create' として記録するが result は dry_run_skipped とする
        （実際は作成も更新もしない）。
        """

        def _add(plan_id: str, fallback_type: str, fallback_id: str, fallback_role: str) -> None:
            meta = metadata_map.get(plan_id, {})
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", fallback_type),
                semantic_id=meta.get("semantic_id", fallback_id),
                render_role=meta.get("render_role", fallback_role),
                action=ItemAction.CREATE,
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
    # Stage 3: item 作成（create_handler.py と同等ロジック）
    # ------------------------------------------------------------------

    def _create_lane_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """lane shape を既存 frame 内に追加する。"""
        for lane in plan.lanes:
            meta = metadata_map.get(lane.id, {})
            lx, ly = to_frame_local_center(
                plan.frame, lane.x, lane.y, lane.width, lane.height
            )
            style = ACTOR_LANE_STYLE if lane.type == "actor_lane" else SYSTEM_LANE_STYLE
            content = f"<b>{lane.label}</b>" if LANE_BOLD_WRAP else lane.label
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape="rectangle",
                    content=content,
                    x=lx,
                    y=ly,
                    width=lane.width,
                    height=lane.height,
                    style=style,
                    parent_id=frame_id,
                )
            except ExecutionError as exc:
                reason = f"lane {lane.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", lane.type),
                    semantic_id=meta.get("semantic_id", lane.semantic_id),
                    render_role=meta.get("render_role", "lane_container"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            miro_id = resp.get("id") if isinstance(resp, dict) else None
            if not miro_id or not isinstance(miro_id, str):
                reason = f"lane {lane.id} 作成レスポンスに id が含まれていない"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", lane.type),
                    semantic_id=meta.get("semantic_id", lane.semantic_id),
                    render_role=meta.get("render_role", "lane_container"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[lane.id] = miro_id
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", lane.type),
                semantic_id=meta.get("semantic_id", lane.semantic_id),
                render_role=meta.get("render_role", "lane_container"),
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=miro_id,
            ))
            result.created_count += 1
            logger.info("lane 作成完了: %s -> %s", lane.id, miro_id)

    def _create_node_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """node shape を既存 frame 内に追加する。"""
        for node in plan.nodes:
            meta = metadata_map.get(node.id, {})
            shape = node_shape(node.type)
            style = NODE_STYLES.get(node.type, NODE_STYLE_BASE)
            lx, ly = to_frame_local_center(
                plan.frame, node.x, node.y, node.width, node.height
            )
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape=shape,
                    content=node.label,
                    x=lx,
                    y=ly,
                    width=node.width,
                    height=node.height,
                    style=style,
                    parent_id=frame_id,
                )
            except ExecutionError as exc:
                reason = f"node {node.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "node"),
                    semantic_id=meta.get("semantic_id", node.semantic_id),
                    render_role=meta.get("render_role", "node_shape"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            miro_id = resp.get("id") if isinstance(resp, dict) else None
            if not miro_id or not isinstance(miro_id, str):
                reason = f"node {node.id} 作成レスポンスに id が含まれていない"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "node"),
                    semantic_id=meta.get("semantic_id", node.semantic_id),
                    render_role=meta.get("render_role", "node_shape"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[node.id] = miro_id
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", "node"),
                semantic_id=meta.get("semantic_id", node.semantic_id),
                render_role=meta.get("render_role", "node_shape"),
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=miro_id,
            ))
            result.created_count += 1
            logger.info("node 作成完了: %s -> %s", node.id, miro_id)

    def _create_system_label_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """system_label shape を既存 frame 内に追加する。"""
        for sl in plan.system_labels:
            meta = metadata_map.get(sl.id, {})
            lx, ly = to_frame_local_center(
                plan.frame, sl.x, sl.y, sl.width, sl.height
            )
            try:
                resp = self._client.create_shape(
                    board_id=board_id,
                    shape="round_rectangle",
                    content=sl.label,
                    x=lx,
                    y=ly,
                    width=sl.width,
                    height=sl.height,
                    style=SYSTEM_LABEL_STYLE,
                    parent_id=frame_id,
                )
            except ExecutionError as exc:
                reason = f"system_label {sl.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", sl.system_id),
                    render_role=meta.get("render_role", "system_label"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            miro_id = resp.get("id") if isinstance(resp, dict) else None
            if not miro_id or not isinstance(miro_id, str):
                reason = f"system_label {sl.id} 作成レスポンスに id が含まれていない"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", sl.system_id),
                    render_role=meta.get("render_role", "system_label"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[sl.id] = miro_id
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", "system_endpoint"),
                semantic_id=meta.get("semantic_id", sl.system_id),
                render_role=meta.get("render_role", "system_label"),
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=miro_id,
            ))
            result.created_count += 1
            logger.info("system_label 作成完了: %s -> %s", sl.id, miro_id)

    def _create_endpoint_items(
        self,
        board_id: str,
        frame_id: str,
        plan: DrawingPlan,
        result: ExecutionResult,
        metadata_map: dict[str, dict[str, str]],
        id_map: dict[str, str],
    ) -> None:
        """endpoint shape を既存 frame 内に追加する（後方互換。通常は空）。"""
        for ep in plan.endpoints:
            meta = metadata_map.get(ep.id, {})
            lx, ly = to_frame_local_center(
                plan.frame, ep.x, ep.y, ep.width, ep.height
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
                    style=ENDPOINT_STYLE,
                    parent_id=frame_id,
                )
            except ExecutionError as exc:
                reason = f"endpoint {ep.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", ep.semantic_id),
                    render_role=meta.get("render_role", "endpoint_shape"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            miro_id = resp.get("id") if isinstance(resp, dict) else None
            if not miro_id or not isinstance(miro_id, str):
                reason = f"endpoint {ep.id} 作成レスポンスに id が含まれていない"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", "system_endpoint"),
                    semantic_id=meta.get("semantic_id", ep.semantic_id),
                    render_role=meta.get("render_role", "endpoint_shape"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[ep.id] = miro_id
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", "system_endpoint"),
                semantic_id=meta.get("semantic_id", ep.semantic_id),
                render_role=meta.get("render_role", "endpoint_shape"),
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=miro_id,
            ))
            result.created_count += 1
            logger.info("endpoint 作成完了: %s -> %s", ep.id, miro_id)

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
            meta = metadata_map.get(conn.id, {})

            # system_access connector は SystemLabel で代替するため skip
            if conn.type == "system_access":
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.SKIPPED,
                    reason="system_access connector は SystemLabel で代替",
                ))
                result.skipped_count += 1
                continue

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
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action=ItemAction.CREATE,
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
                connector_style = BACK_EDGE_CONNECTOR_STYLE
            else:
                start_item = {"id": from_miro_id, "position": {"x": "100%", "y": "50%"}}
                end_item = {"id": to_miro_id, "position": {"x": "0%", "y": "50%"}}
                connector_style = CONNECTOR_STYLE

            try:
                resp = self._client.create_connector(
                    board_id=board_id,
                    start_item=start_item,
                    end_item=end_item,
                    shape="elbowed",
                    style=connector_style,
                    captions=captions,
                )
            except ExecutionError as exc:
                reason = f"connector {conn.id} 作成失敗: {exc}"
                result.item_results.append(ItemResult(
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
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
                    stable_item_id=meta.get("stable_item_id", ""),
                    semantic_type=meta.get("semantic_type", conn.type),
                    semantic_id=meta.get("semantic_id", conn.id),
                    render_role=meta.get("render_role", "edge_connector"),
                    action=ItemAction.CREATE,
                    result=ItemResultStatus.FAILED,
                    reason=reason,
                ))
                result.failed_count += 1
                logger.warning(reason)
                continue

            id_map[conn.id] = conn_miro_id
            result.item_results.append(ItemResult(
                stable_item_id=meta.get("stable_item_id", ""),
                semantic_type=meta.get("semantic_type", conn.type),
                semantic_id=meta.get("semantic_id", conn.id),
                render_role=meta.get("render_role", "edge_connector"),
                action=ItemAction.CREATE,
                result=ItemResultStatus.SUCCESS,
                miro_item_id=conn_miro_id,
            ))
            result.created_count += 1
            logger.info("connector 作成完了: %s -> %s", conn.id, conn_miro_id)

        return False


# ---------------------------------------------------------------------------
# 既存占有領域計算
# ---------------------------------------------------------------------------


def _get_parent_id(item: dict[str, Any]) -> str | None:
    """Miro item レスポンスから parent_id を抽出する。

    Miro API v2 では parent フィールドは以下のいずれかの形式をとる:
    - ``{"id": "..."}``
    - ``{"links": {...}, "id": "..."}``
    """
    parent = item.get("parent")
    if isinstance(parent, dict):
        pid = parent.get("id")
        if isinstance(pid, str):
            return pid
    return None


def _compute_auto_frame_placement(
    board_items: list[dict[str, Any]],
    plan: DrawingPlan,
) -> tuple[float, float]:
    """新規 frame を board 上に配置する center 座標 (x, y) を返す。

    戦略:
    - X: 既存 frame の右端最大 + ``FRAME_MARGIN`` の位置に新 frame の左端を揃える
    - Y: 既存 frame の top 最小値に新 frame の top を揃える（水平に積む）
    - 既存 frame が無ければ ``(0, 0)``

    旧実装では Y を ``plan.frame.height / 2`` 固定（= top=0）にしていたが、
    board 上の既存 frame は通常 ``center_y=0, top=-height/2 < 0`` なので
    垂直方向に揃わないというバグ (P1-2) があった。ここでは既存 frame の
    最上端に合わせることで水平に並べる。

    Args:
        board_items: ``GET /boards/{id}/items`` のレスポンス。
        plan: 配置したい DrawingPlan。``plan.frame.width / height`` を使って
            新 frame 右下端を決める。

    Returns:
        ``(center_x, center_y)``: Miro の position（中心座標）。
    """
    max_right: float | None = None
    min_top: float | None = None
    for item in board_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "frame":
            continue
        pos = item.get("position") or {}
        geom = item.get("geometry") or {}
        if not isinstance(pos, dict) or not isinstance(geom, dict):
            continue
        try:
            cx = float(pos.get("x", 0))
            cy = float(pos.get("y", 0))
            w = float(geom.get("width", 0))
            h = float(geom.get("height", 0))
        except (TypeError, ValueError):
            continue
        right = cx + w / 2.0
        top = cy - h / 2.0
        if max_right is None or right > max_right:
            max_right = right
        if min_top is None or top < min_top:
            min_top = top

    if max_right is None or min_top is None:
        return (0.0, 0.0)

    new_left = max_right + FRAME_MARGIN
    new_cx = new_left + float(plan.frame.width) / 2.0
    # Y: 既存 frame の最上端に新 frame の top を揃える
    new_cy = min_top + float(plan.frame.height) / 2.0
    return (new_cx, new_cy)


def _calculate_occupied_bottom(items_in_frame: list[dict[str, Any]]) -> float:
    """frame 内 item の最大下端 (position.y + geometry.height/2) を返す。

    items が空の場合は 0.0 を返す（frame 左上基準で append 開始）。
    Miro API の position は item の中心座標、geometry は item 寸法。
    """
    max_bottom = 0.0
    for item in items_in_frame:
        position = item.get("position") or {}
        geometry = item.get("geometry") or {}
        if not isinstance(position, dict) or not isinstance(geometry, dict):
            continue
        try:
            y = float(position.get("y", 0.0))
            h = float(geometry.get("height", 0.0))
        except (TypeError, ValueError):
            continue
        bottom = y + h / 2.0
        if bottom > max_bottom:
            max_bottom = bottom
    return max_bottom


# ---------------------------------------------------------------------------
# DrawingPlan 座標シフト
# ---------------------------------------------------------------------------


def _shift_plan(plan: DrawingPlan, dx: float, dy: float) -> DrawingPlan:
    """plan 内の lane / node / system_label / endpoint の座標を (dx, dy) シフトする。

    frame は変更しない（既存 frame を再利用するため）。
    connector は plan_id 参照で具体的な座標を持たないため変更不要。
    frozen dataclass のため ``dataclasses.replace`` で新しいインスタンスを構築する。
    """
    new_lanes = [replace(lane, x=lane.x + dx, y=lane.y + dy) for lane in plan.lanes]
    new_nodes = [replace(node, x=node.x + dx, y=node.y + dy) for node in plan.nodes]
    new_system_labels = [
        replace(sl, x=sl.x + dx, y=sl.y + dy) for sl in plan.system_labels
    ]
    new_endpoints = [
        replace(ep, x=ep.x + dx, y=ep.y + dy) for ep in plan.endpoints
    ]
    return replace(
        plan,
        lanes=new_lanes,
        nodes=new_nodes,
        system_labels=new_system_labels,
        endpoints=new_endpoints,
    )


