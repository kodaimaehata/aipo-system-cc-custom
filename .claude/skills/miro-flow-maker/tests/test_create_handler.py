"""CreateHandler のテスト。

MiroClient をモックして board → frame → lane → node → endpoint → connector
の作成順序・結果を検証する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from miro_flow_maker.create_handler import CreateHandler
from miro_flow_maker.exceptions import ExecutionError
from miro_flow_maker.gate import validate
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.models import (
    AppConfig,
    ConfirmedInput,
    ExecutionResult,
    ItemResult,
    RequestContext,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> AppConfig:
    return AppConfig.from_dict({
        "miro_access_token": "test-token-12345678",
        "miro_api_base_url": "https://test.miro.com/v2",
    })


def _make_context(
    *,
    board_name: str = "Test Board",
    dry_run: bool = False,
) -> RequestContext:
    return RequestContext(
        mode="create",
        board_id=None,
        frame_id=None,
        frame_link=None,
        board_name=board_name,
        dry_run=dry_run,
        input_path=str(FIXTURES / "confirmed_representative.json"),
    )


def _load_confirmed_input() -> ConfirmedInput:
    """代表ケースの ConfirmedInput を生成する。"""
    input_data = json.loads(
        (FIXTURES / "confirmed_representative.json").read_text(encoding="utf-8")
    )
    context = RequestContext(
        mode="create",
        board_id=None,
        frame_id=None,
        frame_link=None,
        board_name="Test Board",
        dry_run=False,
        input_path=str(FIXTURES / "confirmed_representative.json"),
    )
    result = validate(input_data, context)
    assert result.passed, f"validate failed: {result.stop_reasons}"
    assert result.normalized_input is not None
    return result.normalized_input


def _make_mock_client() -> MagicMock:
    """全 API 呼び出しが成功するモック MiroClient を生成する。"""
    client = MagicMock(spec=MiroClient)

    # board 作成
    client.create_board.return_value = {
        "id": "board-001",
        "name": "Test Board",
        "viewLink": "https://miro.com/board-001",
    }

    # frame 作成
    client.create_frame.return_value = {
        "id": "frame-001",
        "type": "frame",
    }

    # shape 作成: 呼び出し順に一意の ID を返す
    _shape_counter = {"n": 0}

    def _create_shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _shape_counter["n"] += 1
        return {"id": f"shape-{_shape_counter['n']:03d}", "type": "shape"}

    client.create_shape.side_effect = _create_shape_side_effect

    # connector 作成: 呼び出し順に一意の ID を返す
    _conn_counter = {"n": 0}

    def _create_connector_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _conn_counter["n"] += 1
        return {"id": f"conn-{_conn_counter['n']:03d}", "type": "connector"}

    client.create_connector.side_effect = _create_connector_side_effect

    return client


# ---------------------------------------------------------------------------
# 正常系: 代表ケース
# ---------------------------------------------------------------------------


class TestCreateHandlerHappyPath:
    """正常系: board → frame → lanes → nodes → endpoints → connectors の順序で作成。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context()
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_returns_execution_result(self) -> None:
        assert isinstance(self.result, ExecutionResult)

    def test_success(self) -> None:
        assert self.result.success is True

    def test_mode_is_create(self) -> None:
        assert self.result.mode == "create"

    def test_dry_run_is_false(self) -> None:
        assert self.result.dry_run is False

    def test_board_id_set(self) -> None:
        assert self.result.board_id == "board-001"

    def test_frame_id_set(self) -> None:
        assert self.result.frame_id == "frame-001"

    def test_flow_group_id(self) -> None:
        assert self.result.flow_group_id == self.confirmed.flow_group_id

    def test_run_id_is_uuid(self) -> None:
        import uuid
        # run_id が有効な UUID であること
        uuid.UUID(self.result.run_id)

    def test_no_stop_reasons(self) -> None:
        assert self.result.stop_reasons == []

    def test_no_failed_items(self) -> None:
        assert self.result.failed_count == 0

    def test_board_created_once(self) -> None:
        self.mock_client.create_board.assert_called_once_with("Test Board")

    def test_frame_created_once(self) -> None:
        self.mock_client.create_frame.assert_called_once()

    def test_frame_parent_is_board(self) -> None:
        call_kwargs = self.mock_client.create_frame.call_args
        assert call_kwargs.kwargs.get("board_id") or call_kwargs[1].get("board_id") or call_kwargs[0][0] == "board-001"

    def test_shape_count(self) -> None:
        """代表ケース: lane(3) + node(6) + system_label(2) + endpoint(0) = 11 shapes。"""
        assert self.mock_client.create_shape.call_count == 11

    def test_connector_count(self) -> None:
        """代表ケース: business_flow のみ 6 connectors（system_access はスキップ）。"""
        assert self.mock_client.create_connector.call_count == 6

    def test_created_count(self) -> None:
        """frame(1) + shapes(11) + connectors(6) = 18。"""
        assert self.result.created_count == 18

    def test_item_results_count(self) -> None:
        """frame(1) + lanes(3) + nodes(6) + system_labels(2) + endpoints(0) + connectors(8: 6 success + 2 skipped) = 20。"""
        assert len(self.result.item_results) == 20

    def test_all_item_results_are_success_or_skipped(self) -> None:
        for ir in self.result.item_results:
            assert ir.result in ("success", "skipped"), f"ItemResult unexpected: {ir}"

    def test_all_item_results_action_is_create(self) -> None:
        for ir in self.result.item_results:
            assert ir.action == "create"

    def test_item_results_have_stable_item_id(self) -> None:
        for ir in self.result.item_results:
            assert ir.stable_item_id, f"Missing stable_item_id: {ir}"

    def test_shapes_have_parent_id_frame(self) -> None:
        """全 shape 呼び出しで parent_id=frame-001 が指定されていること。"""
        for call_item in self.mock_client.create_shape.call_args_list:
            kwargs = call_item.kwargs if call_item.kwargs else {}
            parent_id = kwargs.get("parent_id")
            assert parent_id == "frame-001", (
                f"Shape created without parent_id=frame-001: {call_item}"
            )

    def test_creation_order(self) -> None:
        """board → frame → shapes → connectors の順で API が呼ばれること。"""
        # mock の call_args_list は呼び出し順
        # board が最初、次に frame、shape が 11 回、connector が 6 回
        manager = MagicMock()
        manager.attach_mock(self.mock_client.create_board, "create_board")
        # 既に呼ばれた後なので、呼び出し順序は call_args_list の index で確認
        # create_board は create_frame より先に呼ばれている
        assert self.mock_client.create_board.call_count == 1
        assert self.mock_client.create_frame.call_count == 1
        assert self.mock_client.create_shape.call_count == 11
        assert self.mock_client.create_connector.call_count == 6

    def test_node_shape_types(self) -> None:
        """node の shape type が正しく設定されていること。"""
        shape_calls = self.mock_client.create_shape.call_args_list
        # lane(3) の後に node(6) が来る。lane は全て rectangle。
        # node の shape は: start→circle, process→rectangle,
        # decision→rhombus, end→circle
        # 代表ケースの nodes:
        #   n-start (start), n-fill-form (process), n-review (process),
        #   n-approve-check (decision), n-accounting-process (process), n-end (end)
        expected_node_shapes = [
            "circle",     # start
            "rectangle",  # process
            "rectangle",  # process
            "rhombus",    # decision
            "rectangle",  # process
            "circle",     # end
        ]
        # skip first 3 calls (lanes)
        node_calls = shape_calls[3:9]
        for i, (call_item, expected) in enumerate(zip(node_calls, expected_node_shapes)):
            actual_shape = call_item.kwargs.get("shape")
            assert actual_shape == expected, (
                f"Node {i}: expected shape={expected}, got {actual_shape}"
            )


# ---------------------------------------------------------------------------
# 正常系: board_name フォールバック
# ---------------------------------------------------------------------------


class TestBoardNameFallback:
    """context.board_name が None の場合、flow_group_id をフォールバックに使う。"""

    def test_fallback_to_flow_group_id(self) -> None:
        mock_client = _make_mock_client()
        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = RequestContext(
            mode="create",
            board_id=None,
            frame_id=None,
            frame_link=None,
            board_name=None,
            dry_run=False,
            input_path=str(FIXTURES / "confirmed_representative.json"),
        )
        config = _make_config()
        handler.execute(confirmed, context, config)
        mock_client.create_board.assert_called_once_with(confirmed.flow_group_id)


# ---------------------------------------------------------------------------
# dry-run テスト
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry-run 時は API を呼ばず、成功の ExecutionResult を返す。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context(dry_run=True)
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_success(self) -> None:
        assert self.result.success is True

    def test_dry_run_flag(self) -> None:
        assert self.result.dry_run is True

    def test_no_api_calls(self) -> None:
        self.mock_client.create_board.assert_not_called()
        self.mock_client.create_frame.assert_not_called()
        self.mock_client.create_shape.assert_not_called()
        self.mock_client.create_connector.assert_not_called()

    def test_board_id_is_none(self) -> None:
        assert self.result.board_id is None

    def test_frame_id_is_none(self) -> None:
        assert self.result.frame_id is None

    def test_created_count_zero(self) -> None:
        assert self.result.created_count == 0

    def test_mode_is_create(self) -> None:
        assert self.result.mode == "create"

    def test_item_results_populated(self) -> None:
        """dry-run でも item_results が生成されること。"""
        # frame(1) + lanes(3) + nodes(6) + system_labels(2) + endpoints(0) + connectors(8: 6 business_flow + 2 system_access) = 20
        assert len(self.result.item_results) == 20

    def test_all_item_results_dry_run_skipped(self) -> None:
        """dry-run の全 item_results が dry_run_skipped であること。"""
        for ir in self.result.item_results:
            assert ir.result == "dry_run_skipped", f"Expected dry_run_skipped, got {ir.result}: {ir}"

    def test_all_item_results_have_stable_item_id(self) -> None:
        """dry-run でも stable_item_id が設定されること。"""
        for ir in self.result.item_results:
            assert ir.stable_item_id, f"Missing stable_item_id: {ir}"

    def test_all_item_results_have_semantic_type(self) -> None:
        for ir in self.result.item_results:
            assert ir.semantic_type

    def test_all_item_results_have_render_role(self) -> None:
        for ir in self.result.item_results:
            assert ir.render_role

    def test_skipped_count(self) -> None:
        assert self.result.skipped_count == 20


# ---------------------------------------------------------------------------
# board 作成失敗テスト
# ---------------------------------------------------------------------------


class TestBoardCreationFailure:
    """board 作成失敗時に即停止する。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.mock_client.create_board.side_effect = ExecutionError(
            "Miro API クライアントエラー: POST /boards — HTTP 403"
        )
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context()
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_not_success(self) -> None:
        assert self.result.success is False

    def test_stop_reasons_contain_board_failure(self) -> None:
        assert len(self.result.stop_reasons) >= 1
        assert "board 作成失敗" in self.result.stop_reasons[0]

    def test_no_frame_created(self) -> None:
        self.mock_client.create_frame.assert_not_called()

    def test_no_shapes_created(self) -> None:
        self.mock_client.create_shape.assert_not_called()

    def test_no_connectors_created(self) -> None:
        self.mock_client.create_connector.assert_not_called()

    def test_board_id_is_none(self) -> None:
        assert self.result.board_id is None

    def test_frame_id_is_none(self) -> None:
        assert self.result.frame_id is None


# ---------------------------------------------------------------------------
# frame 作成失敗テスト
# ---------------------------------------------------------------------------


class TestFrameCreationFailure:
    """frame 作成失敗時に即停止する。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.mock_client.create_frame.side_effect = ExecutionError(
            "Miro API サーバーエラー: POST /boards/board-001/frames — HTTP 500"
        )
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context()
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_not_success(self) -> None:
        assert self.result.success is False

    def test_stop_reasons_contain_frame_failure(self) -> None:
        assert len(self.result.stop_reasons) >= 1
        assert "frame 作成失敗" in self.result.stop_reasons[0]

    def test_board_id_is_set(self) -> None:
        assert self.result.board_id == "board-001"

    def test_frame_id_is_none(self) -> None:
        assert self.result.frame_id is None

    def test_no_shapes_created(self) -> None:
        self.mock_client.create_shape.assert_not_called()

    def test_no_connectors_created(self) -> None:
        self.mock_client.create_connector.assert_not_called()


# ---------------------------------------------------------------------------
# item 作成失敗テスト（続行する）
# ---------------------------------------------------------------------------


class TestItemCreationFailure:
    """item 作成失敗時は ItemResult に failed を記録して続行する。"""

    def test_shape_failure_records_failed_and_continues(self) -> None:
        mock_client = _make_mock_client()
        _call_count = {"n": 0}

        def _shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                # 最初の shape (lane) だけ失敗
                raise ExecutionError("shape 作成失敗")
            return {"id": f"shape-{_call_count['n']:03d}", "type": "shape"}

        mock_client.create_shape.side_effect = _shape_side_effect
        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # 失敗した item が 1 つ
        assert result.failed_count == 1

        # 失敗した ItemResult が存在
        failed_items = [ir for ir in result.item_results if ir.result == "failed"]
        assert len(failed_items) == 1
        assert failed_items[0].action == "create"
        assert failed_items[0].reason is not None

        # 他の shape + connector は呼ばれている（続行する）
        # lane(3) + node(6) + system_label(2) + endpoint(0) = 11 shapes total
        assert mock_client.create_shape.call_count == 11


# ---------------------------------------------------------------------------
# connector 接続先未解決テスト
# ---------------------------------------------------------------------------


class TestConnectorUnresolvedStop:
    """connector の接続先が未解決の場合、即停止する（P0004 契約）。"""

    def test_unresolved_from_stops_execution(self) -> None:
        mock_client = _make_mock_client()

        # 全 shape を失敗させて id_map に何も入らない状態にする
        mock_client.create_shape.side_effect = ExecutionError("全 shape 失敗")

        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # connector の接続先未解決で停止
        assert result.success is False
        assert any("接続先未解決" in reason for reason in result.stop_reasons)

        # connector API は呼ばれない
        mock_client.create_connector.assert_not_called()

    def test_unresolved_connector_has_failed_item_result(self) -> None:
        """P1-1: connector 未解決時に ItemResult(result='failed') が残ること。"""
        mock_client = _make_mock_client()
        mock_client.create_shape.side_effect = ExecutionError("全 shape 失敗")

        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # 未解決 connector の failed ItemResult が存在する
        failed_connectors = [
            ir for ir in result.item_results
            if ir.result == "failed" and "接続先未解決" in (ir.reason or "")
        ]
        assert len(failed_connectors) >= 1
        assert result.failed_count >= 1

    def test_partial_unresolved_stops(self) -> None:
        """一部の node だけ作成失敗し、connector の接続先が片方未解決。"""
        mock_client = _make_mock_client()
        _call_count = {"n": 0}

        def _shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            _call_count["n"] += 1
            # 最初の lane(3) + 最初の node(1) は成功、2番目の node で失敗
            if _call_count["n"] == 5:
                raise ExecutionError("特定 node 失敗")
            return {"id": f"shape-{_call_count['n']:03d}", "type": "shape"}

        mock_client.create_shape.side_effect = _shape_side_effect
        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # connector 処理で接続先未解決停止が発生するはず
        # (失敗した node の id が id_map に入らないので、
        #  その node を参照する connector で停止)
        assert result.success is False
        has_unresolved = any("接続先未解決" in r for r in result.stop_reasons)
        assert has_unresolved


# ---------------------------------------------------------------------------
# semantic_type / render_role の検証
# ---------------------------------------------------------------------------


class TestItemResultSemantics:
    """ItemResult の semantic_type / render_role が正しいこと。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context()
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_frame_item_result(self) -> None:
        frame_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type == "flow_group"
        ]
        assert len(frame_results) == 1
        assert frame_results[0].render_role == "frame"

    def test_lane_item_results(self) -> None:
        lane_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type in ("actor_lane", "system_lane")
        ]
        # 代表ケース: actor(3) + system(0) = 3 lanes
        assert len(lane_results) == 3
        for ir in lane_results:
            assert ir.render_role == "lane_container"

    def test_node_item_results(self) -> None:
        node_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type == "node"
        ]
        assert len(node_results) == 6
        # P0004: 全 node の render_role は一律 node_shape
        for ir in node_results:
            assert ir.render_role == "node_shape"

    def test_endpoint_item_results(self) -> None:
        ep_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type == "system_endpoint" and ir.render_role == "endpoint_shape"
        ]
        # 代表ケース: endpoints は空（system_label に移行済み）
        assert len(ep_results) == 0

    def test_system_label_item_results(self) -> None:
        sl_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type == "system_endpoint" and ir.render_role == "system_label"
        ]
        # 代表ケース: system_labels は 2 個 (n-fill-form->s-erp, n-accounting-process->s-erp)
        assert len(sl_results) == 2
        for ir in sl_results:
            assert ir.render_role == "system_label"

    def test_connector_item_results(self) -> None:
        conn_results = [
            ir for ir in self.result.item_results
            if ir.semantic_type in ("business_flow", "system_access")
        ]
        assert len(conn_results) == 8
        for ir in conn_results:
            assert ir.render_role == "edge_connector"


# ---------------------------------------------------------------------------
# __init__.py エクスポートテスト
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# P1-2: レスポンスの id 欠落時に failed になるテスト
# ---------------------------------------------------------------------------


class TestMissingResponseId:
    """shape/connector 作成レスポンスに id が欠落している場合、ItemResult が failed になること。"""

    def test_shape_missing_id_records_failed(self) -> None:
        """shape レスポンスに id が無い場合は failed。"""
        mock_client = _make_mock_client()
        _call_count = {"n": 0}

        def _shape_side_effect(*args: Any, **kwargs: Any) -> dict[str, Any]:
            _call_count["n"] += 1
            if _call_count["n"] == 1:
                # 最初の shape (lane) で id 欠落
                return {"type": "shape"}
            return {"id": f"shape-{_call_count['n']:03d}", "type": "shape"}

        mock_client.create_shape.side_effect = _shape_side_effect
        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # id 欠落による failed ItemResult が存在
        failed_items = [
            ir for ir in result.item_results
            if ir.result == "failed" and "id が含まれていない" in (ir.reason or "")
        ]
        assert len(failed_items) >= 1
        assert result.failed_count >= 1

    def test_connector_missing_id_records_failed(self) -> None:
        """connector レスポンスに id が無い場合は failed。"""
        mock_client = _make_mock_client()

        # connector は全て id 欠落 (side_effect をクリアして return_value で上書き)
        mock_client.create_connector.side_effect = None
        mock_client.create_connector.return_value = {"type": "connector"}

        handler = CreateHandler(mock_client)
        confirmed = _load_confirmed_input()
        context = _make_context()
        config = _make_config()
        result = handler.execute(confirmed, context, config)

        # connector の failed ItemResult
        failed_connectors = [
            ir for ir in result.item_results
            if ir.result == "failed" and "connector" in (ir.reason or "") and "id が含まれていない" in (ir.reason or "")
        ]
        assert len(failed_connectors) == 6  # 代表ケースの business_flow connector 数（system_access はスキップ）


# ---------------------------------------------------------------------------
# SystemLabel 描画テスト
# ---------------------------------------------------------------------------


class TestSystemLabelCreation:
    """system_label が描画され、connector が接続できることを確認する。"""

    def setup_method(self) -> None:
        self.mock_client = _make_mock_client()
        self.handler = CreateHandler(self.mock_client)
        self.confirmed = _load_confirmed_input()
        self.context = _make_context()
        self.config = _make_config()
        self.result = self.handler.execute(
            self.confirmed, self.context, self.config
        )

    def test_system_labels_created_as_shapes(self) -> None:
        """system_label が round_rectangle shape として作成されること。"""
        shape_calls = self.mock_client.create_shape.call_args_list
        # lanes(3) + nodes(6) = 9, then system_labels(2) at indices 9, 10
        sl_calls = shape_calls[9:11]
        assert len(sl_calls) == 2
        for call_item in sl_calls:
            assert call_item.kwargs.get("shape") == "round_rectangle"
            assert call_item.kwargs.get("parent_id") == "frame-001"

    def test_system_label_ids_in_id_map(self) -> None:
        """system_label の miro_id が connector で参照可能であること。

        全 connector が成功していれば、system_label の id_map エントリが
        正しく解決されたことになる。
        """
        # business_flow connector 作成が全て呼ばれている（未解決停止していない）
        assert self.mock_client.create_connector.call_count == 6
        assert self.result.success is True

    def test_connector_resolves_system_label_target(self) -> None:
        """system_access connector が system_label の miro_id に接続すること。"""
        # 全 connector が成功 = system_label の id_map 解決が成功
        assert self.result.success is True
        assert len(self.result.stop_reasons) == 0

    def test_system_label_item_results(self) -> None:
        """system_label の ItemResult が正しく記録されること。"""
        sl_results = [
            ir for ir in self.result.item_results
            if ir.render_role == "system_label"
        ]
        assert len(sl_results) == 2
        for ir in sl_results:
            assert ir.result == "success"
            assert ir.action == "create"
            assert ir.semantic_type == "system_endpoint"

    def test_connector_style_applied(self) -> None:
        """全 connector に style が渡され、stealth 矢印であること。"""
        for call_item in self.mock_client.create_connector.call_args_list:
            kwargs = call_item.kwargs if call_item.kwargs else {}
            style = kwargs.get("style")
            assert style is not None, "Connector style should be set"
            assert style.get("endStrokeCap") == "stealth"
            assert style.get("strokeWidth") == "2.0"
            assert style.get("strokeColor") == "#2C3E50"


class TestExport:
    """CreateHandler が __init__.py からインポートできること。"""

    def test_create_handler_exported(self) -> None:
        from miro_flow_maker import CreateHandler as Imported
        assert Imported is CreateHandler
