# Office-Python Supported Scope Reference

## Supported V1 Files

Only these file extensions are in scope:

- `xlsx`
- `xlsm`
- `docx`
- `pptx`
- `pdf`

## Supported Wrapper Modes

- `read`
- `edit`

`office-python` is a file read/edit skill. It is not a metadata-summary-first skill.

## Save Behavior

For `edit` requests the wrapper:

- preserves the original by default
- honors an explicit `output_path` when valid
- otherwise derives `<stem>-edited<suffix>` beside the source file
- or derives `<output_dir>/<stem>-edited<suffix>` when `output_dir` is supplied
- avoids silently overwriting derived destinations by using collision-safe names such as `-edited-2`
- passes the resolved path into `instructions["output_path"]` as the authoritative runtime target

For `read` requests the wrapper rejects edit-only save controls such as:

- non-null `output_path`
- non-null `output_dir`
- `copy_before_edit == True`
- non-null `instructions`

## Explicitly Unsupported / Rejected Scope

The wrapper should reject these as unsupported in V1 when the excluded intent is clear:

- legacy Office formats: `xls`, `xlsb`, `doc`, `ppt`
- VBA editing or macro authoring
- embedded-object handling or embedded-file extraction / cleanup
- external OCR flows such as Tesseract
- OCR-dependent cleanup requests outside Python-library-only handling
- Word track-changes cleanup
- Word complex text-box-specific editing outside ordinary body paragraph / table operations
- PowerPoint SmartArt-specific editing
- PowerPoint advanced animation rewriting
- requests that require exact PDF reflow preservation, full-fidelity vector rewriting, or perfect visual parity claims

## User-Facing Rejection Posture

When a request is out of scope, explain:

- what is unsupported in V1
- that the rejection is wrapper-owned scope gating, not a hidden runtime failure
- a nearby supported flow when one exists

Examples:

- `xls` / `xlsb`: ask for conversion to `xlsx` or `xlsm`
- VBA requests: workbook edits are supported for `xlsx` / `xlsm`, but VBA editing is not
- Word track changes: ordinary paragraph and table edits are supported, acceptance / rejection cleanup is not
- SmartArt requests: edit regular slide text or tables instead of SmartArt-specific structures
- PDF fidelity requests: use overlay / annotation / redaction / rebuild flows with manual review instead of exact-fidelity promises

## Status Mapping

- `0`: success within supported scope
- `1`: unsupported format or unsupported scope rejected by the wrapper
- `2`: completed with warnings or manual-review caveats
- `3`: fatal processing or invalid-request failure
