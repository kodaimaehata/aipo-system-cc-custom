from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
import warnings


_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNTIME_SRC = _REPO_ROOT / "tools" / "office-automation" / "src"
if str(_RUNTIME_SRC) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_SRC))

from office_automation import excel_ops, pdf_ops, powerpoint_ops, word_ops  # noqa: E402


_SUPPORTED_EXTENSIONS = {
    "xlsx": excel_ops,
    "xlsm": excel_ops,
    "docx": word_ops,
    "pptx": powerpoint_ops,
    "pdf": pdf_ops,
}
_STATUS_LABELS = {
    0: "success",
    1: "unsupported_scope",
    2: "success_with_warnings",
    3: "fatal_error",
}
_UNSUPPORTED_EXTENSION_MESSAGES = {
    "xls": "V1 does not support '.xls'. Convert the workbook to '.xlsx' or '.xlsm' before using office-python.",
    "xlsb": "V1 does not support '.xlsb'. Convert the workbook to '.xlsx' or '.xlsm' before using office-python.",
    "doc": "V1 does not support '.doc'. Convert the document to '.docx' before using office-python.",
    "ppt": "V1 does not support '.ppt'. Convert the presentation to '.pptx' before using office-python.",
}
_MACRO_SCOPE_TOKENS = ("macro", "macros", "vba")
_TRACK_CHANGE_TOKENS = (
    "accept_track_changes",
    "reject_track_changes",
    "cleanup_track_changes",
    "track_changes",
    "track changes",
)
_WORD_TEXTBOX_TOKENS = ("text_box", "text_boxes", "text box", "textbox")
_SMARTART_TOKENS = ("smartart", "smart_art", "smart art", "diagram")
_ANIMATION_TOKENS = ("animation", "animations", "timing")
_EMBEDDED_OBJECT_TOKENS = (
    "embedded_object",
    "embedded_objects",
    "embedded object",
    "embedded file",
    "ole",
)
_OCR_TOKENS = ("ocr", "tesseract")
_PDF_FIDELITY_TOKENS = (
    "exact_fidelity",
    "full_fidelity",
    "perfect_fidelity",
    "exact fidelity",
    "full fidelity",
    "perfect fidelity",
    "exact reflow",
    "preserve vector",
    "vector rewrite",
    "lossless pdf",
)
_SELECTOR_KEYS = {"op", "operation", "type", "mode", "request", "goal", "description", "requirements", "constraint"}


class UnsupportedScopeError(ValueError):
    """Raised when the wrapper rejects an unsupported V1 request before runtime handoff."""


def run(
    *,
    file_path: str | Path,
    mode: str,
    instructions: Mapping | None = None,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    copy_before_edit: bool | None = None,
) -> dict:
    return run_request(
        {
            "file_path": file_path,
            "mode": mode,
            "instructions": instructions,
            "output_path": output_path,
            "output_dir": output_dir,
            "copy_before_edit": copy_before_edit,
        }
    )


def run_request(request: Mapping) -> dict:
    detected_format: str | None = None
    mode: str | None = None
    source_path: Path | None = None

    try:
        normalized = _normalize_request(request)
        source_path = normalized["source_path"]
        detected_format = normalized["extension"]
        mode = normalized["mode"]
        runtime_module = _SUPPORTED_EXTENSIONS[detected_format]

        if mode == "read":
            return _execute_read(
                runtime_module=runtime_module,
                source_path=source_path,
                detected_format=detected_format,
            )

        return _execute_edit(
            runtime_module=runtime_module,
            source_path=source_path,
            detected_format=detected_format,
            wrapper_request=normalized,
        )
    except UnsupportedScopeError as exc:
        return _result(
            status=1,
            file_path=str(source_path) if source_path is not None else _safe_request_path(request),
            detected_format=detected_format,
            mode=mode,
            message=str(exc),
        )
    except Exception as exc:
        return _result(
            status=3,
            file_path=str(source_path) if source_path is not None else _safe_request_path(request),
            detected_format=detected_format,
            mode=mode,
            message=str(exc),
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        )


def _normalize_request(request: Mapping) -> dict:
    if not isinstance(request, Mapping):
        raise TypeError("office-python wrapper request must be a mapping.")

    source_path = _coerce_required_path(request.get("file_path"), field_name="file_path")
    _validate_source_path(source_path)

    extension = _path_extension(source_path)
    if extension in _UNSUPPORTED_EXTENSION_MESSAGES:
        raise UnsupportedScopeError(_UNSUPPORTED_EXTENSION_MESSAGES[extension])
    if extension not in _SUPPORTED_EXTENSIONS:
        supported_text = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        display_extension = extension or "<none>"
        raise UnsupportedScopeError(
            f"office-python V1 supports only {supported_text}. Received unsupported extension '{display_extension}'."
        )

    mode = request.get("mode")
    if not isinstance(mode, str) or mode not in {"read", "edit"}:
        raise ValueError("office-python wrapper mode must be 'read' or 'edit'.")

    instructions = request.get("instructions")
    output_path = _coerce_optional_path(request.get("output_path"), field_name="output_path")
    output_dir = _coerce_optional_path(request.get("output_dir"), field_name="output_dir")
    copy_before_edit = request.get("copy_before_edit")
    if copy_before_edit is None:
        copy_before_edit = True if mode == "edit" else False
    elif not isinstance(copy_before_edit, bool):
        raise TypeError("office-python wrapper field 'copy_before_edit' must be a boolean when provided.")

    if mode == "read":
        if instructions is not None:
            raise ValueError("Read requests must not include edit instructions.")
        if output_path is not None or output_dir is not None or copy_before_edit:
            raise ValueError(
                "Read requests must not include edit-only save controls such as output_path, output_dir, or copy_before_edit=True."
            )
        return {
            "source_path": source_path,
            "extension": extension,
            "mode": mode,
        }

    if not isinstance(instructions, Mapping):
        raise ValueError("Edit requests must include structured instruction data as a mapping.")

    normalized_instructions = dict(instructions)
    operations = normalized_instructions.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError("Edit instructions must include a non-empty 'operations' list.")
    if not all(isinstance(operation, Mapping) for operation in operations):
        raise TypeError("Each edit operation must be a mapping.")

    options = normalized_instructions.get("options", {})
    if not isinstance(options, Mapping):
        raise TypeError("Edit instructions field 'options' must be a mapping when provided.")
    normalized_instructions["options"] = dict(options)

    _reject_unsupported_scope(extension=extension, instructions=normalized_instructions)

    resolved_output_path = _resolve_output_path(
        source_path=source_path,
        extension=extension,
        requested_output_path=output_path,
        requested_output_dir=output_dir,
        copy_before_edit=copy_before_edit,
    )

    normalized_instructions["output_path"] = str(resolved_output_path)
    normalized_instructions["output_dir"] = str(output_dir) if output_dir is not None else None
    normalized_instructions["copy_before_edit"] = copy_before_edit

    return {
        "source_path": source_path,
        "extension": extension,
        "mode": mode,
        "instructions": normalized_instructions,
        "resolved_output_path": resolved_output_path,
        "requested_output_dir": output_dir,
        "copy_before_edit": copy_before_edit,
    }


def _execute_read(*, runtime_module, source_path: Path, detected_format: str) -> dict:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        runtime_result = runtime_module.read(source_path)

    manual_review_notes = _collect_manual_review_notes(runtime_result, caught)
    status = 2 if manual_review_notes else 0
    result_shape = _read_result_shape(detected_format, runtime_result)
    message = "Read completed successfully."
    if manual_review_notes:
        message = "Read completed with caveats that may affect interpretation."

    return _result(
        status=status,
        file_path=str(source_path),
        detected_format=detected_format,
        mode="read",
        message=message,
        manual_review_notes=manual_review_notes,
        summary={
            "result_shape": result_shape,
        },
        data=runtime_result,
    )


def _execute_edit(*, runtime_module, source_path: Path, detected_format: str, wrapper_request: dict) -> dict:
    instructions = wrapper_request["instructions"]
    resolved_output_path = wrapper_request["resolved_output_path"]
    copy_before_edit = wrapper_request["copy_before_edit"]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        saved_path = runtime_module.edit(source_path, instructions)

    saved_path = Path(saved_path)
    manual_review_notes = _collect_manual_review_notes(None, caught)
    status = 2 if manual_review_notes else 0
    attempted_operations = [_summarize_operation(operation) for operation in instructions.get("operations", [])]
    preserved_original = not _paths_refer_to_same_location(source_path, saved_path)
    message = "Edit completed successfully."
    if manual_review_notes:
        message = "Edit completed, but manual review is recommended."

    return _result(
        status=status,
        file_path=str(source_path),
        detected_format=detected_format,
        mode="edit",
        message=message,
        output_path=str(saved_path),
        manual_review_notes=manual_review_notes,
        summary={
            "resolved_output_path": str(resolved_output_path),
            "preserved_original": preserved_original,
            "copy_before_edit": copy_before_edit,
            "attempted_operations": attempted_operations,
        },
    )


def _reject_unsupported_scope(*, extension: str, instructions: Mapping) -> None:
    findings = _find_scope_signals(instructions)

    if findings["embedded_object"]:
        raise UnsupportedScopeError(
            "Embedded-object handling is outside office-python V1 scope. Edit the surrounding supported file content instead."
        )
    if findings["ocr"]:
        raise UnsupportedScopeError(
            "External OCR-dependent flows are outside office-python V1 scope. Use files that already contain an extractable text layer."
        )
    if findings["macro_or_vba"]:
        raise UnsupportedScopeError(
            "VBA and macro editing are outside office-python V1 scope. Workbook-level xlsx/xlsm edits are supported, but macro authoring is not."
        )
    if extension == "docx" and findings["track_changes"]:
        raise UnsupportedScopeError(
            "Word track-changes cleanup is outside office-python V1 scope. Use body paragraph or table edits instead."
        )
    if extension == "docx" and findings["word_textbox"]:
        raise UnsupportedScopeError(
            "Word text-box-specific editing is outside office-python V1 scope. Use body paragraph or table edits instead."
        )
    if extension == "pptx" and findings["smartart"]:
        raise UnsupportedScopeError(
            "PowerPoint SmartArt-specific editing is outside office-python V1 scope. Edit regular slide text or tables instead."
        )
    if extension == "pptx" and findings["animation"]:
        raise UnsupportedScopeError(
            "PowerPoint advanced animation rewriting is outside office-python V1 scope. Edit regular slide text, titles, or tables instead."
        )
    if extension == "pdf" and findings["pdf_exact_fidelity"]:
        raise UnsupportedScopeError(
            "office-python PDF edits do not promise exact-fidelity reflow or vector rewriting. Use supported overlay, annotation, redaction, or rebuild flows with manual review."
        )


def _find_scope_signals(payload: object) -> dict[str, bool]:
    signals = {
        "macro_or_vba": False,
        "track_changes": False,
        "word_textbox": False,
        "smartart": False,
        "animation": False,
        "embedded_object": False,
        "ocr": False,
        "pdf_exact_fidelity": False,
    }

    def visit(node: object, *, key_hint: str | None = None) -> None:
        if isinstance(node, Mapping):
            for raw_key, value in node.items():
                key_text = _normalize_text(raw_key)
                _mark_signal_from_text(signals, key_text)
                should_inspect_value = key_text in _SELECTOR_KEYS or any(
                    token in key_text
                    for token in (
                        *_MACRO_SCOPE_TOKENS,
                        *_TRACK_CHANGE_TOKENS,
                        *_WORD_TEXTBOX_TOKENS,
                        *_SMARTART_TOKENS,
                        *_ANIMATION_TOKENS,
                        *_EMBEDDED_OBJECT_TOKENS,
                        *_OCR_TOKENS,
                    )
                )
                if should_inspect_value or isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
                    visit(value, key_hint=key_text)
            return

        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            for item in node:
                visit(item, key_hint=key_hint)
            return

        if isinstance(node, str):
            if key_hint in _SELECTOR_KEYS or key_hint is None:
                _mark_signal_from_text(signals, _normalize_text(node))
            return

        if isinstance(node, bool) and node and key_hint:
            _mark_signal_from_text(signals, key_hint)

    visit(payload)
    return signals


def _mark_signal_from_text(signals: dict[str, bool], text: str) -> None:
    if any(token in text for token in _MACRO_SCOPE_TOKENS):
        signals["macro_or_vba"] = True
    if any(token in text for token in _TRACK_CHANGE_TOKENS):
        signals["track_changes"] = True
    if any(token in text for token in _WORD_TEXTBOX_TOKENS):
        signals["word_textbox"] = True
    if any(token in text for token in _SMARTART_TOKENS):
        signals["smartart"] = True
    if any(token in text for token in _ANIMATION_TOKENS):
        signals["animation"] = True
    if any(token in text for token in _EMBEDDED_OBJECT_TOKENS):
        signals["embedded_object"] = True
    if any(token in text for token in _OCR_TOKENS):
        signals["ocr"] = True
    if any(token in text for token in _PDF_FIDELITY_TOKENS):
        signals["pdf_exact_fidelity"] = True


def _resolve_output_path(
    *,
    source_path: Path,
    extension: str,
    requested_output_path: Path | None,
    requested_output_dir: Path | None,
    copy_before_edit: bool,
) -> Path:
    if requested_output_path is not None:
        resolved_output_path = requested_output_path
        if _path_extension(resolved_output_path) != extension:
            raise ValueError(
                f"Output path '{resolved_output_path}' must keep the source '.{extension}' extension."
            )
        if copy_before_edit and _paths_refer_to_same_location(source_path, resolved_output_path):
            raise ValueError(
                "Edit requests cannot preserve the original when output_path points to the source file and copy_before_edit is True."
            )
        if resolved_output_path.exists() and not _paths_refer_to_same_location(source_path, resolved_output_path):
            raise FileExistsError(
                f"Explicit output path '{resolved_output_path}' already exists. Choose a new destination or remove the existing file first."
            )
        return resolved_output_path

    base_candidate = _default_output_candidate(source_path=source_path, output_dir=requested_output_dir)
    return _make_collision_safe_candidate(source_path, base_candidate)


def _default_output_candidate(*, source_path: Path, output_dir: Path | None) -> Path:
    filename = f"{source_path.stem}-edited{source_path.suffix}"
    if output_dir is not None:
        return output_dir / filename
    return source_path.with_name(filename)


def _make_collision_safe_candidate(source_path: Path, candidate: Path) -> Path:
    if not candidate.exists() and not _paths_refer_to_same_location(source_path, candidate):
        return candidate

    index = 2
    while True:
        indexed_candidate = candidate.with_name(f"{candidate.stem}-{index}{candidate.suffix}")
        if not indexed_candidate.exists() and not _paths_refer_to_same_location(source_path, indexed_candidate):
            return indexed_candidate
        index += 1


def _collect_manual_review_notes(runtime_result: Mapping | None, caught_warnings: Sequence[warnings.WarningMessage]) -> list[str]:
    notes: list[str] = []
    if isinstance(runtime_result, Mapping):
        runtime_warnings = runtime_result.get("warnings")
        if isinstance(runtime_warnings, Sequence) and not isinstance(runtime_warnings, (str, bytes, bytearray)):
            notes.extend(str(item).strip() for item in runtime_warnings if str(item).strip())

    notes.extend(str(item.message).strip() for item in caught_warnings if str(item.message).strip())
    return _deduplicate_preserving_order(notes)


def _read_result_shape(detected_format: str, runtime_result: Mapping) -> dict:
    if detected_format in {"xlsx", "xlsm"}:
        return {
            "sheet_count": runtime_result.get("sheet_count"),
            "sheet_names": runtime_result.get("sheet_names"),
        }
    if detected_format == "docx":
        return {
            "paragraph_count": len(runtime_result.get("paragraphs", [])),
            "table_count": len(runtime_result.get("tables", [])),
            "body_item_count": len(runtime_result.get("body", [])),
        }
    if detected_format == "pptx":
        return {
            "slide_count": runtime_result.get("slide_count"),
        }
    if detected_format == "pdf":
        return {
            "page_count": runtime_result.get("page_count"),
        }
    return {}


def _summarize_operation(operation: Mapping) -> str:
    operation_name = operation.get("op") or operation.get("type") or operation.get("operation") or "<unknown>"
    operation_name = str(operation_name)

    if operation_name == "set_cell":
        return f"set_cell({operation.get('sheet', '?')}!{operation.get('cell', '?')})"
    if operation_name == "clear_cell":
        return f"clear_cell({operation.get('sheet', '?')}!{operation.get('cell', '?')})"
    if operation_name in {"replace_title_text", "replace_shape_text"}:
        slide_ref = operation.get("slide_number")
        if slide_ref is None and operation.get("slide_index") is not None:
            slide_ref = int(operation["slide_index"]) + 1
        return f"{operation_name}(slide={slide_ref if slide_ref is not None else '?'})"
    if operation_name in {"replace_table_cell", "append_table_row"} and (
        operation.get("slide_number") is not None or operation.get("slide_index") is not None
    ):
        slide_ref = operation.get("slide_number")
        if slide_ref is None and operation.get("slide_index") is not None:
            slide_ref = int(operation["slide_index"]) + 1
        return f"{operation_name}(slide={slide_ref if slide_ref is not None else '?'})"
    if operation_name in {"overlay_text", "redact_region", "annotate_text_change", "rebuild_text_pdf"}:
        page_ref = operation.get("page_number")
        if page_ref is None and operation.get("page_index") is not None:
            page_ref = int(operation["page_index"]) + 1
        if page_ref is None:
            return operation_name
        return f"{operation_name}(page={page_ref})"
    if operation_name == "replace_paragraph_text":
        return f"replace_paragraph_text(paragraph={operation.get('paragraph_index', '?')})"
    if operation_name == "insert_paragraph_after":
        return f"insert_paragraph_after(paragraph={operation.get('paragraph_index', '?')})"
    if operation_name == "delete_paragraph":
        return f"delete_paragraph(paragraph={operation.get('paragraph_index', '?')})"
    if operation_name in {"replace_table_cell", "append_table_row", "update_table_row"}:
        return f"{operation_name}(table={operation.get('table_index', '?')})"
    return operation_name


def _result(
    *,
    status: int,
    file_path: str | None,
    detected_format: str | None,
    mode: str | None,
    message: str,
    output_path: str | None = None,
    manual_review_notes: Sequence[str] | None = None,
    summary: Mapping | None = None,
    data: object | None = None,
    error: Mapping | None = None,
) -> dict:
    return {
        "status": status,
        "status_label": _STATUS_LABELS[status],
        "message": message,
        "file_path": file_path,
        "detected_format": detected_format,
        "mode": mode,
        "output_path": output_path,
        "manual_review_notes": list(manual_review_notes or []),
        "summary": dict(summary or {}),
        "data": data,
        "error": dict(error or {}) if error is not None else None,
    }


def _coerce_required_path(value: object, *, field_name: str) -> Path:
    path = _coerce_optional_path(value, field_name=field_name)
    if path is None:
        raise ValueError(f"office-python wrapper field '{field_name}' is required.")
    return path


def _coerce_optional_path(value: object, *, field_name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"office-python wrapper field '{field_name}' cannot be empty.")
        return Path(value)
    raise TypeError(f"office-python wrapper field '{field_name}' must be a string or Path when provided.")


def _validate_source_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Source file '{path}' does not exist.")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Source file '{path}' is not a regular file.")


def _path_extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _paths_refer_to_same_location(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve(strict=False)


def _normalize_text(value: object) -> str:
    return str(value).strip().lower().replace("-", "_")


def _safe_request_path(request: Mapping) -> str | None:
    value = request.get("file_path") if isinstance(request, Mapping) else None
    return str(value) if value is not None else None


def _deduplicate_preserving_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
