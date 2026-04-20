from __future__ import annotations

from copy import deepcopy

import pytest

from office_automation.anonymize.candidate_summary import (
    build_body_text_candidate_summary,
    resolve_body_text_confirmation,
)


def _make_finding(
    finding_id: str,
    *,
    relative_path: str,
    extension: str,
    matched_text: str,
    normalized_text: str | None = None,
    candidate_category: str | None = None,
    confidence: str = "high",
    source: str = "user_hint",
    reason_tags: list[str] | None = None,
    action_hint: str = "candidate_confirmation_required",
    manual_review_reason: str | None = None,
    transform_supported: bool | None = None,
    suggested_replacement: str | None = None,
    default_replacement_text: str | None = None,
    location: dict | None = None,
    excerpt: str | None = None,
) -> dict:
    payload = {
        "matched_text": matched_text,
        "normalized_text": normalized_text or matched_text.casefold(),
        "excerpt": excerpt or f"Excerpt for {matched_text}",
        "surface_type": f"{extension}_surface",
    }
    if candidate_category is not None:
        payload["candidate_category"] = candidate_category
    if transform_supported is not None:
        payload["transform_supported"] = transform_supported
    if suggested_replacement is not None:
        payload["suggested_replacement"] = suggested_replacement
    if default_replacement_text is not None:
        payload["default_replacement_text"] = default_replacement_text

    return {
        "finding_id": finding_id,
        "file_path": f"/tmp/{relative_path}",
        "relative_path": relative_path,
        "extension": extension,
        "category": "body_text",
        "location": location or {"match_start": 0, "match_end": len(matched_text)},
        "payload": payload,
        "action_hint": action_hint,
        "confidence": confidence,
        "manual_review_reason": manual_review_reason,
        "source": source,
        "reason_tags": list(reason_tags or []),
    }


@pytest.fixture
def mixed_summary() -> dict:
    findings = [
        _make_finding(
            "alpha::jane-1",
            relative_path="alpha.docx",
            extension="docx",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="high",
            source="user_hint",
            reason_tags=["person_hint"],
            suggested_replacement="[PERSON]",
            location={"surface": "paragraph", "paragraph_index": 0, "match_start": 16, "match_end": 28},
            excerpt="Primary contact: Jane Example",
        ),
        _make_finding(
            "beta::jane-2",
            relative_path="beta.xlsx",
            extension="xlsx",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="high",
            source="user_hint",
            reason_tags=["person_hint", "context_term"],
            suggested_replacement="[PERSON]",
            location={"sheet": "Sheet1", "cell": "B2", "match_start": 0, "match_end": 12},
            excerpt="Jane Example approved the budget",
        ),
        _make_finding(
            "gamma::jane-3",
            relative_path="gamma.pdf",
            extension="pdf",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="low",
            source="pattern",
            reason_tags=["pdf_text_layer", "person_hint"],
            action_hint="review",
            manual_review_reason="PDF text-layer matches remain review-first.",
            transform_supported=False,
            suggested_replacement="[PERSON]",
            location={"page_number": 1, "span_index": 2, "match_start": 4, "match_end": 16},
            excerpt="Reach Jane Example on page one",
        ),
        _make_finding(
            "delta::project-1",
            relative_path="delta.docx",
            extension="docx",
            matched_text="Project Lotus",
            candidate_category="exact_phrase",
            confidence="medium",
            source="heuristic",
            reason_tags=["exact_phrase"],
            default_replacement_text="[DEFAULT]",
            location={"surface": "paragraph", "paragraph_index": 2, "match_start": 8, "match_end": 21},
            excerpt="Budget owner: Project Lotus",
        ),
    ]
    return build_body_text_candidate_summary(findings)


def test_build_body_text_candidate_summary_aggregates_repeats_and_mixed_safe_unsafe_findings() -> None:
    findings = [
        _make_finding(
            "beta::jane-2",
            relative_path="beta.xlsx",
            extension="xlsx",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="high",
            source="user_hint",
            reason_tags=["person_hint", "context_term"],
            suggested_replacement="[PERSON]",
            location={"sheet": "Sheet1", "cell": "B2", "match_start": 0, "match_end": 12},
        ),
        _make_finding(
            "gamma::jane-3",
            relative_path="gamma.pdf",
            extension="pdf",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="low",
            source="pattern",
            reason_tags=["pdf_text_layer", "person_hint"],
            action_hint="review",
            manual_review_reason="PDF text-layer matches remain review-first.",
            transform_supported=False,
            suggested_replacement="[PERSON]",
            location={"page_number": 1, "span_index": 2, "match_start": 4, "match_end": 16},
        ),
        _make_finding(
            "alpha::jane-1",
            relative_path="alpha.docx",
            extension="docx",
            matched_text="Jane Example",
            candidate_category="person_name",
            confidence="high",
            source="user_hint",
            reason_tags=["person_hint"],
            suggested_replacement="[PERSON]",
            location={"surface": "paragraph", "paragraph_index": 0, "match_start": 16, "match_end": 28},
        ),
    ] + [
        _make_finding(
            f"samples::lotus-{index}",
            relative_path=f"lotus-{index}.docx",
            extension="docx",
            matched_text="Project Lotus",
            candidate_category="exact_phrase",
            confidence="medium",
            source="heuristic",
            reason_tags=["exact_phrase"],
            location={"surface": "paragraph", "paragraph_index": index, "match_start": 8, "match_end": 21},
            excerpt=f"Excerpt {index} for Project Lotus",
        )
        for index in range(6)
    ]

    summary = build_body_text_candidate_summary(findings)

    assert summary["summary_version"] == "sg5-v1"
    assert summary["confirmation_required"] is True
    assert summary["candidate_count"] == 2
    assert summary["finding_count"] == 9
    assert summary["manual_review_candidate_count"] == 1

    jane = next(candidate for candidate in summary["candidates"] if candidate["display_text"] == "Jane Example")
    assert jane["candidate_id"].startswith("btc::")
    assert jane["normalized_candidate_key"] == "person_name::jane example"
    assert jane["candidate_category"] == "person_name"
    assert jane["occurrence_count"] == 3
    assert jane["file_count"] == 3
    assert jane["extensions"] == ["docx", "pdf", "xlsx"]
    assert jane["reason_tags"] == ["context_term", "pdf_text_layer", "person_hint"]
    assert jane["confidence_counts"] == {"high": 2, "medium": 0, "low": 1}
    assert jane["source_counts"] == {"heuristic": 0, "mixed": 0, "pattern": 1, "user_hint": 2}
    assert jane["recommended_replacement"] == "[PERSON]"
    assert jane["manual_review_required"] is True
    assert jane["transformable_occurrence_count"] == 2
    assert jane["non_transformable_occurrence_count"] == 1
    assert jane["finding_ids"] == ["alpha::jane-1", "beta::jane-2", "gamma::jane-3"]
    assert jane["transformable_finding_ids"] == ["alpha::jane-1", "beta::jane-2"]
    assert jane["non_transformable_finding_ids"] == ["gamma::jane-3"]
    assert len(jane["location_samples"]) == 3
    assert len(jane["excerpt_samples"]) == 3

    lotus = next(candidate for candidate in summary["candidates"] if candidate["display_text"] == "Project Lotus")
    assert lotus["occurrence_count"] == 6
    assert lotus["file_count"] == 6
    assert lotus["manual_review_required"] is False
    assert len(lotus["location_samples"]) == 5
    assert len(lotus["excerpt_samples"]) == 5

    assert summary["finding_to_candidate"]["alpha::jane-1"] == jane["candidate_id"]
    assert summary["finding_to_candidate"]["gamma::jane-3"] == jane["candidate_id"]


def test_build_body_text_candidate_summary_is_stable_across_reordered_findings_and_separates_categories() -> None:
    findings = [
        _make_finding(
            "company::1",
            relative_path="alpha.docx",
            extension="docx",
            matched_text="Example",
            candidate_category="company_name",
            reason_tags=["company_hint"],
        ),
        _make_finding(
            "phrase::1",
            relative_path="alpha.docx",
            extension="docx",
            matched_text="Example",
            candidate_category="exact_phrase",
            reason_tags=["exact_phrase"],
        ),
        _make_finding(
            "company::2",
            relative_path="beta.docx",
            extension="docx",
            matched_text="Example",
            candidate_category="company_name",
            reason_tags=["company_hint"],
        ),
    ]

    forward = build_body_text_candidate_summary(findings)
    reverse = build_body_text_candidate_summary(list(reversed(findings)))

    assert [candidate["normalized_candidate_key"] for candidate in forward["candidates"]] == [
        "company_name::example",
        "exact_phrase::example",
    ]
    assert forward == reverse
    assert forward["candidates"][0]["candidate_id"] != forward["candidates"][1]["candidate_id"]


def test_build_body_text_candidate_summary_tolerates_current_t003_style_findings_without_optional_payload_fields() -> None:
    findings = [
        _make_finding(
            "email::1",
            relative_path="alpha.pdf",
            extension="pdf",
            matched_text="john@example.com",
            normalized_text="john@example.com",
            candidate_category=None,
            confidence="low",
            source="pattern",
            reason_tags=["email_pattern", "pdf_text_layer"],
            action_hint="review",
            manual_review_reason="PDF text-layer matches remain review-first because layout-safe rewrite is not proven in this runtime.",
            transform_supported=None,
        ),
        {
            "finding_id": "structural::1",
            "file_path": "/tmp/alpha.docx",
            "relative_path": "alpha.docx",
            "extension": "docx",
            "category": "metadata",
            "location": {"scope": "document"},
            "payload": {"fields": {"author": "Example"}},
            "action_hint": "clear",
            "confidence": "high",
            "manual_review_reason": None,
        },
    ]

    summary = build_body_text_candidate_summary(findings)

    assert summary["candidate_count"] == 1
    candidate = summary["candidates"][0]
    assert candidate["candidate_category"] == "email"
    assert candidate["normalized_candidate_key"] == "email::john@example.com"
    assert candidate["recommended_replacement"] is None
    assert candidate["manual_review_required"] is True
    assert candidate["transformable_occurrence_count"] == 0
    assert candidate["non_transformable_occurrence_count"] == 1
    assert summary["finding_to_candidate"] == {"email::1": candidate["candidate_id"]}


def test_resolve_body_text_confirmation_preview_only_and_apply_confirmed_subset(mixed_summary: dict) -> None:
    jane = next(candidate for candidate in mixed_summary["candidates"] if candidate["display_text"] == "Jane Example")
    lotus = next(candidate for candidate in mixed_summary["candidates"] if candidate["display_text"] == "Project Lotus")

    preview = resolve_body_text_confirmation(
        mixed_summary,
        {
            "mode": "preview_only",
            "approved_candidate_ids": [jane["candidate_id"]],
            "rejected_candidate_ids": [],
            "replacement_overrides": {},
            "review_notes": [],
        },
    )
    assert preview["mode"] == "preview_only"
    assert preview["confirmation_complete"] is False
    assert preview["approved_candidate_ids"] == []
    assert preview["rejected_candidate_ids"] == []
    assert preview["undecided_candidate_ids"] == [lotus["candidate_id"]]
    assert preview["candidate_decisions"][jane["candidate_id"]]["decision"] == "manual_review"
    assert preview["candidate_decisions"][lotus["candidate_id"]]["decision"] == "undecided"
    assert preview["approved_finding_ids"] == []
    assert preview["non_transformable_finding_ids"] == ["gamma::jane-3"]
    assert any("preview_only" in warning for warning in preview["warnings"])

    applied = resolve_body_text_confirmation(
        mixed_summary,
        {
            "mode": "apply_confirmed",
            "approved_candidate_ids": [jane["candidate_id"]],
            "rejected_candidate_ids": [lotus["candidate_id"]],
            "replacement_overrides": {jane["candidate_id"]: "[APPROVED PERSON]"},
            "review_notes": ["review pdf manually"],
        },
    )
    assert applied["mode"] == "apply_confirmed"
    assert applied["confirmation_complete"] is True
    assert applied["approved_candidate_ids"] == [jane["candidate_id"]]
    assert applied["rejected_candidate_ids"] == [lotus["candidate_id"]]
    assert applied["undecided_candidate_ids"] == []
    assert applied["candidate_decisions"][jane["candidate_id"]] == {
        "decision": "approved",
        "replacement_text": "[APPROVED PERSON]",
        "manual_review_required": True,
        "transformable_finding_ids": ["alpha::jane-1", "beta::jane-2"],
        "non_transformable_finding_ids": ["gamma::jane-3"],
    }
    assert applied["candidate_decisions"][lotus["candidate_id"]]["decision"] == "rejected"
    assert applied["candidate_decisions"][lotus["candidate_id"]]["replacement_text"] == "[DEFAULT]"
    assert applied["approved_finding_ids"] == ["alpha::jane-1", "beta::jane-2"]
    assert applied["non_transformable_finding_ids"] == ["gamma::jane-3"]
    assert applied["warnings"] == []


def test_resolve_body_text_confirmation_accepts_explicit_reject_all() -> None:
    summary = build_body_text_candidate_summary(
        [
            _make_finding(
                "cand::1",
                relative_path="alpha.docx",
                extension="docx",
                matched_text="Project Lotus",
                candidate_category="exact_phrase",
                reason_tags=["exact_phrase"],
            )
        ]
    )
    candidate_id = summary["candidates"][0]["candidate_id"]

    resolved = resolve_body_text_confirmation(
        summary,
        {
            "mode": "apply_confirmed",
            "approved_candidate_ids": [],
            "rejected_candidate_ids": [candidate_id],
            "replacement_overrides": {},
            "review_notes": [],
        },
    )

    assert resolved["confirmation_complete"] is True
    assert resolved["approved_candidate_ids"] == []
    assert resolved["rejected_candidate_ids"] == [candidate_id]
    assert resolved["undecided_candidate_ids"] == []
    assert resolved["approved_finding_ids"] == []
    assert resolved["candidate_decisions"][candidate_id]["decision"] == "rejected"


@pytest.mark.parametrize(
    ("confirmation", "error_type", "message"),
    [
        (
            {"mode": "apply_confirmed", "approved_candidate_ids": ["btc::missing"], "rejected_candidate_ids": [], "replacement_overrides": {}, "review_notes": []},
            ValueError,
            "Unknown approved candidate_id 'btc::missing'",
        ),
        (
            {"mode": "apply_confirmed", "approved_candidate_ids": ["dup"], "rejected_candidate_ids": ["dup"], "replacement_overrides": {}, "review_notes": []},
            ValueError,
            "listed in both approved_candidate_ids and rejected_candidate_ids",
        ),
        (
            {"mode": "apply_confirmed", "approved_candidate_ids": [], "rejected_candidate_ids": [], "replacement_overrides": {"btc::missing": "x"}, "review_notes": []},
            ValueError,
            "Unknown replacement_overrides candidate_id 'btc::missing'",
        ),
        (
            {"mode": "apply_confirmed", "approved_candidate_ids": [], "rejected_candidate_ids": [], "replacement_overrides": {"x": 5}, "review_notes": []},
            TypeError,
            "replacement_overrides must be a mapping of strings to strings",
        ),
    ],
)
def test_resolve_body_text_confirmation_rejects_invalid_confirmation_input(
    mixed_summary: dict,
    confirmation: dict,
    error_type: type[Exception],
    message: str,
) -> None:
    if confirmation["approved_candidate_ids"] == ["dup"]:
        candidate_id = mixed_summary["candidates"][0]["candidate_id"]
        confirmation = deepcopy(confirmation)
        confirmation["approved_candidate_ids"] = [candidate_id]
        confirmation["rejected_candidate_ids"] = [candidate_id]

    with pytest.raises(error_type, match=message):
        resolve_body_text_confirmation(mixed_summary, confirmation)
