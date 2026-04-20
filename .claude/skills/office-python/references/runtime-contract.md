# Office-Python Runtime Contract Reference

This skill stays thin by importing the SG1 shared runtime from:

- `tools/office-automation/src/office_automation/excel_ops.py`
- `tools/office-automation/src/office_automation/word_ops.py`
- `tools/office-automation/src/office_automation/powerpoint_ops.py`
- `tools/office-automation/src/office_automation/pdf_ops.py`
- `tools/office-automation/src/office_automation/common/files.py`

## Stable Boundary

The stable V1 boundary is Python imports, not a shared-runtime CLI contract.
The wrapper may add repo-local convenience helpers, but SG1 only guarantees importable modules and callable signatures.

## Routed Callables

- `office_automation.excel_ops.read(file_path)`
- `office_automation.excel_ops.edit(file_path, instructions)`
- `office_automation.word_ops.read(file_path)`
- `office_automation.word_ops.edit(file_path, instructions)`
- `office_automation.powerpoint_ops.read(file_path)`
- `office_automation.powerpoint_ops.edit(file_path, instructions)`
- `office_automation.pdf_ops.read(file_path)`
- `office_automation.pdf_ops.edit(file_path, instructions)`

## Shared Helpers The Wrapper May Reuse

- `office_automation.common.files.copy_original(src, dest_dir)`
- `office_automation.common.files.list_office_files(folder, extensions=None)`

The current SG2 wrapper primarily resolves output paths and lets the routed runtime perform the actual file mutation flow.
It does not redefine copy logic that already belongs in the shared runtime.

## Wrapper-Owned Responsibilities

The wrapper owns:

- request envelope validation
- `read` vs `edit` mode gating
- extension routing for `xlsx`, `xlsm`, `docx`, `pptx`, `pdf`
- pre-runtime unsupported-scope rejection
- output-path resolution and collision-safe `-edited` naming
- inserting the authoritative `instructions["output_path"]`
- warning capture and mapping to SG2 status codes `0` / `1` / `2` / `3`
- concise user-facing summaries

## Runtime-Owned Responsibilities

The runtime owns:

- actual file parsing and mutation
- format-specific operation validation
- workbook / document / presentation / PDF save behavior for the provided `output_path`
- reusable copy / metadata / image helpers shared across skills

## Execution Environment

Preferred repo-local execution pattern:

```bash
uv run --project tools/office-automation python ...
```

If importing the wrapper directly from Python, ensure `tools/office-automation/src` is importable.
The wrapper script also adds that repo-local runtime source path automatically when used in-place from this repository.
