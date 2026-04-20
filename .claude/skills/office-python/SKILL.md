---
name: office-python
description: Read and edit supported Office and PDF files through a thin SG2 wrapper that routes xlsx, xlsm, docx, pptx, and pdf requests into the shared office_automation runtime at tools/office-automation/.
---

# Office Python

Use this skill for file-oriented read and edit work on supported Office and PDF documents.
It is a thin wrapper over the shared Python runtime in `tools/office-automation/`, not a package-owned runtime CLI.

## When To Use

- Read supported `xlsx`, `xlsm`, `docx`, `pptx`, or `pdf` files.
- Apply structured edits that stay inside the SG2 V1 runtime scope.
- Preserve the original by default and save to a wrapper-resolved output path.

## When Not To Use

- Legacy or unsupported formats such as `xls`, `xlsb`, `doc`, or `ppt`.
- VBA or macro editing.
- Word track-changes cleanup or complex text-box-specific editing.
- PowerPoint SmartArt-specific editing or advanced animation rewriting.
- Requests that require exact-fidelity PDF rewriting, embedded-object handling, or external OCR.

## Supported Extensions

- `xlsx`
- `xlsm`
- `docx`
- `pptx`
- `pdf`

## Notes

- Detailed runtime boundaries: `references/runtime-contract.md`
- Detailed supported / unsupported scope: `references/supported-scope.md`
- Wrapper implementation: `scripts/office_python_wrapper.py`
- Run inside the shared uv project at `tools/office-automation/` or with that runtime source on `PYTHONPATH`.
