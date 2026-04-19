from __future__ import annotations

import json
from pathlib import Path

from miro_flow_maker.gate import build_stable_item_id, validate
from miro_flow_maker.models import RequestContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_validate_confirmed_input_passes() -> None:
    input_data = _load_fixture("confirmed_minimal.json")
    context = RequestContext(
        mode="create",
        board_id=None,
        frame_id=None,
        frame_link=None,
        board_name="Review Board",
        dry_run=True,
        input_path=str(FIXTURES / "confirmed_minimal.json"),
    )

    result = validate(input_data, context)

    assert result.passed is True
    assert result.stop_reasons == []
    assert result.normalized_input is not None
    assert result.normalized_input.flow_group_id == "flow-approval-01"
    assert result.normalized_input.document_set.id == "ds-001"
    assert len(result.normalized_input.nodes) == 1
    assert len(result.normalized_input.connections) == 0
    assert len(result.normalized_input.lanes) == 1


def test_validate_candidate_input_collects_multiple_stop_reasons() -> None:
    input_data = _load_fixture("rejected_candidate.json")
    context = RequestContext(
        mode="create",
        board_id=None,
        frame_id=None,
        frame_link=None,
        board_name="Review Board",
        dry_run=True,
        input_path=str(FIXTURES / "rejected_candidate.json"),
    )

    result = validate(input_data, context)

    assert result.passed is False
    assert result.normalized_input is None
    assert any("expected 'confirmed'" in reason for reason in result.stop_reasons)
    assert any("confirmation_packet_ref is missing" in reason for reason in result.stop_reasons)
    assert any("source_evidence must contain at least 1 element" in reason for reason in result.stop_reasons)
    assert any("nodes must contain at least 1 element" in reason for reason in result.stop_reasons)


def test_validate_update_requires_board_id_in_request_context() -> None:
    input_data = _load_fixture("confirmed_minimal.json")
    context = RequestContext(
        mode="update",
        board_id=None,
        frame_id="frame-123",
        frame_link=None,
        board_name=None,
        dry_run=False,
        input_path=str(FIXTURES / "confirmed_minimal.json"),
    )

    result = validate(input_data, context)

    assert result.passed is False
    assert any("request_context.board_id" in reason for reason in result.stop_reasons)


def test_build_stable_item_id_uses_contract_format() -> None:
    assert (
        build_stable_item_id("flow-001", "node", "n-01", "shape")
        == "flow-001:node:n-01:shape"
    )
