# Post-Pass and Mapping Reference

## What Post-Pass Is (and Isn't)

`scripts/post_pass.py` picks up SG5 residuals that the shared runtime refused
to modify automatically (typically pptx table cells or paragraphs whose text
is split across multiple runs) and applies targeted replacements at the exact
coordinates SG5 returned.

Post-pass is **not** a fallback string-replace. It never touches content the
SG5 layer did not already flag. If SG5 returns a residual in a category the
post-pass does not support, the module raises
`UnsupportedPostPassScope` and the wrapper lets that exception bubble up so
the final re-validation can report the leak instead of silently patching it.

## Supported Scope

- pptx body text inside:
  - top-level shape `text_frame`s
  - nested group shapes (recursively)
  - table cell `text_frame`s

## Out-of-Scope (raises `UnsupportedPostPassScope`)

- pptx notes / comments / headers / footers / metadata
- docx / xlsx / xlsm / pdf of any kind

## Secondary Cleanups (body scope only)

Once the targeted replacements are applied, post-pass runs two additional
sweeps inside the same shapes/paragraphs:

1. **Role-suffix dedupe.** When an anonymized label already carries a role
   (e.g. `"A役員"`) and the original text had the same role right after the
   name (e.g. `"平本役員"` → after replace: `"A役員役員"`), the duplicated
   suffix is collapsed using the approved-replacement set plus a fixed role
   vocabulary (`役員 / 部長 / 次長 / 統括次長 / 総括次長 / 副部長 / 副社長 /
   課長 / 係長 / リーダー / マネージャー / ディレクター / フェロー / 顧問 /
   参与 / 氏 / さん`).

2. **Concatenation spacing.** For known bare labels (`RET / WP / AM / CN /
   PMO`, extend per deployment), if the original had no delimiter before the
   name (e.g. `RET髙口` → after replace: `RETM氏`), a single space is inserted
   between the bare label and the anonymized token so the output reads as
   `RET M氏`.

Both sweeps operate strictly on already-identified paragraphs; neither runs a
document-wide string substitution.

## Mapping Sheet Contract

`scripts/mapping_sheet.py` emits the human-readable mapping only when the
caller provides an explicit absolute path via `emit_mapping_to`. There is no
implicit default location inside `target_folder`, because the mapping itself
is re-identification data.

Every emitted sheet:

- Starts with a bold warning header that classifies the file as re-identification data.
- Lists each approved mapping as a Markdown table row.
- Ends with a SHA-256 footer `<!-- sha256:... -->` computed over the body
  minus the footer itself. Any tampering changes the hash.
- Is chmod'd to `0o600` immediately after writing.

If the caller passes a relative path the module raises `ValueError` to avoid
accidental in-tree emission.
