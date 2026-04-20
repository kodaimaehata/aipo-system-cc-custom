from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from office_automation import pdf_ops


def _create_text_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf_canvas = canvas.Canvas(str(path), pagesize=letter)
    pdf_canvas.setTitle("PDF runtime sample")
    pdf_canvas.drawString(72, 720, "Hello PDF runtime")
    pdf_canvas.drawString(72, 700, "Secret 12345")
    pdf_canvas.showPage()
    pdf_canvas.drawString(72, 720, "Second page note")
    pdf_canvas.save()
    return path


def _create_blank_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf_canvas = canvas.Canvas(str(path), pagesize=letter)
    pdf_canvas.showPage()
    pdf_canvas.save()
    return path


def _search_rect(path: Path, needle: str, *, page_index: int = 0) -> list[float]:
    document = fitz.open(path)
    try:
        matches = document[page_index].search_for(needle)
        assert matches, f"Expected to find text {needle!r} in {path}"
        rect = matches[0]
        return [rect.x0, rect.y0, rect.x1, rect.y1]
    finally:
        document.close()



def test_read_returns_page_oriented_pdf_text_and_signals(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")

    result = pdf_ops.read(source)

    assert result["format"] == "pdf"
    assert result["file_path"] == str(source)
    assert result["page_count"] == 2
    assert result["metadata"]["title"] == "PDF runtime sample"
    assert result["warnings"] == []

    first_page = result["pages"][0]
    assert first_page["page_index"] == 0
    assert first_page["page_number"] == 1
    assert first_page["text_layer_present"] is True
    assert first_page["likely_image_only"] is False
    assert first_page["extraction_confidence"] in {"medium", "high"}
    assert "Hello PDF runtime" in first_page["text"]
    assert "Secret 12345" in first_page["text"]
    assert first_page["extraction_sources"] == ["pdfplumber", "pymupdf"]

    second_page = result["pages"][1]
    assert second_page["page_number"] == 2
    assert second_page["text"] == "Second page note"



def test_read_surfaces_missing_text_layer_warning_for_blank_pdf_page(tmp_path: Path) -> None:
    source = _create_blank_pdf(tmp_path / "blank.pdf")

    result = pdf_ops.read(source)

    assert result["page_count"] == 1
    assert result["pages"][0]["text"] == ""
    assert result["pages"][0]["text_layer_present"] is False
    assert result["pages"][0]["warnings"] == [
        "Page 1 does not appear to contain an extractable text layer."
    ]
    assert result["warnings"] == [
        "Page 1 does not appear to contain an extractable text layer.",
        "This PDF does not appear to contain an extractable text layer. OCR-free PDF V1 editing is limited for scanned/image-only documents.",
    ]



def test_edit_overlay_text_honors_output_path_and_preserves_original(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")
    output_path = tmp_path / "exports" / "overlay-result.pdf"
    ignored_output_dir = tmp_path / "ignored-dir"

    with pytest.warns(RuntimeWarning, match="manual review"):
        saved_path = pdf_ops.edit(
            source,
            {
                "operations": [
                    {
                        "type": "overlay_text",
                        "page_number": 1,
                        "rect": [72, 120, 280, 150],
                        "text": "Overlay text added",
                        "font_size": 12,
                    }
                ],
                "output_path": str(output_path),
                "output_dir": str(ignored_output_dir),
                "copy_before_edit": True,
                "options": {},
            },
        )

    assert saved_path == output_path
    assert output_path.exists()
    assert not ignored_output_dir.exists()
    assert "Overlay text added" not in pdf_ops.read(source)["pages"][0]["text"]
    assert "Overlay text added" in pdf_ops.read(output_path)["pages"][0]["text"]



def test_edit_redact_region_removes_target_text_and_writes_replacement(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")
    output_path = tmp_path / "redacted.pdf"
    secret_rect = _search_rect(source, "Secret 12345")

    with pytest.warns(RuntimeWarning) as caught_warnings:
        saved_path = pdf_ops.edit(
            source,
            {
                "operations": [
                    {
                        "type": "redact_region",
                        "page_index": 0,
                        "rect": secret_rect,
                        "replacement_text": "REDACTED",
                        "font_size": 11,
                    }
                ],
                "output_path": str(output_path),
                "copy_before_edit": True,
                "options": {},
            },
        )

    assert any("Redaction on page 1 succeeded" in str(item.message) for item in caught_warnings)
    assert any("manual review" in str(item.message) for item in caught_warnings)

    assert saved_path == output_path
    assert output_path.exists()
    assert "Secret 12345" in pdf_ops.read(source)["pages"][0]["text"]

    redacted = pdf_ops.read(output_path)
    assert "Secret 12345" not in redacted["pages"][0]["text"]
    assert "REDACTED" in redacted["pages"][0]["text"]



def test_edit_rebuild_text_pdf_creates_readable_text_oriented_output(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")
    output_path = tmp_path / "rebuilt.pdf"

    with pytest.warns(RuntimeWarning, match="text-oriented PDF"):
        saved_path = pdf_ops.edit(
            source,
            {
                "operations": [{"type": "rebuild_text_pdf", "font_size": 12}],
                "output_path": str(output_path),
                "copy_before_edit": True,
                "options": {},
            },
        )

    assert saved_path == output_path
    assert output_path.exists()
    rebuilt = pdf_ops.read(output_path)
    assert rebuilt["page_count"] == 2
    assert "Hello PDF runtime" in rebuilt["pages"][0]["text"]
    assert "Second page note" in rebuilt["pages"][1]["text"]


@pytest.mark.parametrize("output_path", [None, "   "])
def test_edit_requires_explicit_non_empty_output_path(tmp_path: Path, output_path: str | None) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")

    with pytest.raises(ValueError, match=r"must include a non-empty 'output_path'"):
        pdf_ops.edit(
            source,
            {
                "operations": [
                    {
                        "type": "overlay_text",
                        "page_number": 1,
                        "rect": [72, 120, 280, 150],
                        "text": "Overlay text added",
                        "font_size": 12,
                    }
                ],
                "output_path": output_path,
                "options": {},
            },
        )


def test_edit_rejects_same_path_when_copy_before_edit_is_true(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")

    with pytest.raises(ValueError, match="cannot preserve the original"):
        pdf_ops.edit(
            source,
            {
                "operations": [
                    {
                        "type": "overlay_text",
                        "page_number": 1,
                        "rect": [72, 120, 280, 150],
                        "text": "In-place edit",
                        "font_size": 12,
                    }
                ],
                "output_path": str(source),
                "copy_before_edit": True,
                "options": {},
            },
        )

    assert "In-place edit" not in pdf_ops.read(source)["pages"][0]["text"]



def test_edit_rejects_unsupported_pdf_operations(tmp_path: Path) -> None:
    source = _create_text_pdf(tmp_path / "sample.pdf")

    with pytest.raises(NotImplementedError, match=r"Unsupported PDF operation 'replace_text'"):
        pdf_ops.edit(
            source,
            {
                "operations": [{"type": "replace_text", "page_index": 0}],
                "output_path": str(tmp_path / "out.pdf"),
                "options": {},
            },
        )
