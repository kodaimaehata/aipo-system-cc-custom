from __future__ import annotations

import os
from pathlib import Path

import pytest

from office_automation.common.files import copy_original, list_office_files


def test_list_office_files_defaults_to_supported_extensions(tmp_path: Path) -> None:
    for name, contents in [
        ("alpha.docx", "docx"),
        ("beta.XLSX", "xlsx"),
        ("gamma.pdf", "pdf"),
        ("macro.xlsm", "xlsm"),
        ("slides.pptx", "pptx"),
        ("legacy.xls", "xls"),
        ("binary.xlsb", "xlsb"),
        ("notes.txt", "txt"),
    ]:
        (tmp_path / name).write_text(contents)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "inside.pdf").write_text("nested")
    symlink_path = tmp_path / "linked.pdf"
    try:
        symlink_path.symlink_to(tmp_path / "gamma.pdf")
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation is not supported in this environment.")

    results = list_office_files(str(tmp_path))

    assert results == [
        tmp_path / "alpha.docx",
        tmp_path / "beta.XLSX",
        tmp_path / "gamma.pdf",
        tmp_path / "macro.xlsm",
        tmp_path / "slides.pptx",
    ]


def test_list_office_files_normalizes_extension_overrides(tmp_path: Path) -> None:
    (tmp_path / "alpha.XLSM").write_text("xlsm")
    (tmp_path / "beta.PDF").write_text("pdf")
    (tmp_path / "gamma.docx").write_text("docx")

    results = list_office_files(tmp_path, extensions=[".pdf", "XLSM"])

    assert results == [tmp_path / "alpha.XLSM", tmp_path / "beta.PDF"]


@pytest.mark.parametrize("extension", ["xls", ".XLSB"])
def test_list_office_files_rejects_unsupported_extension_overrides(
    tmp_path: Path,
    extension: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"Unsupported extension override: .* Supported extensions: docx, pdf, pptx, xlsm, xlsx\.",
    ):
        list_office_files(tmp_path, extensions=[extension])


def test_copy_original_copies_into_fresh_destination_directory(tmp_path: Path) -> None:
    source = tmp_path / "report.docx"
    source.write_text("hello world")
    os.utime(source, (946684800, 946684800))

    destination_directory = tmp_path / "copies"
    copied = copy_original(source, destination_directory)

    assert destination_directory.is_dir()
    assert copied == destination_directory / source.name
    assert copied.read_text() == source.read_text()
    assert copied.stat().st_mtime_ns == source.stat().st_mtime_ns


def test_copy_original_uses_copy_suffix_in_same_directory(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_text("original")

    copied = copy_original(source, tmp_path)

    assert copied == tmp_path / "report-copy.pdf"
    assert copied.read_text() == "original"
    assert source.read_text() == "original"


def test_copy_original_uses_collision_safe_names(tmp_path: Path) -> None:
    source = tmp_path / "report.pdf"
    source.write_text("original")
    (tmp_path / "report-copy.pdf").write_text("existing")

    copied = copy_original(source, tmp_path)

    assert copied == tmp_path / "report-copy-2.pdf"
    assert copied.read_text() == "original"
    assert source.read_text() == "original"


@pytest.mark.parametrize(
    ("extensions", "exception_type", "message"),
    [
        ("pdf", TypeError, r"Extension override must be an iterable of extension strings\."),
        ([], ValueError, r"Extension override cannot be empty\."),
        ([""], ValueError, r"Extension override cannot be empty\."),
        ([123], TypeError, r"Extension override values must be strings\."),
    ],
)
def test_list_office_files_rejects_invalid_extension_override_inputs(
    tmp_path: Path,
    extensions,
    exception_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception_type, match=message):
        list_office_files(tmp_path, extensions=extensions)


@pytest.mark.parametrize(
    ("callable_obj", "exception_type", "message"),
    [
        (
            lambda tmp_path: list_office_files(tmp_path / "missing"),
            FileNotFoundError,
            r"Folder '.*missing' does not exist\.",
        ),
        (
            lambda tmp_path: list_office_files(tmp_path / "plain.txt"),
            NotADirectoryError,
            r"Folder '.*plain\.txt' is not a directory\.",
        ),
        (
            lambda tmp_path: copy_original(tmp_path / "missing.docx", tmp_path / "copies"),
            FileNotFoundError,
            r"Source file '.*missing\.docx' does not exist\.",
        ),
        (
            lambda tmp_path: copy_original(tmp_path / "folder-source", tmp_path / "copies"),
            ValueError,
            r"Source file '.*folder-source' is not a regular file\.",
        ),
        (
            lambda tmp_path: copy_original(tmp_path / "linked.docx", tmp_path / "copies"),
            ValueError,
            r"Source file '.*linked\.docx' is not a regular file\.",
        ),
        (
            lambda tmp_path: copy_original(tmp_path / "unsupported.xls", tmp_path / "copies"),
            ValueError,
            r"Source file '.*unsupported\.xls' has unsupported extension 'xls'\. Supported extensions: docx, pdf, pptx, xlsm, xlsx\.",
        ),
        (
            lambda tmp_path: copy_original(tmp_path / "report.docx", tmp_path / "dest.txt"),
            NotADirectoryError,
            r"Destination directory '.*dest\.txt' is not a directory\.",
        ),
    ],
)
def test_path_validation_failures(
    tmp_path: Path,
    callable_obj,
    exception_type: type[Exception],
    message: str,
) -> None:
    (tmp_path / "plain.txt").write_text("plain")
    (tmp_path / "folder-source").mkdir()
    (tmp_path / "unsupported.xls").write_text("legacy")
    (tmp_path / "report.docx").write_text("report")
    (tmp_path / "dest.txt").write_text("not a dir")
    try:
        (tmp_path / "linked.docx").symlink_to(tmp_path / "report.docx")
    except (NotImplementedError, OSError):
        pass

    if "linked\\.docx" in message and not (tmp_path / "linked.docx").exists():
        pytest.skip("Symlink creation is not supported in this environment.")

    with pytest.raises(exception_type, match=message):
        callable_obj(tmp_path)
