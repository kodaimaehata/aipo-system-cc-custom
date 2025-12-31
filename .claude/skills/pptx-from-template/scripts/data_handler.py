"""Data handling for pptx-from-template.

Handles loading and validation of JSON/YAML data files.
"""

import json
from pathlib import Path
from typing import Any


class DataError(Exception):
    """Data handling error."""

    def __init__(self, code: str, message: str, details: str = ""):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")


def load_data(data_path: str | Path) -> dict[str, Any]:
    """Load data from JSON or YAML file.

    Args:
        data_path: Path to the data file (.json or .yaml/.yml)

    Returns:
        Parsed data dictionary

    Raises:
        DataError: If file not found or parsing fails
    """
    path = Path(data_path)

    if not path.exists():
        raise DataError(
            "E002",
            "データファイルが見つかりません",
            f"パス: {path}",
        )

    suffix = path.suffix.lower()

    try:
        with open(path, encoding="utf-8") as f:
            if suffix == ".json":
                return json.load(f)
            elif suffix in (".yaml", ".yml"):
                try:
                    import yaml
                except ImportError:
                    raise DataError(
                        "E003",
                        "YAMLファイルの読み込みにはPyYAMLが必要です",
                        "uv add pyyaml を実行してください",
                    )
                return yaml.safe_load(f)
            else:
                raise DataError(
                    "E003",
                    "サポートされていないファイル形式です",
                    f"対応形式: .json, .yaml, .yml (指定: {suffix})",
                )
    except json.JSONDecodeError as e:
        raise DataError(
            "E003",
            "JSONの構文エラーです",
            f"行 {e.lineno}, 列 {e.colno}: {e.msg}",
        )
    except Exception as e:
        if isinstance(e, DataError):
            raise
        raise DataError(
            "E003",
            "データファイルの読み込みに失敗しました",
            str(e),
        )


def validate_data(data: dict[str, Any]) -> list[str]:
    """Validate data structure and return warnings.

    Args:
        data: Parsed data dictionary

    Returns:
        List of warning messages (empty if no warnings)
    """
    warnings = []

    # Check for slides array
    if "slides" not in data:
        warnings.append("W003: 'slides'キーがありません。空のプレゼンテーションになります。")
        return warnings

    slides = data.get("slides", [])
    if not isinstance(slides, list):
        warnings.append("W003: 'slides'は配列である必要があります。")
        return warnings

    for i, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            warnings.append(f"W003: スライド{i}: 辞書形式である必要があります。")
            continue

        # Check layout index
        layout = slide.get("layout", 1)
        if not isinstance(layout, int) or layout < 0 or layout > 10:
            warnings.append(f"W003: スライド{i}: layoutは0-10の整数である必要があります。デフォルト(1)を使用します。")

        # Check table data
        if "table" in slide:
            table = slide["table"]
            if not isinstance(table, dict):
                warnings.append(f"W002: スライド{i}: tableは辞書形式である必要があります。")
            elif "headers" not in table and "rows" not in table:
                warnings.append(f"W002: スライド{i}: 表データが空です。")

        # Check image path
        if "image" in slide:
            image_path = Path(slide["image"])
            if not image_path.exists():
                warnings.append(f"W001: スライド{i}: 画像ファイルが見つかりません ({slide['image']})")

        # Check content length
        if "content" in slide:
            content = slide["content"]
            if isinstance(content, list):
                for j, item in enumerate(content):
                    if isinstance(item, str) and len(item) > 500:
                        warnings.append(f"W004: スライド{i}: コンテンツ{j+1}が長すぎます（{len(item)}文字）。切り詰められる可能性があります。")

    return warnings
