# Office-Anonymizer Replay Examples

These examples keep the packaged wrapper boundary intact:

- run from repo root `/Users/kodai/projects/aipo-system-cc-custom`
- import `.codex/skills/office-anonymizer/scripts/office_anonymizer_wrapper.py`
- build a minimal fixture inline
- print wrapper JSON to stdout
- preserve the generated Markdown report and human-review notes

Do not replace these examples with an invented shared-runtime CLI.
The replay contract is the wrapper import surface.

## 1) SG3-compatible call

```bash
cd /Users/kodai/projects/aipo-system-cc-custom
tools/office-automation/.venv/bin/python - <<'PY'
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook
from openpyxl.comments import Comment

sys.path.insert(0, str(Path('.codex/skills/office-anonymizer/scripts').resolve()))
from office_anonymizer_wrapper import run

with TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    workbook = Workbook()
    sheet = workbook.active
    sheet['A1'] = 'hello'
    sheet['A1'].comment = Comment('remove me', 'analyst')
    workbook.save(root / 'cleanable.xlsx')
    workbook.close()

    result = run(target_folder=root)
    print(json.dumps({
        'status': result['status'],
        'status_label': result['status_label'],
        'message': result['message'],
        'report_path': result['report_path'],
        'runtime_report_path': result['runtime_report_path'],
        'validation_status_counts': result['validation_status_counts'],
        'manual_review_item_count': result['manual_review_item_count'],
        'residual_findings_count': result['residual_findings_count'],
        'body_text_run_mode': result['body_text_run_mode'],
        'body_text_candidate_summary_count': result['body_text_candidate_summary_count'],
    }, indent=2, ensure_ascii=False))
PY
```

Expected behavior:
- normal SG3-era invocation still works with no body-text keys
- expected status is usually `0` for a clean supported run
- `report_path` points to the Markdown report
- existing SG3 summary fields still exist
- SG5 fields stay neutral, typically `body_text_run_mode="absent"`

Evidence to preserve:
- stdout JSON
- saved Markdown report at `report_path`
- confirmation that SG3-visible fields and neutral SG5-visible fields both exist

## 2) SG5 preview-only first pass

```bash
cd /Users/kodai/projects/aipo-system-cc-custom
tools/office-automation/.venv/bin/python - <<'PY'
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook

sys.path.insert(0, str(Path('.codex/skills/office-anonymizer/scripts').resolve()))
from office_anonymizer_wrapper import run

with TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    workbook = Workbook()
    sheet = workbook.active
    sheet['A1'] = 'Jane Example is assigned to Project Lotus.'
    workbook.save(root / 'body-text-preview.xlsx')
    workbook.close()

    result = run(
        target_folder=root,
        body_text_candidate_inputs={
            'person_names': ['Jane Example'],
            'exact_phrases': ['Project Lotus'],
            'replacement_text': '[REDACTED]',
        },
    )
    print(json.dumps({
        'status': result['status'],
        'status_label': result['status_label'],
        'report_path': result['report_path'],
        'body_text_run_mode': result['body_text_run_mode'],
        'body_text_candidate_summary_count': result['body_text_candidate_summary_count'],
        'body_text_candidate_summaries': result['body_text_candidate_summaries'],
        'body_text_next_step_guidance': result['body_text_next_step_guidance'],
        'body_text_confirmation_request_template': result['body_text_confirmation_request_template'],
    }, indent=2, ensure_ascii=False))
PY
```

Expected behavior:
- expected `status=2`
- `body_text_run_mode="preview_only"`
- `body_text_candidate_summaries` contains replayable `candidate_id` values
- the Markdown report contains the body-text summary, next-step guidance, and confirmation-request-template sections
- no body-text text rewrite is auto-applied in this pass

Evidence to preserve:
- stdout JSON
- candidate IDs from `body_text_candidate_summaries`
- `body_text_confirmation_request_template`
- saved preview Markdown report at `report_path`
- any manual-review note, especially for searchable PDF behavior

## 3) SG5 confirmed second pass

```bash
cd /Users/kodai/projects/aipo-system-cc-custom
tools/office-automation/.venv/bin/python - <<'PY'
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path('.codex/skills/office-anonymizer/scripts').resolve()))
from office_anonymizer_wrapper import run

with TemporaryDirectory() as temp_dir:
    root = Path(temp_dir)
    workbook = Workbook()
    sheet = workbook.active
    sheet['A1'] = 'Jane Example is assigned to Project Lotus.'
    workbook.save(root / 'body-text-confirm.xlsx')
    workbook.close()

    candidate_inputs = {
        'person_names': ['Jane Example'],
        'exact_phrases': ['Project Lotus'],
        'replacement_text': '[REDACTED]',
    }

    preview = run(target_folder=root, body_text_candidate_inputs=candidate_inputs)
    candidate_ids = {item['normalized_text']: item['candidate_id'] for item in preview['body_text_candidate_summaries']}

    confirmed = run(
        target_folder=root,
        body_text_candidate_inputs=candidate_inputs,
        body_text_confirmation={
            'mode': 'apply_confirmed',
            'approved_candidate_ids': [candidate_ids['jane example']],
            'rejected_candidate_ids': [candidate_ids['project lotus']],
            'replacement_overrides': {
                candidate_ids['jane example']: '[PERSON]'
            },
        },
    )

    workbook = load_workbook(root / 'body-text-confirm.xlsx')
    updated_value = workbook.active['A1'].value
    workbook.close()

    print(json.dumps({
        'preview_status': preview['status'],
        'confirmed_status': confirmed['status'],
        'confirmed_report_path': confirmed['report_path'],
        'body_text_run_mode': confirmed['body_text_run_mode'],
        'body_text_approved_candidate_count': confirmed['body_text_approved_candidate_count'],
        'body_text_rejected_candidate_count': confirmed['body_text_rejected_candidate_count'],
        'body_text_residual_candidate_count': confirmed['body_text_residual_candidate_count'],
        'body_text_candidate_summaries': confirmed['body_text_candidate_summaries'],
        'updated_cell_value': updated_value,
    }, indent=2, ensure_ascii=False))
PY
```

Expected behavior:
- the second pass reruns with the same `body_text_candidate_inputs`
- `body_text_confirmation.mode="apply_confirmed"` enables confirmed application for the approved subset only
- stdout JSON shows approved and rejected counts
- the report preserves the decision trace and any residual/manual-review follow-up
- the final run still may be `status=2` if rejected candidates, searchable-PDF follow-up, or other warnings remain

Evidence to preserve:
- stdout JSON from both passes
- approved and rejected `candidate_id` values carried forward from preview evidence
- final `report_path`
- updated file evidence such as the post-run cell value
- the preview report plus the final report so the confirmation trail remains replayable

## Replay Reminder For T009

Keep these assumptions stable for downstream replay work:
- candidate IDs from the preview pass are the identifiers to reuse in the second pass
- preserve the preview report, final report, and stdout JSON together
- human review is still required even when the confirmed pass succeeds
- searchable PDFs remain manual-review-sensitive and OCR is still out of scope
