"""review gate 検証モジュール。

confirmed 入力を検証し、通過可否と正規化済み入力を返す。
"""

from __future__ import annotations

from miro_flow_maker.models import (
    ConfirmedInput,
    ConnectionDef,
    DocumentSet,
    ItemMetadata,
    LaneDef,
    NodeDef,
    RequestContext,
    ReviewResult,
    SourceEvidence,
)

_NODE_TYPES = frozenset({"start", "process", "decision", "end"})
_EDGE_TYPES = frozenset({"business_flow"})


def _as_dict(value: object, path: str, stop_reasons: list[str]) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    stop_reasons.append(f"{path} must be an object")
    return None


def _as_list(value: object, path: str, stop_reasons: list[str]) -> list[object]:
    if isinstance(value, list):
        return value
    stop_reasons.append(f"{path} must be a list")
    return []


def _required_non_empty_str(
    value: object,
    path: str,
    stop_reasons: list[str],
) -> str | None:
    if not isinstance(value, str):
        stop_reasons.append(f"{path} must be a string")
        return None
    stripped = value.strip()
    if not stripped:
        stop_reasons.append(f"{path} is missing")
        return None
    return stripped


def _optional_label(value: object, path: str, stop_reasons: list[str]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        stop_reasons.append(f"{path} must be a string")
        return ""
    return value.strip()


def validate(
    input_data: dict,
    request_context: RequestContext,
) -> ReviewResult:
    """
    confirmed 入力を検証し、通過可否と正規化済み入力を返す。
    通過しない場合は stop_reasons に理由を列挙する。

    """
    stop_reasons: list[str] = []
    if not isinstance(input_data, dict):
        return ReviewResult(
            passed=False,
            stop_reasons=["input must be a JSON object"],
            normalized_input=None,
        )

    status = input_data.get("status")
    if status != "confirmed":
        stop_reasons.append(f"status is {status!r}, expected 'confirmed'")

    confirmation_packet_ref = _required_non_empty_str(
        input_data.get("confirmation_packet_ref"),
        "confirmation_packet_ref",
        stop_reasons,
    )

    document_set_raw = _as_dict(input_data.get("document_set"), "document_set", stop_reasons)
    flow_group_raw = _as_dict(input_data.get("flow_group"), "flow_group", stop_reasons)
    metadata_raw = _as_dict(input_data.get("metadata"), "metadata", stop_reasons)

    actors_raw = _as_list(input_data.get("actors"), "actors", stop_reasons)
    systems_raw = _as_list(input_data.get("systems"), "systems", stop_reasons)
    nodes_raw = _as_list(input_data.get("nodes"), "nodes", stop_reasons)
    edges_raw = _as_list(input_data.get("edges"), "edges", stop_reasons)
    system_accesses_raw = _as_list(
        input_data.get("system_accesses"),
        "system_accesses",
        stop_reasons,
    )
    source_evidence_raw = _as_list(
        input_data.get("source_evidence"),
        "source_evidence",
        stop_reasons,
    )

    if not source_evidence_raw:
        stop_reasons.append("source_evidence must contain at least 1 element")
    if not nodes_raw:
        stop_reasons.append("nodes must contain at least 1 element")
    if request_context.mode in {"update", "append"} and not request_context.board_id:
        stop_reasons.append(f"{request_context.mode} mode requires request_context.board_id")

    document_set_id = None
    document_set_label = None
    if document_set_raw is not None:
        document_set_id = _required_non_empty_str(document_set_raw.get("id"), "document_set.id", stop_reasons)
        document_set_label = _required_non_empty_str(
            document_set_raw.get("label"),
            "document_set.label",
            stop_reasons,
        )

    flow_group_id = None
    flow_group_label = None
    if flow_group_raw is not None:
        flow_group_id = _required_non_empty_str(flow_group_raw.get("id"), "flow_group.id", stop_reasons)
        flow_group_label = _required_non_empty_str(flow_group_raw.get("label"), "flow_group.label", stop_reasons)

    actors: list[LaneDef] = []
    actor_ids: set[str] = set()
    for idx, actor_value in enumerate(actors_raw):
        actor_raw = _as_dict(actor_value, f"actors[{idx}]", stop_reasons)
        if actor_raw is None:
            continue
        actor_id = _required_non_empty_str(actor_raw.get("id"), f"actors[{idx}].id", stop_reasons)
        label = _required_non_empty_str(actor_raw.get("label"), f"actors[{idx}].label", stop_reasons)
        kind = _required_non_empty_str(actor_raw.get("kind"), f"actors[{idx}].kind", stop_reasons)
        if actor_id and label and kind:
            actors.append(LaneDef(id=actor_id, type="actor_lane", label=label, kind=kind))
            actor_ids.add(actor_id)

    systems: list[LaneDef] = []
    system_ids: set[str] = set()
    for idx, system_value in enumerate(systems_raw):
        system_raw = _as_dict(system_value, f"systems[{idx}]", stop_reasons)
        if system_raw is None:
            continue
        system_id = _required_non_empty_str(system_raw.get("id"), f"systems[{idx}].id", stop_reasons)
        label = _required_non_empty_str(system_raw.get("label"), f"systems[{idx}].label", stop_reasons)
        kind = _required_non_empty_str(system_raw.get("kind"), f"systems[{idx}].kind", stop_reasons)
        if system_id and label and kind:
            systems.append(LaneDef(id=system_id, type="system_lane", label=label, kind=kind))
            system_ids.add(system_id)

    nodes: list[NodeDef] = []
    node_ids: set[str] = set()
    start_count = 0
    for idx, node_value in enumerate(nodes_raw):
        node_raw = _as_dict(node_value, f"nodes[{idx}]", stop_reasons)
        if node_raw is None:
            continue
        node_id = _required_non_empty_str(node_raw.get("id"), f"nodes[{idx}].id", stop_reasons)
        node_type = _required_non_empty_str(node_raw.get("type"), f"nodes[{idx}].type", stop_reasons)
        label = _required_non_empty_str(node_raw.get("label"), f"nodes[{idx}].label", stop_reasons)
        actor_id = _required_non_empty_str(node_raw.get("actor_id"), f"nodes[{idx}].actor_id", stop_reasons)
        if node_type and node_type not in _NODE_TYPES:
            stop_reasons.append(
                f"nodes[{idx}].type must be one of {sorted(_NODE_TYPES)}, got {node_type!r}"
            )
        if actor_id and actor_id not in actor_ids:
            stop_reasons.append(
                f"node {node_id!r} references actor {actor_id!r} not found in actors"
            )
        if node_id and node_type and label and actor_id and actor_id in actor_ids and node_type in _NODE_TYPES:
            nodes.append(NodeDef(id=node_id, type=node_type, label=label, actor_id=actor_id))
            node_ids.add(node_id)
            if node_type == "start":
                start_count += 1

    if nodes_raw and start_count < 1:
        stop_reasons.append("nodes must contain at least 1 node with type='start'")

    connections: list[ConnectionDef] = []
    for idx, edge_value in enumerate(edges_raw):
        edge_raw = _as_dict(edge_value, f"edges[{idx}]", stop_reasons)
        if edge_raw is None:
            continue
        edge_id = _required_non_empty_str(edge_raw.get("id"), f"edges[{idx}].id", stop_reasons)
        from_id = _required_non_empty_str(edge_raw.get("from_node_id"), f"edges[{idx}].from_node_id", stop_reasons)
        to_id = _required_non_empty_str(edge_raw.get("to_node_id"), f"edges[{idx}].to_node_id", stop_reasons)
        edge_type = _required_non_empty_str(edge_raw.get("kind"), f"edges[{idx}].kind", stop_reasons)
        if edge_type and edge_type not in _EDGE_TYPES:
            stop_reasons.append(
                f"edges[{idx}].kind must be one of {sorted(_EDGE_TYPES)}, got {edge_type!r}"
            )
        if from_id and from_id not in node_ids:
            stop_reasons.append(f"edge {edge_raw.get('id', idx)!r} references from_node_id {from_id!r} not found in nodes")
        if to_id and to_id not in node_ids:
            stop_reasons.append(f"edge {edge_raw.get('id', idx)!r} references to_node_id {to_id!r} not found in nodes")
        if (
            edge_id
            and from_id
            and to_id
            and edge_type in _EDGE_TYPES
            and from_id in node_ids
            and to_id in node_ids
        ):
            connections.append(
                ConnectionDef(
                    id=edge_id,
                    from_id=from_id,
                    to_id=to_id,
                    type=edge_type,
                    label=_optional_label(edge_raw.get("label"), f"edges[{idx}].label", stop_reasons),
                )
            )

    for idx, access_value in enumerate(system_accesses_raw):
        access_raw = _as_dict(access_value, f"system_accesses[{idx}]", stop_reasons)
        if access_raw is None:
            continue
        access_id = _required_non_empty_str(
            access_raw.get("id"),
            f"system_accesses[{idx}].id",
            stop_reasons,
        )
        from_id = _required_non_empty_str(
            access_raw.get("from_node_id"),
            f"system_accesses[{idx}].from_node_id",
            stop_reasons,
        )
        system_id = _required_non_empty_str(
            access_raw.get("system_id"),
            f"system_accesses[{idx}].system_id",
            stop_reasons,
        )
        action = _required_non_empty_str(
            access_raw.get("action"),
            f"system_accesses[{idx}].action",
            stop_reasons,
        )
        if from_id and from_id not in node_ids:
            stop_reasons.append(
                f"system_access {access_raw.get('id', idx)!r} references from_node_id {from_id!r} not found in nodes"
            )
        if system_id and system_id not in system_ids:
            stop_reasons.append(
                f"system_access {access_raw.get('id', idx)!r} references system_id {system_id!r} not found in systems"
            )
        if (
            access_id
            and from_id
            and system_id
            and action
            and from_id in node_ids
            and system_id in system_ids
        ):
            connections.append(
                ConnectionDef(
                    id=access_id,
                    from_id=from_id,
                    to_id=system_id,
                    type="system_access",
                    label=_optional_label(
                        access_raw.get("label"),
                        f"system_accesses[{idx}].label",
                        stop_reasons,
                    ),
                    system_id=system_id,
                    action=action,
                )
            )

    source_evidence: list[SourceEvidence] = []
    for idx, evidence_value in enumerate(source_evidence_raw):
        evidence_raw = _as_dict(evidence_value, f"source_evidence[{idx}]", stop_reasons)
        if evidence_raw is None:
            continue
        ref = _required_non_empty_str(evidence_raw.get("ref"), f"source_evidence[{idx}].ref", stop_reasons)
        description = _required_non_empty_str(
            evidence_raw.get("description"),
            f"source_evidence[{idx}].description",
            stop_reasons,
        )
        if ref and description:
            source_evidence.append(SourceEvidence(ref=ref, description=description))

    metadata_project_id = None
    metadata_layer_id = None
    managed_by = "miro-flow-maker"
    update_mode = "managed"
    if metadata_raw is not None:
        metadata_project_id = _required_non_empty_str(metadata_raw.get("project_id"), "metadata.project_id", stop_reasons)
        metadata_layer_id = _required_non_empty_str(metadata_raw.get("layer_id"), "metadata.layer_id", stop_reasons)
        managed_by = _required_non_empty_str(metadata_raw.get("managed_by"), "metadata.managed_by", stop_reasons) or "miro-flow-maker"
        update_mode = _required_non_empty_str(metadata_raw.get("update_mode"), "metadata.update_mode", stop_reasons) or "managed"

    if stop_reasons:
        return ReviewResult(
            passed=False,
            stop_reasons=stop_reasons,
            normalized_input=None,
        )

    normalized_input = ConfirmedInput(
        flow_group_id=flow_group_id or "",
        flow_group_label=flow_group_label or "",
        document_set=DocumentSet(id=document_set_id or "", label=document_set_label or ""),
        nodes=nodes,
        connections=connections,
        lanes=[*actors, *systems],
        metadata=ItemMetadata(
            stable_item_id_prefix=flow_group_id or "",
            managed_by=managed_by,
            update_mode=update_mode,
            project_id=metadata_project_id or "",
            layer_id=metadata_layer_id or "",
            document_set_id=document_set_id or "",
            flow_group_id=flow_group_id or "",
        ),
        confirmation_packet_ref=confirmation_packet_ref or "",
        source_evidence=source_evidence,
        confirmed_by_user=True,
    )
    return ReviewResult(
        passed=True,
        stop_reasons=[],
        normalized_input=normalized_input,
    )


def build_stable_item_id(
    flow_group_id: str,
    semantic_type: str,
    semantic_id: str,
    render_role: str,
) -> str:
    """
    deterministic な stable_item_id を生成する。
    形式: <flow_group_id>:<semantic_type>:<semantic_id>:<render_role>

    SG2/SG3 が item 作成・照合時に使用する公開ヘルパー。
    """
    return f"{flow_group_id}:{semantic_type}:{semantic_id}:{render_role}"
