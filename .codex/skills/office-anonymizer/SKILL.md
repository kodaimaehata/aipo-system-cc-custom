---
name: office-anonymizer
description: Anonymize Office and PDF files in a target folder. Auto-discovers candidate identifiers, proposes a mapping for explicit user confirmation, runs the SG5 detect/transform/validate chain, applies a position-based post_pass and codex-driven image anonymization, then hard-fails if any approved identifier leaks into the output.
---

# Office Anonymizer

Folder-scoped anonymization for `xlsx`, `xlsm`, `docx`, `pptx`, and searchable
`pdf` files. The skill orchestrates the shared runtime at
`tools/office-automation/`, but layers on top an auto-discovery pass, an
explicit user-confirmation gate, position-based cleanup for pptx residuals,
codex-driven image anonymization, and a mandatory hard-fail re-validation.

This SKILL file is the **canonical source**; the mirror at
`.codex/skills/office-anonymizer/` is generated from here by
`.claude/scripts/sync_skills.py`. Edit only `.claude/` and re-run
`python .claude/scripts/sync_skills.py --write` to publish.

## Default Flow (v2)

```
0. janitor_sweep             stale cache dirs > 30 days or past expires_at
1. discover_files            list supported extensions under target_folder
2. auto_dump_bodies          extract every paragraph from each supported file
3. heuristic_candidate_scan  propose person/company/property candidates
4. propose_mapping           write candidates.yaml (0600, in cache) for edit
5. [user confirms]           user edits the file; caller re-invokes with mapping
6. sg5_run                   detect + transform + validate via the shared runtime
7. post_pass                 pptx body position-based cleanup (raises on out-of-scope residual)
8. image_codex_anonymize     per-image codex judgment; clone image part on replace
9. final_revalidate          hard-fail on any residual approved identifier
10. produce_artifacts        anonymization_report.md in target_folder only
11. cleanup_runid            remove cache dir on success
```

Each step is documented in detail under `references/`.

## When to Use

- Folder contains one or more `.pptx` / `.docx` / `.xlsx` / `.xlsm` / `.pdf`
  files that need person-name, company-name, and property-name redaction.
- The caller is prepared to review the proposed candidate mapping before any
  content is rewritten — the skill refuses to proceed without explicit
  approval.
- The environment has the Codex CLI (`codex` 0.122+) installed and
  authenticated when image anonymization is needed.

## When Not to Use

- Legacy Office formats (`xls`, `xlsb`, `doc`, `ppt`) — convert first.
- Bulk automation without a human review step — the pipeline deliberately
  hard-fails on leaks rather than silently passing a partial result through.
- Runtime dependencies absent (`tools/office-automation/` unreachable, Codex
  CLI missing when image anonymization is requested).
- Guaranteed perfect anonymization — the skill reduces risk; final sign-off
  remains human.

## Required Input

- `target_folder` (absolute or user-expanded path to an existing directory).

## Optional Inputs

- `approved_mapping: {original: replacement, ...}` — required on the second
  run after the user has edited the candidates file.
- `emit_mapping_to: <absolute path>` — opt-in mapping sheet output (outside
  `target_folder`). The sheet contains re-identification data and is always
  written at mode `0600` with a SHA-256 integrity footer.
- `enable_post_pass: bool = True` — run the position-based pptx cleanup.
- `enable_image_codex: bool = False` — invoke Codex CLI to anonymize pictures.
- `extensions` — optional narrowing of the supported-extension set.

## Artifacts and Their Locations

| Artifact                 | Location                                                | Contains re-identification data? |
| ------------------------ | ------------------------------------------------------- | -------------------------------- |
| Anonymized file(s)       | `target_folder/` (overwrite)                            | No                               |
| SG5 Markdown report      | `target_folder/anonymization_report.md`                 | No (counts + coordinates only)   |
| `candidates.yaml`        | `$XDG_CACHE_HOME/office-anonymizer/<runid>/`            | Yes (approved text + context)    |
| `image_codex_log.md`     | `$XDG_CACHE_HOME/office-anonymizer/<runid>/`            | Yes (tracks per-image outcomes)  |
| `leak_report.md`         | `$XDG_CACHE_HOME/office-anonymizer/<runid>/` on failure | Yes                              |
| `anonymization_mapping.md` | Caller-specified absolute path (opt-in only)          | Yes                              |
| Backup `.pre-postpass.bak` | `$XDG_CACHE_HOME/office-anonymizer/<runid>/backups/`  | Yes                              |

Cache directories are created under `resolve_cache_base()` (see
`scripts/cache_utils.py`) with permissions `0o700`. All sensitive files are
written at `0o600`. On success the run's cache dir is deleted; on failure it
is retained for debugging and reaped by the next run's janitor sweep.

## References

- `references/runtime-contract.md` — SG5 wrapper request/result contract.
- `references/policy-and-scope.md` — supported/rejected scope details.
- `references/report-and-status.md` — SG5 report sections and status mapping.
- `references/replay-examples.md` — historical request/confirmation recipes.
- `references/post-pass-and-mapping.md` — post_pass scope, dedupe patterns,
  opt-in mapping sheet contract.
- `references/image-codex-flow.md` — Codex CLI integration details
  (timeouts, retries, part cloning).

## Sync Guard

Every `run_request()` call verifies the `.claude` / `.codex` mirror is in sync
by invoking `python .claude/scripts/sync_skills.py --check`. If drift is
detected the wrapper raises. Tests may opt out with the environment variable
`OFFICE_ANONYMIZER_SKIP_SYNC_CHECK=1` — **do not set this in production or
user-facing runs**. The sync check keeps the canonical `.claude/` copy and the
derived `.codex/` copy from quietly drifting.

## Known Limitations

- Heuristic candidate scan relies on job-title suffixes ("…部長", "…次長",
  "…リーダー", "…氏") to detect person names. Plain-name occurrences without a
  trailing title (e.g. "WealthPark 山田") are *not* proposed automatically;
  the user can add them manually in `candidates.yaml`.
- Post-pass covers pptx body text (shapes / tables / groups) only. Notes,
  comments, headers, footers, metadata, and non-pptx formats are handled by
  SG5 first; any residual in those areas becomes a hard-fail at
  `final_revalidate` rather than being silently patched.
- Image anonymization depends on an authenticated Codex CLI. When the CLI is
  unavailable or exhausts its retry budget, the original image stays in place
  and the failure is logged.
