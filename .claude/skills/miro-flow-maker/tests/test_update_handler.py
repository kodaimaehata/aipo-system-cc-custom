"""UpdateHandler のテスト。

MiroClient をモックし、ModeHandler Protocol 実装として
update / create / skip / stop / orphaned の各ケースを検証する。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from miro_flow_maker.create_handler import CreateHandler
from miro_flow_maker.exceptions import ExecutionError
from miro_flow_maker.gate import build_stable_item_id, validate
from miro_flow_maker.layout import build_drawing_plan
from miro_flow_maker.metadata_helper import build_plan_metadata_map
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.models import (
    AppConfig,
    ConfirmedInput,
    ExecutionResult,
    ItemResult,
    RequestContext,
)
from miro_flow_maker._frame_helpers import extract_frame_id_from_link
from miro_flow_maker.run_log import (
    RunLog,
    build_run_log,
    find_latest_run_log,
    write_run_log,
)
from miro_flow_maker.update_handler import UpdateHandler

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
) -> RequestContext:
    return RequestContext(
        mode="update",
        board_id=board_id,
        frame_id=frame_id,
        frame_link=frame_link,
        board_name=None,
        dry_run=dry_run,
        input_path=str(FIXTURES / "confirmed_representative.json"),
    )


def _load_confirmed_input() -> ConfirmedInput:
    input_data = json.loads(
        (FIXTURES / "confirmed_representative.json").read_text(encoding="utf-8")
    )
    context = RequestContext(
        mode="update",
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


def _assign_miro_ids(
    confirmed: ConfirmedInput,
) -> tuple[dict[str, str], dict[str, str]]:
    """confirmed_representative から (plan_id -> miro_id, stable_id -> miro_id) を生成する。

    決定的な ID 割当を行い、テストで再利用する。
    """
    plan = build_drawing_plan(confirmed, board_name="")
    metadata_map = build_plan_metadata_map(confirmed, plan)

    plan_to_miro: dict[str, str] = {}
    stable_to_miro: dict[str, str] = {}

    counter = {"n": 0}

    def _next(prefix: str) -> str:
        counter["n"] += 1
        return f"{prefix}-{counter['n']:03d}"

    plan_to_miro["frame"] = "frame-001"
    stable_to_miro[metadata_map["frame"]["stable_item_id"]] = "frame-001"

    for lane in plan.lanes:
        miro_id = _next("lane")
        plan_to_miro[lane.id] = miro_id
        stable_to_miro[metadata_map[lane.id]["stable_item_id"]] = miro_id
    for node in plan.nodes:
        miro_id = _next("node")
        plan_to_miro[node.id] = miro_id
        stable_to_miro[metadata_map[node.id]["stable_item_id"]] = miro_id
    for sl in plan.system_labels:
        miro_id = _next("sl")
        plan_to_miro[sl.id] = miro_id
        stable_to_miro[metadata_map[sl.id]["stable_item_id"]] = miro_id
    for ep in plan.endpoints:
        miro_id = _next("ep")
        plan_to_miro[ep.id] = miro_id
        stable_to_miro[metadata_map[ep.id]["stable_item_id"]] = miro_id
    for conn in plan.connectors:
        miro_id = _next("conn")
        plan_to_miro[conn.id] = miro_id
        stable_to_miro[metadata_map[conn.id]["stable_item_id"]] = miro_id

    return plan_to_miro, stable_to_miro


def _build_board_state(
    confirmed: ConfirmedInput,
    plan_to_miro: dict[str, str],
    *,
    exclude_plan_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """ConfirmedInput と plan_to_miro から board 状態（board_items / board_connectors）を構築する。"""
    plan = build_drawing_plan(confirmed, board_name="")
    exclude_plan_ids = exclude_plan_ids or set()
    frame_miro_id = plan_to_miro["frame"]

    board_items: list[dict[str, Any]] = [
        {"id": frame_miro_id, "type": "frame", "data": {"title": plan.frame.title}},
    ]

    def _shape(plan_id: str, label: str) -> None:
        if plan_id in exclude_plan_ids:
            return
        miro_id = plan_to_miro[plan_id]
        board_items.append({
            "id": miro_id,
            "type": "shape",
            "data": {"content": label},
            "parent": {"id": frame_miro_id},
        })

    for lane in plan.lanes:
        _shape(lane.id, lane.label)
    for node in plan.nodes:
        _shape(node.id, node.label)
    for sl in plan.system_labels:
        _shape(sl.id, sl.label)
    for ep in plan.endpoints:
        _shape(ep.id, ep.label)

    board_connectors: list[dict[str, Any]] = []
    for conn in plan.connectors:
        if conn.id in exclude_plan_ids:
            continue
        board_connectors.append({
            "id": plan_to_miro[conn.id],
            "type": "connector",
            "data": {},
        })

    return board_items, board_connectors


def _build_prev_run_log(
    confirmed: ConfirmedInput,
    plan_to_miro: dict[str, str],
    *,
    exclude_plan_ids: set[str] | None = None,
    override_update_mode: dict[str, str] | None = None,
) -> dict[str, Any]:
    """前回 run log の dict 表現を生成する（write_run_log で書き出す形式）。"""
    plan = build_drawing_plan(confirmed, board_name="")
    metadata_map = build_plan_metadata_map(confirmed, plan)
    exclude_plan_ids = exclude_plan_ids or set()
    override_update_mode = override_update_mode or {}

    items: list[dict[str, Any]] = []
    for plan_id, meta in metadata_map.items():
        if plan_id in exclude_plan_ids:
            continue
        miro_id = plan_to_miro.get(plan_id)
        item: dict[str, Any] = {
            "stable_item_id": meta["stable_item_id"],
            "semantic_type": meta["semantic_type"],
            "semantic_id": meta["semantic_id"],
            "render_role": meta["render_role"],
            "action": "create",
            "result": "success",
            "managed_by": meta["managed_by"],
            "project_id": meta["project_id"],
            "layer_id": meta["layer_id"],
            "document_set_id": meta["document_set_id"],
            "flow_group_id": meta["flow_group_id"],
            "confirmation_packet_ref": meta["confirmation_packet_ref"],
            "update_mode": override_update_mode.get(plan_id, meta["update_mode"]),
        }
        if miro_id is not None:
            item["miro_item_id"] = miro_id
        items.append(item)

    return {
        "run_id": "prev-run",
        "timestamp": "2026-04-16T00:00:00+00:00",
        "mode": "create",
        "board_id": "board-001",
        "frame_id": plan_to_miro["frame"],
        "flow_group_id": confirmed.flow_group_id,
        "dry_run": False,
        "created_count": len(items),
        "updated_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "stop_reasons": [],
        "duration_ms": 1000,
        "errors": [],
        "item_results": items,
        "partial_success": False,
        "stopped_stage": None,
        "rerun_eligible": True,
    }


def _write_prev_run_log_json(
    log_dir: str,
    run_log_dict: dict[str, Any],
) -> str:
    """run log dict を log_dir に書き出し、絶対パスを返す。"""
    os.makedirs(log_dir, exist_ok=True)
    safe_ts = run_log_dict["timestamp"].replace(":", "").replace("+", "p")
    filename = f"run_{run_log_dict['run_id']}_{safe_ts}.json"
    path = os.path.join(log_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run_log_dict, f, ensure_ascii=False, indent=2)
    return path


def _make_mock_client_for_update(
    *,
    board_items: list[dict[str, Any]],
    board_connectors: list[dict[str, Any]],
) -> MagicMock:
    client = MagicMock(spec=MiroClient)
    client.get_board.return_value = {"id": "board-001"}
    client.get_items_on_board.return_value = board_items
    client.get_connectors_on_board.return_value = board_connectors
    client.update_shape.return_value = {"id": "updated"}
    client.update_connector.return_value = {"id": "updated-conn"}

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


# ---------------------------------------------------------------------------
# TestUpdateHandlerExecute: 全 item が update
# ---------------------------------------------------------------------------


class TestUpdateHandlerExecute:
    """全 item が 1:1 で一致し update されるケース。"""

    def setup_method(self) -> None:
        self.confirmed = _load_confirmed_input()
        self.plan_to_miro, _ = _assign_miro_ids(self.confirmed)
        self.board_items, self.board_connectors = _build_board_state(
            self.confirmed, self.plan_to_miro
        )
        self.tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        prev_dict = _build_prev_run_log(self.confirmed, self.plan_to_miro)
        _write_prev_run_log_json(self.tmpdir, prev_dict)
        self.client = _make_mock_client_for_update(
            board_items=self.board_items,
            board_connectors=self.board_connectors,
        )
        self.handler = UpdateHandler(self.client)
        self.context = _make_context(
            board_id="board-001",
            frame_id=self.plan_to_miro["frame"],
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

    def test_mode(self) -> None:
        assert self.result.mode == "update"

    def test_no_creates(self) -> None:
        self.client.create_shape.assert_not_called()
        self.client.create_connector.assert_not_called()

    def test_updated_count_positive(self) -> None:
        # lane(3) + node(6) + system_label(2) + connector(6) = 17 updates
        assert self.result.updated_count == 17

    def test_stopped_stage_none(self) -> None:
        assert self.result.stopped_stage is None

    def test_board_id_preserved(self) -> None:
        assert self.result.board_id == "board-001"

    def test_frame_id_preserved(self) -> None:
        assert self.result.frame_id == self.plan_to_miro["frame"]

    def test_rerun_eligible(self) -> None:
        assert self.result.rerun_eligible is True


# ---------------------------------------------------------------------------
# TestUpdateHandlerCreateMissing: 前回 log に無い item は create
# ---------------------------------------------------------------------------


class TestUpdateHandlerCreateMissing:
    """前回 run log に含まれない item は create 扱いとなる。"""

    def test_missing_item_creates(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        # n-end を run log から除外 → create 扱い
        missing = {"n-end"}
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro, exclude_plan_ids=missing
        )

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(
                confirmed, plan_to_miro, exclude_plan_ids=missing
            )
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001",
                frame_id=plan_to_miro["frame"],
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is True, result.stop_reasons
            # create 系 API が最低 1 回呼ばれている (node 1 件 + その先の connector も create 扱い可)
            assert client.create_shape.call_count >= 1
            # updated_count > 0 かつ created_count > 0
            assert result.updated_count > 0
            assert result.created_count >= 1
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerSkipManualDetached
# ---------------------------------------------------------------------------


class TestUpdateHandlerSkipManualDetached:
    """update_mode=manual_detached の item は skipped_manual_detached で保護される。"""

    def test_manual_detached_skipped(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro
        )

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(
                confirmed,
                plan_to_miro,
                override_update_mode={"n-review": "manual_detached"},
            )
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=plan_to_miro["frame"]
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # skipped_manual_detached を持つ ItemResult が少なくとも 1 つ
            detached = [
                ir for ir in result.item_results
                if ir.result == "skipped_manual_detached"
            ]
            assert len(detached) >= 1
            # 対象の node の update_shape が呼ばれていないこと
            for call in client.update_shape.call_args_list:
                args = call.args
                if len(args) >= 2 and args[1] == plan_to_miro["n-review"]:
                    raise AssertionError("manual_detached 対象が更新されている")
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerStopOnDuplicate
# ---------------------------------------------------------------------------


class TestUpdateHandlerStopOnDuplicate:
    """run log に stable_item_id の重複がある場合 reconcile で停止する。"""

    def test_duplicate_stops(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro
        )

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            # n-start の item を複製して重複を作る
            start_items = [
                it for it in prev_dict["item_results"]
                if it["semantic_id"] == "n-start"
            ]
            assert start_items, "n-start entry missing"
            dup = dict(start_items[0])
            dup["miro_item_id"] = "miro-node-start-dup"
            prev_dict["item_results"].append(dup)
            _write_prev_run_log_json(tmpdir, prev_dict)

            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=plan_to_miro["frame"]
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "reconcile"
            assert result.rerun_eligible is False
            assert any("stable_item_id 重複" in r for r in result.stop_reasons)
            # update / create が行われていない
            client.update_shape.assert_not_called()
            client.create_shape.assert_not_called()
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerResolveBoardFailure
# ---------------------------------------------------------------------------


class TestUpdateHandlerResolveBoardFailure:
    """get_board 失敗時は stopped_stage=resolve_board で停止し再実行可能。"""

    def test_resolve_board_failure(self) -> None:
        confirmed = _load_confirmed_input()
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            client = MagicMock(spec=MiroClient)
            client.get_board.side_effect = ExecutionError(
                "Miro API クライアントエラー: GET /boards/board-001 — HTTP 404"
            )
            handler = UpdateHandler(client)
            context = _make_context(board_id="board-001", frame_id="frame-001")
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_board"
            assert result.rerun_eligible is True
            assert any("board 取得失敗" in r for r in result.stop_reasons)
            client.get_items_on_board.assert_not_called()
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerResolveFrameFailure
# ---------------------------------------------------------------------------


class TestUpdateHandlerResolveFrameFailure:
    """board 上に frame_id が存在しない場合、stopped_stage=resolve_frame。"""

    def test_frame_not_on_board(self) -> None:
        confirmed = _load_confirmed_input()
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            client = MagicMock(spec=MiroClient)
            client.get_board.return_value = {"id": "board-001"}
            client.get_items_on_board.return_value = [
                {"id": "other-frame", "type": "frame"},
            ]
            client.get_connectors_on_board.return_value = []
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id="missing-frame"
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "resolve_frame"
            assert result.rerun_eligible is True
            assert any("frame_id" in r and "存在しない" in r for r in result.stop_reasons)
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerConnectorUnresolved
# ---------------------------------------------------------------------------


class TestUpdateHandlerConnectorUnresolved:
    """connector の接続先が未解決の場合、stopped_stage=upsert_connectors で停止し partial_success。"""

    def test_unresolved_stops_with_partial_success(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro
        )

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            _write_prev_run_log_json(tmpdir, prev_dict)

            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            # update_shape を全失敗させる → shape の id_map が埋まらない →
            # connector で接続先未解決
            client.update_shape.side_effect = ExecutionError("update shape failed")

            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=plan_to_miro["frame"]
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is False
            assert result.stopped_stage == "upsert_connectors"
            assert result.rerun_eligible is True
            assert any("接続先未解決" in r for r in result.stop_reasons)
            # shape の更新が試行された（failed として記録されている）
            assert result.failed_count > 0
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerDryRun
# ---------------------------------------------------------------------------


class TestUpdateHandlerDryRun:
    """dry-run 時は API を呼ばず run log のみ書き出す。"""

    def test_dry_run_no_api_calls(self) -> None:
        confirmed = _load_confirmed_input()
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            client = MagicMock(spec=MiroClient)
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001",
                frame_id="frame-001",
                dry_run=True,
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            assert result.success is True
            assert result.dry_run is True
            assert result.mode == "update"
            client.get_board.assert_not_called()
            client.get_items_on_board.assert_not_called()
            client.update_shape.assert_not_called()
            client.create_shape.assert_not_called()
            # item_results が dry_run_skipped で埋まっている
            assert len(result.item_results) > 0
            assert all(ir.result == "dry_run_skipped" for ir in result.item_results)
            # run log ファイルが書き出されている
            files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]
            assert len(files) == 1
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerOrphanedRecorded
# ---------------------------------------------------------------------------


class TestUpdateHandlerOrphanedRecorded:
    """DrawingPlan にない managed item が orphaned として ItemResult に記録される。"""

    def test_orphaned_recorded(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro
        )
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            # DrawingPlan に無い orphan を 1 件追加
            orphan = {
                "stable_item_id": build_stable_item_id(
                    flow_group_id=confirmed.flow_group_id,
                    semantic_type="node",
                    semantic_id="n-deleted",
                    render_role="node_shape",
                ),
                "semantic_type": "node",
                "semantic_id": "n-deleted",
                "render_role": "node_shape",
                "action": "create",
                "result": "success",
                "managed_by": "miro-flow-maker",
                "project_id": "P0006",
                "layer_id": "P0006-SG2",
                "document_set_id": confirmed.metadata.document_set_id,
                "flow_group_id": confirmed.flow_group_id,
                "confirmation_packet_ref": confirmed.confirmation_packet_ref,
                "update_mode": "managed",
                "miro_item_id": "miro-node-deleted",
            }
            prev_dict["item_results"].append(orphan)
            _write_prev_run_log_json(tmpdir, prev_dict)

            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=plan_to_miro["frame"]
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            orphaned_irs = [
                ir for ir in result.item_results if ir.action == "orphaned"
            ]
            assert len(orphaned_irs) == 1
            assert orphaned_irs[0].miro_item_id == "miro-node-deleted"
            assert orphaned_irs[0].result == "skipped_orphaned"
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerFrameLinkParsing
# ---------------------------------------------------------------------------


class TestUpdateHandlerFrameLinkParsing:
    """frame_id が無く frame_link から抽出するケース。"""

    def test_extract_from_move_to_widget(self) -> None:
        fid = extract_frame_id_from_link(
            "https://miro.com/app/board/abc/?moveToWidget=frame-xyz"
        )
        assert fid == "frame-xyz"

    def test_extract_from_fragment(self) -> None:
        fid = extract_frame_id_from_link(
            "https://miro.com/app/board/abc#/frames/frame-xyz"
        )
        assert fid == "frame-xyz"

    def test_unparsable_returns_none(self) -> None:
        assert extract_frame_id_from_link("not-a-url") is None


# ---------------------------------------------------------------------------
# TestUpdateHandlerFindLatestRunLog
# ---------------------------------------------------------------------------


class TestUpdateHandlerFindLatestRunLog:
    """find_latest_run_log: 最新の一致する run log を返す。"""

    def test_filters_by_board_and_frame(self) -> None:
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            # 3 件書き出す（1 件だけ一致）
            _write_prev_run_log_json(tmpdir, {
                "run_id": "r1",
                "timestamp": "2026-04-10T00:00:00+00:00",
                "mode": "create",
                "board_id": "other-board",
                "frame_id": "f1",
                "flow_group_id": "flow-rep-01",
                "dry_run": False,
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "stop_reasons": [],
                "duration_ms": 0,
                "errors": [],
                "item_results": [],
            })
            _write_prev_run_log_json(tmpdir, {
                "run_id": "r2",
                "timestamp": "2026-04-11T00:00:00+00:00",
                "mode": "create",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": "flow-rep-01",
                "dry_run": False,
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "stop_reasons": [],
                "duration_ms": 0,
                "errors": [],
                "item_results": [],
            })
            _write_prev_run_log_json(tmpdir, {
                "run_id": "r3",
                "timestamp": "2026-04-12T00:00:00+00:00",
                "mode": "update",
                "board_id": "board-001",
                "frame_id": "frame-001",
                "flow_group_id": "flow-rep-01",
                "dry_run": False,
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "stop_reasons": [],
                "duration_ms": 0,
                "errors": [],
                "item_results": [],
            })

            found = find_latest_run_log(
                tmpdir, "board-001", "frame-001", "flow-rep-01"
            )
            assert found is not None
            assert found.run_id == "r3"
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_no_match_returns_none(self) -> None:
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            found = find_latest_run_log(
                tmpdir, "board-001", "frame-001", "flow-rep-01"
            )
            assert found is None
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerSkipGranularity: P1-C
# ---------------------------------------------------------------------------


class TestUpdateHandlerSkipGranularity:
    """P1-C: skip 理由の粒度を分類した ItemResult.result が記録される。"""

    def test_frame_outside_skip_granularity(self) -> None:
        """frame 外 item（board 上で別 frame の子）は skipped_frame_outside で記録。"""
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)

        # n-review の item を「別 frame の子」として board に配置
        frame_miro_id = plan_to_miro["frame"]
        plan = build_drawing_plan(confirmed, board_name="")

        board_items: list[dict[str, Any]] = [
            {"id": frame_miro_id, "type": "frame",
             "data": {"title": plan.frame.title}},
            # 他 frame
            {"id": "other-frame", "type": "frame",
             "data": {"title": "other"}},
        ]
        for lane in plan.lanes:
            board_items.append({
                "id": plan_to_miro[lane.id],
                "type": "shape",
                "data": {"content": lane.label},
                "parent": {"id": frame_miro_id},
            })
        for node in plan.nodes:
            parent_id = (
                "other-frame" if node.id == "n-review" else frame_miro_id
            )
            board_items.append({
                "id": plan_to_miro[node.id],
                "type": "shape",
                "data": {"content": node.label},
                "parent": {"id": parent_id},
            })
        for sl in plan.system_labels:
            board_items.append({
                "id": plan_to_miro[sl.id],
                "type": "shape",
                "data": {"content": sl.label},
                "parent": {"id": frame_miro_id},
            })
        board_connectors = [
            {"id": plan_to_miro[conn.id], "type": "connector", "data": {}}
            for conn in plan.connectors
        ]

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=frame_miro_id
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # n-review の ItemResult は skipped_frame_outside
            review_irs = [
                ir for ir in result.item_results
                if ir.semantic_id == "n-review"
            ]
            assert len(review_irs) >= 1
            assert any(
                ir.result == "skipped_frame_outside" for ir in review_irs
            )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerFrameOutsideIdMapIsolation: P0-C
# ---------------------------------------------------------------------------


class TestUpdateHandlerFrameOutsideIdMapIsolation:
    """P0-C: frame 外で skip された shape の miro_item_id は id_map に流入せず、
    その shape に接続する connector も skipped_connector_dependency で skip される。"""

    def test_frame_outside_connector_not_updated(self) -> None:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        frame_miro_id = plan_to_miro["frame"]
        plan = build_drawing_plan(confirmed, board_name="")

        board_items: list[dict[str, Any]] = [
            {"id": frame_miro_id, "type": "frame",
             "data": {"title": plan.frame.title}},
            {"id": "other-frame", "type": "frame",
             "data": {"title": "other"}},
        ]
        for lane in plan.lanes:
            board_items.append({
                "id": plan_to_miro[lane.id],
                "type": "shape",
                "data": {"content": lane.label},
                "parent": {"id": frame_miro_id},
            })
        for node in plan.nodes:
            # n-start を別 frame 配下にする（frame 外）
            parent_id = (
                "other-frame" if node.id == "n-start" else frame_miro_id
            )
            board_items.append({
                "id": plan_to_miro[node.id],
                "type": "shape",
                "data": {"content": node.label},
                "parent": {"id": parent_id},
            })
        for sl in plan.system_labels:
            board_items.append({
                "id": plan_to_miro[sl.id],
                "type": "shape",
                "data": {"content": sl.label},
                "parent": {"id": frame_miro_id},
            })
        board_connectors = [
            {"id": plan_to_miro[conn.id], "type": "connector", "data": {}}
            for conn in plan.connectors
        ]

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=frame_miro_id
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # n-start が frame 外で skip されている
            start_irs = [
                ir for ir in result.item_results
                if ir.semantic_id == "n-start"
            ]
            assert any(
                ir.result == "skipped_frame_outside" for ir in start_irs
            )

            # n-start を endpoint に持つ connector も skip 扱い
            # （connector が update_connector/create_connector で呼ばれていない）
            n_start_miro = plan_to_miro["n-start"]
            for call in client.update_connector.call_args_list:
                args = call.args
                kwargs = call.kwargs
                start_item = kwargs.get("start_item") or (
                    args[2] if len(args) >= 3 else {}
                )
                end_item = kwargs.get("end_item") or (
                    args[3] if len(args) >= 4 else {}
                )
                assert start_item.get("id") != n_start_miro, (
                    "frame 外 shape の miro_item_id が connector startItem に "
                    "流入している (P0-C 違反)"
                )
                assert end_item.get("id") != n_start_miro, (
                    "frame 外 shape の miro_item_id が connector endItem に "
                    "流入している (P0-C 違反)"
                )

            # skipped_connector_dependency が少なくとも 1 件
            dep_skips = [
                ir for ir in result.item_results
                if ir.result == "skipped_connector_dependency"
            ]
            assert len(dep_skips) >= 1
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerManualDetachedConnector: P1 (2回目指摘)
# ---------------------------------------------------------------------------


class TestUpdateHandlerManualDetachedConnector:
    """P1 (2回目指摘, Q1 確定): manual_detached / unmanaged な shape は
    shape 自体の update は skip されるが、その shape に接続する connector は
    通常通り update される（保護対象は shape のみ、connector は touch OK）。
    """

    def _run_case(
        self,
        override_plan_id: str,
        override_mode: str,
    ) -> tuple[MagicMock, ExecutionResult, dict[str, str]]:
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        board_items, board_connectors = _build_board_state(
            confirmed, plan_to_miro
        )
        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(
                confirmed,
                plan_to_miro,
                override_update_mode={override_plan_id: override_mode},
            )
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=plan_to_miro["frame"]
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        return client, result, plan_to_miro

    def test_manual_detached_connectors_still_updated(self) -> None:
        """n-review を manual_detached にしても、n-review に繋がる
        connector は通常通り update される（update_connector が呼ばれる）。"""
        client, result, plan_to_miro = self._run_case(
            "n-review", "manual_detached"
        )

        # shape 側: n-review は skip されている（update_shape が呼ばれていない）
        n_review_miro = plan_to_miro["n-review"]
        for call in client.update_shape.call_args_list:
            args = call.args
            assert args[1] != n_review_miro, (
                "manual_detached 対象の shape が更新されている"
            )

        # connector 側: n-review に繋がる connector が少なくとも 1 件
        # update_connector で更新されていること
        assert client.update_connector.called, (
            "manual_detached shape に接続する connector の update_connector が "
            "一度も呼ばれていない (Q1: connector は通常通り更新される)"
        )
        # 更新された connector のうち、n-review が from/to のものが存在する
        connector_touches_review = False
        for call in client.update_connector.call_args_list:
            kwargs = call.kwargs
            start_id = (kwargs.get("start_item") or {}).get("id")
            end_id = (kwargs.get("end_item") or {}).get("id")
            if start_id == n_review_miro or end_id == n_review_miro:
                connector_touches_review = True
                break
        assert connector_touches_review, (
            "manual_detached shape を endpoint とする connector が "
            "update_connector で呼ばれていない"
        )

        # skipped_connector_dependency は発生していない（保護系 shape は
        # id_map に登録され、connector 側は解決される）
        dep_skips = [
            ir for ir in result.item_results
            if ir.result == "skipped_connector_dependency"
        ]
        assert len(dep_skips) == 0, (
            f"manual_detached shape 配下の connector が誤って "
            f"skipped_connector_dependency として記録された: {dep_skips}"
        )

    def test_unmanaged_connectors_still_updated(self) -> None:
        """unmanaged な shape (sl-n-fill-form-s-erp) 配下の connector も
        通常通り update される。"""
        client, result, plan_to_miro = self._run_case(
            "sl-n-fill-form-s-erp", "unmanaged"
        )

        sl_miro = plan_to_miro["sl-n-fill-form-s-erp"]
        # shape 側: update_shape は呼ばれていない（unmanaged 保護）
        for call in client.update_shape.call_args_list:
            args = call.args
            assert args[1] != sl_miro, (
                "unmanaged 対象の shape が更新されている"
            )

        # connector 側: SystemLabel に繋がる connector は system_access なので
        # skip される（元実装のまま）。ただし skipped_connector_dependency では
        # ないことを確認する。
        dep_skips = [
            ir for ir in result.item_results
            if ir.result == "skipped_connector_dependency"
        ]
        assert len(dep_skips) == 0, (
            f"unmanaged shape 配下の connector が誤って "
            f"skipped_connector_dependency として記録された: {dep_skips}"
        )


# ---------------------------------------------------------------------------
# TestUpdateHandlerSkipReasonPropagation: P2-1 (2回目指摘)
# ---------------------------------------------------------------------------


class TestUpdateHandlerSkipReasonPropagation:
    """P2-1 (2回目指摘): reconciler が設定する skip_reason が
    _classify_skip_status で正しく ItemResultStatus に変換されるか検証する。
    """

    def test_frame_outside_skip_reason_routes_to_frame_outside_status(self) -> None:
        """frame 外 item は skip_reason=frame_outside となり、
        ItemResultStatus.SKIPPED_FRAME_OUTSIDE として記録される。"""
        confirmed = _load_confirmed_input()
        plan_to_miro, _ = _assign_miro_ids(confirmed)
        frame_miro_id = plan_to_miro["frame"]
        plan = build_drawing_plan(confirmed, board_name="")

        board_items: list[dict[str, Any]] = [
            {"id": frame_miro_id, "type": "frame",
             "data": {"title": plan.frame.title}},
            {"id": "other-frame", "type": "frame",
             "data": {"title": "other"}},
        ]
        for lane in plan.lanes:
            board_items.append({
                "id": plan_to_miro[lane.id],
                "type": "shape",
                "data": {"content": lane.label},
                "parent": {"id": frame_miro_id},
            })
        for node in plan.nodes:
            parent_id = (
                "other-frame" if node.id == "n-review" else frame_miro_id
            )
            board_items.append({
                "id": plan_to_miro[node.id],
                "type": "shape",
                "data": {"content": node.label},
                "parent": {"id": parent_id},
            })
        for sl in plan.system_labels:
            board_items.append({
                "id": plan_to_miro[sl.id],
                "type": "shape",
                "data": {"content": sl.label},
                "parent": {"id": frame_miro_id},
            })
        board_connectors = [
            {"id": plan_to_miro[conn.id], "type": "connector", "data": {}}
            for conn in plan.connectors
        ]

        tmpdir = tempfile.mkdtemp(prefix="miro_upd_test_")
        try:
            prev_dict = _build_prev_run_log(confirmed, plan_to_miro)
            _write_prev_run_log_json(tmpdir, prev_dict)
            client = _make_mock_client_for_update(
                board_items=board_items,
                board_connectors=board_connectors,
            )
            handler = UpdateHandler(client)
            context = _make_context(
                board_id="board-001", frame_id=frame_miro_id
            )
            config = _make_config(tmpdir)
            result = handler.execute(confirmed, context, config)

            # skip_reason 経由で正しく SKIPPED_FRAME_OUTSIDE にマップされる
            review_irs = [
                ir for ir in result.item_results
                if ir.semantic_id == "n-review"
            ]
            assert any(
                ir.result == "skipped_frame_outside" for ir in review_irs
            ), (
                "frame 外 item が SKIPPED_FRAME_OUTSIDE にマップされていない。"
                " reconciler の skip_reason 設定が消えた可能性がある"
            )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TestUpdateHandlerExport
# ---------------------------------------------------------------------------


class TestUpdateHandlerExport:
    """UpdateHandler が __init__.py からインポートできる。"""

    def test_exported(self) -> None:
        from miro_flow_maker import UpdateHandler as Imported

        assert Imported is UpdateHandler
