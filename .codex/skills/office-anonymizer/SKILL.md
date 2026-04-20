---
name: office-anonymizer
description: Anonymize supported Office and PDF files in a required target_folder through a thin wrapper over the shared office_automation detect -> transform -> validate runtime, including SG5 body-text preview and confirmation support.
---

# Office Anonymizer

Use this skill for folder-scoped anonymization runs on supported Office and searchable-PDF files.
It stays thin: load packaged defaults, normalize wrapper inputs, run `detect(...)`, require preview-first confirmation for SG5 body text, then call `transform(...)` and `validate(...)`.

## When To Use

- Anonymize supported `xlsx`, `xlsm`, `docx`, `pptx`, and `pdf` files in a folder.
- Remove or replace supported targets such as comments, notes, headers, footers, metadata, images, and SG5 `body_text` candidates.
- Produce a Markdown anonymization report plus a concise wrapper summary.

## Default Flow

`detect -> preview/report -> explicit confirmation -> transform -> validate -> Markdown report -> human review`

Packaged SG5 defaults are preview-first:
- `body_text.enabled: true`
- `body_text.mode: report_only`
- `body_text.confirmation_required: true`

Confirmed body-text application happens only when the rerun supplies `body_text_confirmation.mode="apply_confirmed"`.

## When Not To Use

- Legacy formats such as `xls`, `xlsb`, `doc`, or `ppt`.
- Embedded objects, OLE content, or file attachments.
- External OCR or `Tesseract` flows.
- Image-only burned-in text cleanup.
- Requests that imply guaranteed perfect anonymization or no-review-required output.

## Required Input

- `target_folder` is required.

## Supported Extensions And Target Families

Supported extensions:
- `xlsx`
- `xlsm`
- `docx`
- `pptx`
- `pdf`

Supported anonymization target families:
- comments
- notes
- headers
- footers
- metadata
- images
- body_text

## Notes

- Public wrapper exports remain `run`, `run_request`, and `UnsupportedScopeError`.
- Request keys now include optional `body_text_candidate_inputs` and `body_text_confirmation` in addition to the SG3-era inputs.
- Markdown report output stays at the runtime default path `<target-folder>/anonymization_report.md`; a wrapper `report_path` override is still just a second copy destination.
- Human review remains mandatory, especially for searchable PDFs, images, layout-sensitive content, preview-only runs, and any `status=2` result.
- Detailed runtime boundary and request/result contract: `references/runtime-contract.md`
- Detailed supported and rejected scope: `references/policy-and-scope.md`
- Detailed report sections and status behavior: `references/report-and-status.md`
- Replayable examples: `references/replay-examples.md`
- Wrapper implementation: `scripts/office_anonymizer_wrapper.py`
- Run inside the shared uv project at `tools/office-automation/` or with that runtime source on `PYTHONPATH`.
