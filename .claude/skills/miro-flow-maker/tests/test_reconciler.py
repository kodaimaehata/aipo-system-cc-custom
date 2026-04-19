"""reconciler モジュールのテスト。

reconcile / backfill_miro_item_ids の主要ケースを検証する。
fixture は DrawingPlan dataclass を直接構築する（confirmed_representative.json 非依存）。
"""

from __future__ import annotations

from typing import Any

import pytest

from miro_flow_maker.layout import (
    ConnectorPlan,
    DrawingPlan,
    FramePlan,
    LanePlan,
    NodePlan,
    SystemLabelPlan,
)
from miro_flow_maker.reconciler import (
    ReconcileAction,
    ReconcileResult,
    backfill_miro_item_ids,
    reconcile,
)
from miro_flow_maker.run_log import RunLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FLOW_GROUP = "flow-rep-01"
_FRAME_ID = "frame-miro-001"


def _stable_id(semantic_type: str, semantic_id: str, render_role: str) -> str:
    return f"{_FLOW_GROUP}::{semantic_type}::{semantic_id}::{render_role}"


def _build_drawing_plan() -> DrawingPlan:
    """小さな DrawingPlan を組み立てる。

    - frame: 1
    - lane: 1 (a-applicant)
    - node: 2 (n-start, n-end)
    - system_label: 1 (sl-n-start-s-crm)
    - connector: 1 (c1: n-start -> n-end)
    """
    frame = FramePlan(title="Flow Representative", x=-50, y=-50, width=1000, height=400)
    lane = LanePlan(
        id="a-applicant",
        type="actor_lane",
        label="Applicant",
        kind="human",
        x=0,
        y=0,
        width=1000,
        height=300,
        semantic_id="a-applicant",
    )
    node_start = NodePlan(
        id="n-start",
        type="start",
        label="Start Task",
        x=200,
        y=100,
        width=120,
        height=60,
        lane_id="a-applicant",
        semantic_id="n-start",
    )
    node_end = NodePlan(
        id="n-end",
        type="end",
        label="End Task",
        x=600,
        y=100,
        width=120,
        height=60,
        lane_id="a-applicant",
        semantic_id="n-end",
    )
    sl = SystemLabelPlan(
        id="sl-n-start-s-crm",
        label="CRM",
        x=220,
        y=170,
        width=80,
        height=25,
        node_id="n-start",
        system_id="s-crm",
    )
    conn = ConnectorPlan(
        id="c1",
        from_plan_id="n-start",
        to_plan_id="n-end",
        type="business_flow",
        label="next",
    )
    return DrawingPlan(
        board_name="Test Board",
        frame=frame,
        lanes=[lane],
        nodes=[node_start, node_end],
        endpoints=[],
        connectors=[conn],
        system_labels=[sl],
    )


def _build_metadata_map() -> dict[str, dict[str, str]]:
    """DrawingPlan と対応する metadata_map を組み立てる。"""
    common: dict[str, str] = {
        "managed_by": "miro-flow-maker",
        "project_id": "P0006",
        "layer_id": "P0006-SG3",
        "document_set_id": "ds-rep-001",
        "flow_group_id": _FLOW_GROUP,
        "update_mode": "managed",
        "confirmation_packet_ref": "packets/cp-001.json",
        "review_status": "confirmed",
        "confirmed_by_user": "true",
    }

    def _mk(plan_id: str, semantic_type: str, semantic_id: str, render_role: str) -> dict[str, str]:
        return {
            **common,
            "semantic_type": semantic_type,
            "semantic_id": semantic_id,
            "render_role": render_role,
            "stable_item_id": _stable_id(semantic_type, semantic_id, render_role),
        }

    return {
        "frame": _mk("frame", "flow_group", _FLOW_GROUP, "frame"),
        "a-applicant": _mk("a-applicant", "actor_lane", "a-applicant", "lane_container"),
        "n-start": _mk("n-start", "node", "n-start", "node_shape"),
        "n-end": _mk("n-end", "node", "n-end", "node_shape"),
        "sl-n-start-s-crm": _mk(
            "sl-n-start-s-crm", "system_endpoint", "sl-n-start-s-crm", "system_label"
        ),
        "c1": _mk("c1", "business_flow", "c1", "edge_connector"),
    }


def _make_run_log_item(
    plan_id: str,
    metadata_map: dict[str, dict[str, str]],
    miro_item_id: str | None,
    *,
    update_mode: str | None = "managed",
    flow_group_id: str | None = None,
) -> dict[str, object]:
    """metadata_map の plan_id に対応する run log item 辞書を生成する。"""
    meta = metadata_map[plan_id]
    item: dict[str, object] = {
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
        "flow_group_id": flow_group_id if flow_group_id is not None else meta["flow_group_id"],
        "confirmation_packet_ref": meta["confirmation_packet_ref"],
    }
    if update_mode is not None:
        item["update_mode"] = update_mode
    if miro_item_id is not None:
        item["miro_item_id"] = miro_item_id
    return item


def _build_run_log(items: list[dict[str, object]]) -> RunLog:
    return RunLog(
        run_id="prev-run",
        timestamp="2026-04-16T00:00:00+00:00",
        mode="create",
        board_id="board-001",
        frame_id=_FRAME_ID,
        flow_group_id=_FLOW_GROUP,
        dry_run=False,
        created_count=len(items),
        updated_count=0,
        skipped_count=0,
        failed_count=0,
        stop_reasons=[],
        duration_ms=1000,
        errors=[],
        item_results=items,
    )


def _board_shape(
    item_id: str,
    content: str,
    *,
    parent_id: str | None = _FRAME_ID,
    item_type: str = "shape",
) -> dict[str, Any]:
    """board_items に並べる shape の簡易構造を返す。"""
    obj: dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "data": {"content": content},
    }
    if parent_id is not None:
        obj["parent"] = {"id": parent_id}
    return obj


def _board_frame(item_id: str, title: str) -> dict[str, Any]:
    return {"id": item_id, "type": "frame", "data": {"title": title}}


def _board_connector(item_id: str) -> dict[str, Any]:
    return {"id": item_id, "type": "connector", "data": {}}


def _miro_ids_for_full_mapping() -> dict[str, str]:
    """全 plan item に対して Miro ID を割り当てる。"""
    return {
        "frame": "miro-frame",
        "a-applicant": "miro-lane-1",
        "n-start": "miro-node-start",
        "n-end": "miro-node-end",
        "sl-n-start-s-crm": "miro-sl-1",
        "c1": "miro-conn-1",
    }


def _build_full_board_state(
    metadata_map: dict[str, dict[str, str]],
    miro_ids: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """metadata_map 全 item を board 上に配置した board_items / board_connectors を構築する。"""
    plan = _build_drawing_plan()
    board_items: list[dict[str, Any]] = [
        _board_frame(miro_ids["frame"], plan.frame.title),
    ]
    # frame の id は自身が frame なので parent は持たない
    for lane in plan.lanes:
        board_items.append(_board_shape(miro_ids[lane.id], lane.label))
    for node in plan.nodes:
        board_items.append(_board_shape(miro_ids[node.id], node.label))
    for sl in plan.system_labels:
        board_items.append(_board_shape(miro_ids[sl.id], sl.label))
    board_connectors: list[dict[str, Any]] = [_board_connector(miro_ids["c1"])]
    return board_items, board_connectors


def _actions_by_plan_id(result: ReconcileResult) -> dict[str, ReconcileAction]:
    return {a.plan_id: a for a in result.actions}


# ---------------------------------------------------------------------------
# TestReconcileAllUpdate
# ---------------------------------------------------------------------------


class TestReconcileAllUpdate:
    """全 item が 1:1 で一致する場合、全て update になる。"""

    def test_all_update(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        prev_run_log = _build_run_log([
            _make_run_log_item(pid, metadata_map, miro_ids[pid]) for pid in miro_ids
        ])

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        assert result.stopped is False
        assert result.stop_reasons == []
        assert result.orphaned_items == []
        actions = _actions_by_plan_id(result)
        assert len(actions) == len(miro_ids)
        for plan_id, miro_id in miro_ids.items():
            assert actions[plan_id].action == "update"
            assert actions[plan_id].miro_item_id == miro_id
            assert actions[plan_id].update_mode == "managed"


# ---------------------------------------------------------------------------
# TestReconcileNewItem
# ---------------------------------------------------------------------------


class TestReconcileNewItem:
    """run log にない item は create 判定される。"""

    def test_missing_item_becomes_create(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        # run log には n-end を含めない（= 新規 item 扱い）
        prev_items = [
            _make_run_log_item(pid, metadata_map, miro_ids[pid])
            for pid in miro_ids
            if pid != "n-end"
        ]
        prev_run_log = _build_run_log(prev_items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)
        # n-end は board にも存在させない（新規作成対象）
        board_items = [bi for bi in board_items if bi["id"] != miro_ids["n-end"]]

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        assert result.stopped is False
        actions = _actions_by_plan_id(result)
        assert actions["n-end"].action == "create"
        assert actions["n-end"].miro_item_id is None
        # 既存 item は update のまま
        assert actions["n-start"].action == "update"


# ---------------------------------------------------------------------------
# TestReconcileStableItemIdDuplicate
# ---------------------------------------------------------------------------


class TestReconcileStableItemIdDuplicate:
    """stable_item_id が run log に 2 件存在する場合は stop する。"""

    def test_duplicate_stops(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        # n-start を 2 回記録（異なる miro_item_id）
        items = [_make_run_log_item(pid, metadata_map, miro_ids[pid]) for pid in miro_ids]
        duplicate = _make_run_log_item("n-start", metadata_map, "miro-node-start-dup")
        items.append(duplicate)
        prev_run_log = _build_run_log(items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        assert result.stopped is True
        assert any("stable_item_id 重複" in r for r in result.stop_reasons)
        actions = _actions_by_plan_id(result)
        assert actions["n-start"].action == "stop"


# ---------------------------------------------------------------------------
# TestReconcileManualDetached
# ---------------------------------------------------------------------------


class TestReconcileManualDetached:
    """update_mode='manual_detached' は skip になる。"""

    def test_manual_detached_skipped(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        items: list[dict[str, object]] = []
        for pid in miro_ids:
            mode = "manual_detached" if pid == "n-end" else "managed"
            items.append(
                _make_run_log_item(pid, metadata_map, miro_ids[pid], update_mode=mode)
            )
        prev_run_log = _build_run_log(items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert actions["n-end"].action == "skip"
        assert actions["n-end"].update_mode == "manual_detached"
        # P2-1 (2回目指摘): skip_reason が構造化ラベルで設定される
        assert actions["n-end"].skip_reason == "manual_detached"
        # 他は update のまま
        assert actions["n-start"].action == "update"
        assert result.stopped is False


# ---------------------------------------------------------------------------
# TestReconcileUnmanaged
# ---------------------------------------------------------------------------


class TestReconcileUnmanaged:
    """update_mode='unmanaged' は skip になる。"""

    def test_unmanaged_skipped(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        items: list[dict[str, object]] = []
        for pid in miro_ids:
            mode = "unmanaged" if pid == "sl-n-start-s-crm" else "managed"
            items.append(
                _make_run_log_item(pid, metadata_map, miro_ids[pid], update_mode=mode)
            )
        prev_run_log = _build_run_log(items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert actions["sl-n-start-s-crm"].action == "skip"
        assert actions["sl-n-start-s-crm"].update_mode == "unmanaged"
        # P2-1 (2回目指摘): skip_reason が構造化ラベルで設定される
        assert actions["sl-n-start-s-crm"].skip_reason == "unmanaged"
        assert result.stopped is False


# ---------------------------------------------------------------------------
# TestReconcileOrphaned
# ---------------------------------------------------------------------------


class TestReconcileOrphaned:
    """confirmed から消えた managed item は orphaned として検出される。"""

    def test_orphaned_detected(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()

        # run log には、DrawingPlan に存在しない "n-deleted" を 1 件追加する
        orphan_meta: dict[str, str] = {
            "managed_by": "miro-flow-maker",
            "project_id": "P0006",
            "layer_id": "P0006-SG3",
            "document_set_id": "ds-rep-001",
            "flow_group_id": _FLOW_GROUP,
            "update_mode": "managed",
            "confirmation_packet_ref": "packets/cp-001.json",
            "semantic_type": "node",
            "semantic_id": "n-deleted",
            "render_role": "node_shape",
            "stable_item_id": _stable_id("node", "n-deleted", "node_shape"),
        }
        orphan_item: dict[str, object] = {
            "stable_item_id": orphan_meta["stable_item_id"],
            "semantic_type": orphan_meta["semantic_type"],
            "semantic_id": orphan_meta["semantic_id"],
            "render_role": orphan_meta["render_role"],
            "action": "create",
            "result": "success",
            "miro_item_id": "miro-node-deleted",
            "flow_group_id": _FLOW_GROUP,
            "update_mode": "managed",
        }
        items = [_make_run_log_item(pid, metadata_map, miro_ids[pid]) for pid in miro_ids]
        items.append(orphan_item)
        prev_run_log = _build_run_log(items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        # orphaned に含まれること
        assert len(result.orphaned_items) == 1
        o = result.orphaned_items[0]
        assert o.action == "orphaned"
        assert o.stable_item_id == orphan_meta["stable_item_id"]
        assert o.miro_item_id == "miro-node-deleted"
        # P2-1 (2回目指摘): orphaned も skip_reason で orphaned とラベリング
        assert o.skip_reason == "orphaned"
        # actions には含まれないこと（DrawingPlan に無いため）
        assert all(a.plan_id != "" for a in result.actions)
        # 既存 item は update のまま（stop しない）
        assert result.stopped is False


# ---------------------------------------------------------------------------
# TestReconcileStaleMiroItemId
# ---------------------------------------------------------------------------


class TestReconcileStaleMiroItemId:
    """board に存在しない miro_item_id は create 扱いになる。"""

    def test_stale_becomes_create(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        prev_run_log = _build_run_log([
            _make_run_log_item(pid, metadata_map, miro_ids[pid]) for pid in miro_ids
        ])

        # n-end の Miro item を board から削除（stale 化）
        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)
        board_items = [bi for bi in board_items if bi["id"] != miro_ids["n-end"]]

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert actions["n-end"].action == "create"
        assert actions["n-end"].miro_item_id is None
        assert actions["n-end"].reason is not None
        assert "stale" in actions["n-end"].reason
        assert result.stopped is False


# ---------------------------------------------------------------------------
# TestReconcileFrameScope
# ---------------------------------------------------------------------------


class TestReconcileFrameScope:
    """frame 外の item (parent_id != frame_id) は skip になる。"""

    def test_item_outside_frame_is_skipped(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        prev_run_log = _build_run_log([
            _make_run_log_item(pid, metadata_map, miro_ids[pid]) for pid in miro_ids
        ])

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)
        # n-end を別 frame の子に差し替える
        for item in board_items:
            if item["id"] == miro_ids["n-end"]:
                item["parent"] = {"id": "other-frame"}

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert actions["n-end"].action == "skip"
        assert "frame_id" in (actions["n-end"].reason or "")
        # P2-1 (2回目指摘): skip_reason が構造化ラベルで設定される
        assert actions["n-end"].skip_reason == "frame_outside"
        # connector は frame scope 判定の対象外（shape のみ検査）
        assert actions["c1"].action == "update"


# ---------------------------------------------------------------------------
# TestReconcileSG2RunLog
# ---------------------------------------------------------------------------


class TestReconcileSG2RunLog:
    """update_mode が欠落した SG2 既存 run log は managed 扱い。"""

    def test_missing_update_mode_treated_as_managed(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        miro_ids = _miro_ids_for_full_mapping()
        # update_mode を全 item で欠落させる
        items = [
            _make_run_log_item(pid, metadata_map, miro_ids[pid], update_mode=None)
            for pid in miro_ids
        ]
        prev_run_log = _build_run_log(items)

        board_items, board_connectors = _build_full_board_state(metadata_map, miro_ids)

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=prev_run_log,
            board_items=board_items,
            board_connectors=board_connectors,
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert all(a.update_mode == "managed" for a in actions.values())
        assert actions["n-start"].action == "update"
        assert result.stopped is False


# ---------------------------------------------------------------------------
# TestReconcileNoPrevRunLog
# ---------------------------------------------------------------------------


class TestReconcileNoPrevRunLog:
    """prev_run_log=None の場合、全 item が create になる。"""

    def test_no_prev_run_log_all_create(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()

        result = reconcile(
            drawing_plan=plan,
            metadata_map=metadata_map,
            prev_run_log=None,
            board_items=[],
            board_connectors=[],
            frame_id=_FRAME_ID,
        )
        actions = _actions_by_plan_id(result)
        assert all(a.action == "create" for a in actions.values())
        assert result.stopped is False
        assert result.orphaned_items == []


# ---------------------------------------------------------------------------
# TestBackfillMiroItemIds
# ---------------------------------------------------------------------------


class TestBackfillMiroItemIds:
    """backfill_miro_item_ids の content 照合ロジック。"""

    def test_single_match_backfilled(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        # SG2 run log 風: miro_item_id なし
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        # board 上には各 label が 1 件ずつ存在
        board_items = [
            _board_frame("miro-frame", plan.frame.title),
            _board_shape("miro-lane-1", "Applicant"),
            _board_shape("miro-node-start", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
            _board_shape("miro-sl-1", "CRM"),
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, [], plan)

        # node / lane / system_label はマッピングされている
        assert mapping[_stable_id("node", "n-start", "node_shape")] == "miro-node-start"
        assert mapping[_stable_id("node", "n-end", "node_shape")] == "miro-node-end"
        assert (
            mapping[_stable_id("actor_lane", "a-applicant", "lane_container")]
            == "miro-lane-1"
        )
        assert (
            mapping[_stable_id("system_endpoint", "sl-n-start-s-crm", "system_label")]
            == "miro-sl-1"
        )

    def test_multiple_match_skipped(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        # "Start Task" が複数件（曖昧）
        board_items = [
            _board_shape("miro-node-start-1", "Start Task"),
            _board_shape("miro-node-start-2", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, [], plan)

        # n-start は複数一致でスキップ
        assert _stable_id("node", "n-start", "node_shape") not in mapping
        # n-end は 1 件一致で補完される
        assert mapping[_stable_id("node", "n-end", "node_shape")] == "miro-node-end"

    def test_zero_match_skipped(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        # label と一致しない content のみ
        board_items = [
            _board_shape("miro-other", "Totally Different Content"),
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, [], plan)
        assert _stable_id("node", "n-start", "node_shape") not in mapping
        assert _stable_id("node", "n-end", "node_shape") not in mapping

    def test_existing_mapping_preserved(self) -> None:
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        # n-start は既に miro_item_id を持つ、他は欠落
        items: list[dict[str, object]] = []
        for pid in metadata_map:
            miro_id = "miro-node-start-existing" if pid == "n-start" else None
            items.append(
                _make_run_log_item(pid, metadata_map, miro_id, update_mode=None)
            )
        run_log = _build_run_log(items)
        board_items = [
            _board_shape("miro-node-start-existing", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, [], plan)
        # 既存は保持
        assert (
            mapping[_stable_id("node", "n-start", "node_shape")]
            == "miro-node-start-existing"
        )
        # 補完は動作
        assert mapping[_stable_id("node", "n-end", "node_shape")] == "miro-node-end"


# ---------------------------------------------------------------------------
# P0-B: connector backfill のテスト
# ---------------------------------------------------------------------------


class TestBackfillConnector:
    """P0-B: SG2 既存 run log（miro_item_id なし）の connector を補完する。"""

    def test_connector_backfilled_when_endpoints_resolved(self) -> None:
        """shape backfill 後に endpoint ペアが一意に解決できる connector は補完される。"""
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        # SG2 run log 風: 全 item で miro_item_id なし
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        # shape 側は 1 件一致で backfill 可能
        board_items = [
            _board_frame("miro-frame", plan.frame.title),
            _board_shape("miro-lane-1", "Applicant"),
            _board_shape("miro-node-start", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
            _board_shape("miro-sl-1", "CRM"),
        ]
        # connector は startItem=miro-node-start, endItem=miro-node-end で 1 件存在
        board_connectors = [
            {
                "id": "miro-conn-1",
                "type": "connector",
                "startItem": {"id": "miro-node-start"},
                "endItem": {"id": "miro-node-end"},
            }
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, board_connectors, plan)
        # connector が backfill されている（P0-B）
        assert (
            mapping[_stable_id("business_flow", "c1", "edge_connector")]
            == "miro-conn-1"
        )

    def test_connector_skipped_when_multiple_match(self) -> None:
        """同じ endpoint ペアの connector が複数件ある場合は曖昧なのでスキップ。"""
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        board_items = [
            _board_shape("miro-node-start", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
        ]
        # 同じペアが 2 件 → スキップ
        board_connectors = [
            {
                "id": "miro-conn-1",
                "startItem": {"id": "miro-node-start"},
                "endItem": {"id": "miro-node-end"},
            },
            {
                "id": "miro-conn-2",
                "startItem": {"id": "miro-node-start"},
                "endItem": {"id": "miro-node-end"},
            },
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, board_connectors, plan)
        assert _stable_id("business_flow", "c1", "edge_connector") not in mapping

    def test_connector_skipped_when_endpoints_unresolved(self) -> None:
        """接続先 shape の miro_item_id が解決できない場合は connector もスキップ。"""
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        # shape backfill できない（label 不一致）
        board_items = [_board_shape("miro-other", "Unrelated")]
        board_connectors = [
            {
                "id": "miro-conn-1",
                "startItem": {"id": "miro-node-start"},
                "endItem": {"id": "miro-node-end"},
            }
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, board_connectors, plan)
        assert _stable_id("business_flow", "c1", "edge_connector") not in mapping

    def test_empty_board_connectors_no_error(self) -> None:
        """board_connectors が空でもエラーにならない（既存 shape backfill は動作する）。"""
        plan = _build_drawing_plan()
        metadata_map = _build_metadata_map()
        items = [
            _make_run_log_item(pid, metadata_map, miro_item_id=None, update_mode=None)
            for pid in metadata_map
        ]
        run_log = _build_run_log(items)
        board_items = [
            _board_shape("miro-node-start", "Start Task"),
            _board_shape("miro-node-end", "End Task"),
        ]
        mapping = backfill_miro_item_ids(run_log, board_items, [], plan)
        # shape は backfill される
        assert mapping[_stable_id("node", "n-start", "node_shape")] == "miro-node-start"
        # connector は backfill できない
        assert _stable_id("business_flow", "c1", "edge_connector") not in mapping


# ---------------------------------------------------------------------------
# TestReconcilerExport
# ---------------------------------------------------------------------------


class TestReconcilerExport:
    """reconciler の公開 API が __init__.py からインポートできる。"""

    def test_exports(self) -> None:
        from miro_flow_maker import (
            ReconcileAction as A,
            ReconcileResult as R,
            reconcile as fn,
            backfill_miro_item_ids as bf,
        )

        assert A is ReconcileAction
        assert R is ReconcileResult
        assert fn is reconcile
        assert bf is backfill_miro_item_ids
