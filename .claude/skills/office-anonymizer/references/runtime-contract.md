# Office-Anonymizer Runtime Contract Reference

This skill stays thin by importing the shared runtime from:

- `tools/office-automation/src/office_automation/anonymize/detect.py`
- `tools/office-automation/src/office_automation/anonymize/transform.py`
- `tools/office-automation/src/office_automation/anonymize/validate.py`
- `tools/office-automation/src/office_automation/common/files.py`

## Stable Boundary

The stable packaged surface is Python imports, not a package-owned CLI.
Public exports remain:

- `run(...)`
- `run_request(request)`
- `UnsupportedScopeError`

The stable runtime call chain remains:

- `detect(target_folder, extensions=None, body_text_candidate_inputs=None)`
- `transform(detected, policy)`
- `validate(target_folder, transform_results)`

Markdown reporting remains runtime-owned at `<target-folder>/anonymization_report.md`.
If the wrapper accepts `report_path`, that path is only a wrapper-local copy destination layered on top of the runtime artifact.

## Wrapper-Owned Responsibilities

The wrapper owns:

- validating `target_folder`
- validating optional extension subsets inside supported scope
- packaged default-rule loading from `default_rules.yaml`
- one-step `customization_overrides`
- one-time `image_policy_confirmation`
- normalization of `body_text_candidate_inputs`
- normalization of `body_text_confirmation`
- explicit unsupported-scope rejection before runtime handoff
- preview-only body-text report writing when SG5 confirmation is still pending
- final wrapper-visible summary and SG-aligned `0/1/2/3` status mapping

`body_text_candidate_inputs` normalization accepts these keys and normalizes string-or-sequence values by trimming, dropping empties, and deduplicating:

- `person_names`
- `company_names`
- `emails`
- `phones`
- `addresses`
- `domains`
- `exact_phrases`
- `context_terms`
- `replacement_text`
- `replacement_map`

`body_text_confirmation` normalization accepts:

- `mode`
- `approved_candidate_ids`
- `rejected_candidate_ids`
- `replacement_overrides`
- `review_notes`

Missing `body_text_candidate_inputs` and `body_text_confirmation` remain neutral defaults, not errors.
SG3-era calls such as `run(target_folder=folder)` remain valid.

## Runtime-Owned Responsibilities

The runtime owns:

- supported-file discovery through shared helpers
- reusable detection logic for comments, notes, headers, footers, metadata, images, and SG5 body-text candidates
- anonymization transforms once the wrapper has produced a policy dict
- post-transform validation and the default Markdown report

For SG5, the runtime payloads now carry body-text candidate summaries and decision data, but the wrapper still only routes data into the same `detect -> transform -> validate` callable chain.
The wrapper must not duplicate body-text detection, transform, or validation logic.

## Wrapper Result Surface

The wrapper keeps the older SG3-visible fields and also exposes these stable SG5-visible fields:

- `body_text_run_mode`
- `body_text_confirmation_required`
- `body_text_candidate_summary_count`
- `body_text_candidate_summaries`
- `body_text_pending_candidate_count`
- `body_text_approved_candidate_count`
- `body_text_rejected_candidate_count`
- `body_text_residual_candidate_count`
- `body_text_low_confidence_candidate_count`
- `body_text_next_step_guidance`
- `body_text_confirmation_request_template`

Backward-compatible SG5 aliases from the earlier wrapper surface remain present too, including:

- `body_text_candidate_count`
- `body_text_candidate_summary`
- `body_text_confirmation_mode`
- `body_text_preview_only`
- `body_text_decision_counts`
- `approved_candidate_ids`
- `rejected_candidate_ids`
- `undecided_candidate_ids`
- `next_step_guidance`
- `body_text_confirmation_warnings`

## Execution Environment

Preferred repo-local execution pattern:

```bash
uv run --project tools/office-automation python ...
```

The wrapper script also adds `tools/office-automation/src` to `sys.path` when it is imported in-place from this repository.
