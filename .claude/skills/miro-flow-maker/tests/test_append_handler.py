"""AppendHandler のテスト。

MiroClient をモックし、ModeHandler Protocol 実装として
既存 board / frame 上に新しい flow_group を追加するケースを検証する。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from miro_flow_maker.append_handler import (
    APPEND_GAP,
    AppendHandler,
    _calculate_occupied_bottom,
    _get_parent_id,
    _shift_plan,
)
from miro_flow_maker.exceptions import ExecutionError
from miro_flow_maker.gate import validate
from miro_flow_maker.layout import build_drawing_plan
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.models import (
    AppConfig,
    ConfirmedInput,
    ExecutionResult,
    ItemMetadata,
    RequestContext,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(log_dir: str) -> AppConfig:
    return AppConfig.from_dict({
        "miro_access_token": "test-token-12345678",
        "miro_api_base_url": "https://test.miro.com/v2",
        "log_dir": log_dir,
    })


def _make_context(
    *,
    board_id: str | None = "board-001",
    frame_id: str | None = "frame-001",
    frame_link: str | None = None,
    dry_run: bool = False,
    auto_frame: bool = False,
    auto_resize: bool = True,
) -> RequestContext:
    return RequestContext(
        mode="append",
        board_id=board_id,
        frame_id=frame_id,
        frame_link=frame_link,
        board_name=None,
        dry_run=dry_run,
        input_path=str(FIXTURES / "confirmed_representative.json"),
        auto_frame=auto_frame,
        auto_resize=auto_resize,
    )


def _load_confirmed_input() -> ConfirmedInput:
    """代表ケースの ConfirmedInput を生成する。"""
    input_data = json.loads(
        (FIXTURES / "confirmed_representative.json").read_text(encoding="utf-8")
    )
    context = RequestContext(
        mode="append",
        board_id="board-001",
        frame_id="frame-001",
        frame_link=None,
        board_name=None,
        dry_run=False,
        input_path=str(FIXTURES / "confirmed_representative.json"),
    )
    result = validate(input_data, context)
    assert result.passed, f"validate failed: {result.stop_reasons}"
    assert result.normalized_input is not None
    return result.normalized_input


def _replace_flow_group_id(
    confirmed: ConfirmedInput,
    new_flow_group_id: str,
) -> ConfirmedInput:
    """ConfirmedInput の flow_group_id を差し替えた新しいインスタンスを返す。

    metadata.flow_group_id も同時に更新する（stable_item_id の構築に使われる）。
    """
    new_metadata = replace(confirmed.metadata, flow_group_id=new_flow_group_id)
    return replace(
        confirmed,
        flow_group_id=new_flow_group_id,
        metadata=new_metadata,
    )


def _make_mock_client_for_append(
    *,
    board_items: list[dict[str, Any]] | None = None,
    board_connectors: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """append 用のモック MiroClient を生成する。"""
    client = MagicMock(spec=MiroClient)
    client.get_board.return_value = {"id": "board-001"}
    client.get_items_on_board.return_value = list(board_items or [])
    client.get_connectors_on_board.return_value = list(board_connectors or [])

    _shape_counter = {"n": 0}

    def _create_shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _shape_counter["n"] += 1
        return {"id": f"new-shape-{_shape_counter['n']:03d}", "type": "shape"}

    client.create_shape.side_effect = _create_shape_side_effect

    _conn_counter = {"n": 0}

    def _create_conn_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _conn_counter["n"] += 1
        return {"id": f"new-conn-{_conn_counter['n']:03d}", "type": "connector"}

    client.create_connector.side_effect = _create_conn_side_effect

    return client


def _build_frame_with_occupancy(
    frame_id: str = "frame-001",
    *,
    occupied_bottom: float = 0.0,
    extra_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """指定の占有下端を持つ frame の board_items を構築する。

    occupied_bottom > 0 の場合、frame 内に 1 つダミー shape を配置する。
    """
    items: list[dict[str, Any]] = [
        {"id": frame_id, "type": "frame", "data": {"title": "既存 frame"}},
    ]
    if occupied_bottom > 0.0:
        # center y + height/2 = occupied_bottom となるように配置
        dummy_height = 60.0
        dummy_center_y = occupied_bottom - dummy_height / 2.0
        items.append({
            "id": "existing-shape-001",
            "type": "shape",
            "parent": {"id": frame_id},
            "position": {"x": 100.0, "y": dummy_center_y},
            "geometry": {"width": 120.0, "height": dummy_height},
        })
    if extra_items:
        items.extend(extra_items)
    return items


# ---------------------------------------------------------------------------
# Unit tests: 内部ヘルパー関数
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """_get_parent_id / _calculate_occupied_bottom / _shift_plan の単体テスト。"""

    def test_get_parent_id_with_id(self) -> None:
        assert _get_parent_id({"parent": {"id": "frame-001"}}) == "frame-001"

    def test_get_parent_id_with_links_and_id(self) -> None:
        item = {"parent": {"links": {"self": "..."}, "id": "frame-002"}}
        assert _get_parent_id(item) == "frame-002"

    def test_get_parent_id_no_parent(self) -> None:
        assert _get_parent_id({}) is None

    def test_get_parent_id_none_parent(self) -> None:
        assert _get_parent_id({"parent": None}) is None

    def test_calculate_occupied_bottom_empty(self) -> None:
        assert _calculate_occupied_bottom([]) == 0.0

    def test_calculate_occupied_bottom_single(self) -> None:
        items = [{
            "position": {"x": 100.0, "y": 200.0},
            "geometry": {"width": 80.0, "height": 60.0},
        }]
        # 200 + 60/2 = 230
        assert _calculate_occupied_bottom(items) == 230.0

    def test_calculate_occupied_bottom_max_wins(self) -> None:
        items = [
            {
                "position": {"y": 100.0},
                "geometry": {"height": 40.0},
            },
            {
                "position": {"y": 500.0},
                "geometry": {"height": 80.0},
            },
            {
                "position": {"y": 300.0},
                "geometry": {"height": 20.0},
            },
        ]
        # 500 + 80/2 = 540
        assert _calculate_occupied_bottom(items) == 540.0

    def test_calculate_occupied_bottom_missing_fields(self) -> None:
        # position / geometry が無い item は 0 扱い（max_bottom に影響しない）
        items = [{"id": "x"}]
        assert _calculate_occupied_bottom(items) == 0.0

    def test_shift_plan_moves_lane_node_system_label_endpoint(self) -> None:
        confirmed = _load_confirmed_input()
        plan = build_drawing_plan(confirmed, board_name="")
        dx, dy = 100.0, 200.0

        shifted = _shift_plan(plan, dx, dy)

        # frame は変更されない
        assert shifted.frame == plan.frame

        # lanes
        for orig, new in zip(plan.lanes, shifted.lanes):
            assert new.x == orig.x + dx
            assert new.y == orig.y + dy
            assert new.width == orig.width
            assert new.height == orig.height

        # nodes
        for orig, new in zip(plan.nodes, shifted.nodes):
            assert new.x == orig.x + dx
            assert new.y == orig.y + dy

        # system_labels
        for orig, new in zip(plan.system_labels, shifted.system_labels):
            assert new.x == orig.x + dx
            assert new.y == orig.y + dy

        # endpoints
        for orig, new in zip(plan.endpoints, shifted.endpoints):
            assert new.x == orig.x + dx
            assert new.y == orig.y + dy

        # connectors は座標を持たないため変化しない
        assert shifted.connectors == plan.connectors


# ---------------------------------------------------------------------------
# TestAppendHandlerExecute: 全 item が成功して新規追加
# ---------------------------------------------------------------------------


class TestAppendHandlerExecute:
    """frame 内に既存 item がある状態で append する。"""

    def setup_method(self) -> None:
        self.confirmed = _load_confirmed_input()
        # 既存 flow_group_id と重複しないように差し替え
        self.confirmed = _replace_flow_group_id(self.confirmed, "flow-append-01")
        self.board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=500.0
        )
        self.client = _make_mock_client_for_append(
            board_items=self.board_items
        )
        self.handler = AppendHandler(self.client)
        self.tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        self.context = _make_context(
            board_id="board-001", frame_id="frame-001"
        )
        self.config = _make_config(self.tmpdir)
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_execution_result(self) -> None:
        assert isinstance(self.result, ExecutionResult)

    def test_success(self) -> None:
        assert self.result.success is True, self.result.stop_reasons

    def test_mode_is_append(self) -> None:
        assert self.result.mode == "append"

    def test_dry_run_false(self) -> None:
        assert self.result.dry_run is False

    def test_board_id(self) -> None:
        assert self.result.board_id == "board-001"

    def test_frame_id(self) -> None:
        assert self.result.frame_id == "frame-001"

    def test_flow_group_id(self) -> None:
        assert self.result.flow_group_id == "flow-append-01"

    def test_no_stop_reasons(self) -> None:
        assert self.result.stop_reasons == []

    def test_stopped_stage_none(self) -> None:
        assert self.result.stopped_stage is None

    def test_shape_count(self) -> None:
        # 代表ケース: lane(3) + node(6) + system_label(2) + endpoint(0) = 11
        assert self.client.create_shape.call_count == 11

    def test_connector_count(self) -> None:
        # business_flow(6) のみ、system_access(2) は skip
        assert self.client.create_connector.call_count == 6

    def test_created_count(self) -> None:
        # shapes(11) + connectors(6) = 17
        assert self.result.created_count == 17

    def test_no_frame_create(self) -> None:
        """append では frame は新規作成しない。"""
        # MiroClient mock には create_frame は存在するが呼ばれていないはず
        self.client.create_frame.assert_not_called()

    def test_no_board_create(self) -> None:
        """append では board は新規作成しない。"""
        self.client.create_board.assert_not_called()

    def test_get_board_called(self) -> None:
        self.client.get_board.assert_called_once_with("board-001")

    def test_get_items_on_board_called(self) -> None:
        self.client.get_items_on_board.assert_called_once_with("board-001")

    def test_all_shapes_parented_to_frame(self) -> None:
        for call_item in self.client.create_shape.call_args_list:
            kwargs = call_item.kwargs
            assert kwargs.get("parent_id") == "frame-001"

    def test_offset_applied(self) -> None:
        """occupied_bottom=500 の場合、lane shape は occupied_bottom + APPEND_GAP
        よりも下に配置されていること（frame 左上基準の中心 y）。"""
        # 最初の shape 呼び出し（= lane）の y 座標を確認
        first_lane_call = self.client.create_shape.call_args_list[0]
        ly = first_lane_call.kwargs.get("y")
        assert ly is not None
        # lane は frame 内占有領域より下に置かれる
        # frame 左上基準での座標なので、占有下端 (500) + APPEND_GAP より大きい
        assert ly > 500.0 + APPEND_GAP

    def test_first_appended_lane_gap_equals_append_gap(self) -> None:
        """append 後の新 lane top と existing bottom の差が丁度 APPEND_GAP px になる。

        既存占有下端 = 500 の frame に対し、最初に配置される lane の
        miro 座標上の上端（center_y - height/2）が 500 + APPEND_GAP (= 560)
        になることを検証する。offset_y = occupied_bottom + APPEND_GAP -
        FRAME_PADDING と計算し、render 時に +FRAME_PADDING されて相殺される。
        """
        first_lane_call = self.client.create_shape.call_args_list[0]
        center_y = first_lane_call.kwargs.get("y")
        height = first_lane_call.kwargs.get("height")
        assert center_y is not None
        assert height is not None
        top = center_y - height / 2.0
        assert top == pytest.approx(500.0 + APPEND_GAP), (
            f"first lane top={top}, expected={500.0 + APPEND_GAP} "
            f"(occupied_bottom=500 + APPEND_GAP={APPEND_GAP})"
        )


# ---------------------------------------------------------------------------
# TestAppendHandlerEmptyFrame: 空 frame
# ---------------------------------------------------------------------------


class TestAppendHandlerEmptyFrame:
    """既存 item が無い空 frame に append する。"""

    def test_empty_frame_append(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-empty"
        )
        # frame だけあって、その中に item は無い
        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=0.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is True, result.stop_reasons
            assert result.stopped_stage is None
            # 空 frame なので offset_y = 0、lane は plan の論理座標のまま配置
            # frame 左上基準（to_frame_local_center）なので lane 中心 y > 0
            first_lane_call = client.create_shape.call_args_list[0]
            ly = first_lane_call.kwargs.get("y")
            assert ly is not None
            assert ly > 0.0
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerFlowGroupCollision: 同一 flow_group_id の run log あり
# ---------------------------------------------------------------------------


class TestAppendHandlerFlowGroupCollision:
    """同一 flow_group_id の前回 run log が存在すると停止する。"""

    def test_collision_stops(self) -> None:
        confirmed = _load_confirmed_input()
        # 既存 confirmed の flow_group_id をそのまま使う
        flow_group_id = confirmed.flow_group_id

        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=100.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            # 同一 board / frame / flow_group の run log を書き出す
            prev_log = {
                "run_id": "prev-run",
                "timestamp": "2026-04-16T00:00:00+00:00",
                "mode": "create",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": flow_group_id,
                "dry_run": False,
                "created_count": 5,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "stop_reasons": [],
                "duration_ms": 1000,
                "errors": [],
                "item_results": [],
                "partial_success": False,
                "stopped_stage": None,
                "rerun_eligible": True,
            }
            path = os.path.join(tmpdir, "run_prev-run_2026-04-16T000000p0000.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(prev_log, f, ensure_ascii=False)

            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "flow_group_collision"
            assert result.rerun_eligible is False
            assert any(
                "同一 flow_group_id" in r for r in result.stop_reasons
            )
            # item 作成は呼ばれない
            client.create_shape.assert_not_called()
            client.create_connector.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_complete_failure_prev_run_is_not_collision(self) -> None:
        """P1-B: 前回 run log の created_count==0（完全失敗）の場合は collision
        扱いにしない（append を許可する）。"""
        confirmed = _load_confirmed_input()
        flow_group_id = confirmed.flow_group_id

        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=0.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            # created_count == 0 の完全失敗 run log（1 件も作れていない）
            prev_log = {
                "run_id": "prev-fail",
                "timestamp": "2026-04-16T00:00:00+00:00",
                "mode": "append",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": flow_group_id,
                "dry_run": False,
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 3,
                "stop_reasons": ["board 接続失敗"],
                "duration_ms": 500,
                "errors": ["board 接続失敗"],
                "item_results": [],
                "partial_success": False,
                "stopped_stage": "resolve_board",
                "rerun_eligible": True,
            }
            path = os.path.join(tmpdir, "run_prev-fail_2026-04-16T000000p0000.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(prev_log, f, ensure_ascii=False)

            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # collision とはならず、append が進行している
            assert result.stopped_stage != "flow_group_collision"
            # create_shape は少なくとも呼ばれる（実際に append 進行）
            assert client.create_shape.called
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_partial_success_prev_run_guides_to_update(self) -> None:
        """P1-B: 前回 run が partial_success=True & created_count > 0 の場合、
        collision として停止し、stop_reasons に update mode への誘導を含める。"""
        confirmed = _load_confirmed_input()
        flow_group_id = confirmed.flow_group_id

        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=100.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            prev_log = {
                "run_id": "prev-partial",
                "timestamp": "2026-04-16T00:00:00+00:00",
                "mode": "append",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": flow_group_id,
                "dry_run": False,
                "created_count": 4,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 2,
                "stop_reasons": ["connector 接続先未解決"],
                "duration_ms": 2000,
                "errors": [],
                "item_results": [],
                "partial_success": True,
                "stopped_stage": "upsert_connectors",
                "rerun_eligible": True,
            }
            path = os.path.join(tmpdir, "run_prev-partial_2026-04-16T000000p0000.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(prev_log, f, ensure_ascii=False)

            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.stopped_stage == "flow_group_collision"
            # stop_reasons に update への誘導が含まれる
            assert any(
                "update" in r.lower() for r in result.stop_reasons
            )
            client.create_shape.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_update_only_prev_run_is_collision(self) -> None:
        """P0 (2回目指摘): 前回 run が update-only（created_count==0 かつ
        updated_count>0）の場合でも collision として扱い、append を停止する。

        修正前は ``created_count > 0`` のみを条件にしていたため、既存 item を
        update で書き換えた直後に append を呼ぶとすり抜けて重複作成していた。
        """
        confirmed = _load_confirmed_input()
        flow_group_id = confirmed.flow_group_id

        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=100.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            # update-only な直前 run: 既存 item を 1 件以上 update している
            prev_log = {
                "run_id": "prev-update-only",
                "timestamp": "2026-04-16T00:00:00+00:00",
                "mode": "update",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": flow_group_id,
                "dry_run": False,
                "created_count": 0,
                "updated_count": 6,
                "skipped_count": 0,
                "failed_count": 0,
                "stop_reasons": [],
                "duration_ms": 900,
                "errors": [],
                "item_results": [],
                "partial_success": False,
                "stopped_stage": None,
                "rerun_eligible": True,
            }
            path = os.path.join(
                tmpdir, "run_prev-update-only_2026-04-16T000000p0000.json"
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(prev_log, f, ensure_ascii=False)

            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # update-only 前 run でも collision として扱われる
            assert result.success is False
            assert result.stopped_stage == "flow_group_collision"
            assert result.rerun_eligible is False
            assert any(
                "同一 flow_group_id" in r for r in result.stop_reasons
            )
            # item 作成は呼ばれない（重複作成が再発していないこと）
            client.create_shape.assert_not_called()
            client.create_connector.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerFrameLinkResolution: P1-A
# ---------------------------------------------------------------------------


class TestAppendHandlerFrameLinkResolution:
    """P1-A: append でも frame_link 経由で frame_id を解決できる。"""

    def test_frame_link_resolves_frame_id(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-link-test"
        )
        board_items = _build_frame_with_occupancy(
            "frame-via-link", occupied_bottom=0.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            # frame_id は指定せず frame_link だけ渡す
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link="https://miro.com/app/board/xyz/?moveToWidget=frame-via-link",
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # resolve_frame で止まらず実際に append 進行
            assert result.stopped_stage != "resolve_frame"
            assert result.frame_id == "frame-via-link"
            assert client.create_shape.called
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_frame_link_fragment_format(self) -> None:
        """fragment 形式 (#/frames/<id>) にも対応する。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-link-frag"
        )
        board_items = _build_frame_with_occupancy(
            "frame-frag-id", occupied_bottom=0.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link="https://miro.com/app/board/xyz/#/frames/frame-frag-id",
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.stopped_stage != "resolve_frame"
            assert result.frame_id == "frame-frag-id"
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerResolveBoardFailure
# ---------------------------------------------------------------------------


class TestAppendHandlerResolveBoardFailure:
    """board API 失敗時に resolve_board で停止する。"""

    def test_get_board_failure(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-board-fail"
        )
        client = _make_mock_client_for_append(board_items=[])
        client.get_board.side_effect = ExecutionError(
            "Miro API クライアントエラー: GET /boards/board-001 — HTTP 404"
        )
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_board"
            assert result.rerun_eligible is True
            assert any("board 取得失敗" in r for r in result.stop_reasons)
            # item 作成は呼ばれない
            client.create_shape.assert_not_called()
            client.get_items_on_board.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_board_id(self) -> None:
        """board_id が指定されていない場合も resolve_board で停止。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-no-board"
        )
        client = _make_mock_client_for_append(board_items=[])
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(board_id=None, frame_id="frame-001")
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_board"
            assert result.rerun_eligible is True
            client.get_board.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerResolveFrameFailure: frame_id None
# ---------------------------------------------------------------------------


class TestAppendHandlerResolveFrameFailure:
    """frame_id が None の場合、resolve_frame で停止する（MVP では frame_id 必須）。"""

    def test_no_frame_id(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-no-frame"
        )
        client = _make_mock_client_for_append(board_items=[])
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(board_id="board-001", frame_id=None)
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_frame"
            assert result.rerun_eligible is True
            assert any("frame_id" in r for r in result.stop_reasons)
            # frame_id 不在のため get_items_on_board は呼ばれない
            client.get_items_on_board.assert_not_called()
            client.create_shape.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerFrameIdNotFound
# ---------------------------------------------------------------------------


class TestAppendHandlerFrameIdNotFound:
    """指定 frame_id が board 上に存在しない場合、resolve_frame で停止する。"""

    def test_frame_not_on_board(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-frame-not-found"
        )
        # 別 frame だけあって target は無い
        board_items = [
            {"id": "other-frame", "type": "frame", "data": {"title": "別 frame"}},
        ]
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001", frame_id="frame-missing"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_frame"
            assert result.rerun_eligible is True
            assert any(
                "frame-missing" in r and "存在しない" in r
                for r in result.stop_reasons
            )
            client.create_shape.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerConnectorUnresolved: 接続先未解決 → partial_success
# ---------------------------------------------------------------------------


class TestAppendHandlerConnectorUnresolved:
    """connector 接続先未解決で停止。一部 item は反映済みなので partial_success。"""

    def test_unresolved_connector_partial_success(self) -> None:
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-conn-unresolved"
        )
        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=100.0
        )
        client = _make_mock_client_for_append(board_items=board_items)

        # shape は全て失敗させる → id_map が空になり、connector で未解決停止
        client.create_shape.side_effect = ExecutionError("shape 作成失敗")

        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "upsert_connectors"
            assert result.rerun_eligible is True
            # 停止理由に接続先未解決が含まれる
            assert any("接続先未解決" in r for r in result.stop_reasons)
            # shape は全て失敗、connector は呼ばれない
            assert result.failed_count >= 1
            client.create_connector.assert_not_called()
            # 何も作成成功していないので partial_success は False
            assert result.partial_success is False
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_partial_success_when_some_created(self) -> None:
        """一部 shape は成功、別の shape は失敗し connector が未解決で停止する場合、
        partial_success=True になること。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-partial"
        )
        board_items = _build_frame_with_occupancy(
            "frame-001", occupied_bottom=100.0
        )
        client = _make_mock_client_for_append(board_items=board_items)

        _call_count = {"n": 0}

        def _shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            _call_count["n"] += 1
            # 最初の 5 回（lane3 + node2）は成功、その後は失敗
            if _call_count["n"] > 5:
                raise ExecutionError("特定 shape 失敗")
            return {"id": f"shape-{_call_count['n']:03d}", "type": "shape"}

        client.create_shape.side_effect = _shape_side_effect
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001", frame_id="frame-001"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            # connector の接続先未解決で停止することを期待
            assert any("接続先未解決" in r for r in result.stop_reasons)
            # 一部作成成功している → partial_success=True
            assert result.created_count > 0
            assert result.partial_success is True
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerDryRun
# ---------------------------------------------------------------------------


class TestAppendHandlerDryRun:
    """dry-run 時は API を呼ばず item_results を dry_run_skipped で生成する。"""

    def setup_method(self) -> None:
        self.confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-dry"
        )
        self.client = _make_mock_client_for_append()
        self.handler = AppendHandler(self.client)
        self.tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        self.context = _make_context(dry_run=True)
        self.config = _make_config(self.tmpdir)
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def teardown_method(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_success(self) -> None:
        assert self.result.success is True

    def test_dry_run_flag(self) -> None:
        assert self.result.dry_run is True

    def test_mode(self) -> None:
        assert self.result.mode == "append"

    def test_no_api_calls(self) -> None:
        self.client.get_board.assert_not_called()
        self.client.get_items_on_board.assert_not_called()
        self.client.create_shape.assert_not_called()
        self.client.create_connector.assert_not_called()

    def test_item_results_populated(self) -> None:
        # frame(1) + lanes(3) + nodes(6) + system_labels(2) + endpoints(0) + connectors(8) = 20
        assert len(self.result.item_results) == 20

    def test_all_dry_run_skipped(self) -> None:
        for ir in self.result.item_results:
            assert ir.result == "dry_run_skipped", f"Unexpected: {ir}"

    def test_all_action_create(self) -> None:
        for ir in self.result.item_results:
            assert ir.action == "create"

    def test_stopped_stage_none(self) -> None:
        assert self.result.stopped_stage is None


# ---------------------------------------------------------------------------
# TestAppendHandlerAutoResize: Stage 2B 自動リサイズ
# ---------------------------------------------------------------------------


def _build_sized_frame(
    frame_id: str = "frame-001",
    *,
    cx: float = 500.0,
    cy: float = 500.0,
    width: float = 1000.0,
    height: float = 1000.0,
    occupied_bottom: float = 0.0,
    frame_top: float | None = None,
) -> list[dict[str, Any]]:
    """position / geometry を持つ frame を含む board_items を返す（auto-resize 用）。

    occupied_bottom は frame 中心基準ではなく board 絶対座標での下端を表す。
    frame_top が指定されない場合は ``cy - height/2`` を使う。
    """
    items: list[dict[str, Any]] = [{
        "id": frame_id,
        "type": "frame",
        "data": {"title": "既存 frame"},
        "position": {"x": cx, "y": cy},
        "geometry": {"width": width, "height": height},
    }]
    if occupied_bottom > 0.0:
        dummy_h = 60.0
        dummy_cy = occupied_bottom - dummy_h / 2.0
        items.append({
            "id": "existing-shape-001",
            "type": "shape",
            "parent": {"id": frame_id},
            "position": {"x": 100.0, "y": dummy_cy},
            "geometry": {"width": 120.0, "height": dummy_h},
        })
    return items


class TestAppendHandlerAutoResize:
    """Stage 2B: append 時の frame 自動リサイズ。"""

    def test_auto_resize_disabled_by_flag(self) -> None:
        """auto_resize=False の場合、update_frame は呼ばれない。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-noresize"
        )
        # frame が十分大きい構成
        board_items = _build_sized_frame(
            "frame-001",
            cx=500.0, cy=500.0,
            width=4000.0, height=4000.0,
            occupied_bottom=100.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=False,
            )
            config = _make_config(tmpdir)
            handler.execute(confirmed, context, config)

            client.update_frame.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_resize_skipped_when_fits(self) -> None:
        """auto_resize=True でも plan が収まる場合、update_frame は呼ばれない。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-fits"
        )
        # 十分大きな frame（plan + padding に対して）
        board_items = _build_sized_frame(
            "frame-001",
            cx=2000.0, cy=2000.0,
            width=5000.0, height=5000.0,
            occupied_bottom=0.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # plan が収まるので resize 不要
            client.update_frame.assert_not_called()
            assert result.stopped_stage is None
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_resize_called_when_exceeds(self) -> None:
        """plan が現 frame を超える場合、update_frame が (cx, cy, w, h) で呼ばれる。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-exceeds"
        )
        # 意図的に小さな frame
        board_items = _build_sized_frame(
            "frame-001",
            cx=100.0, cy=100.0,
            width=200.0, height=200.0,
            occupied_bottom=180.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # update_frame が呼ばれ、必要キーを含む
            client.update_frame.assert_called_once()
            kwargs = client.update_frame.call_args.kwargs
            assert kwargs["board_id"] == "board-001"
            assert kwargs["frame_id"] == "frame-001"
            assert "x" in kwargs and "y" in kwargs
            assert "width" in kwargs and "height" in kwargs
            # 拡張されている（既存より大きい）
            assert kwargs["width"] >= 200.0
            assert kwargs["height"] >= 200.0
            # append 処理は継続している
            assert client.create_shape.called
            # success は resize 成功 + shape 成功の前提
            assert result.success is True, result.stop_reasons
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_resize_failure_falls_through(self) -> None:
        """update_frame が ExecutionError を送出しても append は継続する。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-resize-fail"
        )
        board_items = _build_sized_frame(
            "frame-001",
            cx=100.0, cy=100.0,
            width=200.0, height=200.0,
            occupied_bottom=180.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        client.update_frame.side_effect = ExecutionError("resize 失敗")
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # resize は呼ばれたが失敗、それでも shape 作成は進行
            client.update_frame.assert_called_once()
            assert client.create_shape.called
            # 既存 append が完走している（stopped_stage なし）
            assert result.stopped_stage is None
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_resize_unexpected_exception_propagates(self) -> None:
        """P2-4: update_frame が ExecutionError 以外（= 上位バグ示唆）を
        送出した場合、握りつぶさずに伝播させる。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-resize-unexpected"
        )
        board_items = _build_sized_frame(
            "frame-001",
            cx=100.0, cy=100.0,
            width=200.0, height=200.0,
            occupied_bottom=180.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        client.update_frame.side_effect = ValueError("想定外バグ")
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=True,
            )
            config = _make_config(tmpdir)
            with pytest.raises(ValueError):
                handler.execute(confirmed, context, config)

            client.update_frame.assert_called_once()
            # 例外で中断したため以降の shape 作成は走っていない
            client.create_shape.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_execute_writes_run_log_on_unexpected_exception(self) -> None:
        """resize で想定外例外が発生しても run log は書き出される (observability)。

        ValueError は上位バグの示唆として握りつぶさず raise するが、それでも
        run log は best-effort で tmpdir に書き出されていること。
        """
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-exc-runlog"
        )
        board_items = _build_sized_frame(
            "frame-001",
            cx=100.0, cy=100.0,
            width=200.0, height=200.0,
            occupied_bottom=180.0,
        )
        client = _make_mock_client_for_append(board_items=board_items)
        client.update_frame.side_effect = ValueError("想定外バグ")
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                auto_resize=True,
            )
            config = _make_config(tmpdir)
            with pytest.raises(ValueError):
                handler.execute(confirmed, context, config)

            # run log が書き出されていること
            log_files = [
                name for name in os.listdir(tmpdir)
                if name.startswith("run_") and name.endswith(".json")
            ]
            assert len(log_files) == 1, (
                f"run log が書き出されていない: {log_files}"
            )
            # run log 内容の確認: uncaught exception が stop_reasons に含まれる
            with open(
                os.path.join(tmpdir, log_files[0]), encoding="utf-8"
            ) as f:
                log_data = json.load(f)
            assert any(
                "uncaught exception" in r and "ValueError" in r
                for r in log_data.get("stop_reasons", [])
            ), f"stop_reasons に uncaught exception が無い: {log_data}"
            assert log_data.get("stopped_stage") is not None
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestAppendHandlerAutoFrame: Stage 3 frame 自動作成
# ---------------------------------------------------------------------------


class TestAppendHandlerAutoFrame:
    """Stage 3: append で frame 未指定かつ auto_frame=True の場合に新規 frame を作成する。"""

    def test_auto_frame_creates_new_frame_and_appends(self) -> None:
        """auto_frame=True + frame 未指定 → create_frame が呼ばれ append が走る。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-auto-frame-new"
        )
        # 既存 frame なし
        client = _make_mock_client_for_append(board_items=[])
        client.create_frame.return_value = {
            "id": "new-frame-xyz",
            "type": "frame",
        }
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link=None,
                auto_frame=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            client.create_frame.assert_called_once()
            # 新規 frame id が採用される
            assert result.frame_id == "new-frame-xyz"
            # 後続 shape は新 frame_id を parent に採る
            for call_item in client.create_shape.call_args_list:
                assert call_item.kwargs.get("parent_id") == "new-frame-xyz"
            assert result.success is True, result.stop_reasons
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_frame_required_when_no_frame(self) -> None:
        """auto_frame=False + frame_id/frame_link 未指定 → 従来通り停止（回帰確認）。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-append-no-auto-frame"
        )
        client = _make_mock_client_for_append(board_items=[])
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link=None,
                auto_frame=False,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_frame"
            assert any("frame_id" in r for r in result.stop_reasons)
            client.create_frame.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_frame_placement_right_of_existing(self) -> None:
        """既存 frame が 1 つある場合、新 frame はその右に FRAME_MARGIN 空けて配置される。"""
        from miro_flow_maker.append_handler import FRAME_MARGIN

        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-auto-frame-right"
        )
        # 既存 frame: center (0, 0), w=1000, h=800 → right edge x=500, top=-400
        board_items = [
            {
                "id": "existing-frame",
                "type": "frame",
                "data": {"title": "existing"},
                "position": {"x": 0.0, "y": 0.0},
                "geometry": {"width": 1000.0, "height": 800.0},
            },
        ]
        client = _make_mock_client_for_append(board_items=board_items)
        client.create_frame.return_value = {
            "id": "new-frame-right", "type": "frame",
        }
        handler = AppendHandler(client)

        # plan.frame.width を把握するため dry-run 風に plan を作ってもよいが、
        # 代表ケース固定なので create_frame の呼び出し引数を数値的に検証する。
        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link=None,
                auto_frame=True,
            )
            config = _make_config(tmpdir)
            handler.execute(confirmed, context, config)

            client.create_frame.assert_called_once()
            kwargs = client.create_frame.call_args.kwargs
            plan_w = kwargs["width"]
            plan_h = kwargs["height"]
            # new_left = 500 + FRAME_MARGIN, new_cx = new_left + plan_w/2
            expected_cx = 500.0 + FRAME_MARGIN + plan_w / 2.0
            assert kwargs["x"] == expected_cx
            # 既存 frame の top (= 0 - 800/2 = -400) に新 frame の top を揃える:
            # new_cy = -400 + plan_h/2
            expected_cy = -400.0 + plan_h / 2.0
            assert kwargs["y"] == expected_cy
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_frame_placement_aligns_top(self) -> None:
        """P1-2: 新 frame の top を既存 frame の top 最小値に揃える。"""
        from miro_flow_maker.append_handler import FRAME_MARGIN

        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-auto-frame-aligntop"
        )
        # 既存 frame: center=(0, 100), w=1000, h=400 → top = 100 - 200 = -100
        board_items = [
            {
                "id": "existing-frame-alt",
                "type": "frame",
                "data": {"title": "existing-alt"},
                "position": {"x": 0.0, "y": 100.0},
                "geometry": {"width": 1000.0, "height": 400.0},
            },
        ]
        client = _make_mock_client_for_append(board_items=board_items)
        client.create_frame.return_value = {
            "id": "new-frame-aligned", "type": "frame",
        }
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link=None,
                auto_frame=True,
            )
            config = _make_config(tmpdir)
            handler.execute(confirmed, context, config)

            client.create_frame.assert_called_once()
            kwargs = client.create_frame.call_args.kwargs
            plan_w = kwargs["width"]
            plan_h = kwargs["height"]
            # 既存 right = 0 + 1000/2 = 500
            expected_cx = 500.0 + FRAME_MARGIN + plan_w / 2.0
            assert kwargs["x"] == expected_cx
            # 既存 top = -100 → 新 top = -100 → new_cy = -100 + plan_h/2
            expected_cy = -100.0 + plan_h / 2.0
            assert kwargs["y"] == expected_cy
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_frame_with_explicit_frame_id_prefers_explicit(self) -> None:
        """auto_frame=True でも frame_id が明示されていれば explicit が優先され、create_frame は呼ばれない。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-auto-frame-explicit-wins"
        )
        board_items = _build_frame_with_occupancy(
            "frame-given", occupied_bottom=0.0
        )
        client = _make_mock_client_for_append(board_items=board_items)
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id="frame-given",
                auto_frame=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            client.create_frame.assert_not_called()
            assert result.frame_id == "frame-given"
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_auto_frame_create_returns_no_id_stops(self) -> None:
        """create_frame レスポンスに id が無い場合、resolve_frame で停止する。"""
        confirmed = _replace_flow_group_id(
            _load_confirmed_input(), "flow-auto-frame-no-id"
        )
        client = _make_mock_client_for_append(board_items=[])
        # id 欠損レスポンス
        client.create_frame.return_value = {"type": "frame"}
        handler = AppendHandler(client)

        tmpdir = tempfile.mkdtemp(prefix="miro_app_test_")
        try:
            context = _make_context(
                board_id="board-001",
                frame_id=None,
                frame_link=None,
                auto_frame=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_frame"
            assert result.rerun_eligible is True
            assert any("auto-frame" in r for r in result.stop_reasons)
            client.create_shape.assert_not_called()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Export テスト
# ---------------------------------------------------------------------------


class TestAppendHandlerExport:
    """AppendHandler が __init__.py からインポートできること。"""

    def test_append_handler_exported(self) -> None:
        from miro_flow_maker import AppendHandler as Imported
        assert Imported is AppendHandler
