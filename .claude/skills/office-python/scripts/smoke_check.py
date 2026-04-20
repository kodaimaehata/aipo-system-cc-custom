from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook

from office_python_wrapper import run



def _build_workbook(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet["A1"] = "hello"
    workbook.save(path)
    workbook.close()
    return path



def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = _build_workbook(root / "sample.xlsx")

        read_result = run(file_path=source, mode="read")
        assert read_result["status"] == 0, read_result
        assert read_result["detected_format"] == "xlsx", read_result
        assert read_result["summary"]["result_shape"]["sheet_count"] == 1, read_result

        edit_result = run(
            file_path=source,
            mode="edit",
            instructions={
                "operations": [
                    {"op": "set_cell", "sheet": "Sheet1", "cell": "A1", "value": "updated"},
                ]
            },
        )
        assert edit_result["status"] == 0, edit_result
        assert edit_result["output_path"], edit_result
        assert Path(edit_result["output_path"]).exists(), edit_result

        unsupported_result = run(file_path=root / "legacy.xls", mode="read")
        assert unsupported_result["status"] == 3, unsupported_result

        legacy_path = root / "legacy.xls"
        legacy_path.write_text("legacy")
        unsupported_result = run(file_path=legacy_path, mode="read")
        assert unsupported_result["status"] == 1, unsupported_result

        invalid_read_result = run(
            file_path=source,
            mode="read",
            output_path=root / "should-not-exist.xlsx",
        )
        assert invalid_read_result["status"] == 3, invalid_read_result

    print("office-python wrapper smoke check passed")


if __name__ == "__main__":
    main()
