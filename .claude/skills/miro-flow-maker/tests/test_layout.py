"""layout.py のテスト。

横スイムレーン + 左→右フローレイアウトの検証。
- 代表ケース（actor lane 3, system lane 0）
- 最小ケース（actor 1, node 1）
- 複数 system lane
- topological sort による列 rank
- SystemLabelPlan の生成
- 差戻し edge が rank 計算から除外されることの検証
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from miro_flow_maker.gate import validate
from miro_flow_maker.layout import (
    APPEND_GAP,
    FRAME_PADDING,
    LANE_HEIGHT,
    LANE_LABEL_WIDTH,
    NODE_GAP_X,
    NODE_HEIGHT,
    NODE_WIDTH,
    SYSTEM_LABEL_GAP,
    SYSTEM_LABEL_HEIGHT,
    SYSTEM_LABEL_WIDTH,
    ConnectorPlan,
    DrawingPlan,
    EndpointPlan,
    FramePlan,
    LanePlan,
    NodePlan,
    SystemLabelPlan,
    build_drawing_plan,
    compute_required_append_frame_size,
    _compute_ranks,
)
from miro_flow_maker.models import (
    ConfirmedInput,
    ConnectionDef,
    DocumentSet,
    ItemMetadata,
    LaneDef,
    NodeDef,
    RequestContext,
    SourceEvidence,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_confirmed_input():
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
        dry_run=True,
        input_path=str(FIXTURES / "confirmed_representative.json"),
    )
    result = validate(input_data, context)
    assert result.passed, f"validate failed: {result.stop_reasons}"
    assert result.normalized_input is not None
    return result.normalized_input


# ---------------------------------------------------------------------------
# 代表ケーステスト: 横スイムレーンレイアウト
# ---------------------------------------------------------------------------


class TestBuildDrawingPlan:
    """build_drawing_plan の代表ケーステスト（横スイムレーン + 左→右フロー）。"""

    def setup_method(self) -> None:
        self.confirmed = _load_confirmed_input()
        self.plan = build_drawing_plan(self.confirmed, "Test Board")

    # --- 基本構造 ---

    def test_returns_drawing_plan(self) -> None:
        assert isinstance(self.plan, DrawingPlan)

    def test_board_name(self) -> None:
        assert self.plan.board_name == "Test Board"

    # --- frame ---

    def test_frame_title_is_flow_group_label(self) -> None:
        assert self.plan.frame.title == self.confirmed.flow_group_label

    def test_frame_contains_all_lanes(self) -> None:
        """frame が全 lane を包含していること。"""
        frame = self.plan.frame
        for lane in self.plan.lanes:
            assert lane.x >= frame.x
            assert lane.y >= frame.y
            assert lane.x + lane.width <= frame.x + frame.width
            assert lane.y + lane.height <= frame.y + frame.height

    def test_frame_contains_all_nodes(self) -> None:
        """frame が全 node を包含していること。"""
        frame = self.plan.frame
        for node in self.plan.nodes:
            assert node.x >= frame.x
            assert node.y >= frame.y
            assert node.x + node.width <= frame.x + frame.width
            assert node.y + node.height <= frame.y + frame.height

    # --- lanes: 横スイムレーン配置 ---

    def test_total_lane_count(self) -> None:
        """actor 3 + system 0 = 3 lane。"""
        assert len(self.plan.lanes) == 3

    def test_actor_lane_count(self) -> None:
        actor_lanes = [lp for lp in self.plan.lanes if lp.type == "actor_lane"]
        assert len(actor_lanes) == 3

    def test_system_lane_count(self) -> None:
        system_lanes = [lp for lp in self.plan.lanes if lp.type == "system_lane"]
        assert len(system_lanes) == 0

    def test_lanes_are_horizontal_rows(self) -> None:
        """全 lane が水平行として配置されていること（x=0, 同一幅）。"""
        for lp in self.plan.lanes:
            assert lp.x == 0.0, f"Lane {lp.id} x={lp.x} != 0"
        widths = {lp.width for lp in self.plan.lanes}
        assert len(widths) == 1, f"Lanes have different widths: {widths}"

    def test_lanes_arranged_top_to_bottom(self) -> None:
        """lane が上から下に並んでいること。"""
        ys = [lp.y for lp in self.plan.lanes]
        assert ys == sorted(ys)
        # 隣接する lane が重ならない
        for i in range(1, len(ys)):
            prev_bottom = self.plan.lanes[i - 1].y + self.plan.lanes[i - 1].height
            assert ys[i] >= prev_bottom

    def test_lanes_have_uniform_height(self) -> None:
        heights = {lp.height for lp in self.plan.lanes}
        assert len(heights) == 1, f"Lanes have different heights: {heights}"

    def test_lane_height_at_least_minimum(self) -> None:
        for lp in self.plan.lanes:
            assert lp.height >= LANE_HEIGHT

    def test_actor_lanes_before_system_lanes(self) -> None:
        """actor lane が system lane より上に配置されていること。"""
        actor_lanes = [lp for lp in self.plan.lanes if lp.type == "actor_lane"]
        system_lanes = [lp for lp in self.plan.lanes if lp.type == "system_lane"]
        if actor_lanes and system_lanes:
            max_actor_y = max(lp.y for lp in actor_lanes)
            min_system_y = min(lp.y for lp in system_lanes)
            assert max_actor_y < min_system_y

    def test_lane_semantic_ids(self) -> None:
        for lp in self.plan.lanes:
            assert lp.semantic_id == lp.id

    # --- nodes: 左→右配置 ---

    def test_node_count(self) -> None:
        assert len(self.plan.nodes) == 6

    def test_node_types_present(self) -> None:
        types = {np.type for np in self.plan.nodes}
        assert types == {"start", "process", "decision", "end"}

    def test_nodes_within_their_lane(self) -> None:
        lane_map = {lp.id: lp for lp in self.plan.lanes}
        for np_ in self.plan.nodes:
            lane = lane_map[np_.lane_id]
            assert np_.x >= lane.x, f"node {np_.id} x={np_.x} < lane x={lane.x}"
            assert np_.y >= lane.y, f"node {np_.id} y={np_.y} < lane y={lane.y}"
            assert np_.x + np_.width <= lane.x + lane.width, (
                f"node {np_.id} right edge exceeds lane {lane.id}"
            )
            assert np_.y + np_.height <= lane.y + lane.height, (
                f"node {np_.id} bottom edge exceeds lane {lane.id}"
            )

    def test_nodes_placed_left_to_right_by_rank(self) -> None:
        """business_flow DAG の rank 順に左→右に配置されていること。"""
        ranks = _compute_ranks(self.confirmed.nodes, self.confirmed.connections)
        node_map = {np_.id: np_ for np_ in self.plan.nodes}
        # rank が小さいノードは x が小さいか等しい
        for n1 in self.confirmed.nodes:
            for n2 in self.confirmed.nodes:
                if ranks[n1.id] < ranks[n2.id]:
                    assert node_map[n1.id].x < node_map[n2.id].x, (
                        f"node {n1.id} (rank {ranks[n1.id]}, x={node_map[n1.id].x}) "
                        f"should be left of {n2.id} (rank {ranks[n2.id]}, x={node_map[n2.id].x})"
                    )

    def test_nodes_in_label_area_right_of_lane_label(self) -> None:
        """全ノードが LANE_LABEL_WIDTH より右に配置されていること。"""
        for np_ in self.plan.nodes:
            assert np_.x >= LANE_LABEL_WIDTH, (
                f"node {np_.id} x={np_.x} overlaps lane label area"
            )

    def test_node_dimensions(self) -> None:
        for np_ in self.plan.nodes:
            assert np_.width == NODE_WIDTH
            assert np_.height == NODE_HEIGHT

    def test_node_semantic_ids(self) -> None:
        for np_ in self.plan.nodes:
            assert np_.semantic_id == np_.id

    # --- endpoints: 空（後方互換） ---

    def test_endpoints_empty(self) -> None:
        """endpoints は空リスト（SystemLabelPlan に置き換え）。"""
        assert self.plan.endpoints == []

    # --- system_labels ---

    def test_system_labels_generated(self) -> None:
        """system_access から SystemLabelPlan が生成されること。"""
        assert len(self.plan.system_labels) > 0

    def test_system_label_count(self) -> None:
        """代表ケース: 2 つの system_access（fill-form->erp, accounting->erp）→ 2 SystemLabel。"""
        assert len(self.plan.system_labels) == 2

    def test_system_label_ids(self) -> None:
        """SystemLabelPlan の id が 'sl-{node_id}-{system_id}' 形式であること。"""
        for sl in self.plan.system_labels:
            assert sl.id == f"sl-{sl.node_id}-{sl.system_id}"

    def test_system_label_placed_below_node(self) -> None:
        """SystemLabel が対応ノードの直下に配置されていること。"""
        node_map = {np_.id: np_ for np_ in self.plan.nodes}
        for sl in self.plan.system_labels:
            node = node_map[sl.node_id]
            assert sl.y >= node.y + node.height, (
                f"SystemLabel {sl.id} y={sl.y} not below node {sl.node_id} bottom={node.y + node.height}"
            )

    def test_system_label_dimensions(self) -> None:
        for sl in self.plan.system_labels:
            assert sl.width == SYSTEM_LABEL_WIDTH
            assert sl.height == SYSTEM_LABEL_HEIGHT

    def test_system_label_has_system_lane_label(self) -> None:
        """SystemLabel の label が system lane の label であること。"""
        for sl in self.plan.system_labels:
            assert sl.label == "ERP システム"

    # --- connectors ---

    def test_connector_count(self) -> None:
        """business_flow 6 + system_access 2 = 8 connector。"""
        assert len(self.plan.connectors) == 8

    def test_business_flow_connectors(self) -> None:
        biz = [c for c in self.plan.connectors if c.type == "business_flow"]
        assert len(biz) == 6

    def test_system_access_connectors(self) -> None:
        sa = [c for c in self.plan.connectors if c.type == "system_access"]
        assert len(sa) == 2

    def test_connector_ids_match_connection_def_ids(self) -> None:
        """connector の id は ConnectionDef.id をそのまま使うこと。"""
        conn_ids = {c.id for c in self.confirmed.connections}
        plan_ids = {c.id for c in self.plan.connectors}
        assert plan_ids == conn_ids

    def test_system_access_connector_to_system_label(self) -> None:
        """system_access connector の to_plan_id が SystemLabelPlan の id であること。"""
        sl_ids = {sl.id for sl in self.plan.system_labels}
        sa_connectors = [c for c in self.plan.connectors if c.type == "system_access"]
        for c in sa_connectors:
            assert c.to_plan_id in sl_ids, (
                f"system_access connector {c.id} to_plan_id={c.to_plan_id} "
                f"not in system_label ids {sl_ids}"
            )


# ---------------------------------------------------------------------------
# Topological sort / rank テスト
# ---------------------------------------------------------------------------


class TestComputeRanks:
    """_compute_ranks の列 rank 検証。"""

    def test_linear_chain(self) -> None:
        """直線的なフロー: A -> B -> C -> D。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="process", label="B", actor_id="a1"),
            NodeDef(id="C", type="process", label="C", actor_id="a1"),
            NodeDef(id="D", type="end", label="D", actor_id="a1"),
        ]
        connections = [
            ConnectionDef(id="e1", from_id="A", to_id="B", type="business_flow", label=""),
            ConnectionDef(id="e2", from_id="B", to_id="C", type="business_flow", label=""),
            ConnectionDef(id="e3", from_id="C", to_id="D", type="business_flow", label=""),
        ]
        ranks = _compute_ranks(nodes, connections)
        assert ranks["A"] == 0
        assert ranks["B"] == 1
        assert ranks["C"] == 2
        assert ranks["D"] == 3

    def test_branching(self) -> None:
        """分岐: A -> B, A -> C。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="process", label="B", actor_id="a1"),
            NodeDef(id="C", type="process", label="C", actor_id="a1"),
        ]
        connections = [
            ConnectionDef(id="e1", from_id="A", to_id="B", type="business_flow", label=""),
            ConnectionDef(id="e2", from_id="A", to_id="C", type="business_flow", label=""),
        ]
        ranks = _compute_ranks(nodes, connections)
        assert ranks["A"] == 0
        assert ranks["B"] == 1
        assert ranks["C"] == 1

    def test_merge(self) -> None:
        """合流: A -> C, B -> C。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="start", label="B", actor_id="a1"),
            NodeDef(id="C", type="end", label="C", actor_id="a1"),
        ]
        connections = [
            ConnectionDef(id="e1", from_id="A", to_id="C", type="business_flow", label=""),
            ConnectionDef(id="e2", from_id="B", to_id="C", type="business_flow", label=""),
        ]
        ranks = _compute_ranks(nodes, connections)
        assert ranks["A"] == 0
        assert ranks["B"] == 0
        assert ranks["C"] == 1

    def test_no_edges(self) -> None:
        """edge なし: 全ノードが rank 0。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="end", label="B", actor_id="a1"),
        ]
        ranks = _compute_ranks(nodes, [])
        assert ranks["A"] == 0
        assert ranks["B"] == 0

    def test_system_access_ignored(self) -> None:
        """system_access edge は rank 計算に含まれない。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="process", label="B", actor_id="a1"),
        ]
        connections = [
            ConnectionDef(id="e1", from_id="A", to_id="B", type="business_flow", label=""),
            ConnectionDef(
                id="sa1", from_id="B", to_id="s-sys",
                type="system_access", label="", system_id="s-sys",
            ),
        ]
        ranks = _compute_ranks(nodes, connections)
        assert ranks["A"] == 0
        assert ranks["B"] == 1


# ---------------------------------------------------------------------------
# 差戻し edge テスト
# ---------------------------------------------------------------------------


class TestBackEdgeExclusion:
    """差戻し edge（rank 逆行）が rank 計算から除外されることの検証。"""

    def test_back_edge_excluded_from_rank(self) -> None:
        """A -> B -> C -> D, C -> B (差戻し)。C->B は除外される。"""
        nodes = [
            NodeDef(id="A", type="start", label="A", actor_id="a1"),
            NodeDef(id="B", type="process", label="B", actor_id="a1"),
            NodeDef(id="C", type="decision", label="C", actor_id="a1"),
            NodeDef(id="D", type="end", label="D", actor_id="a1"),
        ]
        connections = [
            ConnectionDef(id="e1", from_id="A", to_id="B", type="business_flow", label=""),
            ConnectionDef(id="e2", from_id="B", to_id="C", type="business_flow", label=""),
            ConnectionDef(id="e3", from_id="C", to_id="D", type="business_flow", label="承認"),
            ConnectionDef(id="e4", from_id="C", to_id="B", type="business_flow", label="差戻"),
        ]
        ranks = _compute_ranks(nodes, connections)
        # C->B は差戻し。B の rank は A の次（rank 1）のまま
        assert ranks["A"] == 0
        assert ranks["B"] == 1
        assert ranks["C"] == 2
        assert ranks["D"] == 3

    def test_representative_case_back_edge(self) -> None:
        """代表ケースの差戻し edge (approve-check -> fill-form) が除外されること。"""
        confirmed = _load_confirmed_input()
        ranks = _compute_ranks(confirmed.nodes, confirmed.connections)
        # n-approve-check -> n-fill-form は差戻し
        # n-fill-form は rank 1, n-approve-check は rank 3
        assert ranks["n-start"] < ranks["n-fill-form"]
        assert ranks["n-fill-form"] < ranks["n-review"]
        assert ranks["n-review"] < ranks["n-approve-check"]
        assert ranks["n-approve-check"] < ranks["n-accounting-process"]
        assert ranks["n-accounting-process"] < ranks["n-end"]

    def test_back_edge_does_not_affect_forward_rank(self) -> None:
        """差戻し edge があっても forward ノードの rank は連続すること。"""
        confirmed = _load_confirmed_input()
        ranks = _compute_ranks(confirmed.nodes, confirmed.connections)
        assert ranks["n-start"] == 0
        assert ranks["n-fill-form"] == 1
        assert ranks["n-review"] == 2
        assert ranks["n-approve-check"] == 3
        assert ranks["n-accounting-process"] == 4
        assert ranks["n-end"] == 5


# ---------------------------------------------------------------------------
# SystemLabelPlan 生成テスト
# ---------------------------------------------------------------------------


class TestSystemLabelPlan:
    """SystemLabelPlan の生成検証。"""

    def test_system_label_for_single_access(self) -> None:
        """1 ノードに 1 system_access の場合。"""
        confirmed = ConfirmedInput(
            flow_group_id="flow-sl-test",
            flow_group_label="SystemLabel テスト",
            document_set=DocumentSet(id="ds-sl", label="SL test"),
            nodes=[
                NodeDef(id="n1", type="start", label="開始", actor_id="a1"),
                NodeDef(id="n2", type="process", label="処理", actor_id="a1"),
            ],
            connections=[
                ConnectionDef(id="e1", from_id="n1", to_id="n2", type="business_flow", label=""),
                ConnectionDef(
                    id="sa1", from_id="n2", to_id="s-db",
                    type="system_access", label="DB登録",
                    system_id="s-db", action="insert",
                ),
            ],
            lanes=[
                LaneDef(id="a1", type="actor_lane", label="担当者", kind="person"),
                LaneDef(id="s-db", type="system_lane", label="データベース", kind="internal_system"),
            ],
            metadata=ItemMetadata(
                stable_item_id_prefix="flow-sl-test",
                managed_by="miro-flow-maker",
                update_mode="managed",
                project_id="P0007",
                layer_id="P0007-SG1",
                document_set_id="ds-sl",
                flow_group_id="flow-sl-test",
            ),
            confirmation_packet_ref="packets/cp-sl.json",
            source_evidence=[SourceEvidence(ref="docs/spec.md", description="仕様書")],
        )
        plan = build_drawing_plan(confirmed, "SL Test")
        assert len(plan.system_labels) == 1
        sl = plan.system_labels[0]
        assert sl.id == "sl-n2-s-db"
        assert sl.label == "データベース"
        assert sl.node_id == "n2"
        assert sl.system_id == "s-db"
        assert sl.width == SYSTEM_LABEL_WIDTH
        assert sl.height == SYSTEM_LABEL_HEIGHT

    def test_multiple_system_access_per_node(self) -> None:
        """1 ノードに複数 system_access がある場合、縦に並ぶこと。"""
        confirmed = ConfirmedInput(
            flow_group_id="flow-multi-sa",
            flow_group_label="Multi SA テスト",
            document_set=DocumentSet(id="ds-msa", label="Multi SA"),
            nodes=[
                NodeDef(id="n1", type="process", label="処理", actor_id="a1"),
            ],
            connections=[
                ConnectionDef(
                    id="sa1", from_id="n1", to_id="s-db",
                    type="system_access", label="DB登録",
                    system_id="s-db", action="insert",
                ),
                ConnectionDef(
                    id="sa2", from_id="n1", to_id="s-mail",
                    type="system_access", label="メール送信",
                    system_id="s-mail", action="send",
                ),
            ],
            lanes=[
                LaneDef(id="a1", type="actor_lane", label="担当者", kind="person"),
                LaneDef(id="s-db", type="system_lane", label="DB", kind="internal_system"),
                LaneDef(id="s-mail", type="system_lane", label="メール", kind="external_system"),
            ],
            metadata=ItemMetadata(
                stable_item_id_prefix="flow-multi-sa",
                managed_by="miro-flow-maker",
                update_mode="managed",
                project_id="P0007",
                layer_id="P0007-SG1",
                document_set_id="ds-msa",
                flow_group_id="flow-multi-sa",
            ),
            confirmation_packet_ref="packets/cp-msa.json",
            source_evidence=[SourceEvidence(ref="docs/spec.md", description="仕様書")],
        )
        plan = build_drawing_plan(confirmed, "Multi SA")
        assert len(plan.system_labels) == 2
        # 縦に並んでいること（2 番目の y > 1 番目の y）
        sls = sorted(plan.system_labels, key=lambda s: s.y)
        assert sls[0].y < sls[1].y
        # 2 番目は 1 番目の直下
        expected_y = sls[0].y + SYSTEM_LABEL_HEIGHT + SYSTEM_LABEL_GAP
        assert abs(sls[1].y - expected_y) < 0.01

    def test_no_system_access_no_system_labels(self) -> None:
        """system_access がない場合、system_labels は空。"""
        confirmed = ConfirmedInput(
            flow_group_id="flow-no-sa",
            flow_group_label="No SA テスト",
            document_set=DocumentSet(id="ds-no-sa", label="No SA"),
            nodes=[
                NodeDef(id="n1", type="start", label="開始", actor_id="a1"),
            ],
            connections=[],
            lanes=[
                LaneDef(id="a1", type="actor_lane", label="担当者", kind="person"),
            ],
            metadata=ItemMetadata(
                stable_item_id_prefix="flow-no-sa",
                managed_by="miro-flow-maker",
                update_mode="managed",
                project_id="P0007",
                layer_id="P0007-SG1",
                document_set_id="ds-no-sa",
                flow_group_id="flow-no-sa",
            ),
            confirmation_packet_ref="packets/cp-no-sa.json",
            source_evidence=[SourceEvidence(ref="docs/spec.md", description="仕様書")],
        )
        plan = build_drawing_plan(confirmed, "No SA")
        assert plan.system_labels == []


# ---------------------------------------------------------------------------
# 最小ケーステスト
# ---------------------------------------------------------------------------


class TestMinimalCase:
    """最小ケース（actor 1, node 1, no connections）。"""

    def test_minimal_produces_valid_plan(self) -> None:
        input_data = json.loads(
            (FIXTURES / "confirmed_minimal.json").read_text(encoding="utf-8")
        )
        context = RequestContext(
            mode="create",
            board_id=None,
            frame_id=None,
            frame_link=None,
            board_name="Minimal",
            dry_run=True,
            input_path=str(FIXTURES / "confirmed_minimal.json"),
        )
        result = validate(input_data, context)
        assert result.passed
        assert result.normalized_input is not None

        plan = build_drawing_plan(result.normalized_input, "Minimal")

        assert isinstance(plan, DrawingPlan)
        assert plan.board_name == "Minimal"
        assert len(plan.lanes) == 1
        assert len(plan.nodes) == 1
        assert len(plan.endpoints) == 0
        assert len(plan.system_labels) == 0
        assert len(plan.connectors) == 0
        # lane は水平行
        assert plan.lanes[0].x == 0.0
        assert plan.lanes[0].height >= LANE_HEIGHT
        # node は lane 内
        node = plan.nodes[0]
        lane = plan.lanes[0]
        assert node.x >= lane.x
        assert node.y >= lane.y
        assert node.x + node.width <= lane.x + lane.width
        assert node.y + node.height <= lane.y + lane.height
        # frame は node を包含する
        assert node.x >= plan.frame.x
        assert node.y >= plan.frame.y


# ---------------------------------------------------------------------------
# 複数 system lane テスト
# ---------------------------------------------------------------------------


def _make_multi_system_input() -> ConfirmedInput:
    """2 つの system lane を持つ ConfirmedInput を構築する。"""
    return ConfirmedInput(
        flow_group_id="flow-multi-sys",
        flow_group_label="複数システムフロー",
        document_set=DocumentSet(id="ds-ms-001", label="Multi-system docs"),
        nodes=[
            NodeDef(id="n-start", type="start", label="開始", actor_id="a-user"),
            NodeDef(id="n-process", type="process", label="処理", actor_id="a-user"),
            NodeDef(id="n-end", type="end", label="完了", actor_id="a-user"),
        ],
        connections=[
            ConnectionDef(
                id="e-01", from_id="n-start", to_id="n-process",
                type="business_flow", label="",
            ),
            ConnectionDef(
                id="e-02", from_id="n-process", to_id="n-end",
                type="business_flow", label="",
            ),
            ConnectionDef(
                id="sa-01", from_id="n-process", to_id="s-db",
                type="system_access", label="DB 登録",
                system_id="s-db", action="insert",
            ),
            ConnectionDef(
                id="sa-02", from_id="n-process", to_id="s-mail",
                type="system_access", label="メール送信",
                system_id="s-mail", action="send",
            ),
        ],
        lanes=[
            LaneDef(id="a-user", type="actor_lane", label="ユーザー", kind="person"),
            LaneDef(id="s-db", type="system_lane", label="DB", kind="internal_system"),
            LaneDef(id="s-mail", type="system_lane", label="メールサーバー", kind="external_system"),
        ],
        metadata=ItemMetadata(
            stable_item_id_prefix="flow-multi-sys",
            managed_by="miro-flow-maker",
            update_mode="managed",
            project_id="P0007",
            layer_id="P0007-SG1",
            document_set_id="ds-ms-001",
            flow_group_id="flow-multi-sys",
        ),
        confirmation_packet_ref="packets/cp-ms-001.json",
        source_evidence=[
            SourceEvidence(ref="docs/spec.md", description="仕様書"),
        ],
    )


class TestMultipleSystemLanes:
    """複数 system lane がある場合のレイアウトテスト。"""

    def setup_method(self) -> None:
        self.confirmed = _make_multi_system_input()
        self.plan = build_drawing_plan(self.confirmed, "Multi-System Board")

    def test_only_actor_lanes(self) -> None:
        """system lane は除外され actor lane のみ配置。"""
        assert len(self.plan.lanes) == 1
        assert all(lp.type == "actor_lane" for lp in self.plan.lanes)

    def test_no_system_lanes(self) -> None:
        system_lanes = [lp for lp in self.plan.lanes if lp.type == "system_lane"]
        assert len(system_lanes) == 0

    def test_system_labels_for_multi_system(self) -> None:
        """n-process が 2 system にアクセス → 2 SystemLabel。"""
        assert len(self.plan.system_labels) == 2
        sys_ids = {sl.system_id for sl in self.plan.system_labels}
        assert sys_ids == {"s-db", "s-mail"}

    def test_endpoints_empty(self) -> None:
        """endpoints は空リスト。"""
        assert self.plan.endpoints == []

    def test_frame_contains_all_items(self) -> None:
        """frame が全 item を包含すること。"""
        frame = self.plan.frame
        for lp in self.plan.lanes:
            assert lp.x >= frame.x
            assert lp.y >= frame.y
            assert lp.x + lp.width <= frame.x + frame.width
            assert lp.y + lp.height <= frame.y + frame.height


# ---------------------------------------------------------------------------
# 既存 fixture 変換テスト
# ---------------------------------------------------------------------------


class TestFixtureConversion:
    """既存 fixture (confirmed_representative.json) をそのまま変換できることの検証。"""

    def test_representative_fixture_converts_without_error(self) -> None:
        """代表ケース fixture が例外なく DrawingPlan に変換できること。"""
        confirmed = _load_confirmed_input()
        plan = build_drawing_plan(confirmed, "Representative")
        assert isinstance(plan, DrawingPlan)
        assert plan.board_name == "Representative"

    def test_representative_all_nodes_placed(self) -> None:
        """代表ケースの全 6 ノードが配置されること。"""
        confirmed = _load_confirmed_input()
        plan = build_drawing_plan(confirmed, "Representative")
        assert len(plan.nodes) == 6
        node_ids = {np_.id for np_ in plan.nodes}
        expected = {"n-start", "n-fill-form", "n-review", "n-approve-check", "n-accounting-process", "n-end"}
        assert node_ids == expected

    def test_representative_all_connectors_present(self) -> None:
        """代表ケースの全 8 connector が生成されること。"""
        confirmed = _load_confirmed_input()
        plan = build_drawing_plan(confirmed, "Representative")
        assert len(plan.connectors) == 8

    def test_representative_system_labels_present(self) -> None:
        """代表ケースで SystemLabel が 2 つ生成されること (fill-form, accounting-process)。"""
        confirmed = _load_confirmed_input()
        plan = build_drawing_plan(confirmed, "Representative")
        assert len(plan.system_labels) == 2
        node_ids = {sl.node_id for sl in plan.system_labels}
        assert node_ids == {"n-fill-form", "n-accounting-process"}

    def test_minimal_fixture_converts_without_error(self) -> None:
        """最小ケース fixture が例外なく DrawingPlan に変換できること。"""
        input_data = json.loads(
            (FIXTURES / "confirmed_minimal.json").read_text(encoding="utf-8")
        )
        context = RequestContext(
            mode="create",
            board_id=None,
            frame_id=None,
            frame_link=None,
            board_name="Minimal",
            dry_run=True,
            input_path=str(FIXTURES / "confirmed_minimal.json"),
        )
        result = validate(input_data, context)
        assert result.passed
        plan = build_drawing_plan(result.normalized_input, "Minimal")
        assert isinstance(plan, DrawingPlan)


# ---------------------------------------------------------------------------
# compute_required_append_frame_size テスト
# ---------------------------------------------------------------------------


def _make_plan_with_frame(width: float, height: float) -> DrawingPlan:
    """テスト用: width / height のみ指定した最小 DrawingPlan を返す。"""
    return DrawingPlan(
        board_name="test",
        frame=FramePlan(
            title="test",
            x=0.0,
            y=0.0,
            width=width,
            height=height,
        ),
    )


class TestComputeRequiredAppendFrameSize:
    """compute_required_append_frame_size の挙動検証。"""

    def test_content_fits_within_current_frame(self) -> None:
        """既存 frame が十分大きい & 占有領域にも余裕がある場合、現在値がそのまま返る。"""
        # 現在 frame: 中心 (500, 400), サイズ 2000x1000
        # 左上 = (-500, -100), 右下 = (1500, 900)
        current_frame = {
            "position": {"x": 500.0, "y": 400.0},
            "geometry": {"width": 2000.0, "height": 1000.0},
        }
        # 新規コンテンツ frame.width=100 は既存幅 2000 より小さい。
        # 占有下端 200 + APPEND_GAP 60 + plan.frame.height 100 = 360 < 1000
        # plan.frame.width/height は build_drawing_plan 内で既に padding 込み。
        plan = _make_plan_with_frame(width=100.0, height=100.0)
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=200.0, current_frame=current_frame
        )
        assert cx == 500.0
        assert cy == 400.0
        assert w == 2000.0
        assert h == 1000.0

    def test_height_exceeds_extends_down(self) -> None:
        """高さが不足する場合、高さを拡張し center_y を下方向にシフトする。"""
        # 現在 frame: 中心 (400, 425), サイズ 800x850
        # 左上 = (0, 0)
        current_frame = {
            "position": {"x": 400.0, "y": 425.0},
            "geometry": {"width": 800.0, "height": 850.0},
        }
        # occupied_bottom=700, plan.frame.height=400, APPEND_GAP=60
        # req_h = max(850, 700 + 60 + 400) = max(850, 1160) = 1160
        # plan.frame.width=200 → req_w = max(800, 200) = 800（拡張なし）
        plan = _make_plan_with_frame(width=200.0, height=400.0)
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=700.0, current_frame=current_frame
        )
        assert w == 800.0
        assert h == 1160.0
        # 左上固定: left=0, top=0 → new_cx = 0 + 800/2 = 400
        assert cx == 400.0
        # new_cy = 0 + 1160/2 = 580
        assert cy == 580.0

    def test_width_exceeds_extends_right(self) -> None:
        """新規コンテンツの width が既存より広ければ width を拡張し center_x を右にシフト。"""
        # 現在 frame: 中心 (300, 200), サイズ 600x400
        # 左上 = (0, 0)
        current_frame = {
            "position": {"x": 300.0, "y": 200.0},
            "geometry": {"width": 600.0, "height": 400.0},
        }
        # plan.frame.width=800 → req_w = max(600, 800) = 800
        # plan.frame.height=50, occupied_bottom=0 → req_h = max(400, 0 + 60 + 50) = 400
        plan = _make_plan_with_frame(width=800.0, height=50.0)
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=0.0, current_frame=current_frame
        )
        assert w == 800.0
        assert h == 400.0
        # 左上固定: left=0, top=0 → new_cx = 0 + 800/2 = 400
        assert cx == 400.0
        # new_cy = 0 + 400/2 = 200（変わらず）
        assert cy == 200.0

    def test_empty_current_frame_dict(self) -> None:
        """current_frame={} の場合も例外なく 0 基準で計算できる。"""
        plan = _make_plan_with_frame(width=300.0, height=200.0)
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=0.0, current_frame={}
        )
        # cur_* はすべて 0, left=top=0
        # req_w = max(0, 300) = 300
        # req_h = max(0, 0 + 60 + 200) = 260
        assert w == 300.0
        assert h == 260.0
        # center = (0 + w/2, 0 + h/2) = (150, 130)
        assert cx == 150.0
        assert cy == 130.0

    def test_negative_occupied_bottom(self) -> None:
        """occupied_bottom<0 は 0 として扱う（防御的）。"""
        current_frame = {
            "position": {"x": 0.0, "y": 0.0},
            "geometry": {"width": 500.0, "height": 500.0},
        }
        plan = _make_plan_with_frame(width=100.0, height=100.0)
        # occupied_bottom=-10 → 0 として扱う → req_h = max(500, 0+60+100)=max(500,160)=500
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=-10.0, current_frame=current_frame
        )
        assert w == 500.0
        assert h == 500.0
        # 現在値のまま
        assert cx == 0.0
        assert cy == 0.0

    def test_both_dimensions_exceed(self) -> None:
        """width と height の両方で拡張が必要な場合、両方拡張し center が両方向にシフト。"""
        # 現在 frame: 中心 (100, 100), サイズ 200x200
        # 左上 = (0, 0)
        current_frame = {
            "position": {"x": 100.0, "y": 100.0},
            "geometry": {"width": 200.0, "height": 200.0},
        }
        # plan.frame.width=500 → req_w = max(200, 500) = 500
        # occupied_bottom=150, plan.frame.height=300
        # req_h = max(200, 150 + 60 + 300) = max(200, 510) = 510
        plan = _make_plan_with_frame(width=500.0, height=300.0)
        cx, cy, w, h = compute_required_append_frame_size(
            plan, occupied_bottom=150.0, current_frame=current_frame
        )
        assert w == 500.0
        assert h == 510.0
        # 左上固定: left=0, top=0
        assert cx == 250.0  # 0 + 500/2
        assert cy == 255.0  # 0 + 510/2
