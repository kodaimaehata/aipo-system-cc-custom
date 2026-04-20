# Office-Anonymizer Policy And Scope Reference

## Supported Files

Only these extensions are in scope:

- `xlsx`
- `xlsm`
- `docx`
- `pptx`
- `pdf`

The wrapper may further narrow a run with an optional validated extension subset.

## Supported Target Families

The packaged defaults and wrapper-local customization flow cover:

- comments
- notes
- headers
- footers
- metadata
- images
- body_text

## Supported Body-Text Surfaces

`body_text` support is limited to repo-backed, text-addressable content:

- Excel cell text
- DOCX paragraphs, tables, and textboxes that the runtime can enumerate
- PPTX text frames and tables that the runtime can enumerate
- searchable PDF text layers

Searchable PDFs remain review-first because text-layer rewrites can still require layout-sensitive manual review.
Image-only text and OCR-dependent cleanup remain out of scope.

## Packaged Defaults

`default_rules.yaml` is the packaged seed policy for each run.
It is not a standing per-project `rules.yaml` contract.

Default posture:

- comments: remove
- notes: remove
- headers: remove
- footers: remove
- metadata: clear
- images: `report_only` until a run-level image decision is confirmed
- body_text: `report_only`, `confirmation_required: true`, replacement seed `[REDACTED]`, report low-confidence candidates, and force manual review for PDF body-text handling
- manual review: still required

The packaged first pass is intentionally preview/report-only for `body_text`.
Confirmed application happens only when the rerun supplies `body_text_confirmation.mode="apply_confirmed"`.

## One-Step Customization Flow

The wrapper resolves policy in this order:

1. load packaged defaults
2. run `detect(...)`
3. merge one-step `customization_overrides`
4. merge one-time `image_policy_confirmation`
5. resolve SG5 body-text candidate summary plus explicit confirmation state
6. pass the resolved Python `dict` into `transform(...)`

Image handling stays run-level, not per-image.
Supported image modes are `report_only`, `remove`, `replace`, and `mask`.
If no run-level image confirmation is supplied, the wrapper keeps image handling at the safe `report_only` posture.

## Explicitly Unsupported / Rejected Scope

The wrapper should reject these as out of scope when the request makes them explicit:

- legacy formats: `xls`, `xlsb`, `doc`, `ppt`
- embedded objects, OLE cleanup, embedded-file cleanup, or attachments
- external OCR or `Tesseract`
- OCR-dependent cleanup promises for scanned or burned-in text
- non-Markdown report expectations
- requests that imply guaranteed perfect anonymization

## User-Facing Explanation Posture

When the wrapper rejects scope, explain:

- what is not supported
- that the rejection is wrapper-owned scope gating
- the closest supported route when one exists
- that human review remains mandatory even after supported runs complete

## Important Limits

The wrapper and report should stay explicit that manual review may still be required for:

- scanned PDFs or burned-in text
- low-confidence body-text candidates
- searchable PDF body-text candidates
- visually sensitive image content
- PowerPoint content on complex masters or shapes
- manual-review-only surfaces already surfaced by the shared runtime
