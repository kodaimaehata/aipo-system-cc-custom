"""run_log モジュールのテスト。

build_run_log の正常系、write_run_log のファイル出力、ディレクトリ自動作成を検証する。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from miro_flow_maker.models import ExecutionResult, ItemResult
from miro_flow_maker.run_log import (
    RunLog,
    build_id_mapping_from_run_log,
    build_run_log,
    load_run_log,
    write_run_log,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execution_result(
    *,
    dry_run: bool = False,
    success: bool = True,
) -> ExecutionResult:
    """テスト用の ExecutionResult を生成する。"""
    result = ExecutionResult(
        run_id="test-run-001",
        mode="create",
        success=success,
        board_id="board-001",
        frame_id="frame-001",
        flow_group_id="flow-rep-01",
        dry_run=dry_run,
    )
    # item_results を追加
    result.item_results.append(ItemResult(
        stable_item_id="flow-rep-01::flow_group::flow-rep-01::frame",
        semantic_type="flow_group",
        semantic_id="flow-rep-01",
        render_role="frame",
        action="create",
        result="success",
    ))
    result.item_results.append(ItemResult(
        stable_item_id="flow-rep-01::lane::a-applicant::lane_shape",
        semantic_type="lane",
        semantic_id="a-applicant",
        render_role="lane_shape",
        action="create",
        result="success",
    ))
    result.item_results.append(ItemResult(
        stable_item_id="flow-rep-01::node::n-start::start_shape",
        semantic_type="node",
        semantic_id="n-start",
        render_role="start_shape",
        action="create",
        result="success",
    ))
    result.created_count = 3
    return result


def _make_metadata_map() -> dict[str, dict[str, str]]:
    """テスト用の metadata_map を生成する。"""
    return {
        "frame": {
            "stable_item_id": "flow-rep-01::flow_group::flow-rep-01::frame",
            "semantic_type": "flow_group",
            "semantic_id": "flow-rep-01",
            "render_role": "frame",
            "managed_by": "miro-flow-maker",
            "project_id": "P0006",
            "layer_id": "P0006-SG2",
            "document_set_id": "ds-rep-001",
            "flow_group_id": "flow-rep-01",
            "update_mode": "managed",
            "confirmation_packet_ref": "packets/cp-rep-001.json",
        },
        "a-applicant": {
            "stable_item_id": "flow-rep-01::lane::a-applicant::lane_shape",
            "semantic_type": "lane",
            "semantic_id": "a-applicant",
            "render_role": "lane_shape",
            "managed_by": "miro-flow-maker",
            "project_id": "P0006",
            "layer_id": "P0006-SG2",
            "document_set_id": "ds-rep-001",
            "flow_group_id": "flow-rep-01",
            "update_mode": "managed",
            "confirmation_packet_ref": "packets/cp-rep-001.json",
        },
        "n-start": {
            "stable_item_id": "flow-rep-01::node::n-start::start_shape",
            "semantic_type": "node",
            "semantic_id": "n-start",
            "render_role": "start_shape",
            "managed_by": "miro-flow-maker",
            "project_id": "P0006",
            "layer_id": "P0006-SG2",
            "document_set_id": "ds-rep-001",
            "flow_group_id": "flow-rep-01",
            "update_mode": "managed",
            "confirmation_packet_ref": "packets/cp-rep-001.json",
        },
    }


# ---------------------------------------------------------------------------
# build_run_log 正常系
# ---------------------------------------------------------------------------


class TestBuildRunLog:
    """build_run_log の正常系テスト。"""

    def setup_method(self) -> None:
        self.result = _make_execution_result()
        self.metadata_map = _make_metadata_map()
        self.log = build_run_log(self.result, self.metadata_map, duration_ms=1234)

    def test_returns_run_log(self) -> None:
        assert isinstance(self.log, RunLog)

    def test_run_id(self) -> None:
        assert self.log.run_id == "test-run-001"

    def test_timestamp_is_iso(self) -> None:
        # ISO 8601 形式であること (最低限 'T' を含む)
        assert "T" in self.log.timestamp

    def test_mode(self) -> None:
        assert self.log.mode == "create"

    def test_board_id(self) -> None:
        assert self.log.board_id == "board-001"

    def test_frame_id(self) -> None:
        assert self.log.frame_id == "frame-001"

    def test_flow_group_id(self) -> None:
        assert self.log.flow_group_id == "flow-rep-01"

    def test_dry_run(self) -> None:
        assert self.log.dry_run is False

    def test_created_count(self) -> None:
        assert self.log.created_count == 3

    def test_updated_count(self) -> None:
        assert self.log.updated_count == 0

    def test_skipped_count(self) -> None:
        assert self.log.skipped_count == 0

    def test_failed_count(self) -> None:
        assert self.log.failed_count == 0

    def test_stop_reasons_empty(self) -> None:
        assert self.log.stop_reasons == []

    def test_duration_ms(self) -> None:
        assert self.log.duration_ms == 1234

    def test_errors_empty(self) -> None:
        assert self.log.errors == []

    def test_item_results_count(self) -> None:
        assert len(self.log.item_results) == 3

    def test_item_results_contain_stable_item_id(self) -> None:
        for item in self.log.item_results:
            assert "stable_item_id" in item
            assert item["stable_item_id"]  # non-empty

    def test_item_results_contain_semantic_type(self) -> None:
        for item in self.log.item_results:
            assert "semantic_type" in item

    def test_item_results_contain_render_role(self) -> None:
        for item in self.log.item_results:
            assert "render_role" in item

    def test_item_results_contain_metadata_fields(self) -> None:
        """metadata_map からマージされたフィールドが含まれること。"""
        frame_item = self.log.item_results[0]
        assert frame_item["managed_by"] == "miro-flow-maker"
        assert frame_item["project_id"] == "P0006"
        assert frame_item["layer_id"] == "P0006-SG2"
        assert frame_item["document_set_id"] == "ds-rep-001"


class TestBuildRunLogWithFailures:
    """失敗 item がある場合の build_run_log テスト。"""

    def test_errors_contain_failure_reasons(self) -> None:
        result = ExecutionResult(
            run_id="test-run-fail",
            mode="create",
            success=False,
            board_id="board-001",
            frame_id="frame-001",
            flow_group_id="flow-rep-01",
            dry_run=False,
        )
        result.item_results.append(ItemResult(
            stable_item_id="flow-rep-01::lane::a-applicant::lane_shape",
            semantic_type="lane",
            semantic_id="a-applicant",
            render_role="lane_shape",
            action="create",
            result="failed",
            reason="API error: 500",
        ))
        result.failed_count = 1

        log = build_run_log(result, {}, duration_ms=500)
        assert len(log.errors) == 1
        assert "API error: 500" in log.errors[0]


class TestBuildRunLogDryRun:
    """dry-run 時の build_run_log テスト。"""

    def test_dry_run_flag(self) -> None:
        result = _make_execution_result(dry_run=True)
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.dry_run is True


# ---------------------------------------------------------------------------
# write_run_log ファイル出力
# ---------------------------------------------------------------------------


class TestWriteRunLog:
    """write_run_log のファイル出力テスト。"""

    def test_creates_json_file(self) -> None:
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=1000)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)

            assert os.path.isfile(path)
            assert path.endswith(".json")

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert data["run_id"] == "test-run-001"
            assert data["mode"] == "create"
            assert data["flow_group_id"] == "flow-rep-01"
            assert data["created_count"] == 3
            assert isinstance(data["item_results"], list)
            assert len(data["item_results"]) == 3

    def test_filename_contains_run_id(self) -> None:
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            filename = os.path.basename(path)
            assert "run_test-run-001" in filename

    def test_returns_absolute_path(self) -> None:
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            assert os.path.isabs(path)


class TestWriteRunLogAutoCreateDir:
    """write_run_log のディレクトリ自動作成テスト。"""

    def test_creates_missing_directory(self) -> None:
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = os.path.join(tmpdir, "sub1", "sub2", "logs")
            assert not os.path.exists(nested_dir)

            path = write_run_log(log, nested_dir)

            assert os.path.isdir(nested_dir)
            assert os.path.isfile(path)

    def test_existing_directory_no_error(self) -> None:
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 既にディレクトリが存在する場合もエラーにならない
            path = write_run_log(log, tmpdir)
            assert os.path.isfile(path)


# ---------------------------------------------------------------------------
# __init__.py エクスポートテスト
# ---------------------------------------------------------------------------


class TestRunLogExport:
    """RunLog, build_run_log, write_run_log が __init__.py からインポートできること。"""

    def test_run_log_exported(self) -> None:
        from miro_flow_maker import RunLog as Imported
        assert Imported is RunLog

    def test_build_run_log_exported(self) -> None:
        from miro_flow_maker import build_run_log as imported
        assert imported is build_run_log

    def test_write_run_log_exported(self) -> None:
        from miro_flow_maker import write_run_log as imported
        assert imported is write_run_log

    def test_load_run_log_exported(self) -> None:
        from miro_flow_maker import load_run_log as imported
        assert imported is load_run_log

    def test_build_id_mapping_from_run_log_exported(self) -> None:
        from miro_flow_maker import build_id_mapping_from_run_log as imported
        assert imported is build_id_mapping_from_run_log


# ---------------------------------------------------------------------------
# SG3: ItemResult.miro_item_id の item_results dict への転記
# ---------------------------------------------------------------------------


class TestItemResultMiroItemId:
    """ItemResult.miro_item_id が build_run_log で item_results dict に含まれること。"""

    def test_miro_item_id_included_when_set(self) -> None:
        """miro_item_id が設定されている場合、item_results dict に含まれる。"""
        result = ExecutionResult(
            run_id="test-run-miro",
            mode="create",
            success=True,
            board_id="board-001",
            frame_id="frame-001",
            flow_group_id="flow-rep-01",
            dry_run=False,
        )
        result.item_results.append(ItemResult(
            stable_item_id="flow-rep-01::node::n-start::start_shape",
            semantic_type="node",
            semantic_id="n-start",
            render_role="start_shape",
            action="create",
            result="success",
            miro_item_id="3458764000000000001",
        ))
        result.created_count = 1

        log = build_run_log(result, {}, duration_ms=100)
        assert len(log.item_results) == 1
        assert log.item_results[0]["miro_item_id"] == "3458764000000000001"

    def test_miro_item_id_absent_when_none(self) -> None:
        """miro_item_id が None の場合、item_results dict に含まれない（後方互換）。"""
        result = ExecutionResult(
            run_id="test-run-none",
            mode="create",
            success=True,
            board_id="board-001",
            frame_id="frame-001",
            flow_group_id="flow-rep-01",
            dry_run=True,
        )
        result.item_results.append(ItemResult(
            stable_item_id="flow-rep-01::node::n-start::start_shape",
            semantic_type="node",
            semantic_id="n-start",
            render_role="start_shape",
            action="create",
            result="dry_run_skipped",
            # miro_item_id は指定せず None (default)
        ))
        result.skipped_count = 1

        log = build_run_log(result, {}, duration_ms=100)
        assert len(log.item_results) == 1
        assert "miro_item_id" not in log.item_results[0]


# ---------------------------------------------------------------------------
# SG3: RunLog の新フィールド (partial_success / stopped_stage / rerun_eligible)
# ---------------------------------------------------------------------------


class TestRunLogNewFields:
    """ExecutionResult の SG3 新フィールドが RunLog に正しく転記されること。"""

    def test_defaults_propagated(self) -> None:
        """デフォルト値（partial_success=False, stopped_stage=None, rerun_eligible=True）が転記されること。"""
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.partial_success is False
        assert log.stopped_stage is None
        assert log.rerun_eligible is True

    def test_custom_values_propagated(self) -> None:
        """カスタム値が転記されること。"""
        result = _make_execution_result()
        result.partial_success = True
        result.stopped_stage = "upsert_connectors"
        result.rerun_eligible = False

        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.partial_success is True
        assert log.stopped_stage == "upsert_connectors"
        assert log.rerun_eligible is False

    def test_new_fields_written_to_file(self) -> None:
        """新フィールドが write_run_log 経由で JSON に書き出されること。"""
        result = _make_execution_result()
        result.partial_success = True
        result.stopped_stage = "reconcile"
        result.rerun_eligible = False
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["partial_success"] is True
            assert data["stopped_stage"] == "reconcile"
            assert data["rerun_eligible"] is False


# ---------------------------------------------------------------------------
# SG3: load_run_log
# ---------------------------------------------------------------------------


class TestLoadRunLog:
    """load_run_log が新形式 / SG2 旧形式の両方を読み込めること。"""

    def test_load_new_format_roundtrip(self) -> None:
        """build_run_log -> write_run_log -> load_run_log のラウンドトリップ。"""
        result = _make_execution_result()
        result.partial_success = True
        result.stopped_stage = "upsert_shapes"
        result.rerun_eligible = False
        # ItemResult に miro_item_id を付与
        result.item_results[0] = ItemResult(
            stable_item_id=result.item_results[0].stable_item_id,
            semantic_type=result.item_results[0].semantic_type,
            semantic_id=result.item_results[0].semantic_id,
            render_role=result.item_results[0].render_role,
            action=result.item_results[0].action,
            result=result.item_results[0].result,
            miro_item_id="miro-id-001",
        )
        log = build_run_log(result, _make_metadata_map(), duration_ms=1234)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            loaded = load_run_log(path)

        assert isinstance(loaded, RunLog)
        assert loaded.run_id == "test-run-001"
        assert loaded.mode == "create"
        assert loaded.board_id == "board-001"
        assert loaded.frame_id == "frame-001"
        assert loaded.flow_group_id == "flow-rep-01"
        assert loaded.dry_run is False
        assert loaded.created_count == 3
        assert loaded.duration_ms == 1234
        assert loaded.partial_success is True
        assert loaded.stopped_stage == "upsert_shapes"
        assert loaded.rerun_eligible is False
        assert len(loaded.item_results) == 3
        # 1 件目 item に miro_item_id が復元されていること
        assert loaded.item_results[0].get("miro_item_id") == "miro-id-001"

    def test_load_sg2_legacy_format(self) -> None:
        """SG2 既存形式（miro_item_id / partial_success / stopped_stage / rerun_eligible なし）を読み込めること。"""
        legacy_data = {
            "run_id": "sg2-run-001",
            "timestamp": "2026-04-15T07:13:59.370599+00:00",
            "mode": "create",
            "board_id": "board-sg2",
            "frame_id": "frame-sg2",
            "flow_group_id": "flow-sg2-01",
            "dry_run": False,
            "created_count": 2,
            "updated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "stop_reasons": [],
            "duration_ms": 5678,
            "errors": [],
            "item_results": [
                {
                    "stable_item_id": "flow-sg2-01::node::n1::shape",
                    "semantic_type": "node",
                    "semantic_id": "n1",
                    "render_role": "shape",
                    "action": "create",
                    "result": "success",
                    # miro_item_id なし
                },
            ],
            # partial_success / stopped_stage / rerun_eligible なし
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run_sg2-run-001_legacy.json"
            path.write_text(json.dumps(legacy_data), encoding="utf-8")
            loaded = load_run_log(str(path))

        assert isinstance(loaded, RunLog)
        assert loaded.run_id == "sg2-run-001"
        assert loaded.mode == "create"
        assert loaded.created_count == 2
        # デフォルト値が適用されること
        assert loaded.partial_success is False
        assert loaded.stopped_stage is None
        assert loaded.rerun_eligible is True
        # item_results 内の miro_item_id が無いことを確認
        assert len(loaded.item_results) == 1
        assert "miro_item_id" not in loaded.item_results[0]


# ---------------------------------------------------------------------------
# SG3: build_id_mapping_from_run_log
# ---------------------------------------------------------------------------


class TestBuildIdMappingFromRunLog:
    """build_id_mapping_from_run_log の動作確認。"""

    def test_maps_items_with_miro_item_id(self) -> None:
        """miro_item_id がある item のみマッピングに含まれること。"""
        log = RunLog(
            run_id="r1",
            timestamp="2026-04-17T00:00:00+00:00",
            mode="create",
            board_id="b1",
            frame_id="f1",
            flow_group_id="fg1",
            dry_run=False,
            created_count=2,
            updated_count=0,
            skipped_count=0,
            failed_count=0,
            stop_reasons=[],
            duration_ms=100,
            errors=[],
            item_results=[
                {
                    "stable_item_id": "fg1::node::n1::shape",
                    "semantic_type": "node",
                    "semantic_id": "n1",
                    "render_role": "shape",
                    "action": "create",
                    "result": "success",
                    "miro_item_id": "miro-id-001",
                },
                {
                    "stable_item_id": "fg1::node::n2::shape",
                    "semantic_type": "node",
                    "semantic_id": "n2",
                    "render_role": "shape",
                    "action": "create",
                    "result": "success",
                    "miro_item_id": "miro-id-002",
                },
            ],
        )
        mapping = build_id_mapping_from_run_log(log)
        assert mapping == {
            "fg1::node::n1::shape": "miro-id-001",
            "fg1::node::n2::shape": "miro-id-002",
        }

    def test_skips_items_without_miro_item_id(self) -> None:
        """miro_item_id が無い / None / 空の item はスキップされること。"""
        log = RunLog(
            run_id="r2",
            timestamp="2026-04-17T00:00:00+00:00",
            mode="create",
            board_id="b1",
            frame_id="f1",
            flow_group_id="fg1",
            dry_run=False,
            created_count=0,
            updated_count=0,
            skipped_count=3,
            failed_count=0,
            stop_reasons=[],
            duration_ms=100,
            errors=[],
            item_results=[
                {
                    "stable_item_id": "fg1::node::n1::shape",
                    "result": "dry_run_skipped",
                    # miro_item_id なし
                },
                {
                    "stable_item_id": "fg1::node::n2::shape",
                    "result": "failed",
                    "miro_item_id": None,
                },
                {
                    "stable_item_id": "fg1::node::n3::shape",
                    "result": "success",
                    "miro_item_id": "miro-id-003",
                },
            ],
        )
        mapping = build_id_mapping_from_run_log(log)
        assert mapping == {"fg1::node::n3::shape": "miro-id-003"}

    def test_empty_log(self) -> None:
        """item_results が空の場合、空のマッピングを返す。"""
        log = RunLog(
            run_id="r3",
            timestamp="2026-04-17T00:00:00+00:00",
            mode="create",
            board_id=None,
            frame_id=None,
            flow_group_id="fg1",
            dry_run=True,
            created_count=0,
            updated_count=0,
            skipped_count=0,
            failed_count=0,
            stop_reasons=[],
            duration_ms=0,
            errors=[],
            item_results=[],
        )
        assert build_id_mapping_from_run_log(log) == {}

    def test_skips_items_without_stable_item_id(self) -> None:
        """stable_item_id が空文字列の item はスキップされること。"""
        log = RunLog(
            run_id="r4",
            timestamp="2026-04-17T00:00:00+00:00",
            mode="create",
            board_id="b1",
            frame_id="f1",
            flow_group_id="fg1",
            dry_run=False,
            created_count=1,
            updated_count=0,
            skipped_count=0,
            failed_count=0,
            stop_reasons=[],
            duration_ms=10,
            errors=[],
            item_results=[
                {
                    "stable_item_id": "",
                    "result": "success",
                    "miro_item_id": "miro-id-999",
                },
            ],
        )
        assert build_id_mapping_from_run_log(log) == {}


# ---------------------------------------------------------------------------
# SG4: top-level success field (write / load)
# ---------------------------------------------------------------------------


class TestRunLogSuccessField:
    """SG4: run_log JSON に top-level success key を含め、load 時に後方互換する。"""

    def test_write_run_log_includes_success_field_on_success(self) -> None:
        """正常系 result → JSON の top-level に "success": true が含まれる。"""
        result = _make_execution_result()
        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.success is True

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        assert "success" in data
        assert data["success"] is True

    def test_write_run_log_success_false_on_failure(self) -> None:
        """failed_count > 0 の result → JSON の "success": false。"""
        result = ExecutionResult(
            run_id="test-run-fail",
            mode="create",
            success=False,
            board_id="board-001",
            frame_id="frame-001",
            flow_group_id="flow-rep-01",
            dry_run=False,
        )
        result.item_results.append(ItemResult(
            stable_item_id="flow-rep-01::lane::a-applicant::lane_shape",
            semantic_type="lane",
            semantic_id="a-applicant",
            render_role="lane_shape",
            action="create",
            result="failed",
            reason="API error: 500",
        ))
        result.failed_count = 1

        log = build_run_log(result, {}, duration_ms=100)
        assert log.success is False

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        assert data["success"] is False

    def test_write_run_log_success_false_on_partial(self) -> None:
        """partial_success=True の result → JSON の "success": false。"""
        result = _make_execution_result()
        result.partial_success = True

        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.success is False

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        assert data["success"] is False

    def test_write_run_log_success_false_on_stopped(self) -> None:
        """stopped_stage='reconcile' の result → JSON の "success": false。"""
        result = _make_execution_result()
        result.stopped_stage = "reconcile"

        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.success is False

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        assert data["success"] is False

    def test_write_run_log_success_false_on_stop_reasons(self) -> None:
        """stop_reasons が非空の result → JSON の "success": false。"""
        result = _make_execution_result()
        result.stop_reasons.append("board 解決失敗")

        log = build_run_log(result, _make_metadata_map(), duration_ms=100)
        assert log.success is False

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_run_log(log, tmpdir)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        assert data["success"] is False

    def test_load_run_log_synthesizes_success_when_missing_normal(self) -> None:
        """success key 無しの旧形式 JSON（正常系）→ 合成で success=True。"""
        legacy_data = {
            "run_id": "legacy-ok-001",
            "timestamp": "2026-04-15T07:13:59.370599+00:00",
            "mode": "create",
            "board_id": "board-legacy",
            "frame_id": "frame-legacy",
            "flow_group_id": "flow-legacy-01",
            "dry_run": False,
            "created_count": 3,
            "updated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "stop_reasons": [],
            "duration_ms": 1000,
            "errors": [],
            "item_results": [],
            # success / partial_success / stopped_stage 無し
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run_legacy-ok-001.json"
            path.write_text(json.dumps(legacy_data), encoding="utf-8")
            loaded = load_run_log(str(path))
        assert loaded.success is True

    def test_load_run_log_synthesizes_success_when_missing_failure(self) -> None:
        """success key 無しの旧形式 JSON（失敗系）→ 合成で success=False。"""
        legacy_data = {
            "run_id": "legacy-fail-001",
            "timestamp": "2026-04-15T07:13:59.370599+00:00",
            "mode": "create",
            "board_id": "board-legacy",
            "frame_id": "frame-legacy",
            "flow_group_id": "flow-legacy-01",
            "dry_run": False,
            "created_count": 1,
            "updated_count": 0,
            "skipped_count": 0,
            "failed_count": 2,
            "stop_reasons": [],
            "duration_ms": 1000,
            "errors": ["API error: 500", "API error: 429"],
            "item_results": [],
            # success 無し
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run_legacy-fail-001.json"
            path.write_text(json.dumps(legacy_data), encoding="utf-8")
            loaded = load_run_log(str(path))
        assert loaded.success is False

    def test_load_run_log_preserves_success_when_present(self) -> None:
        """"success": true が含まれる JSON を load → log.success == True をそのまま。"""
        new_data = {
            "run_id": "new-format-001",
            "timestamp": "2026-04-18T00:00:00+00:00",
            "mode": "create",
            "board_id": "board-new",
            "frame_id": "frame-new",
            "flow_group_id": "flow-new-01",
            "dry_run": False,
            "created_count": 2,
            "updated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "stop_reasons": [],
            "duration_ms": 500,
            "errors": [],
            "item_results": [],
            "partial_success": False,
            "stopped_stage": None,
            "rerun_eligible": True,
            "success": True,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run_new-format-001.json"
            path.write_text(json.dumps(new_data), encoding="utf-8")
            loaded = load_run_log(str(path))
        assert loaded.success is True

    def test_load_run_log_preserves_success_false_when_present(self) -> None:
        """"success": false が含まれる JSON を load → log.success == False をそのまま。

        合成条件的には True に見えても、明示値を尊重する。
        """
        # 合成条件上は True だが success=False が明示されている
        new_data = {
            "run_id": "explicit-false-001",
            "timestamp": "2026-04-18T00:00:00+00:00",
            "mode": "create",
            "board_id": "board-x",
            "frame_id": "frame-x",
            "flow_group_id": "flow-x-01",
            "dry_run": False,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "stop_reasons": [],
            "duration_ms": 0,
            "errors": [],
            "item_results": [],
            "partial_success": False,
            "stopped_stage": None,
            "rerun_eligible": True,
            "success": False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run_explicit-false-001.json"
            path.write_text(json.dumps(new_data), encoding="utf-8")
            loaded = load_run_log(str(path))
        assert loaded.success is False
