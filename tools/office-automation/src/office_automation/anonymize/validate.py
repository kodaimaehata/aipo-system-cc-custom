"""Post-transform validation helpers for SG3 V1 anonymization workflows.

`validate(target_folder, transform_results)` is the SG1 public callable used after
`transform(...)` completes. The callable intentionally keeps a narrow contract:
- it re-scans the runtime-supplied folder with `detect()` so validation is driven
  by actual post-transform evidence instead of transform intent alone
- it writes the default Markdown report to
  `<target-folder>/anonymization_report.md`
- it returns structured per-file validation results that preserve transform
  carry-forward context, residual findings, warnings, and manual-review items

Validation status vocabulary mirrors SG3 wrapper handoff needs:
- `success`: clean re-scan with no warnings or manual-review requirements
- `partial_success`: residual findings, warnings, or mixed cleanup outcomes
- `manual_review_required`: no hard residuals were proven, but human review is
  still required for low-confidence or visually sensitive surfaces
- `error`: transform already failed for the file or validation could not reason
  about the file in a trustworthy way

The report is written here so later wrapper code can rely on one deterministic
runtime artifact without duplicating residual-analysis logic.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from office_automation.anonymize.detect import detect
from office_automation.common.files import list_office_files

__all__ = ["validate"]

_REPORT_FILENAME = "anonymization_report.md"
_VISUAL_REVIEW_CATEGORIES = frozenset({"headers", "footers", "images"})
_REVIEW_ONLY_CATEGORIES = frozenset({"images"})


def validate(target_folder: str, transform_results: list[dict]) -> list[dict]:
    """Re-scan target_folder after transform, write the Markdown report, and return per-file validation results."""
    folder = Path(target_folder)
    report_path = folder / _REPORT_FILENAME

    supported_files = list_office_files(folder)
    grouped_transform = _group_transform_results(folder, transform_results)

    rescanned_findings = detect(str(folder))
    grouped_rescan = _group_findings_by_file(rescanned_findings)

    body_text_rescan_inputs, body_text_enabled_files = _collect_body_text_rescan_context(grouped_transform)
    if body_text_rescan_inputs is not None:
        body_text_findings = [
            finding
            for finding in detect(str(folder), body_text_candidate_inputs=body_text_rescan_inputs)
            if str(finding.get("category") or "") == "body_text"
            and _file_key(str(finding.get("file_path") or "<unknown>"), str(finding.get("extension") or "")) in body_text_enabled_files
        ]
        grouped_body_text = _group_findings_by_file(body_text_findings)
        for file_key, findings in grouped_body_text.items():
            grouped_rescan.setdefault(file_key, [])
            grouped_rescan[file_key].extend(findings)
            grouped_rescan[file_key] = sorted(grouped_rescan[file_key], key=_finding_sort_key)

    ordered_keys = _ordered_file_keys(folder, supported_files, grouped_transform)
    validation_results: list[dict] = []

    for file_key in ordered_keys:
        file_path, extension = file_key
        transform_result = grouped_transform.get(file_key)
        rescan_findings = list(grouped_rescan.get(file_key, []))
        validation_results.append(
            _validate_file(
                folder=folder,
                file_path=file_path,
                extension=extension,
                transform_result=transform_result,
                rescan_findings=rescan_findings,
                report_path=report_path,
            )
        )

    report_path.write_text(_render_report(folder, report_path, validation_results), encoding="utf-8")
    return [_sorted_copy(result) for result in validation_results]



def _validate_file(
    *,
    folder: Path,
    file_path: str,
    extension: str,
    transform_result: dict | None,
    rescan_findings: list[dict],
    report_path: Path,
) -> dict:
    path = Path(file_path)
    result = {
        "file_path": file_path,
        "relative_path": _relative_path_for_result(folder, path, transform_result),
        "extension": extension,
        "status": "success",
        "residual_findings": [],
        "warnings": [],
        "manual_review_items": [],
        "body_text": _default_body_text_summary(),
        "body_text_candidates": [],
        "transform_summary": {
            "transform_status": str((transform_result or {}).get("status") or "not_targeted"),
            "output_path": (transform_result or {}).get("output_path") or file_path,
            "warnings": list((transform_result or {}).get("warnings") or []),
            "action_status_counts": {},
            "actions": [],
        },
        "report_path": str(report_path),
    }

    for warning in result["transform_summary"]["warnings"]:
        _add_warning(result, warning)

    if transform_result and not path.exists():
        _add_warning(result, f"File '{file_path}' was present in transform results but missing during validation re-scan.")

    rescan_index = {_finding_match_key(finding): finding for finding in rescan_findings}
    matched_rescan_keys: set[tuple[str, str]] = set()

    transform_actions = list((transform_result or {}).get("actions") or [])
    result["transform_summary"]["action_status_counts"] = dict(
        sorted(Counter(str(action.get("status") or "unknown") for action in transform_actions).items())
    )

    for manual_item in list((transform_result or {}).get("manual_review_items") or []):
        _add_manual_review_item(
            result,
            {
                "category": manual_item.get("category"),
                "finding_id": manual_item.get("finding_id"),
                "location": _sorted_copy(manual_item.get("location") or {}),
                "reason": manual_item.get("reason"),
                "requested_action": manual_item.get("requested_action"),
                "source": "transform",
                "validation_outcome": "manual_review_required",
            },
        )

    for action in transform_actions:
        for warning in list(action.get("warnings") or []):
            _add_warning(result, warning)

        matched_rescan = rescan_index.get(_action_match_key(action))
        if matched_rescan is not None:
            matched_rescan_keys.add(_finding_match_key(matched_rescan))

        action_summary, residual_entry, manual_review_items = _evaluate_action(action, matched_rescan)
        result["transform_summary"]["actions"].append(action_summary)

        if residual_entry is not None:
            result["residual_findings"].append(residual_entry)
            _add_manual_review_item(result, _manual_review_from_residual(residual_entry, action=action))

        for manual_review_item in manual_review_items:
            _add_manual_review_item(result, manual_review_item)

    body_text_rescan_findings = [finding for finding in rescan_findings if str(finding.get("category") or "") == "body_text"]

    for finding in rescan_findings:
        if str(finding.get("category") or "") == "body_text":
            continue
        finding_key = _finding_match_key(finding)
        if finding_key in matched_rescan_keys:
            continue
        if _is_review_only_finding(finding):
            _add_manual_review_item(result, _manual_review_from_rescan(finding, validation_outcome="manual_review_required"))
            continue
        if _is_review_only_category(finding):
            _add_manual_review_item(result, _manual_review_from_rescan(finding, validation_outcome="manual_review_required"))
            continue

        residual_entry = _residual_entry(
            finding,
            validation_outcome="not_attempted",
            reason="The post-transform re-scan still found this target and no matching transform action was available for comparison.",
            action=None,
        )
        result["residual_findings"].append(residual_entry)
        _add_manual_review_item(result, _manual_review_from_residual(residual_entry, action=None))

    body_text_summary, body_text_residuals, body_text_manual_review_items = _summarize_body_text_validation(
        transform_result=transform_result,
        transform_actions=transform_actions,
        body_text_rescan_findings=body_text_rescan_findings,
        matched_rescan_keys=matched_rescan_keys,
    )
    result["body_text"] = body_text_summary
    result["body_text_candidates"] = _body_text_candidates_from_transform_result(transform_result)
    for residual_entry in body_text_residuals:
        result["residual_findings"].append(residual_entry)
    for manual_review_item in body_text_manual_review_items:
        _add_manual_review_item(result, manual_review_item)

    result["residual_findings"] = _sorted_residuals(result["residual_findings"])
    result["manual_review_items"] = _sorted_manual_review_items(result["manual_review_items"])
    result["status"] = _finalize_validation_status(result)
    result["transform_summary"]["actions"] = _sorted_actions(result["transform_summary"]["actions"])
    return _sorted_copy(result)



def _evaluate_action(action: dict, matched_rescan: dict | None) -> tuple[dict, dict | None, list[dict]]:
    category = str(action.get("category") or "unknown")
    transform_status = str(action.get("status") or "unknown")
    requested_action = str(action.get("requested_action") or "unknown")
    applied_action = str(action.get("applied_action") or "none")
    manual_review_items: list[dict] = []
    residual_entry: dict | None = None

    if matched_rescan is None:
        if transform_status == "applied":
            validation_outcome = "cleared"
        elif transform_status == "skipped":
            validation_outcome = "not_present_at_rescan"
        elif transform_status == "manual_review_required":
            validation_outcome = "manual_review_required"
        elif transform_status == "error":
            validation_outcome = "error"
        else:
            validation_outcome = "indeterminate"
    elif _is_review_only_finding(matched_rescan) or _is_review_only_category(matched_rescan):
        validation_outcome = "manual_review_required"
        manual_review_items.append(_manual_review_from_rescan(matched_rescan, validation_outcome=validation_outcome, action=action))
    elif transform_status == "applied" and category == "images":
        validation_outcome = "manual_review_required"
        manual_review_items.append(_visual_review_item(action, matched_rescan))
    elif transform_status == "applied" and requested_action == "replace" and not _payloads_equal(action.get("payload"), matched_rescan.get("payload")):
        validation_outcome = "changed_in_place"
        if _requires_visual_review(action):
            manual_review_items.append(_visual_review_item(action, matched_rescan))
    elif transform_status == "applied":
        validation_outcome = "residual"
        residual_entry = _residual_entry(
            matched_rescan,
            validation_outcome=validation_outcome,
            reason="The post-transform re-scan still found the same target at the same location after an applied transform action.",
            action=action,
        )
    elif transform_status == "skipped":
        validation_outcome = "left_in_place"
        residual_entry = _residual_entry(
            matched_rescan,
            validation_outcome=validation_outcome,
            reason="The target remained after validation because the confirmed transform policy skipped or report-only'd it.",
            action=action,
        )
    elif transform_status == "manual_review_required":
        validation_outcome = "manual_review_required"
        residual_entry = _residual_entry(
            matched_rescan,
            validation_outcome=validation_outcome,
            reason="The target remained after transform and the transform runtime already marked it as requiring manual review.",
            action=action,
        )
    elif transform_status == "error":
        validation_outcome = "error"
        residual_entry = _residual_entry(
            matched_rescan,
            validation_outcome=validation_outcome,
            reason="The target remained after a transform error prevented trustworthy cleanup confirmation.",
            action=action,
        )
    else:
        validation_outcome = "indeterminate"
        residual_entry = _residual_entry(
            matched_rescan,
            validation_outcome=validation_outcome,
            reason="The target remained after transform, but validation could not classify the transform outcome more precisely.",
            action=action,
        )

    if transform_status == "applied" and _requires_visual_review(action):
        manual_review_items.append(_visual_review_item(action, matched_rescan))

    if matched_rescan is None and transform_status in {"manual_review_required", "error"}:
        manual_review_items.append(
            {
                "category": category,
                "finding_id": action.get("finding_id"),
                "location": _sorted_copy(action.get("location") or {}),
                "reason": str(action.get("message") or action.get("manual_review_reason") or "Transform outcome still requires human confirmation."),
                "requested_action": action.get("requested_action"),
                "source": "transform",
                "validation_outcome": validation_outcome,
            }
        )

    action_summary = {
        "finding_id": action.get("finding_id"),
        "category": category,
        "location": _sorted_copy(action.get("location") or {}),
        "requested_action": requested_action,
        "applied_action": applied_action,
        "transform_status": transform_status,
        "message": action.get("message"),
        "warnings": list(action.get("warnings") or []),
        "details": _sorted_copy(action.get("details") or {}),
        "validation_outcome": validation_outcome,
        "matched_post_scan_finding_id": matched_rescan.get("finding_id") if matched_rescan is not None else None,
    }
    return _sorted_copy(action_summary), residual_entry, manual_review_items



def _collect_body_text_rescan_context(grouped_transform: dict[tuple[str, str], dict]) -> tuple[dict | None, set[tuple[str, str]]]:
    candidate_inputs = {
        "person_names": [],
        "company_names": [],
        "emails": [],
        "phones": [],
        "addresses": [],
        "domains": [],
        "exact_phrases": [],
        "context_terms": [],
        "replacement_map": {},
        "replacement_text": None,
    }
    seen_values = {key: set() for key in candidate_inputs if isinstance(candidate_inputs[key], list)}
    enabled_files: set[tuple[str, str]] = set()

    for file_key, transform_result in grouped_transform.items():
        if not _transform_result_has_body_text_state(transform_result):
            continue
        enabled_files.add(file_key)
        for candidate in _body_text_candidates_from_transform_result(transform_result):
            display_text = str(candidate.get("display_text") or "").strip()
            if not display_text:
                continue
            field_name = _candidate_input_field_for_candidate(candidate)
            if display_text not in seen_values[field_name]:
                candidate_inputs[field_name].append(display_text)
                seen_values[field_name].add(display_text)

        if any(str(action.get("category") or "") == "body_text" for action in list((transform_result or {}).get("actions") or [])):
            for action in list((transform_result or {}).get("actions") or []):
                if str(action.get("category") or "") != "body_text":
                    continue
                payload = action.get("payload") or {}
                matched_text = str(payload.get("matched_text") or payload.get("normalized_text") or "").strip()
                if matched_text and matched_text not in seen_values["exact_phrases"]:
                    candidate_inputs["exact_phrases"].append(matched_text)
                    seen_values["exact_phrases"].add(matched_text)

    if not enabled_files:
        return None, set()
    return candidate_inputs, enabled_files



def _transform_result_has_body_text_state(transform_result: dict | None) -> bool:
    if not isinstance(transform_result, dict):
        return False
    if isinstance(transform_result.get("body_text"), dict):
        return True
    return any(str(action.get("category") or "") == "body_text" for action in list(transform_result.get("actions") or []))



def _body_text_candidates_from_transform_result(transform_result: dict | None) -> list[dict]:
    body_text = (transform_result or {}).get("body_text")
    if isinstance(body_text, dict):
        candidate_summary = body_text.get("candidate_summary")
        if isinstance(candidate_summary, dict):
            candidates = candidate_summary.get("candidates")
            if isinstance(candidates, list):
                return [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]

    grouped: dict[str, dict] = {}
    for action in list((transform_result or {}).get("actions") or []):
        if str(action.get("category") or "") != "body_text":
            continue
        candidate_id = str(action.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        payload = action.get("payload") or {}
        candidate = grouped.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "display_text": str(payload.get("matched_text") or payload.get("normalized_text") or candidate_id),
                "occurrence_count": 0,
                "confidence_counts": {"high": 0, "low": 0, "medium": 0},
                "location_samples": [],
                "reason_tags": [],
            },
        )
        candidate["occurrence_count"] += 1
        confidence = str(action.get("confidence") or "").lower()
        if confidence:
            candidate["confidence_counts"][confidence] = candidate["confidence_counts"].get(confidence, 0) + 1
        if len(candidate["location_samples"]) < 5:
            candidate["location_samples"].append({"location": _sorted_copy(action.get("location") or {})})
    return sorted(grouped.values(), key=lambda candidate: (str(candidate.get("display_text") or "").casefold(), str(candidate.get("candidate_id") or "")))



def _candidate_input_field_for_candidate(candidate: dict) -> str:
    category = str(candidate.get("candidate_category") or "").strip().lower()
    return {
        "address": "addresses",
        "company_name": "company_names",
        "domain": "domains",
        "email": "emails",
        "exact_phrase": "exact_phrases",
        "generic_identifier": "exact_phrases",
        "person_name": "person_names",
        "phone": "phones",
    }.get(category, "exact_phrases")



def _default_body_text_summary() -> dict:
    return {
        "run_mode": "absent",
        "confirmation_required": False,
        "candidate_summary_count": 0,
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "pending_candidate_ids": [],
        "residual_candidate_ids": [],
        "low_confidence_candidate_ids": [],
        "decision_counts": {
            "approved": 0,
            "rejected": 0,
            "pending": 0,
            "skipped": 0,
            "manual_review_required": 0,
            "residual": 0,
            "low_confidence": 0,
        },
        "decision_trace": [],
        "next_step_guidance": "No body-text candidates were generated for this run.",
    }



def _summarize_body_text_validation(
    *,
    transform_result: dict | None,
    transform_actions: list[dict],
    body_text_rescan_findings: list[dict],
    matched_rescan_keys: set[tuple[str, str]],
) -> tuple[dict, list[dict], list[dict]]:
    if not _transform_result_has_body_text_state(transform_result) and not body_text_rescan_findings:
        return _default_body_text_summary(), [], []

    context = dict((transform_result or {}).get("body_text") or {}) if isinstance((transform_result or {}).get("body_text"), dict) else {}
    candidates = _body_text_candidates_from_transform_result(transform_result)
    candidates_by_id = {
        str(candidate.get("candidate_id") or _synthetic_body_text_candidate_id(candidate)): _normalize_body_text_candidate(candidate)
        for candidate in candidates
    }

    body_text_actions = [action for action in transform_actions if str(action.get("category") or "") == "body_text"]
    action_groups: dict[str, list[dict]] = {}
    for action in body_text_actions:
        candidate_id = str(action.get("candidate_id") or _candidate_id_for_body_text_finding(candidates_by_id, action) or "").strip()
        if not candidate_id:
            continue
        action_groups.setdefault(candidate_id, []).append(action)
        candidates_by_id.setdefault(candidate_id, _candidate_from_body_text_action(candidate_id, action))

    rescan_groups: dict[str, list[dict]] = {}
    unmatched_rescans: list[dict] = []
    for finding in body_text_rescan_findings:
        candidate_id = _candidate_id_for_body_text_finding(candidates_by_id, finding)
        if candidate_id is None:
            unmatched_rescans.append(finding)
            continue
        rescan_groups.setdefault(candidate_id, []).append(finding)
        candidates_by_id.setdefault(candidate_id, _candidate_from_body_text_finding(candidate_id, finding))

    approved_candidate_ids = _string_list(context.get("approved_candidate_ids"))
    rejected_candidate_ids = _string_list(context.get("rejected_candidate_ids"))
    pending_candidate_ids = _string_list(context.get("pending_candidate_ids") or context.get("undecided_candidate_ids"))
    candidate_decisions = context.get("candidate_decisions") if isinstance(context.get("candidate_decisions"), dict) else {}
    run_mode = str(context.get("run_mode") or ("apply_confirmed" if body_text_actions else "preview_only")).strip().lower() or "absent"
    if not candidates_by_id and run_mode == "preview_only":
        run_mode = "absent"

    residual_candidate_ids: list[str] = []
    low_confidence_candidate_ids: list[str] = []
    manual_review_candidate_ids: list[str] = []
    skipped_candidate_ids: list[str] = []
    decision_trace: list[dict] = []
    residual_entries: list[dict] = []
    manual_review_items: list[dict] = []

    ordered_candidate_ids = sorted(candidates_by_id, key=lambda candidate_id: (str(candidates_by_id[candidate_id].get("display_text") or "").casefold(), candidate_id))
    if not approved_candidate_ids and not rejected_candidate_ids and not pending_candidate_ids and run_mode == "preview_only":
        pending_candidate_ids = ordered_candidate_ids

    for candidate_id in ordered_candidate_ids:
        candidate = candidates_by_id[candidate_id]
        candidate_actions = action_groups.get(candidate_id, [])
        candidate_rescans = rescan_groups.get(candidate_id, [])
        decision_payload = candidate_decisions.get(candidate_id) if isinstance(candidate_decisions, dict) and isinstance(candidate_decisions.get(candidate_id), dict) else {}
        replacement_text = decision_payload.get("replacement_text")
        if replacement_text in (None, ""):
            replacement_text = _first_non_empty([(action.get("details") or {}).get("replacement_text") for action in candidate_actions]) or candidate.get("recommended_replacement")

        if candidate_id in approved_candidate_ids:
            decision = "approved"
        elif candidate_id in rejected_candidate_ids:
            decision = "rejected"
        elif candidate_id in pending_candidate_ids or run_mode == "preview_only":
            decision = "pending"
        else:
            decision = str(decision_payload.get("decision") or "pending")

        transform_status = _aggregate_transform_status(candidate_actions, default="not_attempted")
        review_only_rescans = [finding for finding in candidate_rescans if _is_review_only_finding(finding) or _is_review_only_category(finding)]
        residual_rescans = [finding for finding in candidate_rescans if finding not in review_only_rescans]

        if decision == "pending":
            validation_outcome = "pending_confirmation"
            transform_status = "not_attempted"
            manual_review_items.append(_body_text_pending_manual_review_item(candidate_id, candidate))
        elif decision == "rejected":
            validation_outcome = "rejected_skip"
            skipped_candidate_ids.append(candidate_id)
            manual_review_items.append(_body_text_rejected_manual_review_item(candidate_id, candidate))
        elif review_only_rescans or any(str(action.get("status") or "") == "manual_review_required" for action in candidate_actions):
            validation_outcome = "low_confidence_manual_review"
            low_confidence_candidate_ids.append(candidate_id)
            manual_review_candidate_ids.append(candidate_id)
            for finding in review_only_rescans:
                manual_review_items.append(_manual_review_from_rescan(finding, validation_outcome="manual_review_required"))
        elif residual_rescans:
            validation_outcome = "residual"
            residual_candidate_ids.append(candidate_id)
            for finding in residual_rescans:
                residual_entry = _residual_entry(
                    finding,
                    validation_outcome="residual",
                    reason="The post-transform re-scan still matched this confirmed body-text candidate after SG5 transform work.",
                    action=candidate_actions[0] if candidate_actions else None,
                )
                residual_entry["candidate_id"] = candidate_id
                residual_entries.append(_sorted_copy(residual_entry))
                manual_review_items.append(_manual_review_from_residual(residual_entry, action=candidate_actions[0] if candidate_actions else None))
        elif decision == "approved":
            validation_outcome = "cleared"
        else:
            validation_outcome = "manual_review_required"
            manual_review_candidate_ids.append(candidate_id)

        decision_trace.append(
            {
                "candidate_id": candidate_id,
                "decision": decision,
                "occurrence_count": int(candidate.get("occurrence_count", 0) or len(candidate_actions) or len(candidate_rescans) or 0),
                "replacement_text": replacement_text,
                "transform_status": transform_status,
                "validation_outcome": validation_outcome,
                "location_samples": _body_text_location_samples(candidate, candidate_actions, candidate_rescans),
            }
        )

    for finding in unmatched_rescans:
        if _finding_match_key(finding) in matched_rescan_keys:
            continue
        if _is_review_only_finding(finding) or _is_review_only_category(finding):
            manual_review_items.append(_manual_review_from_rescan(finding, validation_outcome="manual_review_required"))

    decision_trace = sorted([_sorted_copy(entry) for entry in decision_trace], key=lambda entry: (str(entry.get("candidate_id") or ""), str(entry.get("decision") or "")))
    residual_candidate_ids = sorted(set(residual_candidate_ids))
    low_confidence_candidate_ids = sorted(set(low_confidence_candidate_ids))
    manual_review_candidate_ids = sorted(set(manual_review_candidate_ids))
    skipped_candidate_ids = sorted(set(skipped_candidate_ids))

    summary = {
        "run_mode": run_mode if candidates_by_id or context else "absent",
        "confirmation_required": bool(context.get("confirmation_required", bool(candidates_by_id))),
        "candidate_summary_count": len(candidates_by_id),
        "approved_candidate_ids": sorted(set(approved_candidate_ids)),
        "rejected_candidate_ids": sorted(set(rejected_candidate_ids)),
        "pending_candidate_ids": sorted(set(pending_candidate_ids)),
        "residual_candidate_ids": residual_candidate_ids,
        "low_confidence_candidate_ids": low_confidence_candidate_ids,
        "decision_counts": {
            "approved": len(set(approved_candidate_ids)),
            "rejected": len(set(rejected_candidate_ids)),
            "pending": len(set(pending_candidate_ids)),
            "skipped": len(skipped_candidate_ids),
            "manual_review_required": len(manual_review_candidate_ids),
            "residual": len(residual_candidate_ids),
            "low_confidence": len(low_confidence_candidate_ids),
        },
        "decision_trace": decision_trace,
        "next_step_guidance": _body_text_next_step_guidance(
            context,
            run_mode=run_mode,
            has_pending=bool(pending_candidate_ids),
            has_residual=bool(residual_candidate_ids),
            has_low_confidence=bool(low_confidence_candidate_ids),
        ),
    }
    return _sorted_copy(summary), _sorted_residuals(residual_entries), manual_review_items



def _normalize_body_text_candidate(candidate: dict) -> dict:
    normalized = dict(candidate)
    normalized["candidate_id"] = str(candidate.get("candidate_id") or _synthetic_body_text_candidate_id(candidate))
    normalized["display_text"] = str(candidate.get("display_text") or normalized["candidate_id"])
    normalized["occurrence_count"] = int(candidate.get("occurrence_count", 0) or 0)
    normalized["location_samples"] = list(candidate.get("location_samples") or [])
    normalized["reason_tags"] = list(candidate.get("reason_tags") or [])
    normalized["confidence_counts"] = dict(candidate.get("confidence_counts") or {})
    return normalized



def _synthetic_body_text_candidate_id(candidate: dict) -> str:
    return f"synthetic::{str(candidate.get('display_text') or candidate.get('normalized_candidate_key') or '<unknown>')}"



def _candidate_from_body_text_action(candidate_id: str, action: dict) -> dict:
    payload = action.get("payload") or {}
    return {
        "candidate_id": candidate_id,
        "display_text": str(payload.get("matched_text") or payload.get("normalized_text") or candidate_id),
        "occurrence_count": 1,
        "location_samples": [{"location": _sorted_copy(action.get("location") or {})}],
        "reason_tags": [],
        "confidence_counts": {str(action.get("confidence") or "unknown").lower(): 1},
    }



def _candidate_from_body_text_finding(candidate_id: str, finding: dict) -> dict:
    payload = finding.get("payload") or {}
    return {
        "candidate_id": candidate_id,
        "display_text": str(payload.get("matched_text") or payload.get("normalized_text") or candidate_id),
        "occurrence_count": 1,
        "location_samples": [{"location": _sorted_copy(finding.get("location") or {})}],
        "reason_tags": list(finding.get("reason_tags") or []),
        "confidence_counts": {str(finding.get("confidence") or "unknown").lower(): 1},
    }



def _candidate_id_for_body_text_finding(candidates_by_id: dict[str, dict], finding: dict) -> str | None:
    explicit_candidate_id = finding.get("candidate_id") or (finding.get("payload") or {}).get("candidate_id")
    if isinstance(explicit_candidate_id, str) and explicit_candidate_id.strip():
        return explicit_candidate_id.strip()
    payload = finding.get("payload") or {}
    matched_text = _normalized_body_text_text(payload.get("matched_text") or payload.get("normalized_text") or "")
    finding_id = str(finding.get("finding_id") or "")
    for candidate_id, candidate in candidates_by_id.items():
        location_samples = candidate.get("location_samples") or []
        if any(str(sample.get("finding_id") or "") == finding_id for sample in location_samples if isinstance(sample, dict)):
            return candidate_id
        if matched_text and matched_text == _normalized_body_text_text(candidate.get("display_text") or ""):
            return candidate_id
        normalized_key = str(candidate.get("normalized_candidate_key") or "")
        if matched_text and normalized_key.endswith(matched_text):
            return candidate_id
    return None



def _normalized_body_text_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())



def _aggregate_transform_status(actions: list[dict], *, default: str) -> str:
    if not actions:
        return default
    statuses = {str(action.get("status") or "unknown") for action in actions}
    if len(statuses) == 1:
        return sorted(statuses)[0]
    return "/".join(sorted(statuses))



def _body_text_location_samples(candidate: dict, actions: list[dict], rescans: list[dict]) -> list[dict]:
    samples: list[dict] = []
    for sample in list(candidate.get("location_samples") or []):
        if isinstance(sample, dict):
            samples.append(_sorted_copy(sample))
    for source in [*actions, *rescans]:
        sample = {"location": _sorted_copy(source.get("location") or {})}
        if sample not in samples:
            samples.append(sample)
        if len(samples) >= 5:
            break
    return samples[:5]



def _body_text_pending_manual_review_item(candidate_id: str, candidate: dict) -> dict:
    return {
        "category": "body_text",
        "finding_id": candidate_id,
        "location": _first_location_from_candidate(candidate),
        "reason": "Body-text candidate preview completed; explicit confirmation is still required before SG5 transforms will run.",
        "requested_action": "confirm",
        "source": "body_text_preview",
        "validation_outcome": "manual_review_required",
    }



def _body_text_rejected_manual_review_item(candidate_id: str, candidate: dict) -> dict:
    return {
        "category": "body_text",
        "finding_id": candidate_id,
        "location": _first_location_from_candidate(candidate),
        "reason": "Body-text candidate was explicitly rejected and left in place for intentional human follow-up.",
        "requested_action": "skip",
        "source": "body_text_confirmation",
        "validation_outcome": "manual_review_required",
    }



def _first_location_from_candidate(candidate: dict) -> dict:
    samples = list(candidate.get("location_samples") or [])
    if samples and isinstance(samples[0], dict):
        return _sorted_copy(samples[0].get("location") or {})
    return {}



def _body_text_next_step_guidance(context: dict, *, run_mode: str, has_pending: bool, has_residual: bool, has_low_confidence: bool) -> str:
    explicit = str(context.get("next_step_guidance") or "").strip()
    if explicit:
        return explicit
    if run_mode == "preview_only":
        return "Review the body-text candidate summary and rerun with body_text_confirmation.mode=apply_confirmed."
    if has_pending:
        return "Some body-text candidates still need explicit approval or rejection before a follow-up SG5 confirmation run."
    if has_residual:
        return "Confirmed body-text transforms left residual matches that still require targeted follow-up and manual review."
    if has_low_confidence:
        return "Low-confidence or layout-sensitive body-text findings remain manual-review items even after confirmation."
    return "Confirmed body-text decisions were resolved for this run. Human review still remains required in V1."



def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []



def _first_non_empty(values: list[object]) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None



def _run_level_body_text_mode(run_modes: Counter) -> str:
    if not run_modes:
        return "absent"
    if "preview_only" in run_modes:
        return "preview_only"
    if "apply_confirmed" in run_modes:
        return "apply_confirmed"
    return sorted(run_modes)[0]



def _render_report(folder: Path, report_path: Path, results: list[dict]) -> str:
    overall_status = _overall_status(results)
    total_residuals = sum(len(result["residual_findings"]) for result in results)
    total_warnings = sum(len(result["warnings"]) for result in results)
    total_manual = sum(len(result["manual_review_items"]) for result in results)
    file_status_counts = Counter(result["status"] for result in results)
    run_modes = Counter(result["body_text"]["run_mode"] for result in results)
    total_body_text_candidates, aggregate_body_text_counts = _aggregate_run_level_body_text(results)

    lines = [
        "# Anonymization Report",
        "",
        "## Run summary",
        f"- target_folder: `{folder}`",
        f"- report_path: `{report_path}`",
        f"- overall_status: `{overall_status}`",
        f"- supported_files_scanned: {len(results)}",
        f"- residual_findings: {total_residuals}",
        f"- warnings: {total_warnings}",
        f"- manual_review_items: {total_manual}",
        f"- file_status_counts: `{json.dumps(dict(sorted(file_status_counts.items())), ensure_ascii=False, sort_keys=True)}`",
        f"- body_text_run_mode: `{_run_level_body_text_mode(run_modes)}`",
        f"- body_text_confirmation_required: {any(result['body_text']['confirmation_required'] for result in results)}",
        f"- body_text_candidate_summary_count: {total_body_text_candidates}",
        f"- body_text_decision_counts: `{json.dumps(dict(sorted(aggregate_body_text_counts.items())), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Files processed",
    ]
    if results:
        for result in results:
            lines.append(
                "- "
                + f"`{result['relative_path']}`"
                + f" ({result['extension']}) -> status `{result['status']}`"
                + f", residuals {len(result['residual_findings'])}"
                + f", warnings {len(result['warnings'])}"
                + f", manual_review_items {len(result['manual_review_items'])}"
            )
    else:
        lines.append("- No supported V1 files were present in the target folder.")

    lines.extend(["", "## Body-text candidate summary"])
    any_body_text_candidates = False
    for result in results:
        candidates = list(result.get("body_text_candidates") or [])
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        if not candidates:
            lines.append("- No body-text candidates were generated for this run.")
            continue
        any_body_text_candidates = True
        for candidate in candidates:
            lines.append(
                "- "
                + f"`{candidate.get('candidate_id')}` | "
                + f"label `{candidate.get('display_text')}` | "
                + f"occurrences {int(candidate.get('occurrence_count', 0) or 0)} | "
                + f"reason_tags `{json.dumps(list(candidate.get('reason_tags') or []), ensure_ascii=False)}` | "
                + f"confidence_mix `{json.dumps(dict(candidate.get('confidence_counts') or {}), ensure_ascii=False, sort_keys=True)}` | "
                + f"sample_locations `{json.dumps([sample.get('location') for sample in list(candidate.get('location_samples') or [])[:3] if isinstance(sample, dict)], ensure_ascii=False, sort_keys=True)}`"
            )
    if not results:
        lines.append("")
        lines.append("- No body-text candidates were generated for this run.")

    lines.extend(["", "## Body-text decision trace and next-step guidance"])
    for result in results:
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        lines.append(f"- run_mode: `{result['body_text']['run_mode']}`")
        lines.append(f"- confirmation_required: {result['body_text']['confirmation_required']}")
        lines.append(f"- approved_candidate_ids: `{json.dumps(result['body_text']['approved_candidate_ids'], ensure_ascii=False)}`")
        lines.append(f"- rejected_candidate_ids: `{json.dumps(result['body_text']['rejected_candidate_ids'], ensure_ascii=False)}`")
        lines.append(f"- pending_candidate_ids: `{json.dumps(result['body_text']['pending_candidate_ids'], ensure_ascii=False)}`")
        lines.append(f"- residual_candidate_ids: `{json.dumps(result['body_text']['residual_candidate_ids'], ensure_ascii=False)}`")
        lines.append(f"- low_confidence_candidate_ids: `{json.dumps(result['body_text']['low_confidence_candidate_ids'], ensure_ascii=False)}`")
        lines.append(f"- decision_counts: `{json.dumps(result['body_text']['decision_counts'], ensure_ascii=False, sort_keys=True)}`")
        if result['body_text']['decision_trace']:
            for entry in result['body_text']['decision_trace']:
                lines.append(
                    "- "
                    + f"`{entry['candidate_id']}` | decision `{entry['decision']}` | "
                    + f"transform `{entry['transform_status']}` | outcome `{entry['validation_outcome']}` | "
                    + f"occurrences {entry['occurrence_count']} | replacement `{entry['replacement_text']}`"
                )
        else:
            lines.append("- No body-text candidates were generated for this run.")
        lines.append(f"- next_step_guidance: {result['body_text']['next_step_guidance']}")
        if result['body_text']['run_mode'] == 'preview_only':
            lines.append("- Replay reminder: rerun with body_text_confirmation.mode=apply_confirmed and explicit approved_candidate_ids and/or rejected_candidate_ids.")

    lines.extend(["", "## Transforms attempted and their statuses"])
    any_actions = False
    for result in results:
        actions = list(result["transform_summary"]["actions"])
        if not actions:
            continue
        any_actions = True
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        lines.append(f"- transform_status: `{result['transform_summary']['transform_status']}`")
        lines.append(
            "- action_status_counts: "
            + f"`{json.dumps(result['transform_summary']['action_status_counts'], ensure_ascii=False, sort_keys=True)}`"
        )
        for action in actions:
            lines.append(
                "- "
                + f"[{action['transform_status']}/{action['validation_outcome']}] "
                + f"{action['category']} at `{_location_text(action['location'])}` "
                + f"requested `{action['requested_action']}` -> applied `{action['applied_action']}`"
            )
    if not any_actions:
        lines.append("")
        lines.append("- No transform actions were provided to validation.")

    lines.extend(["", "## Warnings / skipped items / unsupported-scope notes"])
    any_warnings = False
    for result in results:
        if not result["warnings"] and not result['body_text']['rejected_candidate_ids']:
            continue
        any_warnings = True
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        for warning in result["warnings"]:
            lines.append(f"- {warning}")
        if result['body_text']['rejected_candidate_ids']:
            lines.append(
                "- rejected candidate ids: "
                + f"`{json.dumps(result['body_text']['rejected_candidate_ids'], ensure_ascii=False)}`"
            )
    if not any_warnings:
        lines.append("")
        lines.append("- None.")

    lines.extend(["", "## Residual findings after re-scan"])
    any_residuals = False
    for result in results:
        file_has_residual_text = bool(result['body_text']['residual_candidate_ids'] or result['body_text']['low_confidence_candidate_ids'])
        if not result["residual_findings"] and not file_has_residual_text:
            continue
        any_residuals = True
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        if result['body_text']['residual_candidate_ids']:
            lines.append(
                "- residual candidate ids: "
                + f"`{json.dumps(result['body_text']['residual_candidate_ids'], ensure_ascii=False)}`"
            )
        if result['body_text']['low_confidence_candidate_ids']:
            lines.append(
                "- low-confidence/manual-review candidate ids: "
                + f"`{json.dumps(result['body_text']['low_confidence_candidate_ids'], ensure_ascii=False)}`"
            )
        for residual in result["residual_findings"]:
            candidate_suffix = f" | candidate_id `{residual.get('candidate_id')}`" if residual.get('candidate_id') else ""
            lines.append(
                "- "
                + f"{residual['validation_outcome']} | "
                + f"category `{residual['category']}`{candidate_suffix} | "
                + f"location `{_location_text(residual['location'])}` | "
                + residual["reason"]
            )
    if not any_residuals:
        lines.append("")
        lines.append("- No high-confidence residual findings were detected by the post-transform re-scan.")

    lines.extend(["", "## Manual-review checklist"])
    any_manual_review = False
    for result in results:
        needs_body_text_review = result['body_text']['run_mode'] == 'preview_only' or bool(result['body_text']['low_confidence_candidate_ids'] or result['body_text']['rejected_candidate_ids'])
        if not result["manual_review_items"] and not needs_body_text_review:
            continue
        any_manual_review = True
        lines.append("")
        lines.append(f"### `{result['relative_path']}`")
        for item in result["manual_review_items"]:
            lines.append(
                "- "
                + f"{item['validation_outcome']} | "
                + f"category `{item['category']}` | "
                + f"location `{_location_text(item['location'])}` | "
                + str(item["reason"])
            )
        if result['body_text']['run_mode'] == 'preview_only':
            lines.append("- body_text confirmation reminder | review the candidate summary and rerun with body_text_confirmation.mode=apply_confirmed.")
        if result['body_text']['low_confidence_candidate_ids']:
            lines.append("- body_text low-confidence reminder | searchable PDF / layout-sensitive body-text findings remain review-first in this runtime.")
    if not any_manual_review:
        lines.append("")
        lines.append("- Manual review still remains recommended before external distribution, but no runtime-generated manual-review checklist items were required for this run.")

    lines.extend(["", "## Final validation outcome per file and overall run", ""])
    for result in results:
        lines.append(
            "- "
            + f"`{result['relative_path']}` -> `{result['status']}` "
            + f"(transform `{result['transform_summary']['transform_status']}`, "
            + f"body_text `{result['body_text']['run_mode']}`, "
            + f"residuals {len(result['residual_findings'])}, "
            + f"warnings {len(result['warnings'])}, "
            + f"manual_review_items {len(result['manual_review_items'])})"
        )
    lines.append("")
    lines.append(f"Overall run outcome: `{overall_status}`")
    return "\n".join(lines) + "\n"



def _aggregate_run_level_body_text(results: list[dict]) -> tuple[int, dict[str, int]]:
    candidate_ids: set[str] = set()
    approved_candidate_ids: set[str] = set()
    rejected_candidate_ids: set[str] = set()
    pending_candidate_ids: set[str] = set()
    residual_candidate_ids: set[str] = set()
    low_confidence_candidate_ids: set[str] = set()
    manual_review_candidate_ids: set[str] = set()
    skipped_candidate_ids: set[str] = set()

    for result in results:
        body_text = dict(result.get("body_text") or {})
        for candidate in list(result.get("body_text_candidates") or []):
            candidate_id = str(candidate.get("candidate_id") or _synthetic_body_text_candidate_id(candidate)).strip()
            if candidate_id:
                candidate_ids.add(candidate_id)

        for key, bucket in (
            ("approved_candidate_ids", approved_candidate_ids),
            ("rejected_candidate_ids", rejected_candidate_ids),
            ("pending_candidate_ids", pending_candidate_ids),
            ("residual_candidate_ids", residual_candidate_ids),
            ("low_confidence_candidate_ids", low_confidence_candidate_ids),
        ):
            for candidate_id in _string_list(body_text.get(key)):
                candidate_ids.add(candidate_id)
                bucket.add(candidate_id)

        for entry in list(body_text.get("decision_trace") or []):
            if not isinstance(entry, dict):
                continue
            candidate_id = str(entry.get("candidate_id") or "").strip()
            if not candidate_id:
                continue
            candidate_ids.add(candidate_id)
            validation_outcome = str(entry.get("validation_outcome") or "").strip().lower()
            if validation_outcome in {"manual_review_required", "low_confidence_manual_review"}:
                manual_review_candidate_ids.add(candidate_id)
            if validation_outcome == "rejected_skip":
                skipped_candidate_ids.add(candidate_id)

    manual_review_candidate_ids.update(low_confidence_candidate_ids)
    skipped_candidate_ids.update(rejected_candidate_ids)
    decision_counts = {
        "approved": len(approved_candidate_ids),
        "rejected": len(rejected_candidate_ids),
        "pending": len(pending_candidate_ids),
        "skipped": len(skipped_candidate_ids),
        "manual_review_required": len(manual_review_candidate_ids),
        "residual": len(residual_candidate_ids),
        "low_confidence": len(low_confidence_candidate_ids),
    }
    return len(candidate_ids), dict(sorted(decision_counts.items()))



def _group_findings_by_file(findings: list[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for finding in findings:
        file_key = _file_key(str(finding.get("file_path") or "<unknown>"), str(finding.get("extension") or ""))
        grouped.setdefault(file_key, []).append(_sorted_copy(finding))
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=_finding_sort_key)
    return grouped



def _group_transform_results(folder: Path, transform_results: list[dict]) -> dict[tuple[str, str], dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for raw_result in transform_results or []:
        result = _sorted_copy(raw_result if isinstance(raw_result, dict) else {"raw_result": raw_result})
        file_path_text = str(result.get("file_path") or "<unknown>")
        extension = str(result.get("extension") or _path_extension(Path(file_path_text)) if file_path_text != "<unknown>" else "")
        key = _file_key(file_path_text, extension)
        result.setdefault("relative_path", _safe_relative_path(folder, file_path_text))
        grouped[key] = result
    return grouped



def _ordered_file_keys(folder: Path, supported_files: list[Path], grouped_transform: dict[tuple[str, str], dict]) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for file_path in supported_files:
        key = _file_key(str(file_path), _path_extension(file_path))
        ordered.append(key)
        seen.add(key)

    extras = []
    for key, result in grouped_transform.items():
        if key in seen:
            continue
        relative_path = str(result.get("relative_path") or result.get("file_path") or "")
        extras.append((relative_path.casefold(), relative_path, key))
    extras.sort()
    ordered.extend(item[2] for item in extras)
    return ordered



def _file_key(file_path: str, extension: str) -> tuple[str, str]:
    return (str(file_path), str(extension or _path_extension(Path(file_path))).lower())



def _finding_match_key(finding: dict) -> tuple[str, str]:
    return (str(finding.get("category") or "unknown"), _location_text(finding.get("location") or {}))



def _action_match_key(action: dict) -> tuple[str, str]:
    return (str(action.get("category") or "unknown"), _location_text(action.get("location") or {}))



def _residual_entry(finding: dict, *, validation_outcome: str, reason: str, action: dict | None) -> dict:
    entry = {
        "finding_id": finding.get("finding_id"),
        "category": finding.get("category"),
        "location": _sorted_copy(finding.get("location") or {}),
        "payload": _sorted_copy(finding.get("payload") or {}),
        "confidence": finding.get("confidence"),
        "manual_review_reason": finding.get("manual_review_reason"),
        "validation_outcome": validation_outcome,
        "reason": reason,
        "matched_transform_action": {
            "finding_id": action.get("finding_id") if action else None,
            "requested_action": action.get("requested_action") if action else None,
            "applied_action": action.get("applied_action") if action else None,
            "transform_status": action.get("status") if action else None,
        },
    }
    return _sorted_copy(entry)



def _manual_review_from_residual(residual: dict, *, action: dict | None) -> dict:
    return {
        "category": residual.get("category"),
        "finding_id": residual.get("finding_id") or (action or {}).get("finding_id"),
        "location": _sorted_copy(residual.get("location") or {}),
        "reason": residual.get("reason"),
        "requested_action": (action or {}).get("requested_action"),
        "source": "residual_rescan",
        "validation_outcome": residual.get("validation_outcome"),
    }



def _manual_review_from_rescan(finding: dict, *, validation_outcome: str, action: dict | None = None) -> dict:
    reason = finding.get("manual_review_reason") or "The post-transform re-scan produced a low-confidence/manual-review validation signal."
    return {
        "category": finding.get("category"),
        "finding_id": finding.get("finding_id") or (action or {}).get("finding_id"),
        "location": _sorted_copy(finding.get("location") or {}),
        "reason": reason,
        "requested_action": (action or {}).get("requested_action"),
        "source": "rescan",
        "validation_outcome": validation_outcome,
    }



def _visual_review_item(action: dict, matched_rescan: dict | None) -> dict:
    category = str(action.get("category") or "unknown")
    location = _sorted_copy((matched_rescan or action).get("location") or {})
    if category == "images":
        reason = "Visually inspect the updated image region to confirm masking/replacement removed sensitive content without introducing obvious layout or rendering defects."
    elif category in {"headers", "footers"}:
        reason = "Visually inspect repeated page/slide/sheet surfaces to confirm rewritten header/footer content is acceptable and layout spacing was not broken."
    elif str(action.get("details") or {}).lower().find("pdf") >= 0:
        reason = "Visually inspect the edited PDF page for redraw/redaction-style artifacts, shifted layout, or visible remnants."
    else:
        reason = "Visually inspect the edited surface because automated validation cannot guarantee a safe final presentation state."
    return {
        "category": category,
        "finding_id": action.get("finding_id"),
        "location": location,
        "reason": reason,
        "requested_action": action.get("requested_action"),
        "source": "visual_review",
        "validation_outcome": "manual_review_required",
    }



def _requires_visual_review(action: dict) -> bool:
    category = str(action.get("category") or "")
    if category in _VISUAL_REVIEW_CATEGORIES:
        return True
    if category in {"comments", "notes"} and str(action.get("applied_action") or "") in {"replace", "clear", "remove"}:
        details_text = json.dumps(action.get("details") or {}, ensure_ascii=False, sort_keys=True)
        return "pdf" in details_text.casefold()
    return False



def _is_review_only_finding(finding: dict) -> bool:
    return bool(finding.get("manual_review_reason")) or str(finding.get("action_hint") or "") == "review" or str(finding.get("confidence") or "") == "low"



def _is_review_only_category(finding: dict) -> bool:
    return str(finding.get("category") or "") in _REVIEW_ONLY_CATEGORIES



def _payloads_equal(left, right) -> bool:
    return _sorted_copy(left or {}) == _sorted_copy(right or {})



def _relative_path_for_result(folder: Path, file_path: Path, transform_result: dict | None) -> str:
    if transform_result and transform_result.get("relative_path"):
        return str(transform_result["relative_path"])
    return _safe_relative_path(folder, str(file_path))



def _safe_relative_path(folder: Path, file_path: str) -> str:
    try:
        return Path(file_path).relative_to(folder).as_posix()
    except Exception:
        return Path(file_path).name or str(file_path)



def _path_extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")



def _location_text(location: dict) -> str:
    return json.dumps(_sorted_copy(location), ensure_ascii=False, separators=(",", ":"), sort_keys=True)



def _finding_sort_key(finding: dict) -> tuple[str, str, str]:
    return (
        str(finding.get("relative_path") or finding.get("file_path") or "").casefold(),
        str(finding.get("category") or ""),
        _location_text(finding.get("location") or {}),
    )



def _sorted_actions(actions: list[dict]) -> list[dict]:
    return sorted(
        [_sorted_copy(action) for action in actions],
        key=lambda action: (
            str(action.get("category") or ""),
            _location_text(action.get("location") or {}),
            str(action.get("finding_id") or ""),
        ),
    )



def _sorted_residuals(residuals: list[dict]) -> list[dict]:
    return sorted(
        [_sorted_copy(residual) for residual in residuals],
        key=lambda residual: (
            str(residual.get("category") or ""),
            _location_text(residual.get("location") or {}),
            str(residual.get("finding_id") or ""),
        ),
    )



def _sorted_manual_review_items(items: list[dict]) -> list[dict]:
    return sorted(
        [_sorted_copy(item) for item in items],
        key=lambda item: (
            str(item.get("category") or ""),
            _location_text(item.get("location") or {}),
            str(item.get("reason") or ""),
            str(item.get("finding_id") or ""),
        ),
    )



def _add_warning(result: dict, warning: str | None) -> None:
    if warning and warning not in result["warnings"]:
        result["warnings"].append(str(warning))



def _add_manual_review_item(result: dict, item: dict) -> None:
    normalized = _sorted_copy(item)
    if not normalized.get("reason"):
        return
    key = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    existing = {
        json.dumps(_sorted_copy(current), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        for current in result["manual_review_items"]
    }
    if key not in existing:
        result["manual_review_items"].append(normalized)



def _finalize_validation_status(result: dict) -> str:
    transform_status = str(result["transform_summary"].get("transform_status") or "")
    if transform_status == "error":
        return "error"
    action_outcomes = [action.get("validation_outcome") for action in result["transform_summary"]["actions"]]
    if any(outcome == "error" for outcome in action_outcomes):
        return "error"
    if result["residual_findings"]:
        return "partial_success"
    if result["warnings"]:
        return "partial_success"

    body_text = result.get("body_text") or _default_body_text_summary()
    if body_text.get("run_mode") == "preview_only" and int(body_text.get("candidate_summary_count", 0) or 0) > 0:
        return "manual_review_required"
    if body_text.get("residual_candidate_ids"):
        return "partial_success"
    if body_text.get("low_confidence_candidate_ids"):
        if any(action.get("transform_status") == "applied" for action in result["transform_summary"]["actions"]):
            return "partial_success"
        return "manual_review_required"
    if body_text.get("rejected_candidate_ids"):
        if any(action.get("transform_status") == "applied" for action in result["transform_summary"]["actions"]):
            return "partial_success"
        return "manual_review_required"
    if result["manual_review_items"]:
        if any(action.get("transform_status") == "applied" for action in result["transform_summary"]["actions"]):
            return "partial_success"
        return "manual_review_required"
    return "success"



def _overall_status(results: list[dict]) -> str:
    statuses = [result["status"] for result in results]
    if any(status == "error" for status in statuses):
        return "error"
    if any(status == "partial_success" for status in statuses):
        return "partial_success"
    if any(status == "manual_review_required" for status in statuses):
        return "manual_review_required"
    return "success"



def _sorted_copy(value):
    if isinstance(value, dict):
        return {key: _sorted_copy(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_copy(item) for item in value]
    return value
