"""Common file helpers limited to V1 Office and PDF formats."""

from __future__ import annotations

from collections.abc import Iterable
from os import PathLike
from pathlib import Path
import shutil

__all__ = ["copy_original", "list_office_files"]

_SUPPORTED_EXTENSIONS = frozenset({"xlsx", "xlsm", "docx", "pptx", "pdf"})
_SUPPORTED_EXTENSIONS_TEXT = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
_COPY_SUFFIX = "-copy"


def copy_original(src: str | PathLike[str], dest_dir: str | PathLike[str]) -> Path:
    """Copy src to dest_dir with collision-safe naming and return the new path."""
    source = _coerce_path(src)
    destination_directory = _coerce_path(dest_dir)

    _validate_file_path(source, label="Source file")
    _validate_supported_path_extension(source, label="Source file")
    _ensure_directory(destination_directory, label="Destination directory")

    target = _resolve_copy_target(source, destination_directory)
    shutil.copy2(source, target)
    return target


def list_office_files(
    folder: str | PathLike[str],
    extensions: Iterable[str] | None = None,
) -> list[Path]:
    """Return regular files in folder matching supported V1 extensions."""
    target_folder = _coerce_path(folder)
    _validate_directory_path(target_folder, label="Folder")

    allowed_extensions = (
        _SUPPORTED_EXTENSIONS if extensions is None else _normalize_extension_override(extensions)
    )

    files = [
        path
        for path in target_folder.iterdir()
        if path.is_file() and not path.is_symlink() and _path_extension(path) in allowed_extensions
    ]
    return sorted(files, key=_path_sort_key)



def _coerce_path(value: str | PathLike[str]) -> Path:
    return Path(value)



def _normalize_extension(extension: str, *, context: str) -> str:
    if not isinstance(extension, str):
        raise TypeError(f"{context} values must be strings.")
    normalized = extension.strip().lower().lstrip(".")
    if not normalized:
        raise ValueError(f"{context} cannot be empty.")
    return normalized



def _normalize_extension_override(extensions: Iterable[str]) -> frozenset[str]:
    if isinstance(extensions, str):
        raise TypeError("Extension override must be an iterable of extension strings.")

    normalized_extensions = {
        _normalize_extension(extension, context="Extension override") for extension in extensions
    }
    if not normalized_extensions:
        raise ValueError("Extension override cannot be empty.")

    unsupported = sorted(normalized_extensions - _SUPPORTED_EXTENSIONS)
    if unsupported:
        unsupported_text = ", ".join(unsupported)
        raise ValueError(
            "Unsupported extension override: "
            f"{unsupported_text}. Supported extensions: {_SUPPORTED_EXTENSIONS_TEXT}."
        )

    return frozenset(normalized_extensions)



def _validate_supported_path_extension(path: Path, *, label: str) -> None:
    extension = _path_extension(path)
    if extension not in _SUPPORTED_EXTENSIONS:
        display_extension = extension or "<none>"
        raise ValueError(
            f"{label} '{path}' has unsupported extension '{display_extension}'. "
            f"Supported extensions: {_SUPPORTED_EXTENSIONS_TEXT}."
        )



def _path_extension(path: Path) -> str:
    return path.suffix.lower().lstrip(".")



def _validate_directory_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} '{path}' does not exist.")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} '{path}' is not a directory.")



def _validate_file_path(path: Path, *, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} '{path}' does not exist.")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} '{path}' is not a regular file.")



def _ensure_directory(path: Path, *, label: str) -> None:
    if path.exists():
        if not path.is_dir():
            raise NotADirectoryError(f"{label} '{path}' is not a directory.")
        return
    path.mkdir(parents=True, exist_ok=True)



def _resolve_copy_target(source: Path, destination_directory: Path) -> Path:
    original_candidate = destination_directory / source.name
    if _is_available_target(source, original_candidate):
        return original_candidate

    copy_candidate = destination_directory / f"{source.stem}{_COPY_SUFFIX}{source.suffix}"
    if _is_available_target(source, copy_candidate):
        return copy_candidate

    index = 2
    while True:
        candidate = destination_directory / f"{source.stem}{_COPY_SUFFIX}-{index}{source.suffix}"
        if _is_available_target(source, candidate):
            return candidate
        index += 1



def _is_available_target(source: Path, candidate: Path) -> bool:
    return not candidate.exists() and not _paths_refer_to_same_location(source, candidate)



def _paths_refer_to_same_location(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve(strict=False)



def _path_sort_key(path: Path) -> tuple[str, str]:
    return (path.name.casefold(), path.name)
