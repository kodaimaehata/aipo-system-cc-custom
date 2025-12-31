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

        # Check shapes array (free-form layout)
        if "shapes" in slide:
            shapes = slide["shapes"]
            if not isinstance(shapes, list):
                warnings.append(f"W005: スライド{i}: shapesは配列である必要があります。")
            else:
                warnings.extend(_validate_shapes(shapes, i))

    return warnings


def _validate_shapes(shapes: list, slide_num: int) -> list[str]:
    """Validate shapes array.

    Args:
        shapes: List of shape specifications
        slide_num: Slide number for error messages

    Returns:
        List of warning messages
    """
    warnings = []
    valid_types = {"textbox", "image", "shape", "table", "line"}
    valid_shape_types = {
        "rectangle", "rounded_rectangle", "oval", "circle", "triangle",
        "right_arrow", "left_arrow", "up_arrow", "down_arrow",
        "pentagon", "hexagon", "star", "callout", "cloud", "heart", "lightning"
    }

    for j, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            warnings.append(f"W005: スライド{slide_num}: shapes[{j}]は辞書形式である必要があります。")
            continue

        shape_type = shape.get("type", "").lower()
        if not shape_type:
            warnings.append(f"W005: スライド{slide_num}: shapes[{j}]にtypeが指定されていません。")
            continue

        if shape_type not in valid_types:
            warnings.append(f"W005: スライド{slide_num}: shapes[{j}]の未知のtype '{shape_type}'")

        # Validate coordinates
        for coord in ["left", "top", "width", "height"]:
            if coord in shape:
                val = shape[coord]
                if not isinstance(val, (int, float)) or val < 0:
                    warnings.append(f"W005: スライド{slide_num}: shapes[{j}].{coord}は正の数値である必要があります。")

        # Type-specific validation
        if shape_type == "image":
            if "path" not in shape:
                warnings.append(f"W001: スライド{slide_num}: shapes[{j}]に画像パスが指定されていません。")
            else:
                image_path = Path(shape["path"])
                if not image_path.exists():
                    warnings.append(f"W001: スライド{slide_num}: shapes[{j}]の画像ファイルが見つかりません ({shape['path']})")

        elif shape_type == "shape":
            st = shape.get("shape_type", "rectangle").lower()
            if st not in valid_shape_types:
                warnings.append(f"W005: スライド{slide_num}: shapes[{j}]の未知のshape_type '{st}'")

        elif shape_type == "textbox":
            if "text" not in shape:
                warnings.append(f"W005: スライド{slide_num}: shapes[{j}]にtextが指定されていません。")

        elif shape_type == "line":
            for coord in ["start_x", "start_y", "end_x", "end_y"]:
                if coord in shape:
                    val = shape[coord]
                    if not isinstance(val, (int, float)):
                        warnings.append(f"W005: スライド{slide_num}: shapes[{j}].{coord}は数値である必要があります。")

    return warnings
