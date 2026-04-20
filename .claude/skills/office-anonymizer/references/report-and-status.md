# Office-Anonymizer Report And Status Reference

## Report Path And Format

Report output is Markdown only.

Default path:

- `<target-folder>/anonymization_report.md`

The shared runtime writes that default report during `validate(target_folder, transform_results)`.
If the wrapper accepts `report_path`, it must still point to Markdown and is treated only as a wrapper-local copy destination layered over the runtime artifact.

## Preview-Only Report Behavior

When SG5 body-text candidates are detected but confirmation is still pending, the wrapper still writes a Markdown report instead of blocking report generation.
The preview report stays Markdown-only and includes at least these sections:

- `## Run summary`
- `## Files in scope`
- `## Body-text candidate summary`
- `## Next step guidance`
- `## Body-text confirmation request template`

Preview-only runs must not silently auto-apply body-text edits.

## Wrapper Summary Expectations

The wrapper keeps SG3-visible summary fields such as:

- `status`
- `status_label`
- `message`
- `report_path`
- `runtime_report_path`
- `validation_status_counts`
- `validation_statuses`
- `manual_review_item_count`
- `residual_findings_count`
- `warning_count`
- `requires_manual_review`

The stable SG5-visible summary fields are:

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

Each `body_text_candidate_summaries` entry includes:

- `candidate_id`
- `candidate_type`
- `normalized_text`
- `occurrence_count`
- `reason_tags`
- `replacement_text`
- `sample_locations`
- `decision`
- `manual_review_required`

Backward-compatible SG5 aliases remain present too:

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

## Manual Review Expectations

Do not collapse warning-bearing or manual-review-bearing runs into silent success.
The report and wrapper summary should stay explicit about:

- residual findings after validation
- manual-review-only surfaces
- preview-only body-text candidates awaiting confirmation
- rejected or undecided body-text candidates after a confirmed rerun
- low-confidence body-text candidates
- skipped or report-only targets
- warnings from transform or validation
- unsupported-scope items discovered around an otherwise supported run

## Status Mapping

- `0`: success within supported scope and no warning-bearing escalation
- `1`: unsupported format or unsupported scope rejected by the wrapper
- `2`: partial success, preview-only confirmation required, residual findings, warnings, or required manual review
- `3`: fatal runtime failure or unrecoverable processing error

Preview-only SG5 runs should be `status=2`.
Manual-review-heavy confirmed runs should also remain `status=2`, including searchable-PDF follow-up, rejected candidates, residual candidates, and warning-bearing results.
