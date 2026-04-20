"""PDF V1 read/edit helpers for SG2.

`read()` is extraction-first and returns page-oriented text results plus heuristics about
text-layer availability and likely image-only/scanned pages.

`edit()` intentionally supports only explicit, limited PDF strategies:
- `overlay_text`
- `redact_region`
- `annotate_text_change`
- `rebuild_text_pdf`

These helpers do not promise lossless, Word-like PDF editing. Exact visual fidelity is not
guaranteed, and human review remains required after successful edits. Successful-but-caveated
edits emit Python warnings so SG2 can map them to wrapper-visible partial-success handling.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from os import PathLike
from pathlib import Path
import shutil
import uuid
import warnings

from office_automation.common.files import copy_original

__all__ = ["read", "edit"]

_SUPPORTED_EXTENSION = ".pdf"
_SUPPORTED_EXTENSION_TEXT = "pdf"
_SUPPORTED_OPERATIONS = frozenset(
    {
        "annotate_text_change",
        "overlay_text",
        "redact_region",
        "rebuild_text_pdf",
    }
)
_DEFAULT_FONT_NAME = "helv"
_DEFAULT_REBUILD_FONT_NAME = "Helvetica"
_DEFAULT_PAGE_WIDTH = 612.0
_DEFAULT_PAGE_HEIGHT = 792.0
_DEFAULT_MARGIN = 54.0
_MANUAL_REVIEW_WARNING = (
    "PDF V1 edits use overlay, annotation, redaction, or rebuild strategies. Exact visual "
    "fidelity is not guaranteed, and manual review is required after saving."
)
_REBUILD_WARNING = (
    "PDF rebuild_text_pdf creates a new text-oriented PDF from supplied or extracted text. "
    "Exact visual fidelity is not guaranteed, and manual review is required."
)


def read(file_path: str | PathLike[str] | Path) -> dict:
    """Read a `.pdf` file and return page-oriented extraction data."""
    source = _validate_pdf_path(file_path, label="PDF source file")
    fitz = _load_pymupdf()
    pdfplumber = _load_pdfplumber()

    document = fitz.open(source)
    plumber_document = None
    try:
        _reject_encrypted_document(document, source)
        try:
            plumber_document = pdfplumber.open(source)
        except Exception as exc:  # pragma: no cover - depends on library-specific failures.
            plumber_document = None
            extraction_warning = (
                f"pdfplumber could not open '{source.name}' ({exc.__class__.__name__}); "
                "falling back to PyMuPDF extraction only."
            )
        else:
            extraction_warning = None

        pages: list[dict] = []
        warning_messages: list[str] = []
        if extraction_warning is not None:
            warning_messages.append(extraction_warning)

        for page_index in range(document.page_count):
            page_result = _read_page(
                document=document,
                page_index=page_index,
                plumber_document=plumber_document,
            )
            pages.append(page_result)
            warning_messages.extend(page_result["warnings"])

        if pages and all(not page["text_layer_present"] for page in pages):
            warning_messages.append(
                "This PDF does not appear to contain an extractable text layer. OCR-free PDF V1 "
                "editing is limited for scanned/image-only documents."
            )
        elif any(not page["text_layer_present"] for page in pages):
            warning_messages.append(
                "Some PDF pages do not appear to contain an extractable text layer. OCR-free PDF V1 "
                "editing is limited for those pages."
            )

        if any(page["likely_image_only"] for page in pages):
            warning_messages.append(
                "One or more PDF pages appear to be image-only or scan-like. Manual review is "
                "required because OCR is out of scope in V1."
            )

        return {
            "format": _SUPPORTED_EXTENSION_TEXT,
            "file_path": str(source),
            "page_count": document.page_count,
            "pages": pages,
            "warnings": _deduplicate_messages(warning_messages),
            "metadata": _normalize_metadata(getattr(document, "metadata", {}) or {}),
        }
    finally:
        if plumber_document is not None:
            plumber_document.close()
        document.close()


def edit(file_path: str | PathLike[str] | Path, instructions: dict) -> Path:
    """Apply limited PDF V1 edits and return the saved output path."""
    source = _validate_pdf_path(file_path, label="PDF source file")
    payload = _validate_edit_instructions(instructions)
    operations = payload["operations"]
    output_path = payload["output_path"]
    copy_before_edit = payload["copy_before_edit"]

    if any(_operation_name(operation) == "rebuild_text_pdf" for operation in operations) and len(operations) != 1:
        raise ValueError("PDF rebuild_text_pdf must be the only operation in a request.")

    if _operation_name(operations[0]) == "rebuild_text_pdf":
        _prepare_output_path(source, output_path, copy_before_edit=copy_before_edit)
        _apply_rebuild_operation(source, output_path, operations[0])
        warnings.warn(_REBUILD_WARNING, RuntimeWarning, stacklevel=2)
        return output_path

    fitz = _load_pymupdf()
    load_path = _prepare_edit_load_path(source, output_path, copy_before_edit=copy_before_edit)
    document = fitz.open(load_path)
    caveat_messages: list[str] = []
    try:
        _reject_encrypted_document(document, load_path)
        for operation in operations:
            _apply_operation(document, operation, caveat_messages)
        _save_document(document, output_path, load_path)
    finally:
        if not document.is_closed:
            document.close()

    if caveat_messages:
        for message in _deduplicate_messages(caveat_messages):
            warnings.warn(message, RuntimeWarning, stacklevel=2)
    return output_path


def _read_page(*, document, page_index: int, plumber_document) -> dict:
    page = document.load_page(page_index)
    plumber_text = ""
    page_warnings: list[str] = []

    if plumber_document is not None:
        try:
            plumber_text = plumber_document.pages[page_index].extract_text() or ""
        except Exception as exc:  # pragma: no cover - depends on library-specific failures.
            page_warnings.append(
                f"Page {page_index + 1} pdfplumber extraction failed ({exc.__class__.__name__}); "
                "PyMuPDF text was used instead."
            )

    pymupdf_text = page.get_text("text") or ""
    normalized_plumber_text = plumber_text.strip()
    normalized_pymupdf_text = pymupdf_text.strip()
    extracted_text = normalized_plumber_text or normalized_pymupdf_text

    extraction_sources: list[str] = []
    if normalized_plumber_text:
        extraction_sources.append("pdfplumber")
    if normalized_pymupdf_text:
        extraction_sources.append("pymupdf")

    words = page.get_text("words")
    image_count = len(page.get_images(full=True))
    text_layer_present = bool(words) or bool(normalized_plumber_text) or bool(normalized_pymupdf_text)
    likely_image_only = image_count > 0 and not text_layer_present and not extracted_text
    extraction_confidence = _estimate_extraction_confidence(
        text=extracted_text,
        text_layer_present=text_layer_present,
        image_count=image_count,
        plumber_text=normalized_plumber_text,
        pymupdf_text=normalized_pymupdf_text,
    )

    if not text_layer_present:
        page_warnings.append(
            f"Page {page_index + 1} does not appear to contain an extractable text layer."
        )
    if likely_image_only:
        page_warnings.append(
            f"Page {page_index + 1} is likely image-only or scanned content; OCR is out of scope in V1."
        )
    elif text_layer_present and not extracted_text:
        page_warnings.append(
            f"Page {page_index + 1} has a text-layer signal but produced no extracted text."
        )
    elif extraction_confidence == "low":
        page_warnings.append(
            f"Page {page_index + 1} text extraction confidence is low; layout or glyph encoding may limit fidelity."
        )

    if normalized_plumber_text and normalized_pymupdf_text:
        length_gap = abs(len(normalized_plumber_text) - len(normalized_pymupdf_text))
        longest = max(len(normalized_plumber_text), len(normalized_pymupdf_text))
        if longest and length_gap > max(25, int(longest * 0.35)):
            page_warnings.append(
                f"Page {page_index + 1} extraction sources disagreed materially; extracted text may be incomplete."
            )

    page_rect = page.rect
    return {
        "page_index": page_index,
        "page_number": page_index + 1,
        "width": float(page_rect.width),
        "height": float(page_rect.height),
        "rotation": int(page.rotation),
        "text": extracted_text,
        "char_count": len(extracted_text),
        "word_count": len(extracted_text.split()) if extracted_text else 0,
        "image_count": image_count,
        "text_layer_present": text_layer_present,
        "likely_image_only": likely_image_only,
        "extraction_confidence": extraction_confidence,
        "extraction_sources": extraction_sources,
        "warnings": _deduplicate_messages(page_warnings),
    }


def _estimate_extraction_confidence(
    *,
    text: str,
    text_layer_present: bool,
    image_count: int,
    plumber_text: str,
    pymupdf_text: str,
) -> str:
    if not text:
        return "none" if not text_layer_present else "low"

    score = 0
    if len(text) >= 80:
        score += 2
    elif len(text) >= 20:
        score += 1

    if len(text.split()) >= 8:
        score += 2
    elif len(text.split()) >= 3:
        score += 1

    if plumber_text and pymupdf_text:
        score += 1
    if image_count:
        score -= 1

    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _validate_edit_instructions(instructions: dict) -> dict:
    if not isinstance(instructions, dict):
        raise TypeError("PDF edit instructions must be a dict.")

    operations = instructions.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("PDF edit instructions must include a non-empty 'operations' list.")
    if not all(isinstance(operation, dict) for operation in operations):
        raise TypeError("Each PDF edit operation must be a dict.")

    for operation in operations:
        operation_name = _operation_name(operation)
        if operation_name not in _SUPPORTED_OPERATIONS:
            supported_text = ", ".join(sorted(_SUPPORTED_OPERATIONS))
            raise NotImplementedError(
                f"Unsupported PDF operation '{operation_name}'. Supported operations: {supported_text}."
            )

    options = instructions.get("options", {})
    if not isinstance(options, dict):
        raise TypeError("PDF edit instructions 'options' must be a dict when provided.")

    copy_before_edit = instructions.get("copy_before_edit", True)
    if not isinstance(copy_before_edit, bool):
        raise TypeError("PDF edit instructions 'copy_before_edit' must be a bool when provided.")

    output_path = instructions.get("output_path")
    normalized_output_path = _normalize_output_path(output_path=output_path)

    return {
        "operations": operations,
        "options": options,
        "copy_before_edit": copy_before_edit,
        "output_path": normalized_output_path,
    }


def _normalize_output_path(
    *,
    output_path: str | PathLike[str] | Path | None,
) -> Path:
    if output_path is None:
        raise ValueError("PDF edit instructions must include a non-empty 'output_path'.")
    if isinstance(output_path, str) and not output_path.strip():
        raise ValueError("PDF edit instructions must include a non-empty 'output_path'.")

    try:
        path = Path(output_path)
    except TypeError as exc:
        raise TypeError("PDF edit instructions 'output_path' must be a path-like value.") from exc

    _validate_pdf_extension(path, label="PDF output path")
    return path


def _prepare_output_path(source: Path, output_path: Path, *, copy_before_edit: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if _paths_refer_to_same_location(source, output_path) and copy_before_edit:
        raise ValueError(
            "PDF edit instructions cannot preserve the original when 'output_path' points to the "
            "source file and 'copy_before_edit' is True."
        )
    if output_path.exists() and not _paths_refer_to_same_location(source, output_path):
        raise FileExistsError(
            f"PDF output path '{output_path}' already exists; the runtime will not silently overwrite it."
        )


def _prepare_edit_load_path(source: Path, output_path: Path, *, copy_before_edit: bool) -> Path:
    _prepare_output_path(source, output_path, copy_before_edit=copy_before_edit)

    if _paths_refer_to_same_location(source, output_path):
        return source

    if not copy_before_edit:
        return source

    if output_path.name == source.name and output_path.parent != source.parent:
        staged_copy = copy_original(source, output_path.parent)
        if staged_copy != output_path:
            shutil.move(str(staged_copy), str(output_path))
        return output_path

    shutil.copy2(source, output_path)
    return output_path


def _apply_operation(document, operation: dict, caveat_messages: list[str]) -> None:
    operation_name = _operation_name(operation)
    if operation_name == "overlay_text":
        _apply_overlay_text(document, operation, caveat_messages)
        return
    if operation_name == "redact_region":
        _apply_redact_region(document, operation, caveat_messages)
        return
    if operation_name == "annotate_text_change":
        _apply_annotate_text_change(document, operation, caveat_messages)
        return
    raise NotImplementedError(f"Unsupported PDF operation '{operation_name}'.")


def _apply_overlay_text(document, operation: dict, caveat_messages: list[str]) -> None:
    fitz = _load_pymupdf()
    page = _resolve_page(document, operation)
    rect = _resolve_rect(operation, fitz=fitz, require_size=True)
    text = _require_non_empty_string(operation, "text")
    font_size = _require_positive_number(operation, "font_size", default=12.0)
    fill_color = _normalize_color(operation.get("fill_color") or operation.get("fill"))
    text_color = _normalize_color(operation.get("text_color") or operation.get("color"), default=(0.0, 0.0, 0.0))
    align = _normalize_alignment(operation.get("align", "left"))

    inserted = page.insert_textbox(
        rect,
        text,
        fontsize=font_size,
        fontname=_DEFAULT_FONT_NAME,
        color=text_color,
        fill=fill_color,
        align=align,
        overlay=True,
    )
    caveat_messages.append(_MANUAL_REVIEW_WARNING)
    if inserted < 0:
        caveat_messages.append(
            f"Overlay text on page {page.number + 1} may not fully fit the requested rectangle."
        )


def _apply_redact_region(document, operation: dict, caveat_messages: list[str]) -> None:
    fitz = _load_pymupdf()
    page = _resolve_page(document, operation)
    rect = _resolve_rect(operation, fitz=fitz, require_size=True)
    replacement_text = operation.get("replacement_text") or operation.get("text")
    font_size = _require_positive_number(operation, "font_size", default=11.0)
    fill_color = _normalize_color(operation.get("fill_color") or operation.get("fill"), default=(1.0, 1.0, 1.0))
    text_color = _normalize_color(operation.get("text_color") or operation.get("color"), default=(0.0, 0.0, 0.0))
    cross_out = bool(operation.get("cross_out", False))

    page.add_redact_annot(
        rect,
        text=str(replacement_text) if replacement_text is not None else None,
        fontname=_DEFAULT_FONT_NAME,
        fontsize=font_size,
        fill=fill_color,
        text_color=text_color,
        cross_out=cross_out,
    )
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_PIXELS,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
        text=fitz.PDF_REDACT_TEXT_REMOVE,
    )
    caveat_messages.append(_MANUAL_REVIEW_WARNING)
    caveat_messages.append(
        f"Redaction on page {page.number + 1} succeeded, but manual review is required to confirm hidden content and layout behavior."
    )


def _apply_annotate_text_change(document, operation: dict, caveat_messages: list[str]) -> None:
    fitz = _load_pymupdf()
    page = _resolve_page(document, operation)
    message = operation.get("message")
    if message is None:
        old_text = operation.get("old_text")
        new_text = operation.get("new_text")
        if old_text is not None and new_text is not None:
            message = f"Requested text change: '{old_text}' -> '{new_text}'"
        else:
            message = _require_non_empty_string(operation, "text")

    if "rect" in operation or _has_rect_fields(operation):
        rect = _resolve_rect(operation, fitz=fitz, require_size=True)
        annot = page.add_freetext_annot(
            rect,
            str(message),
            fontsize=_require_positive_number(operation, "font_size", default=11.0),
            text_color=_normalize_color(operation.get("text_color") or operation.get("color"), default=(0.0, 0.0, 0.0)),
            fill_color=_normalize_color(operation.get("fill_color"), default=(1.0, 1.0, 0.8)),
            border_color=_normalize_color(operation.get("border_color"), default=(0.2, 0.2, 0.2)),
        )
    else:
        point = _resolve_point(operation, fitz=fitz)
        annot = page.add_text_annot(point, str(message), icon=str(operation.get("icon", "Note")))
    annot.update()
    caveat_messages.append(_MANUAL_REVIEW_WARNING)
    caveat_messages.append(
        f"Annotation added on page {page.number + 1}; the original PDF content was not fully rewritten."
    )


def _apply_rebuild_operation(source: Path, output_path: Path, operation: dict) -> None:
    canvas_cls, pdfmetrics = _load_reportlab()
    pages = _normalize_rebuild_pages(source, operation)
    temp_output = _temporary_output_path(output_path)
    overflow_pages: list[int] = []

    pdf_canvas = canvas_cls(str(temp_output), pagesize=(pages[0]["width"], pages[0]["height"]))
    try:
        for page_index, page_data in enumerate(pages):
            pdf_canvas.setPageSize((page_data["width"], page_data["height"]))
            overflowed = _draw_rebuilt_page(
                pdf_canvas,
                text=page_data["text"],
                width=page_data["width"],
                height=page_data["height"],
                font_name=str(operation.get("font_name", _DEFAULT_REBUILD_FONT_NAME)),
                font_size=_require_positive_number(operation, "font_size", default=11.0),
                margin=_require_positive_number(operation, "margin", default=_DEFAULT_MARGIN),
                pdfmetrics=pdfmetrics,
            )
            if overflowed:
                overflow_pages.append(page_index + 1)
            if page_index != len(pages) - 1:
                pdf_canvas.showPage()
        pdf_canvas.save()
    except Exception:
        if temp_output.exists():
            temp_output.unlink()
        raise

    _replace_file(temp_output, output_path)
    if overflow_pages:
        overflow_text = ", ".join(str(page_number) for page_number in overflow_pages)
        warnings.warn(
            f"Rebuilt PDF text overflowed the available page area on page(s) {overflow_text}; content may be truncated.",
            RuntimeWarning,
            stacklevel=2,
        )


def _normalize_rebuild_pages(source: Path, operation: dict) -> list[dict]:
    source_pages = read(source)["pages"]
    requested_pages = operation.get("pages")
    page_texts = operation.get("page_texts")
    single_text = operation.get("text")

    if requested_pages is not None:
        if not isinstance(requested_pages, list) or not requested_pages:
            raise ValueError("PDF rebuild_text_pdf operation field 'pages' must be a non-empty list.")
        return _normalize_rebuild_page_entries(requested_pages, fallback_pages=source_pages)

    if page_texts is not None:
        if not isinstance(page_texts, list) or not page_texts:
            raise ValueError("PDF rebuild_text_pdf operation field 'page_texts' must be a non-empty list.")
        return _normalize_rebuild_page_entries(page_texts, fallback_pages=source_pages)

    if single_text is not None:
        return _normalize_rebuild_page_entries([single_text], fallback_pages=source_pages)

    return [
        {
            "text": page["text"],
            "width": float(page["width"]),
            "height": float(page["height"]),
        }
        for page in source_pages
    ]


def _normalize_rebuild_page_entries(entries: list, *, fallback_pages: list[dict]) -> list[dict]:
    normalized_pages: list[dict] = []
    for index, entry in enumerate(entries):
        fallback_page = fallback_pages[index] if index < len(fallback_pages) else None
        default_width = float(fallback_page["width"]) if fallback_page is not None else _DEFAULT_PAGE_WIDTH
        default_height = float(fallback_page["height"]) if fallback_page is not None else _DEFAULT_PAGE_HEIGHT

        if isinstance(entry, str):
            normalized_pages.append(
                {
                    "text": entry,
                    "width": default_width,
                    "height": default_height,
                }
            )
            continue

        if not isinstance(entry, dict):
            raise TypeError("PDF rebuild_text_pdf pages must be strings or dict objects.")

        text = str(entry.get("text", ""))
        width = _coerce_positive_float(entry.get("width", default_width), context="PDF rebuild page width")
        height = _coerce_positive_float(entry.get("height", default_height), context="PDF rebuild page height")
        normalized_pages.append({"text": text, "width": width, "height": height})

    return normalized_pages


def _draw_rebuilt_page(
    pdf_canvas,
    *,
    text: str,
    width: float,
    height: float,
    font_name: str,
    font_size: float,
    margin: float,
    pdfmetrics,
) -> bool:
    max_width = max(width - (margin * 2), 1)
    line_height = font_size * 1.25
    cursor_y = height - margin
    overflowed = False

    pdf_canvas.setFont(font_name, font_size)
    text_object = pdf_canvas.beginText(margin, cursor_y)
    text_object.setFont(font_name, font_size)

    paragraphs = text.splitlines() or [""]
    for paragraph in paragraphs:
        wrapped_lines = _wrap_text(paragraph, max_width=max_width, font_name=font_name, font_size=font_size, pdfmetrics=pdfmetrics)
        if not wrapped_lines:
            wrapped_lines = [""]
        for line in wrapped_lines:
            if cursor_y < margin:
                overflowed = True
                break
            text_object.textLine(line)
            cursor_y -= line_height
        if overflowed:
            break
        if paragraph == "":
            if cursor_y < margin:
                overflowed = True
                break
            text_object.textLine("")
            cursor_y -= line_height

    pdf_canvas.drawText(text_object)
    return overflowed


def _wrap_text(text: str, *, max_width: float, font_name: str, font_size: float, pdfmetrics) -> list[str]:
    if not text:
        return [""]

    wrapped_lines: list[str] = []
    for source_line in text.split("\n"):
        words = source_line.split()
        if not words:
            wrapped_lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
                continue
            wrapped_lines.extend(_split_long_token(current, max_width=max_width, font_name=font_name, font_size=font_size, pdfmetrics=pdfmetrics))
            current = word
        wrapped_lines.extend(_split_long_token(current, max_width=max_width, font_name=font_name, font_size=font_size, pdfmetrics=pdfmetrics))

    return wrapped_lines


def _split_long_token(text: str, *, max_width: float, font_name: str, font_size: float, pdfmetrics) -> list[str]:
    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return [text]

    chunks: list[str] = []
    current = ""
    for character in text:
        candidate = f"{current}{character}"
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            chunks.append(current)
            current = character
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _save_document(document, output_path: Path, load_path: Path) -> None:
    if _paths_refer_to_same_location(output_path, load_path):
        temp_output = _temporary_output_path(output_path)
        try:
            document.save(temp_output, garbage=4, deflate=True)
        except Exception:
            if temp_output.exists():
                temp_output.unlink()
            raise
        document.close()
        _replace_file(temp_output, output_path)
        return

    document.save(output_path, garbage=4, deflate=True)
    document.close()


def _replace_file(temp_output: Path, final_output: Path) -> None:
    try:
        shutil.move(str(temp_output), str(final_output))
    finally:
        if temp_output.exists():
            temp_output.unlink()


def _resolve_page(document, operation: dict):
    if "page_index" in operation:
        page_index = _require_non_negative_int(operation, "page_index")
    elif "page_number" in operation:
        page_number = _require_positive_int(operation, "page_number")
        page_index = page_number - 1
    else:
        raise ValueError("PDF edit operations must include 'page_index' or 'page_number'.")

    if page_index >= document.page_count:
        raise IndexError(
            f"PDF page target {page_index} is out of range for a document with {document.page_count} pages."
        )
    return document.load_page(page_index)


def _resolve_rect(operation: dict, *, fitz, require_size: bool) -> object:
    rect_value = operation.get("rect")
    if rect_value is not None:
        return _coerce_rect(rect_value, fitz=fitz)

    if {"x0", "y0", "x1", "y1"}.issubset(operation):
        return _coerce_rect(
            [operation["x0"], operation["y0"], operation["x1"], operation["y1"]],
            fitz=fitz,
        )

    if {"x", "y", "width", "height"}.issubset(operation):
        x = _coerce_float(operation["x"], context="PDF rectangle x")
        y = _coerce_float(operation["y"], context="PDF rectangle y")
        width = _coerce_positive_float(operation["width"], context="PDF rectangle width")
        height = _coerce_positive_float(operation["height"], context="PDF rectangle height")
        return fitz.Rect(x, y, x + width, y + height)

    if require_size:
        raise ValueError(
            "PDF edit operation requires a rectangle via 'rect', ['x0','y0','x1','y1'], or ['x','y','width','height']."
        )
    raise ValueError("PDF edit operation could not resolve a rectangle target.")


def _coerce_rect(value, *, fitz):
    if isinstance(value, dict):
        if {"x0", "y0", "x1", "y1"}.issubset(value):
            coordinates = [value["x0"], value["y0"], value["x1"], value["y1"]]
        elif {"left", "top", "right", "bottom"}.issubset(value):
            coordinates = [value["left"], value["top"], value["right"], value["bottom"]]
        elif {"x", "y", "width", "height"}.issubset(value):
            x = _coerce_float(value["x"], context="PDF rectangle x")
            y = _coerce_float(value["y"], context="PDF rectangle y")
            width = _coerce_positive_float(value["width"], context="PDF rectangle width")
            height = _coerce_positive_float(value["height"], context="PDF rectangle height")
            return fitz.Rect(x, y, x + width, y + height)
        else:
            raise ValueError("PDF rectangle dict must provide x0/y0/x1/y1, left/top/right/bottom, or x/y/width/height.")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 4:
        coordinates = list(value)
    else:
        raise TypeError("PDF rectangle must be a dict or a 4-item sequence.")

    x0, y0, x1, y1 = (_coerce_float(item, context="PDF rectangle coordinate") for item in coordinates)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("PDF rectangle coordinates must define a positive-area region.")
    return fitz.Rect(x0, y0, x1, y1)


def _resolve_point(operation: dict, *, fitz):
    if "point" in operation:
        value = operation["point"]
        if isinstance(value, dict):
            if not {"x", "y"}.issubset(value):
                raise ValueError("PDF point dict must contain 'x' and 'y'.")
            x = _coerce_float(value["x"], context="PDF point x")
            y = _coerce_float(value["y"], context="PDF point y")
            return fitz.Point(x, y)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 2:
            x = _coerce_float(value[0], context="PDF point x")
            y = _coerce_float(value[1], context="PDF point y")
            return fitz.Point(x, y)
        raise TypeError("PDF point must be a dict or a 2-item sequence.")

    if {"x", "y"}.issubset(operation):
        x = _coerce_float(operation["x"], context="PDF point x")
        y = _coerce_float(operation["y"], context="PDF point y")
        return fitz.Point(x, y)

    raise ValueError("PDF annotation operation requires 'point' or both 'x' and 'y'.")


def _normalize_alignment(value) -> int:
    mapping = {"left": 0, "center": 1, "centre": 1, "right": 2, "justify": 3}
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in mapping:
            return mapping[normalized]
    raise ValueError("PDF text alignment must be one of: left, center, right, justify.")


def _normalize_color(value, *, default: tuple[float, float, float] | None = None):
    if value is None:
        return default
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise TypeError("PDF colors must be 3-item RGB sequences.")
    channels: list[float] = []
    for channel in value:
        numeric = _coerce_float(channel, context="PDF color channel")
        if numeric > 1.0:
            numeric = numeric / 255.0
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError("PDF color channels must be between 0 and 1, or between 0 and 255.")
        channels.append(numeric)
    return tuple(channels)


def _operation_name(operation: dict) -> str:
    operation_name = operation.get("type") or operation.get("operation") or operation.get("op")
    if not isinstance(operation_name, str) or not operation_name.strip():
        raise ValueError("PDF edit operations must include a non-empty operation name.")
    return operation_name.strip()


def _validate_pdf_path(file_path: str | PathLike[str] | Path, *, label: str) -> Path:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"{label} '{path}' does not exist.")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} '{path}' is not a regular file.")
    _validate_pdf_extension(path, label=label)
    return path


def _validate_pdf_extension(path: Path, *, label: str) -> None:
    if path.suffix.lower() != _SUPPORTED_EXTENSION:
        display_extension = path.suffix.lower().lstrip(".") or "<none>"
        raise ValueError(
            f"{label} '{path}' has unsupported extension '{display_extension}'. Supported extension: pdf."
        )


def _reject_encrypted_document(document, source: Path) -> None:
    if getattr(document, "needs_pass", False):
        raise NotImplementedError(
            f"Encrypted PDF files are outside PDF V1 runtime scope: '{source}'."
        )


def _normalize_metadata(metadata: dict) -> dict:
    normalized: dict[str, str | None] = {}
    for key, value in metadata.items():
        normalized[str(key).lstrip("/")] = None if value in (None, "") else str(value)
    return normalized


def _deduplicate_messages(messages: Iterable[str]) -> list[str]:
    deduplicated: list[str] = []
    seen: set[str] = set()
    for message in messages:
        if not isinstance(message, str):
            continue
        normalized = message.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(normalized)
    return deduplicated


def _has_rect_fields(operation: dict) -> bool:
    return bool(
        {"x0", "y0", "x1", "y1"}.issubset(operation)
        or {"x", "y", "width", "height"}.issubset(operation)
    )


def _paths_refer_to_same_location(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve(strict=False)


def _temporary_output_path(output_path: Path) -> Path:
    return output_path.with_name(
        f".{output_path.stem}.tmp-{uuid.uuid4().hex}{output_path.suffix}"
    )


def _require_non_empty_string(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"PDF field '{field}' must be a non-empty string.")
    return value


def _require_positive_number(payload: dict, field: str, *, default: float) -> float:
    value = payload.get(field, default)
    return _coerce_positive_float(value, context=f"PDF field '{field}'")


def _require_non_negative_int(payload: dict, field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"PDF field '{field}' must be a non-negative integer.")
    return value


def _require_positive_int(payload: dict, field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"PDF field '{field}' must be a positive integer.")
    return value


def _coerce_float(value, *, context: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{context} must be numeric.") from exc


def _coerce_positive_float(value, *, context: str) -> float:
    numeric = _coerce_float(value, context=context)
    if numeric <= 0:
        raise ValueError(f"{context} must be greater than 0.")
    return numeric


def _load_pymupdf():
    try:
        import fitz
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment.
        raise ModuleNotFoundError(
            "PyMuPDF is required for PDF operations. Install the office-automation 'pdf' dependencies."
        ) from exc
    return fitz


def _load_pdfplumber():
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment.
        raise ModuleNotFoundError(
            "pdfplumber is required for PDF read operations. Install the office-automation 'pdf' dependencies."
        ) from exc
    return pdfplumber


def _load_reportlab():
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfgen.canvas import Canvas
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment.
        raise ModuleNotFoundError(
            "reportlab is required for PDF rebuild operations. Install the office-automation 'pdf' dependencies."
        ) from exc
    return Canvas, pdfmetrics
