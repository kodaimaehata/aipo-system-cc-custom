from __future__ import annotations

from collections.abc import Mapping, Sequence
import re

__all__ = [
    "build_body_text_policy_fragment",
    "normalize_body_text_candidate_inputs",
    "normalize_body_text_confirmation",
]

_CANDIDATE_LIST_FIELDS = (
    "person_names",
    "company_names",
    "emails",
    "phones",
    "addresses",
    "domains",
    "exact_phrases",
    "context_terms",
)
_CANDIDATE_ALLOWED_KEYS = {*_CANDIDATE_LIST_FIELDS, "replacement_text", "replacement_map"}
_CONFIRMATION_LIST_FIELDS = ("approved_candidate_ids", "rejected_candidate_ids", "review_notes")
_CONFIRMATION_ALLOWED_KEYS = {*_CONFIRMATION_LIST_FIELDS, "mode", "replacement_overrides"}
_ALLOWED_CONFIRMATION_MODES = {"preview_only", "apply_confirmed", "disabled"}



def normalize_body_text_candidate_inputs(value: object) -> dict:
    if value is None:
        return _empty_candidate_inputs()
    if not isinstance(value, Mapping):
        raise TypeError("body_text_candidate_inputs must be a mapping or None.")

    _reject_unknown_keys(value, allowed_keys=_CANDIDATE_ALLOWED_KEYS, container_name="body_text_candidate_inputs")

    normalized = _empty_candidate_inputs()
    normalized["person_names"] = _normalize_text_list(
        value.get("person_names"),
        container_name="body_text_candidate_inputs",
        field_name="person_names",
    )
    normalized["company_names"] = _normalize_text_list(
        value.get("company_names"),
        container_name="body_text_candidate_inputs",
        field_name="company_names",
    )
    normalized["emails"] = _normalize_text_list(
        value.get("emails"),
        container_name="body_text_candidate_inputs",
        field_name="emails",
        text_normalizer=lambda item: item.lower(),
    )
    normalized["phones"] = _normalize_text_list(
        value.get("phones"),
        container_name="body_text_candidate_inputs",
        field_name="phones",
        text_normalizer=_normalize_phone_text,
    )
    normalized["addresses"] = _normalize_text_list(
        value.get("addresses"),
        container_name="body_text_candidate_inputs",
        field_name="addresses",
    )
    normalized["domains"] = _normalize_text_list(
        value.get("domains"),
        container_name="body_text_candidate_inputs",
        field_name="domains",
        text_normalizer=_normalize_domain_text,
    )
    normalized["exact_phrases"] = _normalize_text_list(
        value.get("exact_phrases"),
        container_name="body_text_candidate_inputs",
        field_name="exact_phrases",
    )
    normalized["context_terms"] = _normalize_text_list(
        value.get("context_terms"),
        container_name="body_text_candidate_inputs",
        field_name="context_terms",
    )
    normalized["replacement_text"] = _normalize_optional_text(
        value.get("replacement_text"),
        container_name="body_text_candidate_inputs",
        field_name="replacement_text",
    )
    normalized["replacement_map"] = _normalize_text_mapping(
        value.get("replacement_map"),
        container_name="body_text_candidate_inputs",
        field_name="replacement_map",
    )
    return normalized



def normalize_body_text_confirmation(value: object) -> dict:
    if value is None:
        return _empty_confirmation()
    if not isinstance(value, Mapping):
        raise TypeError("body_text_confirmation must be a mapping or None.")

    _reject_unknown_keys(value, allowed_keys=_CONFIRMATION_ALLOWED_KEYS, container_name="body_text_confirmation")

    normalized = _empty_confirmation()
    raw_mode = value.get("mode", "preview_only")
    if not isinstance(raw_mode, str):
        raise TypeError("body_text_confirmation field 'mode' must be a string when provided.")
    mode = raw_mode.strip().lower()
    if mode not in _ALLOWED_CONFIRMATION_MODES:
        raise ValueError(
            "body_text_confirmation mode must be one of "
            + ", ".join(sorted(_ALLOWED_CONFIRMATION_MODES))
            + "."
        )
    normalized["mode"] = mode
    normalized["approved_candidate_ids"] = _normalize_text_list(
        value.get("approved_candidate_ids"),
        container_name="body_text_confirmation",
        field_name="approved_candidate_ids",
    )
    normalized["rejected_candidate_ids"] = _normalize_text_list(
        value.get("rejected_candidate_ids"),
        container_name="body_text_confirmation",
        field_name="rejected_candidate_ids",
    )
    normalized["replacement_overrides"] = _normalize_text_mapping(
        value.get("replacement_overrides"),
        container_name="body_text_confirmation",
        field_name="replacement_overrides",
    )
    normalized["review_notes"] = _normalize_text_list(
        value.get("review_notes"),
        container_name="body_text_confirmation",
        field_name="review_notes",
    )
    return normalized



def build_body_text_policy_fragment(candidate_inputs: object, confirmation: object) -> dict:
    normalized_candidate_inputs = normalize_body_text_candidate_inputs(candidate_inputs)
    normalized_confirmation = normalize_body_text_confirmation(confirmation)
    return {
        "body_text": {
            "enabled": normalized_confirmation["mode"] != "disabled",
            "mode": normalized_confirmation["mode"],
            "confirmation_required": True,
            "approved_candidate_ids": list(normalized_confirmation["approved_candidate_ids"]),
            "rejected_candidate_ids": list(normalized_confirmation["rejected_candidate_ids"]),
            "replacement_text": normalized_candidate_inputs["replacement_text"],
            "replacement_map": dict(normalized_candidate_inputs["replacement_map"]),
            "replacement_overrides": dict(normalized_confirmation["replacement_overrides"]),
        }
    }



def _normalize_text_list(
    value: object,
    *,
    container_name: str,
    field_name: str,
    text_normalizer=None,
) -> list[str]:
    items = _coerce_text_listlike(value, container_name=container_name, field_name=field_name)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if text_normalizer is not None:
            text = text_normalizer(text)
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized



def _normalize_optional_text(value: object, *, container_name: str, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{container_name} field '{field_name}' must be a string or None.")
    text = value.strip()
    return text or None



def _normalize_text_mapping(value: object, *, container_name: str, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{container_name} field '{field_name}' must be a mapping of strings to strings.")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise TypeError(f"{container_name} field '{field_name}' must be a mapping of strings to strings.")
        key = raw_key.strip()
        replacement = raw_value.strip()
        if not key or not replacement:
            continue
        normalized[key] = replacement
    return normalized



def _coerce_text_listlike(value: object, *, container_name: str, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise TypeError(
                    f"{container_name} field '{field_name}' must be a string or a sequence of strings."
                )
            items.append(item)
        return items
    raise TypeError(f"{container_name} field '{field_name}' must be a string or a sequence of strings.")



def _reject_unknown_keys(value: Mapping, *, allowed_keys: set[str], container_name: str) -> None:
    unknown = sorted(str(key) for key in value if str(key) not in allowed_keys)
    if unknown:
        raise ValueError(
            f"Unsupported {container_name} key '{unknown[0]}'. Allowed keys: "
            + ", ".join(sorted(allowed_keys))
            + "."
        )



def _normalize_phone_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())



def _normalize_domain_text(value: str) -> str:
    text = value.strip().lower()
    for prefix in ("http://", "https://", "mailto:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    text = text.split("/", 1)[0]
    text = text.split("?", 1)[0]
    text = text.split("#", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text.strip().strip("/")



def _empty_candidate_inputs() -> dict:
    return {
        "person_names": [],
        "company_names": [],
        "emails": [],
        "phones": [],
        "addresses": [],
        "domains": [],
        "exact_phrases": [],
        "context_terms": [],
        "replacement_text": None,
        "replacement_map": {},
    }



def _empty_confirmation() -> dict:
    return {
        "mode": "preview_only",
        "approved_candidate_ids": [],
        "rejected_candidate_ids": [],
        "replacement_overrides": {},
        "review_notes": [],
    }
