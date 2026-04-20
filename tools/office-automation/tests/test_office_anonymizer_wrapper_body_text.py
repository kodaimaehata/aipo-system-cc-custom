from __future__ import annotations

from pathlib import Path
import json
import sys

from openpyxl import Workbook
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WRAPPER_SCRIPTS = REPO_ROOT / ".codex" / "skills" / "office-anonymizer" / "scripts"
if str(WRAPPER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WRAPPER_SCRIPTS))

import office_anonymizer_wrapper as wrapper
from body_text_request_normalization import (
    build_body_text_policy_fragment,
    normalize_body_text_candidate_inputs,
    normalize_body_text_confirmation,
)
from office_automation.anonymize.candidate_summary import build_body_text_candidate_summary


def _write_placeholder_supported_file(root: Path, name: str = "sample.xlsx") -> Path:
    path = root / name
    path.write_text("placeholder", encoding="utf-8")
    return path


def _create_xlsx_with_repeated_body_text_candidates(path: Path) -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    worksheet["A1"] = "Primary contact: Jane Example"
    worksheet["A2"] = "Backup contact: Jane Example"
    worksheet["A3"] = "Vendor: Example Corp"
    workbook.save(path)
    workbook.close()
    return path


def _body_text_finding(
    *,
    file_path: Path,
    finding_id: str,
    matched_text: str,
    candidate_category: str = "exact_phrase",
    reason_tags: list[str] | None = None,
    recommended_replacement: str = "[REDACTED]",
    transform_supported: bool = True,
    manual_review_reason: str | None = None,
    action_hint: str = "replace",
    confidence: str = "high",
) -> dict:
    return {
        "finding_id": finding_id,
        "file_path": str(file_path),
        "relative_path": file_path.name,
        "extension": file_path.suffix.lstrip("."),
        "category": "body_text",
        "location": {"sheet": "Sheet1", "cell": "A1"},
        "payload": {
            "matched_text": matched_text,
            "normalized_text": matched_text.lower(),
            "candidate_category": candidate_category,
            "recommended_replacement": recommended_replacement,
            "transform_supported": transform_supported,
        },
        "reason_tags": reason_tags or ["exact_phrase"],
        "action_hint": action_hint,
        "confidence": confidence,
        "source": "user_hint",
        "manual_review_reason": manual_review_reason,
    }


def test_normalize_body_text_candidate_inputs_canonicalizes_and_deduplicates() -> None:
    normalized = normalize_body_text_candidate_inputs(
        {
            "person_names": [" Alice ", "Alice", "Bob"],
            "company_names": " Example Corp ",
            "emails": [" USER@Example.com ", "user@example.com"],
            "phones": [" 03  1234  5678 ", "03 1234 5678"],
            "addresses": [" 1 Main St ", ""],
            "domains": [" https://www.Example.com/path ", "MAILTO:example.com"],
            "exact_phrases": [" Confidential Project ", "Confidential Project"],
            "context_terms": [" Sales ", "Sales", " Tokyo "],
            "replacement_text": " [REDACTED] ",
            "replacement_map": {
                " Alice ": " [PERSON] ",
                "": "ignored",
                "Beta": "",
                " Project X ": " [PROJECT] ",
            },
        }
    )

    assert normalized == {
        "person_names": ["Alice", "Bob"],
        "company_names": ["Example Corp"],
        "emails": ["user@example.com"],
        "phones": ["03 1234 5678"],
        "addresses": ["1 Main St"],
        "domains": ["example.com"],
        "exact_phrases": ["Confidential Project"],
        "context_terms": ["Sales", "Tokyo"],
        "replacement_text": "[REDACTED]",
        "replacement_map": {
            "Alice": "[PERSON]",
            "Project X": "[PROJECT]",
        },
    }


def test_normalize_body_text_payloads_reject_unknown_keys_and_bad_types() -> None:
    with pytest.raises(ValueError, match=r"Unsupported body_text_candidate_inputs key 'nickname'"):
        normalize_body_text_candidate_inputs({"nickname": ["ally"]})

    with pytest.raises(TypeError, match=r"body_text_candidate_inputs field 'person_names' must be a string or a sequence of strings"):
        normalize_body_text_candidate_inputs({"person_names": ["Alice", 123]})

    with pytest.raises(ValueError, match=r"Unsupported body_text_confirmation key 'comment'"):
        normalize_body_text_confirmation({"comment": "ship it"})

    with pytest.raises(ValueError, match=r"body_text_confirmation mode must be one of"):
        normalize_body_text_confirmation({"mode": "auto_apply"})


def test_normalize_body_text_confirmation_defaults_and_builds_policy_fragment() -> None:
    normalized = normalize_body_text_confirmation(
        {
            "approved_candidate_ids": [" cand-1 ", "cand-1", "cand-2"],
            "rejected_candidate_ids": " cand-3 ",
            "replacement_overrides": {
                " cand-1 ": " [PERSON] ",
                "": "ignored",
                "cand-2": "",
            },
            "review_notes": [" needs follow-up ", "needs follow-up", " pdf is tricky "],
        }
    )

    assert normalized == {
        "mode": "preview_only",
        "approved_candidate_ids": ["cand-1", "cand-2"],
        "rejected_candidate_ids": ["cand-3"],
        "replacement_overrides": {"cand-1": "[PERSON]"},
        "review_notes": ["needs follow-up", "pdf is tricky"],
    }

    candidate_inputs = normalize_body_text_candidate_inputs(
        {
            "exact_phrases": ["Project X"],
            "replacement_text": " [REDACTED] ",
            "replacement_map": {" Project X ": " [PROJECT] "},
        }
    )
    policy_fragment = build_body_text_policy_fragment(candidate_inputs, normalized)

    assert policy_fragment == {
        "body_text": {
            "enabled": True,
            "mode": "preview_only",
            "confirmation_required": True,
            "approved_candidate_ids": ["cand-1", "cand-2"],
            "rejected_candidate_ids": ["cand-3"],
            "replacement_text": "[REDACTED]",
            "replacement_map": {"Project X": "[PROJECT]"},
            "replacement_overrides": {"cand-1": "[PERSON]"},
        }
    }


def test_run_request_passes_normalized_body_text_candidate_inputs_to_detect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    expected_candidate_inputs = normalize_body_text_candidate_inputs(
        {
            "emails": [" USER@Example.com ", "user@example.com"],
            "domains": ["https://www.Example.com/path"],
        }
    )
    expected_confirmation = normalize_body_text_confirmation(None)

    def fake_detect(target_folder: str, extensions=None, body_text_candidate_inputs=None):
        captured["target_folder"] = target_folder
        captured["extensions"] = extensions
        captured["body_text_candidate_inputs"] = body_text_candidate_inputs
        return []

    def fake_transform(detected, policy):
        captured["resolved_policy"] = policy
        return []

    def fake_validate(target_folder: str, transform_results):
        report_path = Path(target_folder) / "anonymization_report.md"
        report_path.write_text("# report\n", encoding="utf-8")
        return []

    monkeypatch.setattr(wrapper, "detect", fake_detect)
    monkeypatch.setattr(wrapper, "transform", fake_transform)
    monkeypatch.setattr(wrapper, "validate", fake_validate)
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {
                "emails": [" USER@Example.com ", "user@example.com"],
                "domains": ["https://www.Example.com/path"],
            },
        }
    )

    assert result["status"] == 0
    assert captured["target_folder"] == str(tmp_path)
    assert captured["extensions"] is None
    assert captured["body_text_candidate_inputs"] == expected_candidate_inputs
    assert captured["resolved_policy"]["body_text"] == {
        "enabled": True,
        "mode": "preview_only",
        "confirmation_required": False,
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "replacement_text": None,
        "replacement_map": {},
        "replacement_overrides": {},
        "candidate_count": 0,
        "undecided_candidate_ids": [],
        "approved_finding_ids": [],
        "non_transformable_finding_ids": [],
        "candidate_decisions": {},
        "confirmation_warnings": [],
        "candidate_summary": {
            "summary_version": "sg5-v1",
            "candidate_count": 0,
            "finding_count": 0,
            "manual_review_candidate_count": 0,
            "candidates": [],
            "finding_to_candidate": {},
        },
    }

    normalized_request = wrapper._normalize_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {
                "emails": [" USER@Example.com ", "user@example.com"],
                "domains": ["https://www.Example.com/path"],
            },
        }
    )

    assert normalized_request["body_text_candidate_inputs"] == expected_candidate_inputs
    assert normalized_request["body_text_confirmation"] == expected_confirmation
    assert result["body_text_run_mode"] == "absent"
    assert result["body_text_candidate_summary_count"] == 0
    assert result["body_text_candidate_summaries"] == []
    assert result["body_text_pending_candidate_count"] == 0
    assert result["body_text_approved_candidate_count"] == 0
    assert result["body_text_rejected_candidate_count"] == 0
    assert result["body_text_residual_candidate_count"] == 0
    assert result["body_text_low_confidence_candidate_count"] == 0
    assert result["body_text_next_step_guidance"] == result["next_step_guidance"]
    assert result["body_text_confirmation_request_template"] == {
        "mode": "apply_confirmed",
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "replacement_overrides": {},
    }


@pytest.mark.parametrize(
    "body_text_confirmation",
    [
        None,
        {"mode": "preview_only"},
        {"mode": "apply_confirmed", "approved_candidate_ids": [], "rejected_candidate_ids": []},
    ],
)
def test_run_request_returns_preview_only_when_confirmation_is_missing_or_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body_text_confirmation: dict | None,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [
        _body_text_finding(file_path=target_file, finding_id="body::1", matched_text="Project Lotus"),
        _body_text_finding(file_path=target_file, finding_id="body::2", matched_text="Jane Example"),
    ]

    def fake_detect(target_folder: str, extensions=None, body_text_candidate_inputs=None):
        assert target_folder == str(tmp_path)
        assert body_text_candidate_inputs == normalize_body_text_candidate_inputs({"exact_phrases": ["Project Lotus", "Jane Example"]})
        return detected

    def fail_transform(detected, policy):  # pragma: no cover - should not be called
        raise AssertionError("transform() must not run during preview-only body-text confirmation flow")

    def fail_validate(target_folder: str, transform_results):  # pragma: no cover - should not be called
        raise AssertionError("validate() must not run during preview-only body-text confirmation flow")

    monkeypatch.setattr(wrapper, "detect", fake_detect)
    monkeypatch.setattr(wrapper, "transform", fail_transform)
    monkeypatch.setattr(wrapper, "validate", fail_validate)
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    request = {
        "target_folder": str(tmp_path),
        "body_text_candidate_inputs": {"exact_phrases": ["Project Lotus", "Jane Example"]},
    }
    if body_text_confirmation is not None:
        request["body_text_confirmation"] = body_text_confirmation

    result = wrapper.run_request(request)

    assert result["status"] == 2
    assert result["body_text_candidate_count"] == 2
    assert result["body_text_confirmation_required"] is True
    assert result["body_text_confirmation_mode"] == "preview_only"
    assert result["body_text_preview_only"] is True
    assert result["body_text_run_mode"] == "preview_only"
    assert result["body_text_candidate_summary_count"] == 2
    assert {item["decision"] for item in result["body_text_candidate_summaries"]} == {"undecided"}
    assert all(
        set(item) >= {
            "candidate_id",
            "candidate_type",
            "normalized_text",
            "occurrence_count",
            "reason_tags",
            "replacement_text",
            "sample_locations",
            "decision",
            "manual_review_required",
        }
        for item in result["body_text_candidate_summaries"]
    )
    assert result["body_text_pending_candidate_count"] == 2
    assert result["body_text_approved_candidate_count"] == 0
    assert result["body_text_rejected_candidate_count"] == 0
    assert result["body_text_residual_candidate_count"] == 2
    assert result["body_text_low_confidence_candidate_count"] == 0
    assert result["body_text_next_step_guidance"] == result["next_step_guidance"]
    assert result["body_text_confirmation_request_template"] == {
        "mode": "apply_confirmed",
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "replacement_overrides": {},
    }
    assert result["approved_candidate_ids"] == []
    assert result["rejected_candidate_ids"] == []
    assert len(result["undecided_candidate_ids"]) == 2
    assert result["body_text_decision_counts"] == {
        "approved": 0,
        "rejected": 0,
        "undecided": 2,
        "manual_review": 0,
    }
    assert result["manual_review_item_count"] == 2
    assert result["transform_status_counts"] == {}
    assert result["validation_status_counts"] == {}
    assert result["runtime_report_path"] == str(tmp_path / "anonymization_report.md")
    report_path = Path(result["report_path"])
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "Candidate preview completed" in report_text
    assert "apply_confirmed" in report_text
    assert result["next_step_guidance"]
    assert result["requires_manual_review"] is True



def test_run_request_resolves_apply_confirmed_subset_and_escalates_when_rejected_candidates_remain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [
        _body_text_finding(file_path=target_file, finding_id="body::1", matched_text="Jane Example", candidate_category="person_name"),
        _body_text_finding(file_path=target_file, finding_id="body::2", matched_text="Project Lotus"),
    ]
    summary = build_body_text_candidate_summary(detected)
    jane = next(candidate for candidate in summary["candidates"] if candidate["display_text"] == "Jane Example")
    lotus = next(candidate for candidate in summary["candidates"] if candidate["display_text"] == "Project Lotus")
    captured: dict[str, object] = {}

    def fake_detect(target_folder: str, extensions=None, body_text_candidate_inputs=None):
        captured["detect_target_folder"] = target_folder
        captured["detect_candidate_inputs"] = body_text_candidate_inputs
        return detected

    def fake_transform(detected_findings, policy):
        captured["transform_detected"] = detected_findings
        captured["transform_policy"] = policy
        return []

    def fake_validate(target_folder: str, transform_results):
        captured["validate_target_folder"] = target_folder
        captured["validate_transform_results"] = transform_results
        report_path = Path(target_folder) / "anonymization_report.md"
        report_path.write_text("# confirmed report\n", encoding="utf-8")
        return []

    monkeypatch.setattr(wrapper, "detect", fake_detect)
    monkeypatch.setattr(wrapper, "transform", fake_transform)
    monkeypatch.setattr(wrapper, "validate", fake_validate)
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {"exact_phrases": ["Jane Example", "Project Lotus"]},
            "body_text_confirmation": {
                "mode": "apply_confirmed",
                "approved_candidate_ids": [jane["candidate_id"]],
                "rejected_candidate_ids": [lotus["candidate_id"]],
                "replacement_overrides": {jane["candidate_id"]: "[APPROVED PERSON]"},
            },
        }
    )

    resolved_body_text_policy = captured["transform_policy"]["body_text"]
    assert captured["detect_target_folder"] == str(tmp_path)
    assert captured["transform_detected"] == detected
    assert captured["validate_target_folder"] == str(tmp_path)
    assert result["status"] == 2
    assert result["body_text_confirmation_mode"] == "apply_confirmed"
    assert result["body_text_preview_only"] is False
    assert result["body_text_run_mode"] == "apply_confirmed"
    assert result["body_text_candidate_summary_count"] == 2
    summaries = {item["candidate_id"]: item for item in result["body_text_candidate_summaries"]}
    assert summaries[jane["candidate_id"]]["decision"] == "approved"
    assert summaries[jane["candidate_id"]]["replacement_text"] == "[APPROVED PERSON]"
    assert summaries[jane["candidate_id"]]["candidate_type"] == "person_name"
    assert summaries[jane["candidate_id"]]["normalized_text"] == "jane example"
    assert summaries[lotus["candidate_id"]]["decision"] == "rejected"
    assert summaries[lotus["candidate_id"]]["replacement_text"] == "[REDACTED]"
    assert result["body_text_pending_candidate_count"] == 0
    assert result["body_text_approved_candidate_count"] == 1
    assert result["body_text_rejected_candidate_count"] == 1
    assert result["body_text_residual_candidate_count"] == 1
    assert result["body_text_low_confidence_candidate_count"] == 0
    assert result["body_text_next_step_guidance"] == result["next_step_guidance"]
    assert result["approved_candidate_ids"] == [jane["candidate_id"]]
    assert result["rejected_candidate_ids"] == [lotus["candidate_id"]]
    assert result["undecided_candidate_ids"] == []
    assert result["body_text_decision_counts"] == {
        "approved": 1,
        "rejected": 1,
        "undecided": 0,
        "manual_review": 0,
    }
    assert resolved_body_text_policy["mode"] == "apply_confirmed"
    assert resolved_body_text_policy["approved_candidate_ids"] == [jane["candidate_id"]]
    assert resolved_body_text_policy["rejected_candidate_ids"] == [lotus["candidate_id"]]
    assert resolved_body_text_policy["undecided_candidate_ids"] == []
    assert resolved_body_text_policy["approved_finding_ids"] == ["body::1"]
    assert resolved_body_text_policy["candidate_decisions"][jane["candidate_id"]]["replacement_text"] == "[APPROVED PERSON]"



def test_run_request_confirmed_body_text_report_stays_consistent_with_wrapper_summary(tmp_path: Path) -> None:
    _create_xlsx_with_repeated_body_text_candidates(tmp_path / "confirmed-report-a.xlsx")
    _create_xlsx_with_repeated_body_text_candidates(tmp_path / "confirmed-report-b.xlsx")
    body_text_candidate_inputs = {
        "person_names": ["Jane Example"],
        "company_names": ["Example Corp"],
    }
    detected = wrapper.detect(str(tmp_path), body_text_candidate_inputs=body_text_candidate_inputs)
    body_text_findings = [finding for finding in detected if finding["category"] == "body_text"]
    summary = build_body_text_candidate_summary(body_text_findings)
    candidates_by_text = {candidate["display_text"]: candidate for candidate in summary["candidates"]}
    jane_candidate_id = candidates_by_text["Jane Example"]["candidate_id"]
    vendor_candidate_id = candidates_by_text["Example Corp"]["candidate_id"]

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": body_text_candidate_inputs,
            "body_text_confirmation": {
                "mode": "apply_confirmed",
                "approved_candidate_ids": [jane_candidate_id],
                "rejected_candidate_ids": [vendor_candidate_id],
                "replacement_overrides": {jane_candidate_id: "[PERSON]"},
            },
        }
    )

    assert result["status"] == 2
    assert result["body_text_run_mode"] == "apply_confirmed"
    assert result["body_text_candidate_summary_count"] == 2
    assert len(result["validation_results"]) == 2
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    runtime_manual_review_item_count = sum(len(item["manual_review_items"]) for item in result["validation_results"])

    assert f"- body_text_candidate_summary_count: {result['body_text_candidate_summary_count']}" in report
    assert (
        '- body_text_decision_counts: `{"approved": 1, "low_confidence": 0, '
        '"manual_review_required": 0, "pending": 0, "rejected": 1, "residual": 0, "skipped": 1}`'
    ) in report
    assert result["manual_review_item_count"] == runtime_manual_review_item_count
    assert f"- manual_review_items: {runtime_manual_review_item_count}" in report
    assert f"- approved_candidate_ids: `{json.dumps([jane_candidate_id], ensure_ascii=False)}`" in report
    assert f"- rejected_candidate_ids: `{json.dumps([vendor_candidate_id], ensure_ascii=False)}`" in report



def test_run_request_attaches_per_file_body_text_context_before_validate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [
        _body_text_finding(file_path=target_file, finding_id="body::1", matched_text="Jane Example", candidate_category="person_name"),
        _body_text_finding(file_path=target_file, finding_id="body::2", matched_text="Project Lotus"),
    ]
    summary = build_body_text_candidate_summary(detected)
    candidates_by_text = {candidate["display_text"]: candidate for candidate in summary["candidates"]}
    jane_candidate_id = candidates_by_text["Jane Example"]["candidate_id"]
    lotus_candidate_id = candidates_by_text["Project Lotus"]["candidate_id"]
    captured: dict[str, object] = {}

    def fake_transform(detected_findings, policy):
        del detected_findings, policy
        return [
            {
                "actions": [
                    {
                        "category": "body_text",
                        "candidate_id": jane_candidate_id,
                        "details": {"replacement_text": "[PERSON]"},
                        "location": {"sheet": "Sheet1", "cell": "A1"},
                        "payload": {"matched_text": "Jane Example", "normalized_text": "jane example"},
                        "status": "applied",
                    },
                    {
                        "category": "body_text",
                        "candidate_id": lotus_candidate_id,
                        "details": {"replacement_text": "[REDACTED]"},
                        "location": {"sheet": "Sheet1", "cell": "A2"},
                        "payload": {"matched_text": "Project Lotus", "normalized_text": "project lotus"},
                        "status": "skipped",
                    },
                ],
                "extension": "xlsx",
                "file_path": str(target_file),
                "manual_review_items": [],
                "output_path": str(target_file),
                "relative_path": target_file.name,
                "status": "partial_success",
                "warnings": [],
            }
        ]

    def fake_validate(target_folder: str, transform_results):
        captured["validate_target_folder"] = target_folder
        captured["validate_transform_results"] = transform_results
        report_path = Path(target_folder) / "anonymization_report.md"
        report_path.write_text("# confirmed report\n", encoding="utf-8")
        return []

    monkeypatch.setattr(wrapper, "detect", lambda *args, **kwargs: detected)
    monkeypatch.setattr(wrapper, "transform", fake_transform)
    monkeypatch.setattr(wrapper, "validate", fake_validate)
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {"exact_phrases": ["Jane Example", "Project Lotus"]},
            "body_text_confirmation": {
                "mode": "apply_confirmed",
                "approved_candidate_ids": [jane_candidate_id],
                "rejected_candidate_ids": [lotus_candidate_id],
                "replacement_overrides": {jane_candidate_id: "[PERSON]"},
            },
        }
    )

    assert result["status"] == 2
    assert captured["validate_target_folder"] == str(tmp_path)
    validate_body_text = captured["validate_transform_results"][0]["body_text"]
    assert validate_body_text["run_mode"] == "apply_confirmed"
    assert validate_body_text["approved_candidate_ids"] == [jane_candidate_id]
    assert validate_body_text["rejected_candidate_ids"] == [lotus_candidate_id]
    assert validate_body_text["pending_candidate_ids"] == []
    assert {candidate["display_text"] for candidate in validate_body_text["candidate_summary"]["candidates"]} == {
        "Jane Example",
        "Project Lotus",
    }



def test_run_request_accepts_explicit_reject_all_without_preview_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [_body_text_finding(file_path=target_file, finding_id="body::1", matched_text="Project Lotus")]
    summary = build_body_text_candidate_summary(detected)
    candidate_id = summary["candidates"][0]["candidate_id"]
    captured: dict[str, object] = {"transform_called": False, "validate_called": False}

    monkeypatch.setattr(wrapper, "detect", lambda *args, **kwargs: detected)

    def fake_transform(detected_findings, policy):
        captured["transform_called"] = True
        captured["transform_policy"] = policy
        return []

    def fake_validate(target_folder: str, transform_results):
        captured["validate_called"] = True
        report_path = Path(target_folder) / "anonymization_report.md"
        report_path.write_text("# reject-all report\n", encoding="utf-8")
        return []

    monkeypatch.setattr(wrapper, "transform", fake_transform)
    monkeypatch.setattr(wrapper, "validate", fake_validate)
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {"exact_phrases": ["Project Lotus"]},
            "body_text_confirmation": {
                "mode": "apply_confirmed",
                "approved_candidate_ids": [],
                "rejected_candidate_ids": [candidate_id],
            },
        }
    )

    assert captured["transform_called"] is True
    assert captured["validate_called"] is True
    assert result["status"] == 2
    assert result["body_text_preview_only"] is False
    assert result["approved_candidate_ids"] == []
    assert result["rejected_candidate_ids"] == [candidate_id]
    assert result["undecided_candidate_ids"] == []
    assert captured["transform_policy"]["body_text"]["approved_candidate_ids"] == []



def test_run_request_counts_low_confidence_body_text_candidates_in_stable_alias_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [
        _body_text_finding(
            file_path=target_file,
            finding_id="body::1",
            matched_text="searchable-pdf@example.com",
            candidate_category="email",
            reason_tags=["email_pattern"],
            confidence="low",
            manual_review_reason="PDF text-layer follow-up required.",
            transform_supported=False,
        )
    ]

    monkeypatch.setattr(wrapper, "detect", lambda *args, **kwargs: detected)
    monkeypatch.setattr(
        wrapper,
        "transform",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transform() must not run during preview-only body-text confirmation flow")),
    )
    monkeypatch.setattr(
        wrapper,
        "validate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("validate() must not run during preview-only body-text confirmation flow")),
    )
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {"emails": ["searchable-pdf@example.com"]},
        }
    )

    assert result["status"] == 2
    assert result["body_text_run_mode"] == "preview_only"
    assert result["body_text_low_confidence_candidate_count"] == 1
    assert result["body_text_residual_candidate_count"] == 1
    assert result["body_text_candidate_summaries"][0]["manual_review_required"] is True
    assert result["body_text_candidate_summaries"][0]["decision"] == "manual_review"



def test_run_request_fails_clearly_for_unknown_confirmed_candidate_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_file = _write_placeholder_supported_file(tmp_path)
    detected = [_body_text_finding(file_path=target_file, finding_id="body::1", matched_text="Project Lotus")]

    monkeypatch.setattr(wrapper, "detect", lambda *args, **kwargs: detected)
    monkeypatch.setattr(
        wrapper,
        "transform",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transform() must not run for invalid confirmation payloads")),
    )
    monkeypatch.setattr(
        wrapper,
        "validate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("validate() must not run for invalid confirmation payloads")),
    )
    monkeypatch.setattr(
        wrapper,
        "_load_default_rules",
        lambda: {
            "comments": {"enabled": True, "action": "remove"},
            "notes": {"enabled": True, "action": "remove"},
            "headers": {"enabled": True, "action": "remove"},
            "footers": {"enabled": True, "action": "remove"},
            "metadata": {"enabled": True, "action": "clear"},
            "images": {"enabled": True, "mode": "report_only", "replacement_path": None},
            "manual_review_required": True,
        },
    )

    result = wrapper.run_request(
        {
            "target_folder": str(tmp_path),
            "body_text_candidate_inputs": {"exact_phrases": ["Project Lotus"]},
            "body_text_confirmation": {
                "mode": "apply_confirmed",
                "approved_candidate_ids": ["btc::missing"],
                "rejected_candidate_ids": [],
            },
        }
    )

    assert result["status"] == 3
    assert result["message"] == "Unknown approved candidate_id 'btc::missing'."
    assert result["error"] == {
        "type": "ValueError",
        "message": "Unknown approved candidate_id 'btc::missing'.",
    }
