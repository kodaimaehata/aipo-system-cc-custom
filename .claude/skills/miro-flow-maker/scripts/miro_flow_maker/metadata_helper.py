"""metadata 付与ヘルパーモジュール。

ConfirmedInput と DrawingPlan から run log 向けの metadata dict を生成する。
Miro API は呼ばない。Miro item にも付与しない。
SG3 (update/append) でも再利用する前提で設計する。
"""

from __future__ import annotations

from miro_flow_maker.gate import build_stable_item_id
from miro_flow_maker.layout import (
    ConnectorPlan,
    DrawingPlan,
    EndpointPlan,
    LanePlan,
    NodePlan,
    SystemLabelPlan,
)
from miro_flow_maker.models import ConfirmedInput, ItemMetadata


def build_item_metadata(
    item_metadata: ItemMetadata,
    semantic_type: str,
    semantic_id: str,
    render_role: str,
    confirmation_packet_ref: str,
    confirmed_by_user: bool = True,
) -> dict[str, str]:
    """P0004 metadata 契約に準拠した metadata dict を生成する。

    Returns:
        全 key を含む dict。run log / item_results に記録する用途。
    """
    stable_item_id = build_stable_item_id(
        flow_group_id=item_metadata.flow_group_id,
        semantic_type=semantic_type,
        semantic_id=semantic_id,
        render_role=render_role,
    )
    return {
        "managed_by": item_metadata.managed_by,
        "project_id": item_metadata.project_id,
        "layer_id": item_metadata.layer_id,
        "document_set_id": item_metadata.document_set_id,
        "flow_group_id": item_metadata.flow_group_id,
        "semantic_type": semantic_type,
        "semantic_id": semantic_id,
        "render_role": render_role,
        "stable_item_id": stable_item_id,
        "update_mode": item_metadata.update_mode,
        "review_status": "confirmed",
        "confirmation_packet_ref": confirmation_packet_ref,
        "confirmed_by_user": str(confirmed_by_user).lower(),
    }


# ---------------------------------------------------------------------------
# semantic_type / render_role マッピング (P0004 契約準拠)
# ---------------------------------------------------------------------------

_NODE_SEMANTIC_TYPE = "node"
_ENDPOINT_SEMANTIC_TYPE = "system_endpoint"

_LANE_RENDER_ROLE = "lane_container"
_NODE_RENDER_ROLE = "node_shape"
_ENDPOINT_RENDER_ROLE = "endpoint_shape"
_SYSTEM_LABEL_RENDER_ROLE = "system_label"
_CONNECTOR_RENDER_ROLE = "edge_connector"


def build_plan_metadata_map(
    confirmed_input: ConfirmedInput,
    plan: DrawingPlan,
) -> dict[str, dict[str, str]]:
    """DrawingPlan 内の各 item に対する metadata dict を生成する。

    Args:
        confirmed_input: review gate 通過済み入力。metadata と confirmation_packet_ref の源泉。
        plan: build_drawing_plan() で生成した描画計画。

    Returns:
        key = plan item の id, value = metadata dict の辞書。
        run log 書き出し時に参照する。
    """
    meta = confirmed_input.metadata
    cpref = confirmed_input.confirmation_packet_ref
    confirmed_by_user = confirmed_input.confirmed_by_user
    result: dict[str, dict[str, str]] = {}

    # --- frame ---
    result["frame"] = build_item_metadata(
        item_metadata=meta,
        semantic_type="flow_group",
        semantic_id=confirmed_input.flow_group_id,
        render_role="frame",
        confirmation_packet_ref=cpref,
        confirmed_by_user=confirmed_by_user,
    )

    # --- lanes ---
    for lane_plan in plan.lanes:
        result[lane_plan.id] = build_item_metadata(
            item_metadata=meta,
            semantic_type=lane_plan.type,
            semantic_id=lane_plan.semantic_id,
            render_role=_LANE_RENDER_ROLE,
            confirmation_packet_ref=cpref,
            confirmed_by_user=confirmed_by_user,
        )

    # --- nodes ---
    for node_plan in plan.nodes:
        result[node_plan.id] = build_item_metadata(
            item_metadata=meta,
            semantic_type=_NODE_SEMANTIC_TYPE,
            semantic_id=node_plan.semantic_id,
            render_role=_NODE_RENDER_ROLE,
            confirmation_packet_ref=cpref,
            confirmed_by_user=confirmed_by_user,
        )

    # --- endpoints ---
    for ep_plan in plan.endpoints:
        result[ep_plan.id] = build_item_metadata(
            item_metadata=meta,
            semantic_type=_ENDPOINT_SEMANTIC_TYPE,
            semantic_id=ep_plan.semantic_id,
            render_role=_ENDPOINT_RENDER_ROLE,
            confirmation_packet_ref=cpref,
            confirmed_by_user=confirmed_by_user,
        )

    # --- system_labels ---
    # semantic_id は sl_plan.id を使う（node スコープで一意化）
    # sl_plan.system_id だと同一 system への複数アクセスで stable_item_id が衝突する
    for sl_plan in plan.system_labels:
        result[sl_plan.id] = build_item_metadata(
            item_metadata=meta,
            semantic_type=_ENDPOINT_SEMANTIC_TYPE,
            semantic_id=sl_plan.id,
            render_role=_SYSTEM_LABEL_RENDER_ROLE,
            confirmation_packet_ref=cpref,
            confirmed_by_user=confirmed_by_user,
        )

    # --- connectors ---
    for conn_plan in plan.connectors:
        result[conn_plan.id] = build_item_metadata(
            item_metadata=meta,
            semantic_type=conn_plan.type,
            semantic_id=conn_plan.id,
            render_role=_CONNECTOR_RENDER_ROLE,
            confirmation_packet_ref=cpref,
            confirmed_by_user=confirmed_by_user,
        )

    return result
