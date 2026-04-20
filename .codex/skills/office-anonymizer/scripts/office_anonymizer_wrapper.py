from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import shutil
import sys


_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNTIME_SRC = _REPO_ROOT / "tools" / "office-automation" / "src"
if str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

from body_text_request_normalization import (  # noqa: E402
    build_body_text_policy_fragment,
    normalize_body_text_candidate_inputs,
    normalize_body_text_confirmation,
)
from office_automation.anonymize.candidate_summary import (  # noqa: E402
    build_body_text_candidate_summary,
    resolve_body_text_confirmation,
)
from office_automation.anonymize.detect import detect  # noqa: E402
from office_automation.anonymize.transform import transform  # noqa: E402
from office_automation.anonymize.validate import validate  # noqa: E402
from office_automation.common.files import list_office_files  # noqa: E402


_SUPPORTED_EXTENSIONS = frozenset({"xlsx", "xlsm", "docx", "pptx", "pdf"})
_SUPPORTED_EXTENSIONS_TEXT = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
_LEGACY_EXTENSION_MESSAGES = {
    "xls": "V1 does not support '.xls'. Convert the workbook to '.xlsx' or '.xlsm' before using office-anonymizer.",
    "xlsb": "V1 does not support '.xlsb'. Convert the workbook to '.xlsx' or '.xlsm' before using office-anonymizer.",
    "doc": "V1 does not support '.doc'. Convert the document to '.docx' before using office-anonymizer.",
    "ppt": "V1 does not support '.ppt'. Convert the presentation to '.pptx' before using office-anonymizer.",
}
_STATUS_LABELS = {
    0: "success",
    1: "unsupported_scope",
    2: "success_with_warnings",
    3: "fatal_error",
}
_DEFAULT_REPORT_NAME = "anonymization_report.md"
_DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "default_rules.yaml"
_ALLOWED_POLICY_KEYS = {
    "comments",
    "notes",
    "headers",
    "footers",
    "metadata",
    "images",
    "body_text",
    "manual_review_required",
}
_ALLOWED_IMAGE_CONFIRMATION_KEYS = {
    "enabled",
    "mode",
    "action",
    "replacement_path",
    "replacement_image",
    "replacement_asset",
    "path",
    "replacement",
    "mask_color",
    "color",
    "confirmed",
    "note",
    "notes",
}
_SCOPE_TEXT_KEYS = {
    "request_notes",
    "request_context",
    "scope_notes",
    "scope_context",
    "goal",
    "goals",
    "requirements",
    "constraints",
    "notes",
    "unsupported_requests",
}
_EMBEDDED_SCOPE_TOKENS = (
    "embedded object",
    "embedded objects",
    "embedded_object",
    "embedded_objects",
    "embedded file",
    "embedded files",
    "attachment",
    "attachments",
    "ole",
)
_OCR_SCOPE_TOKENS = (
    "tesseract",
    "external ocr",
    "ocr-dependent",
    "ocr dependent",
    "burned-in text cleanup",
    "burned in text cleanup",
    "scanned pdf cleanup",
    "scan-only cleanup",
    "image-only cleanup",
)
_PERFECT_GUARANTEE_TOKENS = (
    "perfect anonymization",
    "guaranteed anonymization",
    "guarantee anonymization",
    "100% anonymization",
    "no manual review",
    "without manual review",
    "perfect cleanup",
)


class UnsupportedScopeError(ValueError):
    """Raised when the wrapper rejects unsupported V1 scope before runtime handoff."""



def run(
    *,
    target_folder: str | Path,
    extensions: Sequence[str] | str | None = None,
    customization_overrides: Mapping | None = None,
    image_policy_confirmation: Mapping | str | None = None,
    body_text_candidate_inputs: Mapping | None = None,
    body_text_confirmation: Mapping | None = None,
    report_path: str | Path | None = None,
    request_notes: object | None = None,
    report_format: str | None = None,
) -> dict:
    return run_request(
        {
            "target_folder": target_folder,
            "extensions": extensions,
            "customization_overrides": customization_overrides,
            "image_policy_confirmation": image_policy_confirmation,
            "body_text_candidate_inputs": body_text_candidate_inputs,
            "body_text_confirmation": body_text_confirmation,
            "report_path": report_path,
            "request_notes": request_notes,
            "report_format": report_format,
        }
    )



def run_request(request: Mapping) -> dict:
    target_folder_text = _safe_request_value(request, "target_folder")

    try:
        normalized = _normalize_request(request)
        folder = normalized["target_folder"]
        requested_report_path = normalized["report_path"]
        default_report_path = folder / _DEFAULT_REPORT_NAME

        inventory = _inspect_target_folder(
            folder,
            extensions=normalized["extensions"],
            ignored_paths={default_report_path, *(set([requested_report_path]) if requested_report_path else set())},
        )

        if inventory["supported_file_count"] == 0 and inventory["unsupported_file_count"] > 0:
            unsupported_message = inventory["unsupported_files"][0]["message"]
            return _result(
                status=1,
                message=(
                    "No supported V1 files were available to anonymize in the target folder. "
                    + unsupported_message
                ),
                target_folder=str(folder),
                report_path=None,
                supported_file_count=0,
                supported_files=[],
                skipped_supported_file_count=inventory["skipped_supported_file_count"],
                skipped_supported_files=inventory["skipped_supported_files"],
                unsupported_file_count=inventory["unsupported_file_count"],
                unsupported_files=inventory["unsupported_files"],
                targeted_extensions=normalized["extensions"],
                policy_mode="not_started",
                policy_notes=[],
                detected_finding_count=0,
                detected_findings_by_category={},
                transform_status_counts={},
                validation_status_counts={},
                validation_statuses={},
                residual_findings_count=0,
                manual_review_item_count=0,
                warning_count=0,
                requires_manual_review=True,
                review_guidance="Human review remains required in V1, but this run was rejected before runtime processing.",
            )

        default_policy = _load_default_rules()
        detected = detect(
            str(folder),
            extensions=normalized["extensions"],
            body_text_candidate_inputs=normalized["body_text_candidate_inputs"],
        )
        body_text_summary = build_body_text_candidate_summary(detected)
        body_text_resolution = resolve_body_text_confirmation(
            body_text_summary,
            normalized["body_text_confirmation"],
        )
        preview_only = _should_return_body_text_preview_only(
            summary=body_text_summary,
            confirmation=normalized["body_text_confirmation"],
        )
        body_text_state = _build_body_text_result_state(
            summary=body_text_summary,
            confirmation=normalized["body_text_confirmation"],
            resolution=body_text_resolution,
            preview_only=preview_only,
        )

        resolved_policy, policy_mode, policy_notes = _resolve_policy(
            default_policy=default_policy,
            detected=detected,
            customization_overrides=normalized["customization_overrides"],
            image_policy_confirmation=normalized["image_policy_confirmation"],
            body_text_candidate_inputs=normalized["body_text_candidate_inputs"],
            body_text_confirmation=normalized["body_text_confirmation"],
            body_text_summary=body_text_summary,
            body_text_resolution=body_text_resolution,
        )

        if body_text_state["body_text_preview_only"]:
            _write_preview_report(
                report_path=default_report_path,
                target_folder=folder,
                targeted_extensions=normalized["extensions"],
                inventory=inventory,
                body_text_state=body_text_state,
            )
            final_report_path = _finalize_report_path(
                default_report_path=default_report_path,
                requested_report_path=requested_report_path,
            )
            return _build_summary(
                target_folder=folder,
                targeted_extensions=normalized["extensions"],
                inventory=inventory,
                policy=resolved_policy,
                policy_mode=policy_mode,
                policy_notes=policy_notes,
                detected=detected,
                transform_results=[],
                validation_results=[],
                report_path=final_report_path,
                runtime_report_path=default_report_path,
                body_text_state=body_text_state,
            )

        transform_results = transform(detected, resolved_policy)
        transform_results = _attach_body_text_context_to_transform_results(
            transform_results=transform_results,
            detected=detected,
            body_text_summary=body_text_summary,
            body_text_resolution=body_text_resolution,
            preview_only=preview_only,
        )
        validation_results = validate(str(folder), transform_results)
        final_report_path = _finalize_report_path(
            default_report_path=default_report_path,
            requested_report_path=requested_report_path,
        )

        summary = _build_summary(
            target_folder=folder,
            targeted_extensions=normalized["extensions"],
            inventory=inventory,
            policy=resolved_policy,
            policy_mode=policy_mode,
            policy_notes=policy_notes,
            detected=detected,
            transform_results=transform_results,
            validation_results=validation_results,
            report_path=final_report_path,
            runtime_report_path=default_report_path,
            body_text_state=body_text_state,
        )
        return summary
    except UnsupportedScopeError as exc:
        return _result(
            status=1,
            message=str(exc),
            target_folder=target_folder_text,
            report_path=None,
            supported_file_count=0,
            supported_files=[],
            skipped_supported_file_count=0,
            skipped_supported_files=[],
            unsupported_file_count=0,
            unsupported_files=[],
            targeted_extensions=None,
            policy_mode="not_started",
            policy_notes=[],
            detected_finding_count=0,
            detected_findings_by_category={},
            transform_status_counts={},
            validation_status_counts={},
            validation_statuses={},
            residual_findings_count=0,
            manual_review_item_count=0,
            warning_count=0,
            requires_manual_review=True,
            review_guidance="Human review remains required in V1, but this request was rejected before runtime processing.",
        )
    except Exception as exc:
        return _result(
            status=3,
            message=str(exc),
            target_folder=target_folder_text,
            report_path=None,
            supported_file_count=0,
            supported_files=[],
            skipped_supported_file_count=0,
            skipped_supported_files=[],
            unsupported_file_count=0,
            unsupported_files=[],
            targeted_extensions=None,
            policy_mode="failed",
            policy_notes=[],
            detected_finding_count=0,
            detected_findings_by_category={},
            transform_status_counts={},
            validation_status_counts={},
            validation_statuses={},
            residual_findings_count=0,
            manual_review_item_count=0,
            warning_count=0,
            requires_manual_review=True,
            review_guidance="Human review remains required in V1, but this run ended in a fatal wrapper/runtime failure.",
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        )



def _normalize_request(request: Mapping) -> dict:
    if not isinstance(request, Mapping):
        raise TypeError("office-anonymizer wrapper request must be a mapping.")

    target_folder_value = request.get("target_folder")
    if target_folder_value in (None, ""):
        raise UnsupportedScopeError("office-anonymizer requires a non-empty 'target_folder'.")

    target_folder = Path(target_folder_value).expanduser()
    if not target_folder.exists():
        raise UnsupportedScopeError(f"Target folder '{target_folder}' does not exist.")
    if target_folder.is_symlink() or not target_folder.is_dir():
        raise UnsupportedScopeError(f"Target folder '{target_folder}' is not a directory.")

    extensions = _normalize_extensions(request.get("extensions"))

    report_format = request.get("report_format")
    if report_format is not None:
        if not isinstance(report_format, str):
            raise TypeError("office-anonymizer field 'report_format' must be a string when provided.")
        normalized_report_format = report_format.strip().lower()
        if normalized_report_format not in {"md", "markdown"}:
            raise UnsupportedScopeError("office-anonymizer V1 writes Markdown reports only.")

    report_path = _coerce_report_path(request.get("report_path"), target_folder=target_folder)
    customization_overrides = _coerce_optional_mapping(
        request.get("customization_overrides"),
        field_name="customization_overrides",
    )
    if customization_overrides is not None:
        _validate_policy_keys(customization_overrides, field_name="customization_overrides")

    image_policy_confirmation = _normalize_image_policy_confirmation(request.get("image_policy_confirmation"))
    body_text_candidate_inputs = normalize_body_text_candidate_inputs(request.get("body_text_candidate_inputs"))
    body_text_confirmation = normalize_body_text_confirmation(request.get("body_text_confirmation"))

    _reject_explicit_unsupported_scope(request)

    return {
        "target_folder": target_folder,
        "extensions": extensions,
        "report_path": report_path,
        "customization_overrides": customization_overrides,
        "image_policy_confirmation": image_policy_confirmation,
        "body_text_candidate_inputs": body_text_candidate_inputs,
        "body_text_confirmation": body_text_confirmation,
    }



def _normalize_extensions(value: Sequence[str] | str | None) -> list[str] | None:
    if value is None:
        return None

    raw_values: list[str]
    if isinstance(value, str):
        raw_values = [part for part in value.replace(",", " ").split() if part]
    elif isinstance(value, Sequence):
        raw_values = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError("office-anonymizer extension overrides must contain strings only.")
            raw_values.append(item)
    else:
        raise TypeError("office-anonymizer field 'extensions' must be a string, a sequence of strings, or None.")

    if not raw_values:
        raise ValueError("office-anonymizer field 'extensions' cannot be empty when provided.")

    normalized = sorted({item.strip().lower().lstrip(".") for item in raw_values if item.strip()})
    if not normalized:
        raise ValueError("office-anonymizer field 'extensions' cannot contain only empty values.")

    unsupported = [item for item in normalized if item not in _SUPPORTED_EXTENSIONS]
    if unsupported:
        first = unsupported[0]
        if first in _LEGACY_EXTENSION_MESSAGES:
            raise UnsupportedScopeError(_LEGACY_EXTENSION_MESSAGES[first])
        raise UnsupportedScopeError(
            "office-anonymizer V1 supports only "
            + _SUPPORTED_EXTENSIONS_TEXT
            + f". Received unsupported extension '{first}'."
        )
    return normalized



def _coerce_report_path(value: str | Path | None, *, target_folder: Path) -> Path | None:
    if value in (None, ""):
        return None
    report_path = Path(value).expanduser()
    if not report_path.is_absolute():
        report_path = target_folder / report_path
    if report_path.suffix.lower() != ".md":
        raise UnsupportedScopeError("office-anonymizer V1 writes Markdown reports only; 'report_path' must end with '.md'.")
    return report_path



def _coerce_optional_mapping(value: object, *, field_name: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"office-anonymizer field '{field_name}' must be a mapping when provided.")
    return {str(key): _plain_value(item) for key, item in value.items()}



def _normalize_image_policy_confirmation(value: object) -> dict | None:
    if value is None:
        return None
    if isinstance(value, str):
        mode = value.strip().lower()
        if not mode:
            raise ValueError("image_policy_confirmation must not be empty when provided.")
        return {"mode": mode}
    if not isinstance(value, Mapping):
        raise TypeError("office-anonymizer field 'image_policy_confirmation' must be a mapping, string, or None.")

    normalized: dict = {}
    for key, raw in value.items():
        key_text = str(key)
        if key_text not in _ALLOWED_IMAGE_CONFIRMATION_KEYS:
            raise ValueError(
                "Unsupported image_policy_confirmation key '"
                + key_text
                + "'. Allowed keys: "
                + ", ".join(sorted(_ALLOWED_IMAGE_CONFIRMATION_KEYS))
                + "."
            )
        if key_text in {"confirmed", "note", "notes"}:
            continue
        normalized[key_text] = _plain_value(raw)
    return normalized



def _validate_policy_keys(policy: Mapping, *, field_name: str) -> None:
    unknown = sorted(str(key) for key in policy if str(key) not in _ALLOWED_POLICY_KEYS)
    if unknown:
        raise ValueError(
            f"office-anonymizer field '{field_name}' contains unsupported top-level policy keys: "
            + ", ".join(unknown)
            + "."
        )



def _reject_explicit_unsupported_scope(request: Mapping) -> None:
    collected = []
    for key in _SCOPE_TEXT_KEYS:
        if key in request:
            collected.extend(_iter_text_fragments(request[key]))

    combined_text = " ".join(collected).lower()
    if not combined_text:
        return
    if any(token in combined_text for token in _EMBEDDED_SCOPE_TOKENS):
        raise UnsupportedScopeError(
            "Embedded objects, OLE cleanup, and attachments are outside office-anonymizer V1 scope. "
            "Use supported file-content anonymization instead."
        )
    if any(token in combined_text for token in _OCR_SCOPE_TOKENS):
        raise UnsupportedScopeError(
            "OCR-dependent cleanup and external OCR / Tesseract flows are outside office-anonymizer V1 scope. "
            "Use files that already expose supported text, metadata, or image targets and keep human review in the loop."
        )
    if any(token in combined_text for token in _PERFECT_GUARANTEE_TOKENS):
        raise UnsupportedScopeError(
            "office-anonymizer V1 reduces risk but does not guarantee perfect anonymization. Human review remains required."
        )



def _inspect_target_folder(folder: Path, *, extensions: list[str] | None, ignored_paths: set[Path]) -> dict:
    ignored_resolved = {path.resolve(strict=False) for path in ignored_paths}
    regular_files = [
        path
        for path in sorted(folder.iterdir(), key=lambda item: (item.name.casefold(), item.name))
        if path.is_file() and not path.is_symlink() and path.resolve(strict=False) not in ignored_resolved
    ]

    all_supported_files = list_office_files(folder)
    targeted_files = list_office_files(folder, extensions=extensions) if extensions is not None else list(all_supported_files)
    targeted_resolved = {path.resolve(strict=False) for path in targeted_files}

    skipped_supported_files = [
        _file_entry(path, reason="Not targeted because the extension filter narrowed this run.")
        for path in all_supported_files
        if path.resolve(strict=False) not in targeted_resolved
    ]

    supported_resolved = {path.resolve(strict=False) for path in all_supported_files}
    unsupported_files = []
    for path in regular_files:
        if path.resolve(strict=False) in supported_resolved:
            continue
        extension = path.suffix.lower().lstrip(".")
        unsupported_files.append(
            {
                "path": path.name,
                "extension": extension or None,
                "message": _unsupported_file_message(extension),
            }
        )

    return {
        "supported_file_count": len(targeted_files),
        "supported_files": [path.name for path in targeted_files],
        "skipped_supported_file_count": len(skipped_supported_files),
        "skipped_supported_files": skipped_supported_files,
        "unsupported_file_count": len(unsupported_files),
        "unsupported_files": unsupported_files,
    }



def _file_entry(path: Path, *, reason: str) -> dict:
    return {
        "path": path.name,
        "extension": path.suffix.lower().lstrip(".") or None,
        "reason": reason,
    }



def _unsupported_file_message(extension: str) -> str:
    if extension in _LEGACY_EXTENSION_MESSAGES:
        return _LEGACY_EXTENSION_MESSAGES[extension]
    display_extension = extension or "<none>"
    return (
        "office-anonymizer V1 supports only "
        + _SUPPORTED_EXTENSIONS_TEXT
        + f". Unsupported file extension '{display_extension}' was skipped."
    )



def _load_default_rules() -> dict:
    payload = json.loads(_DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("default_rules.yaml must decode to a top-level mapping.")
    _validate_policy_keys(payload, field_name="default_rules.yaml")
    return _json_clone(payload)



def _resolve_policy(
    *,
    default_policy: dict,
    detected: list[dict],
    customization_overrides: dict | None,
    image_policy_confirmation: dict | None,
    body_text_candidate_inputs: dict,
    body_text_confirmation: dict,
    body_text_summary: dict,
    body_text_resolution: dict,
) -> tuple[dict, str, list[str]]:
    policy = _json_clone(default_policy)
    policy_notes: list[str] = []
    policy_mode = "default"

    if customization_overrides:
        policy = _merge_dicts(policy, customization_overrides)
        policy_mode = "customized"
        policy_notes.append("Applied one-step customization overrides on top of the packaged defaults.")

    images_detected = any(str(finding.get("category") or "") == "images" for finding in detected)
    current_image_policy = dict(policy.get("images") or {})

    if image_policy_confirmation:
        current_image_policy = _merge_dicts(current_image_policy, image_policy_confirmation)
        policy["images"] = current_image_policy
        policy_mode = "customized"
        confirmed_mode = str(
            current_image_policy.get("mode", current_image_policy.get("action", "report_only"))
        ).strip().lower()
        policy_notes.append(f"Applied one-time image policy confirmation for this run with mode '{confirmed_mode}'.")
    elif images_detected:
        image_mode = str(current_image_policy.get("mode", current_image_policy.get("action", "report_only"))).strip().lower()
        if image_mode not in {"report_only", "skip"}:
            current_image_policy["mode"] = "report_only"
            policy["images"] = current_image_policy
            policy_notes.append(
                "Image findings were kept at 'report_only' because no one-time image_policy_confirmation was provided for this run."
            )
        else:
            policy_notes.append(
                "Image findings remain at the packaged safe posture until a run-level image decision is confirmed."
            )

    if _has_body_text_request_state(body_text_candidate_inputs, body_text_confirmation) or any(
        str(finding.get("category") or "") == "body_text" for finding in detected
    ):
        body_text_policy = build_body_text_policy_fragment(body_text_candidate_inputs, body_text_confirmation)["body_text"]
        body_text_policy["confirmation_required"] = bool(body_text_summary.get("confirmation_required"))
        body_text_policy["candidate_count"] = int(body_text_summary.get("candidate_count", 0) or 0)
        body_text_policy["approved_candidate_ids"] = list(body_text_resolution.get("approved_candidate_ids") or [])
        body_text_policy["rejected_candidate_ids"] = list(body_text_resolution.get("rejected_candidate_ids") or [])
        body_text_policy["undecided_candidate_ids"] = list(body_text_resolution.get("undecided_candidate_ids") or [])
        body_text_policy["approved_finding_ids"] = list(body_text_resolution.get("approved_finding_ids") or [])
        body_text_policy["non_transformable_finding_ids"] = list(body_text_resolution.get("non_transformable_finding_ids") or [])
        body_text_policy["candidate_decisions"] = _plain_value(body_text_resolution.get("candidate_decisions") or {})
        body_text_policy["confirmation_warnings"] = list(body_text_resolution.get("warnings") or [])
        body_text_policy["candidate_summary"] = {
            "summary_version": body_text_summary.get("summary_version"),
            "candidate_count": body_text_summary.get("candidate_count", 0),
            "finding_count": body_text_summary.get("finding_count", 0),
            "manual_review_candidate_count": body_text_summary.get("manual_review_candidate_count", 0),
            "candidates": _plain_value(body_text_summary.get("candidates") or []),
            "finding_to_candidate": _plain_value(body_text_summary.get("finding_to_candidate") or {}),
        }
        policy["body_text"] = body_text_policy
        policy_mode = "customized"
        policy_notes.append(
            "Resolved SG5 body-text candidate summary and explicit confirmation state for this run."
        )

    policy.setdefault("manual_review_required", True)
    return policy, policy_mode, policy_notes



def _attach_body_text_context_to_transform_results(
    *,
    transform_results: list[dict],
    detected: list[dict],
    body_text_summary: Mapping,
    body_text_resolution: Mapping,
    preview_only: bool,
) -> list[dict]:
    if not transform_results:
        return transform_results

    grouped_findings: dict[str, list[dict]] = {}
    for finding in detected:
        if str(finding.get("category") or "") != "body_text":
            continue
        relative_path = str(finding.get("relative_path") or "").strip()
        if not relative_path:
            continue
        grouped_findings.setdefault(relative_path, []).append(finding)

    if not grouped_findings:
        return transform_results

    candidate_decisions = body_text_resolution.get("candidate_decisions")
    if not isinstance(candidate_decisions, Mapping):
        candidate_decisions = {}

    approved_candidate_ids = list(body_text_resolution.get("approved_candidate_ids") or [])
    rejected_candidate_ids = list(body_text_resolution.get("rejected_candidate_ids") or [])
    pending_candidate_ids = list(body_text_resolution.get("undecided_candidate_ids") or [])
    run_mode = _body_text_run_mode(
        candidate_count=int(body_text_summary.get("candidate_count", 0) or 0),
        preview_only=preview_only,
    )
    next_step_guidance = (
        "Review the body-text candidate summary and rerun with body_text_confirmation.mode=apply_confirmed."
        if preview_only
        else "Confirmed body-text decisions were applied only to the approved subset."
    )

    for result in transform_results:
        if not isinstance(result, dict):
            continue
        relative_path = str(result.get("relative_path") or Path(str(result.get("file_path") or "")).name).strip()
        findings = grouped_findings.get(relative_path)
        if not findings:
            continue

        file_summary = build_body_text_candidate_summary(findings)
        candidate_ids = {str(candidate.get("candidate_id") or "") for candidate in file_summary.get("candidates") or []}
        candidate_ids.discard("")
        result["body_text"] = {
            "candidate_summary": _plain_value(file_summary),
            "candidate_decisions": {
                candidate_id: _plain_value(candidate_decisions[candidate_id])
                for candidate_id in candidate_ids
                if candidate_id in candidate_decisions
            },
            "confirmation_required": bool(file_summary.get("confirmation_required")),
            "next_step_guidance": next_step_guidance,
            "pending_candidate_ids": [candidate_id for candidate_id in pending_candidate_ids if candidate_id in candidate_ids],
            "approved_candidate_ids": [candidate_id for candidate_id in approved_candidate_ids if candidate_id in candidate_ids],
            "rejected_candidate_ids": [candidate_id for candidate_id in rejected_candidate_ids if candidate_id in candidate_ids],
            "undecided_candidate_ids": [candidate_id for candidate_id in pending_candidate_ids if candidate_id in candidate_ids],
            "run_mode": run_mode,
        }

    return transform_results



def _should_return_body_text_preview_only(*, summary: Mapping, confirmation: Mapping) -> bool:
    if int(summary.get("candidate_count", 0) or 0) == 0:
        return False
    if str(confirmation.get("mode") or "preview_only") != "apply_confirmed":
        return True
    return not _has_explicit_body_text_decisions(confirmation)



def _has_explicit_body_text_decisions(confirmation: Mapping) -> bool:
    return bool(confirmation.get("approved_candidate_ids") or confirmation.get("rejected_candidate_ids"))



def _build_body_text_result_state(
    *,
    summary: Mapping,
    confirmation: Mapping,
    resolution: Mapping,
    preview_only: bool,
) -> dict:
    candidate_count = int(summary.get("candidate_count", 0) or 0)
    confirmation_required = bool(summary.get("confirmation_required"))
    candidate_decisions = dict(resolution.get("candidate_decisions") or {})
    approved_candidate_ids = list(resolution.get("approved_candidate_ids") or [])
    rejected_candidate_ids = list(resolution.get("rejected_candidate_ids") or [])
    undecided_candidate_ids = list(resolution.get("undecided_candidate_ids") or [])
    manual_review_candidate_ids = [
        candidate_id
        for candidate_id, decision in candidate_decisions.items()
        if isinstance(decision, Mapping) and bool(decision.get("manual_review_required"))
    ]
    flagged_candidate_ids = [
        candidate_id
        for candidate_id, decision in candidate_decisions.items()
        if (
            (isinstance(decision, Mapping) and bool(decision.get("manual_review_required")))
            or str((decision or {}).get("decision") or "") in {"manual_review", "rejected", "undecided"}
        )
    ]

    if candidate_count == 0:
        confirmation_mode = "not_needed"
        next_step_guidance = "No SG5 body-text candidates were detected, so no explicit body-text confirmation rerun is required for this folder."
    elif preview_only:
        confirmation_mode = "preview_only"
        next_step_guidance = (
            "Review the body-text candidate summary and rerun with body_text_confirmation.mode='apply_confirmed' plus explicit "
            "approved_candidate_ids and/or rejected_candidate_ids."
        )
    else:
        confirmation_mode = "apply_confirmed"
        if undecided_candidate_ids:
            next_step_guidance = (
                "Only explicitly approved body-text candidates will be eligible for SG5 transforms. Rerun with additional "
                "approved_candidate_ids and/or rejected_candidate_ids to resolve the remaining undecided candidates."
            )
        elif rejected_candidate_ids or manual_review_candidate_ids:
            next_step_guidance = (
                "Confirmed body-text decisions were applied to the approved subset only. Rejected or manual-review body-text "
                "candidates remain in the report for human follow-up."
            )
        else:
            next_step_guidance = "Confirmed body-text decisions were resolved for all detected candidates in this run. Human review still remains required in V1."

    decision_counts = {
        "approved": len(approved_candidate_ids),
        "rejected": len(rejected_candidate_ids),
        "undecided": len(undecided_candidate_ids),
        "manual_review": len(manual_review_candidate_ids),
    }
    warning_messages = list(resolution.get("warnings") or [])
    if preview_only and candidate_count:
        warning_messages.insert(
            0,
            "Candidate preview completed; explicit confirmation is required before body-text transforms will run.",
        )

    candidate_summaries = _build_body_text_candidate_summaries(summary=summary, resolution=resolution)
    confirmation_request_template = {
        "mode": "apply_confirmed",
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "replacement_overrides": {},
    }
    low_confidence_candidate_count = sum(
        1 for candidate in summary.get("candidates") or [] if _candidate_has_low_confidence(candidate)
    )
    run_mode = _body_text_run_mode(candidate_count=candidate_count, preview_only=preview_only)
    residual_candidate_count = len(set(flagged_candidate_ids)) if candidate_count else 0

    return {
        "body_text_candidate_summary": _plain_value(summary),
        "body_text_candidate_count": candidate_count,
        "body_text_confirmation_required": confirmation_required,
        "body_text_confirmation_mode": confirmation_mode,
        "body_text_preview_only": preview_only,
        "body_text_decision_counts": decision_counts,
        "approved_candidate_ids": approved_candidate_ids,
        "rejected_candidate_ids": rejected_candidate_ids,
        "undecided_candidate_ids": undecided_candidate_ids,
        "next_step_guidance": next_step_guidance,
        "body_text_confirmation_warnings": warning_messages,
        "manual_review_item_count": residual_candidate_count,
        "warning_count": len(warning_messages),
        "raw_confirmation_mode": str(confirmation.get("mode") or "preview_only"),
        "body_text_run_mode": run_mode,
        "body_text_candidate_summary_count": len(candidate_summaries),
        "body_text_candidate_summaries": candidate_summaries,
        "body_text_pending_candidate_count": len(undecided_candidate_ids),
        "body_text_approved_candidate_count": len(approved_candidate_ids),
        "body_text_rejected_candidate_count": len(rejected_candidate_ids),
        "body_text_residual_candidate_count": residual_candidate_count,
        "body_text_low_confidence_candidate_count": low_confidence_candidate_count,
        "body_text_next_step_guidance": next_step_guidance,
        "body_text_confirmation_request_template": confirmation_request_template,
    }



def _write_preview_report(
    *,
    report_path: Path,
    target_folder: Path,
    targeted_extensions: list[str] | None,
    inventory: Mapping,
    body_text_state: Mapping,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary = body_text_state["body_text_candidate_summary"]
    candidates = list(summary.get("candidates") or [])
    lines = [
        "# Anonymization Report",
        "",
        "## Run summary",
        f"- target_folder: `{target_folder}`",
        f"- overall_status: `preview_only`",
        f"- supported_files_scanned: {inventory['supported_file_count']}",
        f"- targeted_extensions: `{json.dumps(targeted_extensions, ensure_ascii=False) if targeted_extensions is not None else 'all supported V1 extensions'}`",
        f"- body_text_run_mode: `{body_text_state['body_text_run_mode']}`",
        f"- body_text_candidate_count: {body_text_state['body_text_candidate_count']}",
        f"- body_text_confirmation_mode: `{body_text_state['body_text_confirmation_mode']}`",
        f"- body_text_decision_counts: `{json.dumps(body_text_state['body_text_decision_counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "Candidate preview completed; explicit confirmation is required before body-text transforms will run.",
        "",
        "## Files in scope",
        f"- supported_files: `{json.dumps(inventory['supported_files'], ensure_ascii=False)}`",
        f"- unsupported_files: `{json.dumps(inventory['unsupported_files'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Body-text candidate summary",
    ]
    if not candidates:
        lines.append("- No body-text candidates were detected.")
    else:
        for candidate in candidates:
            lines.append(
                "- "
                + f"`{candidate['candidate_id']}` | "
                + f"{candidate['candidate_category']} | "
                + f"display `{candidate['display_text']}` | "
                + f"occurrences {candidate['occurrence_count']} | "
                + f"recommended replacement `{candidate.get('recommended_replacement')}`"
            )

    lines.extend(
        [
            "",
            "## Next step guidance",
            f"- {body_text_state['next_step_guidance']}",
            "- Use body_text_confirmation.mode=`apply_confirmed` with explicit approved_candidate_ids and/or rejected_candidate_ids on the next run.",
            "",
            "## Body-text confirmation request template",
            f"```json\n{json.dumps(body_text_state['body_text_confirmation_request_template'], ensure_ascii=False, indent=2)}\n```",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")



def _body_text_run_mode(*, candidate_count: int, preview_only: bool) -> str:
    if candidate_count == 0:
        return "absent"
    if preview_only:
        return "preview_only"
    return "apply_confirmed"



def _build_body_text_candidate_summaries(*, summary: Mapping, resolution: Mapping) -> list[dict]:
    candidate_summaries: list[dict] = []
    candidate_decisions = resolution.get("candidate_decisions") if isinstance(resolution, Mapping) else None
    if not isinstance(candidate_decisions, Mapping):
        candidate_decisions = {}

    for raw_candidate in summary.get("candidates") or []:
        if not isinstance(raw_candidate, Mapping):
            continue
        candidate = dict(raw_candidate)
        candidate_id = str(candidate.get("candidate_id") or "")
        decision_payload = candidate_decisions.get(candidate_id)
        if not isinstance(decision_payload, Mapping):
            decision_payload = {}
        candidate_summaries.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": str(candidate.get("candidate_category") or "generic_identifier"),
                "normalized_text": _body_text_candidate_normalized_text(candidate),
                "occurrence_count": int(candidate.get("occurrence_count", 0) or 0),
                "reason_tags": list(candidate.get("reason_tags") or []),
                "replacement_text": decision_payload.get("replacement_text", candidate.get("recommended_replacement")),
                "sample_locations": _plain_value(candidate.get("location_samples") or []),
                "decision": str(decision_payload.get("decision") or "undecided"),
                "manual_review_required": bool(
                    decision_payload.get("manual_review_required", candidate.get("manual_review_required"))
                ),
            }
        )
    return candidate_summaries



def _body_text_candidate_normalized_text(candidate: Mapping) -> str:
    normalized_key = str(candidate.get("normalized_candidate_key") or "")
    parts = normalized_key.split("::")
    if len(parts) >= 2:
        return parts[1]
    display_text = str(candidate.get("display_text") or "").strip().lower()
    return display_text



def _candidate_has_low_confidence(candidate: Mapping) -> bool:
    confidence_counts = candidate.get("confidence_counts")
    if not isinstance(confidence_counts, Mapping):
        return False
    return int(confidence_counts.get("low", 0) or 0) > 0



def _finalize_report_path(*, default_report_path: Path, requested_report_path: Path | None) -> Path:
    if requested_report_path is None or requested_report_path.resolve(strict=False) == default_report_path.resolve(strict=False):
        return default_report_path
    requested_report_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(default_report_path, requested_report_path)
    return requested_report_path



def _build_summary(
    *,
    target_folder: Path,
    targeted_extensions: list[str] | None,
    inventory: dict,
    policy: dict,
    policy_mode: str,
    policy_notes: list[str],
    detected: list[dict],
    transform_results: list[dict],
    validation_results: list[dict],
    report_path: Path,
    runtime_report_path: Path,
    body_text_state: Mapping,
) -> dict:
    detected_by_category = dict(sorted(Counter(str(item.get("category") or "unknown") for item in detected).items()))
    transform_status_counts = dict(sorted(Counter(str(item.get("status") or "unknown") for item in transform_results).items()))
    validation_status_counts = dict(sorted(Counter(str(item.get("status") or "unknown") for item in validation_results).items()))
    validation_statuses = {
        str(item.get("relative_path") or item.get("file_path") or f"file-{index}"): str(item.get("status") or "unknown")
        for index, item in enumerate(validation_results, start=1)
    }

    residual_findings_count = sum(len(item.get("residual_findings") or []) for item in validation_results)
    runtime_manual_review_item_count = sum(len(item.get("manual_review_items") or []) for item in validation_results)
    runtime_warning_count = sum(len(item.get("warnings") or []) for item in validation_results)
    body_text_manual_review_item_count = int(body_text_state.get("manual_review_item_count", 0) or 0)
    body_text_warning_count = int(body_text_state.get("warning_count", 0) or 0)
    manual_review_item_count = (
        runtime_manual_review_item_count if validation_results else body_text_manual_review_item_count
    )
    warning_count = runtime_warning_count + body_text_warning_count
    fatal_runtime_error = any(str(item.get("status") or "") == "error" for item in validation_results) or any(
        str(item.get("status") or "") == "error" for item in transform_results
    )
    preview_only = bool(body_text_state.get("body_text_preview_only"))

    if fatal_runtime_error:
        status = 3
        message = "Anonymization failed with a fatal runtime error. Review the error details and report context."
    elif preview_only:
        status = 2
        message = "Candidate preview completed; explicit confirmation is required before body-text transforms will run."
    elif residual_findings_count or manual_review_item_count or warning_count or inventory["unsupported_file_count"]:
        status = 2
        message = "Anonymization completed, but manual review and report follow-up are required."
    else:
        status = 0
        message = "Anonymization completed within supported V1 scope."

    return _result(
        status=status,
        message=message,
        target_folder=str(target_folder),
        report_path=str(report_path),
        runtime_report_path=str(runtime_report_path),
        supported_file_count=inventory["supported_file_count"],
        supported_files=inventory["supported_files"],
        skipped_supported_file_count=inventory["skipped_supported_file_count"],
        skipped_supported_files=inventory["skipped_supported_files"],
        unsupported_file_count=inventory["unsupported_file_count"],
        unsupported_files=inventory["unsupported_files"],
        targeted_extensions=targeted_extensions,
        policy_mode=policy_mode,
        policy_notes=policy_notes,
        resolved_policy=policy,
        detected_finding_count=len(detected),
        detected_findings_by_category=detected_by_category,
        transform_status_counts=transform_status_counts,
        validation_status_counts=validation_status_counts,
        validation_statuses=validation_statuses,
        residual_findings_count=residual_findings_count,
        manual_review_item_count=manual_review_item_count,
        warning_count=warning_count,
        requires_manual_review=bool(status == 2 or manual_review_item_count or residual_findings_count),
        review_guidance=(
            "Human review remains required in V1, especially for PDFs, images, visually sensitive content, "
            "and any warning-bearing or residual-bearing result."
        ),
        validation_results=validation_results,
        body_text_candidate_count=body_text_state["body_text_candidate_count"],
        body_text_candidate_summary=body_text_state["body_text_candidate_summary"],
        body_text_confirmation_required=body_text_state["body_text_confirmation_required"],
        body_text_confirmation_mode=body_text_state["body_text_confirmation_mode"],
        body_text_preview_only=body_text_state["body_text_preview_only"],
        body_text_decision_counts=body_text_state["body_text_decision_counts"],
        approved_candidate_ids=body_text_state["approved_candidate_ids"],
        rejected_candidate_ids=body_text_state["rejected_candidate_ids"],
        undecided_candidate_ids=body_text_state["undecided_candidate_ids"],
        next_step_guidance=body_text_state["next_step_guidance"],
        body_text_confirmation_warnings=body_text_state["body_text_confirmation_warnings"],
        body_text_run_mode=body_text_state["body_text_run_mode"],
        body_text_candidate_summary_count=body_text_state["body_text_candidate_summary_count"],
        body_text_candidate_summaries=body_text_state["body_text_candidate_summaries"],
        body_text_pending_candidate_count=body_text_state["body_text_pending_candidate_count"],
        body_text_approved_candidate_count=body_text_state["body_text_approved_candidate_count"],
        body_text_rejected_candidate_count=body_text_state["body_text_rejected_candidate_count"],
        body_text_residual_candidate_count=body_text_state["body_text_residual_candidate_count"],
        body_text_low_confidence_candidate_count=body_text_state["body_text_low_confidence_candidate_count"],
        body_text_next_step_guidance=body_text_state["body_text_next_step_guidance"],
        body_text_confirmation_request_template=body_text_state["body_text_confirmation_request_template"],
    )



def _merge_dicts(base: Mapping, overrides: Mapping) -> dict:
    merged = _json_clone(base)
    for key, value in overrides.items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[str(key)] = _merge_dicts(merged[str(key)], value)
        else:
            merged[str(key)] = _plain_value(value)
    return merged



def _has_body_text_request_state(candidate_inputs: Mapping, confirmation: Mapping) -> bool:
    return bool(
        candidate_inputs.get("person_names")
        or candidate_inputs.get("company_names")
        or candidate_inputs.get("emails")
        or candidate_inputs.get("phones")
        or candidate_inputs.get("addresses")
        or candidate_inputs.get("domains")
        or candidate_inputs.get("exact_phrases")
        or candidate_inputs.get("context_terms")
        or candidate_inputs.get("replacement_text")
        or candidate_inputs.get("replacement_map")
        or confirmation.get("mode") != "preview_only"
        or confirmation.get("approved_candidate_ids")
        or confirmation.get("rejected_candidate_ids")
        or confirmation.get("replacement_overrides")
        or confirmation.get("review_notes")
    )



def _iter_text_fragments(value: object) -> list[str]:
    fragments: list[str] = []
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            fragments.extend(_iter_text_fragments(nested_key))
            fragments.extend(_iter_text_fragments(nested_value))
        return fragments
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            fragments.extend(_iter_text_fragments(item))
        return fragments
    if value in (None, ""):
        return fragments
    fragments.append(str(value))
    return fragments



def _plain_value(value: object):
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    return value



def _json_clone(value):
    return json.loads(json.dumps(value))



def _safe_request_value(request: object, field_name: str) -> str | None:
    if isinstance(request, Mapping):
        value = request.get(field_name)
        if value not in (None, ""):
            return str(value)
    return None



def _result(*, status: int, message: str, **payload) -> dict:
    result = {
        "status": status,
        "status_label": _STATUS_LABELS.get(status, "unknown"),
        "message": message,
    }
    result.update(payload)
    return result
