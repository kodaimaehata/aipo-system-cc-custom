"""metadata_helper.py のテスト。

metadata の全 key が存在すること、P0004 契約に準拠した値が生成されることを検証する。
"""

from __future__ import annotations

import json
from pathlib import Path

from miro_flow_maker.gate import validate
from miro_flow_maker.layout import build_drawing_plan
from miro_flow_maker.metadata_helper import (
    build_item_metadata,
    build_plan_metadata_map,
)
from miro_flow_maker.models import ItemMetadata, RequestContext

FIXTURES = Path(__file__).parent / "fixtures"

# P0004 metadata 契約で定義された全 key
_REQUIRED_METADATA_KEYS = frozenset({
    "managed_by",
    "project_id",
    "layer_id",
    "document_set_id",
    "flow_group_id",
    "semantic_type",
    "semantic_id",
    "render_role",
    "stable_item_id",
    "update_mode",
    "review_status",
    "confirmation_packet_ref",
    "confirmed_by_user",
})


def _load_confirmed_input():
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
    assert result.passed
    assert result.normalized_input is not None
    return result.normalized_input


class TestBuildItemMetadata:
    """build_item_metadata の単体テスト。"""

    def setup_method(self) -> None:
        self.meta = ItemMetadata(
            stable_item_id_prefix="flow-rep-01",
            managed_by="miro-flow-maker",
            update_mode="managed",
            project_id="P0006",
            layer_id="P0006-SG2",
            document_set_id="ds-rep-001",
            flow_group_id="flow-rep-01",
        )

    def test_all_required_keys_present(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="node",
            semantic_id="n-01",
            render_role="process_shape",
            confirmation_packet_ref="packets/cp-001.json",
        )
        assert set(result.keys()) == _REQUIRED_METADATA_KEYS

    def test_all_values_are_strings(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="node",
            semantic_id="n-01",
            render_role="process_shape",
            confirmation_packet_ref="packets/cp-001.json",
        )
        for key, value in result.items():
            assert isinstance(value, str), f"{key} is {type(value)}, expected str"

    def test_stable_item_id_format(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="node",
            semantic_id="n-01",
            render_role="process_shape",
            confirmation_packet_ref="packets/cp-001.json",
        )
        assert result["stable_item_id"] == "flow-rep-01:node:n-01:process_shape"

    def test_review_status_is_confirmed(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="lane",
            semantic_id="a-01",
            render_role="lane_shape",
            confirmation_packet_ref="packets/cp-001.json",
        )
        assert result["review_status"] == "confirmed"

    def test_metadata_values_from_item_metadata(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="node",
            semantic_id="n-01",
            render_role="process_shape",
            confirmation_packet_ref="packets/cp-001.json",
        )
        assert result["managed_by"] == "miro-flow-maker"
        assert result["project_id"] == "P0006"
        assert result["layer_id"] == "P0006-SG2"
        assert result["document_set_id"] == "ds-rep-001"
        assert result["flow_group_id"] == "flow-rep-01"
        assert result["update_mode"] == "managed"
        assert result["confirmation_packet_ref"] == "packets/cp-001.json"

    def test_semantic_fields_propagated(self) -> None:
        result = build_item_metadata(
            item_metadata=self.meta,
            semantic_type="connector",
            semantic_id="e-01",
            render_role="connector_line",
            confirmation_packet_ref="packets/cp-001.json",
        )
        assert result["semantic_type"] == "connector"
        assert result["semantic_id"] == "e-01"
        assert result["render_role"] == "connector_line"


class TestBuildPlanMetadataMap:
    """build_plan_metadata_map の代表ケーステスト。"""

    def setup_method(self) -> None:
        self.confirmed = _load_confirmed_input()
        self.plan = build_drawing_plan(self.confirmed, "Test Board")
        self.meta_map = build_plan_metadata_map(self.confirmed, self.plan)

    def test_returns_dict(self) -> None:
        assert isinstance(self.meta_map, dict)

    def test_all_plan_items_have_metadata(self) -> None:
        """plan 内の全 item (frame, lane, node, endpoint, system_label, connector) に metadata が存在すること。"""
        expected_ids: set[str] = {"frame"}
        for lp in self.plan.lanes:
            expected_ids.add(lp.id)
        for np_ in self.plan.nodes:
            expected_ids.add(np_.id)
        for ep in self.plan.endpoints:
            expected_ids.add(ep.id)
        for sl in self.plan.system_labels:
            expected_ids.add(sl.id)
        for cp in self.plan.connectors:
            expected_ids.add(cp.id)

        assert set(self.meta_map.keys()) == expected_ids

    def test_all_metadata_dicts_have_required_keys(self) -> None:
        for item_id, meta_dict in self.meta_map.items():
            assert set(meta_dict.keys()) == _REQUIRED_METADATA_KEYS, (
                f"Item {item_id} missing keys: "
                f"{_REQUIRED_METADATA_KEYS - set(meta_dict.keys())}"
            )

    def test_all_metadata_values_are_strings(self) -> None:
        for item_id, meta_dict in self.meta_map.items():
            for key, value in meta_dict.items():
                assert isinstance(value, str), (
                    f"Item {item_id} key {key} is {type(value)}"
                )

    def test_frame_metadata(self) -> None:
        frame_meta = self.meta_map["frame"]
        assert frame_meta["semantic_type"] == "flow_group"
        assert frame_meta["semantic_id"] == self.confirmed.flow_group_id
        assert frame_meta["render_role"] == "frame"

    def test_lane_metadata_semantic_type(self) -> None:
        for lp in self.plan.lanes:
            meta = self.meta_map[lp.id]
            # P0004: semantic_type は LaneDef.type に従う
            assert meta["semantic_type"] == lp.type
            assert meta["render_role"] == "lane_container"

    def test_node_metadata_render_roles(self) -> None:
        """全 node の render_role が一律 node_shape であること (P0004 契約)。"""
        for np_ in self.plan.nodes:
            meta = self.meta_map[np_.id]
            assert meta["semantic_type"] == "node"
            assert meta["render_role"] == "node_shape", (
                f"Node {np_.id} (type={np_.type}) render_role={meta['render_role']}, "
                f"expected node_shape"
            )

    def test_endpoint_metadata(self) -> None:
        for ep in self.plan.endpoints:
            meta = self.meta_map[ep.id]
            assert meta["semantic_type"] == "system_endpoint"
            assert meta["render_role"] == "endpoint_shape"
            # P0004: semantic_id は system_id そのまま
            assert meta["semantic_id"] == ep.system_id

    def test_system_label_metadata(self) -> None:
        """system_labels に対する metadata が生成されること。"""
        for sl in self.plan.system_labels:
            meta = self.meta_map[sl.id]
            assert meta["semantic_type"] == "system_endpoint"
            assert meta["render_role"] == "system_label"
            assert meta["semantic_id"] == sl.id  # node スコープで一意化

    def test_connector_metadata_uses_connection_def_id(self) -> None:
        """connector の semantic_id は ConnectionDef.id をそのまま使うこと。"""
        for cp in self.plan.connectors:
            meta = self.meta_map[cp.id]
            # P0004: semantic_type は ConnectorPlan.type に従う
            assert meta["semantic_type"] == cp.type
            assert meta["semantic_id"] == cp.id
            assert meta["render_role"] == "edge_connector"

    def test_review_status_all_confirmed(self) -> None:
        for item_id, meta_dict in self.meta_map.items():
            assert meta_dict["review_status"] == "confirmed"

    def test_confirmation_packet_ref_consistent(self) -> None:
        for item_id, meta_dict in self.meta_map.items():
            assert meta_dict["confirmation_packet_ref"] == self.confirmed.confirmation_packet_ref

    def test_project_and_layer_ids_consistent(self) -> None:
        for item_id, meta_dict in self.meta_map.items():
            assert meta_dict["project_id"] == self.confirmed.metadata.project_id
            assert meta_dict["layer_id"] == self.confirmed.metadata.layer_id

    def test_item_count(self) -> None:
        """代表ケース: frame(1) + lanes(3) + nodes(6) + system_labels(2) + endpoints(0) + connectors(8) = 20。"""
        assert len(self.meta_map) == 20

    def test_confirmed_by_user_present_and_true(self) -> None:
        """P0-2: confirmed_by_user が全 metadata に存在し 'true' であること。"""
        for item_id, meta_dict in self.meta_map.items():
            assert "confirmed_by_user" in meta_dict, (
                f"Item {item_id} missing confirmed_by_user"
            )
            assert meta_dict["confirmed_by_user"] == "true"
