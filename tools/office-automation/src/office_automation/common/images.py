"""Shared image extraction and replacement helpers for supported V1 formats."""

from __future__ import annotations

from io import BytesIO
from os import PathLike
from pathlib import Path
import shutil
import zipfile

import fitz
from PIL import Image, UnidentifiedImageError

__all__ = ["extract_images", "replace_image"]

_SUPPORTED_EXTENSIONS = frozenset({"xlsx", "xlsm", "docx", "pptx", "pdf"})
_SUPPORTED_EXTENSIONS_TEXT = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
_OFFICE_MEDIA_PREFIX = {
    "xlsx": "xl/media/",
    "xlsm": "xl/media/",
    "docx": "word/media/",
    "pptx": "ppt/media/",
}
_RASTER_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff"})
_PILLOW_SAVE_FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "gif": "GIF",
    "bmp": "BMP",
    "tif": "TIFF",
    "tiff": "TIFF",
}


def extract_images(file_path: str | PathLike[str] | Path, output_dir: str | PathLike[str] | Path) -> list[Path]:
    """Extract directly addressable raster images in deterministic order.

    Index contract:
    - Office packages: zero-based order of sorted media part names under the package media folder.
    - PDFs: zero-based order of raster image occurrences in page order, then image order within each page.
    """
    source = _validate_source_path(file_path, label="Image source file")
    destination = _prepare_output_directory(output_dir)
    extension = _path_extension(source)

    if extension == "pdf":
        slots = _list_pdf_image_slots(source)
    else:
        slots = _list_office_image_slots(source)

    extracted_paths: list[Path] = []
    for image_index, slot in enumerate(slots):
        output_path = destination / f"{source.stem}-image-{image_index:04d}.{slot['extension']}"
        output_path.write_bytes(slot["bytes"])
        extracted_paths.append(output_path)
    return extracted_paths


def replace_image(
    file_path: str | PathLike[str] | Path,
    image_index: int,
    replacement: str | PathLike[str] | Path,
) -> None:
    """Replace a previously indexed image slot in place."""
    source = _validate_source_path(file_path, label="Image source file")
    normalized_index = _validate_image_index(image_index)
    extension = _path_extension(source)

    if extension == "pdf":
        slot = _resolve_image_slot(_list_pdf_image_slots(source), image_index=normalized_index, path=source)
        replacement_image = _load_replacement_image(replacement)
        _replace_pdf_image(source, normalized_index, slot, replacement_image)
        return
    slot = _resolve_image_slot(_list_office_image_slots(source), image_index=normalized_index, path=source)
    replacement_image = _load_replacement_image(replacement)
    _replace_office_image(source, normalized_index, slot, replacement_image)


def _list_office_image_slots(path: Path) -> list[dict[str, object]]:
    extension = _path_extension(path)
    media_prefix = _OFFICE_MEDIA_PREFIX[extension]
    try:
        with zipfile.ZipFile(path) as archive:
            media_names = sorted(
                (
                    info.filename
                    for info in archive.infolist()
                    if info.filename.startswith(media_prefix)
                    and _is_supported_raster_extension(Path(info.filename).suffix)
                ),
                key=_archive_name_sort_key,
            )
            return [
                {
                    "archive_name": media_name,
                    "extension": _normalize_image_extension(Path(media_name).suffix),
                    "bytes": archive.read(media_name),
                }
                for media_name in media_names
            ]
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Office file '{path}' is not a valid Open XML package.") from exc


def _list_pdf_image_slots(path: Path) -> list[dict[str, object]]:
    document = fitz.open(path)
    try:
        _reject_encrypted_pdf(document, path)
        slots: list[dict[str, object]] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            for page_image_index, image_info in enumerate(page.get_image_info(xrefs=True)):
                xref = int(image_info["xref"])
                extracted = document.extract_image(xref)
                extension = _normalize_image_extension(f".{extracted.get('ext', '')}")
                if extension not in _RASTER_EXTENSIONS:
                    continue
                slots.append(
                    {
                        "page_index": page_index,
                        "page_image_index": page_image_index,
                        "xref": xref,
                        "extension": extension,
                        "bytes": extracted["image"],
                    }
                )
        return slots
    finally:
        document.close()


def _replace_office_image(
    path: Path,
    image_index: int,
    slot: dict[str, object],
    replacement_image: dict[str, object],
) -> None:
    target_extension = str(slot["extension"])
    if target_extension not in _PILLOW_SAVE_FORMATS:
        raise NotImplementedError(
            f"Office image slot {image_index} in '{path}' uses unsupported raster type '{target_extension}'."
        )

    rendered_bytes = _render_replacement_bytes(replacement_image, target_extension=target_extension)
    _rewrite_zip_member(path, archive_name=str(slot["archive_name"]), replacement_bytes=rendered_bytes)


def _replace_pdf_image(
    path: Path,
    image_index: int,
    slot: dict[str, object],
    replacement_image: dict[str, object],
) -> None:
    slots = _list_pdf_image_slots(path)
    xref = int(slot["xref"])
    occurrence_count = sum(1 for candidate in slots if int(candidate["xref"]) == xref)
    if occurrence_count > 1:
        raise NotImplementedError(
            "PDF image replacement only supports uniquely addressed raster image objects. "
            f"Image slot {image_index} in '{path}' shares xref {xref} with {occurrence_count} occurrences."
        )

    document = fitz.open(path)
    temp_output = _temporary_output_path(path)
    try:
        _reject_encrypted_pdf(document, path)
        page = document.load_page(int(slot["page_index"]))
        page.replace_image(xref, stream=_render_replacement_bytes(replacement_image, target_extension="png"))
        document.save(temp_output, garbage=4, deflate=True)
    except Exception as exc:  # pragma: no cover - PyMuPDF failures vary by file and image type.
        if temp_output.exists():
            temp_output.unlink()
        raise ValueError(f"Failed to replace PDF image slot {image_index} in '{path}': {exc}") from exc
    finally:
        if not document.is_closed:
            document.close()

    _replace_file(temp_output, path)


def _rewrite_zip_member(path: Path, *, archive_name: str, replacement_bytes: bytes) -> None:
    temp_output = _temporary_output_path(path)
    try:
        with zipfile.ZipFile(path) as source_archive, zipfile.ZipFile(temp_output, "w") as target_archive:
            found = False
            for info in source_archive.infolist():
                payload = replacement_bytes if info.filename == archive_name else source_archive.read(info.filename)
                if info.filename == archive_name:
                    found = True
                target_archive.writestr(info, payload)
    except Exception:
        if temp_output.exists():
            temp_output.unlink()
        raise

    if not found:
        if temp_output.exists():
            temp_output.unlink()
        raise ValueError(f"Archive member '{archive_name}' was not found in '{path}'.")

    _replace_file(temp_output, path)


def _resolve_image_slot(slots: list[dict[str, object]], *, image_index: int, path: Path) -> dict[str, object]:
    if image_index >= len(slots):
        raise IndexError(
            f"Image index {image_index} is out of range for '{path}'. Available image count: {len(slots)}."
        )
    return slots[image_index]


def _load_replacement_image(path_value: str | PathLike[str] | Path) -> dict[str, object]:
    path = _coerce_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Replacement image '{path}' does not exist.")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Replacement image '{path}' is not a regular file.")

    try:
        with Image.open(path) as image:
            image.load()
            return {
                "path": path,
                "image": image.copy(),
            }
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Replacement image '{path}' is not a readable image file.") from exc


def _render_replacement_bytes(replacement_image: dict[str, object], *, target_extension: str) -> bytes:
    image = replacement_image["image"]
    save_format = _PILLOW_SAVE_FORMATS[target_extension]
    prepared = image
    if save_format == "JPEG" and prepared.mode not in {"RGB", "L"}:
        prepared = prepared.convert("RGB")
    elif save_format in {"PNG", "GIF", "TIFF", "BMP"} and prepared.mode == "P":
        prepared = prepared.convert("RGBA")

    buffer = BytesIO()
    prepared.save(buffer, format=save_format)
    return buffer.getvalue()


def _prepare_output_directory(path_value: str | PathLike[str] | Path) -> Path:
    path = _coerce_path(path_value)
    if path.exists() and not path.is_dir():
        raise NotADirectoryError(f"Image output directory '{path}' is not a directory.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_source_path(file_path: str | PathLike[str] | Path, *, label: str) -> Path:
    path = _coerce_path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"{label} '{path}' does not exist.")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} '{path}' is not a regular file.")

    extension = _path_extension(path)
    if extension not in _SUPPORTED_EXTENSIONS:
        display_extension = extension or "<none>"
        raise ValueError(
            f"{label} '{path}' has unsupported extension '{display_extension}'. "
            f"Supported extensions: {_SUPPORTED_EXTENSIONS_TEXT}."
        )
    return path


def _validate_image_index(image_index: int) -> int:
    if isinstance(image_index, bool) or not isinstance(image_index, int) or image_index < 0:
        raise ValueError("image_index must be a zero-based non-negative integer.")
    return image_index


def _reject_encrypted_pdf(document, path: Path) -> None:
    if getattr(document, "needs_pass", False):
        raise NotImplementedError(f"Encrypted PDF files are outside image-helper V1 scope: '{path}'.")


def _coerce_path(value: str | PathLike[str] | Path) -> Path:
    return Path(value)


def _path_extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _normalize_image_extension(value: str) -> str:
    return value.lower().lstrip(".")


def _is_supported_raster_extension(value: str) -> bool:
    return _normalize_image_extension(value) in _RASTER_EXTENSIONS


def _archive_name_sort_key(value: str) -> tuple[str, str]:
    return (value.casefold(), value)


def _temporary_output_path(path: Path) -> Path:
    return path.with_name(f".{path.stem}.images-tmp{path.suffix}")


def _replace_file(temp_output: Path, final_output: Path) -> None:
    try:
        shutil.move(str(temp_output), str(final_output))
    finally:
        if temp_output.exists():
            temp_output.unlink()
