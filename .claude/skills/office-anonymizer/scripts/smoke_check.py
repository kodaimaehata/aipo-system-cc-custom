from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook
from openpyxl.comments import Comment

from office_anonymizer_wrapper import run



def _build_workbook(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet["A1"] = "sensitive"
    sheet["A1"].comment = Comment("remove me", "analyst")
    sheet.oddHeader.center.text = "Confidential Header"
    sheet.oddFooter.center.text = "Footer Note"
    workbook.save(path)
    workbook.close()
    return path



def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _build_workbook(root / "sample.xlsx")

        result = run(target_folder=root)
        assert result["status"] in {0, 2}, result
        assert result["supported_file_count"] == 1, result
        assert Path(result["report_path"]).exists(), result
        assert result["validation_status_counts"], result
        assert result["body_text_run_mode"] == "absent", result
        assert result["body_text_candidate_summary_count"] == 0, result
        assert result["body_text_candidate_summaries"] == [], result
        assert result["body_text_confirmation_request_template"] == {
            "mode": "apply_confirmed",
            "approved_candidate_ids": [],
            "rejected_candidate_ids": [],
            "replacement_overrides": {},
        }, result

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy = root / "legacy.xls"
        legacy.write_text("legacy", encoding="utf-8")

        rejected = run(target_folder=root)
        assert rejected["status"] == 1, rejected
        assert rejected["unsupported_file_count"] == 1, rejected

    print("office-anonymizer wrapper smoke check passed")


if __name__ == "__main__":
    main()
