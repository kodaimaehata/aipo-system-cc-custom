"""Body-text candidate aggregation and confirmation helpers for SG5."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import re

__all__ = ["build_body_text_candidate_summary", "resolve_body_text_confirmation"]

_ALLOWED_CONFIRMATION_KEYS = {
    "mode",
    "approved_candidate_ids",
    "rejected_candidate_ids",
    "replacement_overrides",
    "review_notes",
}
_ALLOWED_CONFIRMATION_MODES = {"preview_only", "apply_confirmed", "disabled"}
_CONFIDENCE_KEYS = ("high", "medium", "low")
_SOURCE_KEYS = ("user_hint", "heuristic", "pattern", "mixed")
_SAMPLE_LIMIT = 5
_REASON_TAG_CATEGORY_MAP = {
    "address_hint": "address",
    "company_hint": "company_name",
    "context_assisted_phrase": "person_name",
    "domain_hint": "domain",
    "domain_pattern": "domain",
    "email_hint": "email",
    "email_pattern": "email",
    "exact_phrase": "exact_phrase",
    "person_hint": "person_name",
    "phone_hint": "phone",
    "phone_pattern": "phone",
}



def build_body_text_candidate_summary(findings: Iterable[object]) -> dict:
    """Aggregate SG5 body_text findings into stable candidate summaries."""
    filtered_findings = [_validate_body_text_finding(finding) for finding in findings if _is_body_text_finding(finding)]
    filtered_findings.sort(key=_finding_sort_key)

    groups: dict[str, list[dict]] = {}
    finding_to_candidate: dict[str, str] = {}
    for finding in filtered_findings:
        normalized_candidate_key = _normalized_candidate_key(finding)
        groups.setdefault(normalized_candidate_key, []).append(finding)
        finding_to_candidate[str(finding["finding_id"])] = _candidate_id(normalized_candidate_key)

    candidates = [_build_candidate_summary(group_key, grouped_findings) for group_key, grouped_findings in groups.items()]
    candidates.sort(key=lambda candidate: _candidate_sort_key(candidate))

    return {
        "summary_version": "sg5-v1",
        "confirmation_required": bool(candidates),
        "candidate_count": len(candidates),
        "finding_count": len(filtered_findings),
        "manual_review_candidate_count": sum(1 for candidate in candidates if candidate["manual_review_required"]),
        "candidates": candidates,
        "finding_to_candidate": finding_to_candidate,
    }



def resolve_body_text_confirmation(summary: Mapping[str, object], confirmation: object) -> dict:
    """Resolve a normalized SG5 confirmation payload against a summary."""
    candidates = list(_summary_candidates(summary))
    candidate_ids_in_order = [str(candidate["candidate_id"]) for candidate in candidates]
    candidate_map = {str(candidate["candidate_id"]): candidate for candidate in candidates}

    normalized_confirmation = _normalize_confirmation(confirmation)
    mode = normalized_confirmation["mode"]
    approved_set = set(normalized_confirmation["approved_candidate_ids"])
    rejected_set = set(normalized_confirmation["rejected_candidate_ids"])
    replacement_overrides = dict(normalized_confirmation["replacement_overrides"])

    _validate_known_candidate_ids(approved_set, candidate_map, field_name="approved_candidate_ids")
    _validate_known_candidate_ids(rejected_set, candidate_map, field_name="rejected_candidate_ids")
    overlap = sorted(approved_set & rejected_set)
    if overlap:
        raise ValueError(
            f"candidate_id '{overlap[0]}' is listed in both approved_candidate_ids and rejected_candidate_ids."
        )
    _validate_known_candidate_ids(set(replacement_overrides), candidate_map, field_name="replacement_overrides")

    approved_candidate_ids: list[str] = []
    rejected_candidate_ids: list[str] = []
    undecided_candidate_ids: list[str] = []
    candidate_decisions: dict[str, dict] = {}
    approved_finding_ids: list[str] = []
    non_transformable_finding_ids: list[str] = []
    warnings: list[str] = []

    if mode == "preview_only":
        if approved_set:
            warnings.append("preview_only mode ignores approved_candidate_ids and does not emit body-text approvals.")
        if replacement_overrides:
            warnings.append("preview_only mode ignores replacement_overrides because no body-text transforms will run.")
    elif mode == "disabled":
        if approved_set or replacement_overrides:
            warnings.append("disabled mode ignores approvals and replacement_overrides because SG5 body-text handling is opted out.")
        if rejected_set:
            warnings.append("disabled mode ignores rejected_candidate_ids because SG5 body-text handling is opted out.")

    for candidate_id in candidate_ids_in_order:
        candidate = candidate_map[candidate_id]
        transformable_ids = list(candidate.get("transformable_finding_ids", []))
        rejected_ids = list(candidate.get("non_transformable_finding_ids", []))
        manual_review_required = bool(candidate.get("manual_review_required", False))
        replacement_text = replacement_overrides.get(candidate_id, candidate.get("recommended_replacement"))

        if mode == "apply_confirmed" and candidate_id in approved_set:
            decision = "approved"
            approved_candidate_ids.append(candidate_id)
            approved_finding_ids.extend(transformable_ids)
        elif mode == "disabled":
            decision = "manual_review" if manual_review_required else "undecided"
            if decision == "undecided":
                undecided_candidate_ids.append(candidate_id)
        elif candidate_id in rejected_set:
            decision = "rejected"
            rejected_candidate_ids.append(candidate_id)
        elif manual_review_required:
            decision = "manual_review"
        else:
            decision = "undecided"
            undecided_candidate_ids.append(candidate_id)

        non_transformable_finding_ids.extend(rejected_ids)
        candidate_decisions[candidate_id] = {
            "decision": decision,
            "replacement_text": replacement_text,
            "manual_review_required": manual_review_required,
            "transformable_finding_ids": transformable_ids,
            "non_transformable_finding_ids": rejected_ids,
        }

    confirmation_complete = mode == "disabled" or (mode == "apply_confirmed" and not undecided_candidate_ids)

    return {
        "mode": mode,
        "confirmation_complete": confirmation_complete,
        "approved_candidate_ids": approved_candidate_ids,
        "rejected_candidate_ids": rejected_candidate_ids,
        "undecided_candidate_ids": undecided_candidate_ids,
        "candidate_decisions": candidate_decisions,
        "approved_finding_ids": approved_finding_ids,
        "non_transformable_finding_ids": non_transformable_finding_ids,
        "warnings": warnings,
    }



def _build_candidate_summary(normalized_candidate_key: str, findings: list[dict]) -> dict:
    findings = sorted(findings, key=_finding_sort_key)
    representative = findings[0]
    candidate_id = _candidate_id(normalized_candidate_key)
    reason_tags = sorted({tag for finding in findings for tag in _reason_tags(finding)})
    extensions = sorted({str(finding["extension"]) for finding in findings})
    relative_paths = {str(finding["relative_path"]) for finding in findings}
    transformable_finding_ids = [str(finding["finding_id"]) for finding in findings if _finding_transform_supported(finding)]
    non_transformable_finding_ids = [str(finding["finding_id"]) for finding in findings if not _finding_transform_supported(finding)]

    candidate = {
        "candidate_id": candidate_id,
        "normalized_candidate_key": normalized_candidate_key,
        "candidate_category": _candidate_category(representative),
        "display_text": _display_text(findings),
        "occurrence_count": len(findings),
        "file_count": len(relative_paths),
        "extensions": extensions,
        "reason_tags": reason_tags,
        "confidence_counts": _aggregate_counts(
            (str(finding.get("confidence", "")).lower() for finding in findings),
            default_keys=_CONFIDENCE_KEYS,
        ),
        "source_counts": _aggregate_counts(
            (str(finding.get("source", "")).lower() for finding in findings),
            default_keys=_SOURCE_KEYS,
        ),
        "recommended_replacement": _recommended_replacement(findings),
        "manual_review_required": any(not _finding_transform_supported(finding) for finding in findings),
        "transformable_occurrence_count": len(transformable_finding_ids),
        "non_transformable_occurrence_count": len(non_transformable_finding_ids),
        "finding_ids": [str(finding["finding_id"]) for finding in findings],
        "transformable_finding_ids": transformable_finding_ids,
        "non_transformable_finding_ids": non_transformable_finding_ids,
        "location_samples": [_location_sample(finding) for finding in findings[:_SAMPLE_LIMIT]],
        "excerpt_samples": [_excerpt_sample(finding) for finding in findings[:_SAMPLE_LIMIT]],
    }
    return candidate



def _location_sample(finding: Mapping[str, object]) -> dict:
    return {
        "finding_id": str(finding["finding_id"]),
        "relative_path": str(finding["relative_path"]),
        "extension": str(finding["extension"]),
        "location": _sorted_copy(finding.get("location", {})),
        "confidence": str(finding.get("confidence", "")).lower(),
        "source": str(finding.get("source", "")).lower(),
        "manual_review_reason": finding.get("manual_review_reason"),
    }



def _excerpt_sample(finding: Mapping[str, object]) -> dict:
    payload = _payload(finding)
    return {
        "finding_id": str(finding["finding_id"]),
        "relative_path": str(finding["relative_path"]),
        "matched_text": _matched_text(finding),
        "excerpt": _optional_str(payload.get("excerpt")),
        "confidence": str(finding.get("confidence", "")).lower(),
        "source": str(finding.get("source", "")).lower(),
    }



def _candidate_sort_key(candidate: Mapping[str, object]) -> tuple[str, str, str, str]:
    location_samples = candidate.get("location_samples")
    first_relative_path = ""
    if isinstance(location_samples, Sequence) and not isinstance(location_samples, (str, bytes, bytearray)) and location_samples:
        first_sample = location_samples[0]
        if isinstance(first_sample, Mapping):
            first_relative_path = str(first_sample.get("relative_path", ""))
    return (
        str(candidate["candidate_category"]).casefold(),
        str(candidate["display_text"]).casefold(),
        first_relative_path.casefold(),
        str(candidate["normalized_candidate_key"]),
    )



def _is_body_text_finding(finding: object) -> bool:
    return isinstance(finding, Mapping) and str(finding.get("category")) == "body_text"



def _validate_body_text_finding(finding: object) -> dict:
    if not isinstance(finding, Mapping):
        raise TypeError("body_text findings must be mappings.")
    required_keys = {"finding_id", "relative_path", "extension", "payload"}
    missing = [key for key in required_keys if key not in finding]
    if missing:
        raise ValueError(f"body_text finding is missing required field '{missing[0]}'.")
    return {
        **finding,
        "payload": _sorted_copy(finding.get("payload", {})),
        "location": _sorted_copy(finding.get("location", {})),
        "reason_tags": list(finding.get("reason_tags", [])),
    }



def _normalized_candidate_key(finding: Mapping[str, object]) -> str:
    candidate_category = _candidate_category(finding)
    payload = _payload(finding)
    replacement_family = _optional_str(payload.get("replacement_family"))
    key_parts = [candidate_category, _normalized_candidate_text(finding)]
    if replacement_family:
        key_parts.append(_normalize_text(replacement_family))
    return "::".join(key_parts)



def _candidate_id(normalized_candidate_key: str) -> str:
    digest = hashlib.sha256(normalized_candidate_key.encode("utf-8")).hexdigest()[:16]
    return f"btc::{digest}"



def _candidate_category(finding: Mapping[str, object]) -> str:
    payload = _payload(finding)
    explicit = _optional_str(payload.get("candidate_category"))
    if explicit:
        return explicit

    for tag in _reason_tags(finding):
        resolved = _REASON_TAG_CATEGORY_MAP.get(tag)
        if resolved is not None:
            return resolved
    return "generic_identifier"



def _normalized_candidate_text(finding: Mapping[str, object]) -> str:
    payload = _payload(finding)
    for key in ("normalized_candidate_key", "normalized_text", "matched_text"):
        text = _optional_str(payload.get(key))
        if text:
            return _normalize_text(text)
    return _normalize_text(str(finding["finding_id"]))



def _display_text(findings: Sequence[Mapping[str, object]]) -> str:
    counts = Counter(_matched_text(finding) for finding in findings)
    return sorted(
        counts,
        key=lambda text: (-counts[text], text.casefold(), text),
    )[0]



def _matched_text(finding: Mapping[str, object]) -> str:
    payload = _payload(finding)
    return _optional_str(payload.get("matched_text")) or _optional_str(payload.get("normalized_text")) or ""



def _reason_tags(finding: Mapping[str, object]) -> list[str]:
    tags = finding.get("reason_tags")
    if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes, bytearray)):
        return sorted({_normalize_text(str(tag)) for tag in tags if str(tag).strip()})
    return []



def _recommended_replacement(findings: Sequence[Mapping[str, object]]) -> str | None:
    ranked_candidates: list[tuple[int, str]] = []
    for finding in findings:
        payload = _payload(finding)
        for rank, key in enumerate(("recommended_replacement", "suggested_replacement", "default_replacement_text")):
            text = _optional_str(payload.get(key))
            if text:
                ranked_candidates.append((rank, text))
                break

    if not ranked_candidates:
        return None

    ranked_candidates.sort(key=lambda item: (item[0], item[1].casefold(), item[1]))
    best_rank = ranked_candidates[0][0]
    texts = [text for rank, text in ranked_candidates if rank == best_rank]
    counts = Counter(texts)
    return sorted(counts, key=lambda text: (-counts[text], text.casefold(), text))[0]



def _finding_transform_supported(finding: Mapping[str, object]) -> bool:
    payload = _payload(finding)
    explicit = payload.get("transform_supported")
    if isinstance(explicit, bool):
        return explicit
    if finding.get("manual_review_reason"):
        return False
    if str(finding.get("action_hint", "")).strip().lower() == "review":
        return False
    if "pdf_text_layer" in _reason_tags(finding):
        return False
    return True



def _aggregate_counts(values: Iterable[str], *, default_keys: Sequence[str]) -> dict[str, int]:
    counts = {key: 0 for key in default_keys}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))



def _summary_candidates(summary: Mapping[str, object]) -> list[dict]:
    candidates = summary.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes, bytearray)):
        raise TypeError("summary must contain a 'candidates' sequence.")
    normalized_candidates: list[dict] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise TypeError("summary candidates must be mappings.")
        normalized_candidates.append(dict(candidate))
    return normalized_candidates



def _normalize_confirmation(confirmation: object) -> dict:
    if confirmation is None:
        confirmation = {}
    if not isinstance(confirmation, Mapping):
        raise TypeError("body_text_confirmation must be a mapping or None.")

    unknown_keys = sorted(str(key) for key in confirmation if str(key) not in _ALLOWED_CONFIRMATION_KEYS)
    if unknown_keys:
        raise ValueError(
            f"Unsupported body_text_confirmation key '{unknown_keys[0]}'. Allowed keys: "
            + ", ".join(sorted(_ALLOWED_CONFIRMATION_KEYS))
            + "."
        )

    raw_mode = confirmation.get("mode", "preview_only")
    if not isinstance(raw_mode, str):
        raise TypeError("body_text_confirmation field 'mode' must be a string when provided.")
    mode = raw_mode.strip().lower()
    if mode not in _ALLOWED_CONFIRMATION_MODES:
        raise ValueError(
            "body_text_confirmation mode must be one of " + ", ".join(sorted(_ALLOWED_CONFIRMATION_MODES)) + "."
        )

    return {
        "mode": mode,
        "approved_candidate_ids": _normalize_string_list(
            confirmation.get("approved_candidate_ids"),
            field_name="approved_candidate_ids",
        ),
        "rejected_candidate_ids": _normalize_string_list(
            confirmation.get("rejected_candidate_ids"),
            field_name="rejected_candidate_ids",
        ),
        "replacement_overrides": _normalize_replacement_overrides(confirmation.get("replacement_overrides")),
        "review_notes": _normalize_string_list(confirmation.get("review_notes"), field_name="review_notes"),
    }



def _normalize_string_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_items = list(value)
    else:
        raise TypeError(f"body_text_confirmation field '{field_name}' must be a string or a sequence of strings.")

    items: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, str):
            raise TypeError(f"body_text_confirmation field '{field_name}' must be a string or a sequence of strings.")
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items



def _normalize_replacement_overrides(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("replacement_overrides must be a mapping of strings to strings.")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise TypeError("replacement_overrides must be a mapping of strings to strings.")
        key = raw_key.strip()
        replacement = raw_value.strip()
        if not key:
            raise ValueError("replacement_overrides contains an empty candidate_id key.")
        if not replacement:
            raise ValueError(f"replacement_overrides for candidate_id '{key}' must be a non-empty string.")
        normalized[key] = replacement
    return normalized



def _validate_known_candidate_ids(candidate_ids: set[str], candidate_map: Mapping[str, object], *, field_name: str) -> None:
    for candidate_id in sorted(candidate_ids):
        if candidate_id in candidate_map:
            continue
        if field_name == "replacement_overrides":
            raise ValueError(f"Unknown replacement_overrides candidate_id '{candidate_id}'.")
        prefix = field_name.removesuffix("_candidate_ids")
        raise ValueError(f"Unknown {prefix} candidate_id '{candidate_id}'.")



def _finding_sort_key(finding: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    relative_path = str(finding.get("relative_path", ""))
    return (
        relative_path.casefold(),
        relative_path,
        str(finding.get("extension", "")).casefold(),
        _location_key(finding.get("location", {})),
        str(finding.get("finding_id", "")),
    )



def _location_key(value: object) -> str:
    return json.dumps(_sorted_copy(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)



def _payload(finding: Mapping[str, object]) -> Mapping[str, object]:
    payload = finding.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return {}



def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None



def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()



def _sorted_copy(value: object):
    if isinstance(value, Mapping):
        return {str(key): _sorted_copy(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_sorted_copy(item) for item in value]
    if isinstance(value, tuple):
        return [_sorted_copy(item) for item in value]
    return value
