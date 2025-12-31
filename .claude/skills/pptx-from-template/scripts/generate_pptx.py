#!/usr/bin/env python3
"""Generate PowerPoint presentations from templates.

Usage:
    python generate_pptx.py --template <template.pptx> --data <data.json> [--output <output.pptx>]
    python generate_pptx.py --data <data.json> [--output <output.pptx>]  # Create new presentation
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .data_handler import DataError, load_data, validate_data
from .template_parser import (
    TemplateError,
    add_slide_from_data,
    create_new_presentation,
    get_layout_name,
    load_template,
    replace_placeholders,
)


class OutputError(Exception):
    """Output handling error."""

    def __init__(self, code: str, message: str, details: str = ""):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")


def generate_pptx(
    template_path: str | Path | None,
    data_path: str | Path,
    output_path: str | Path | None = None,
    force: bool = False,
) -> tuple[Path, list[str], list[dict[str, str]]]:
    """Generate a PowerPoint presentation.

    Args:
        template_path: Path to template file (None to create new)
        data_path: Path to data file (JSON/YAML)
        output_path: Output file path (auto-generated if None)
        force: Overwrite existing files

    Returns:
        Tuple of (output_path, warnings, slide_info)

    Raises:
        DataError: Data file issues
        TemplateError: Template file issues
        OutputError: Output file issues
    """
    # Load data
    data = load_data(data_path)
    warnings = validate_data(data)

    # Load or create presentation
    if template_path:
        prs = load_template(template_path)
        # Handle placeholder mode vs slide generation mode
        if "placeholders" in data:
            # Placeholder replacement mode
            replace_placeholders(prs, data["placeholders"])
    else:
        prs = create_new_presentation()

    # Generate slides from data
    slides = data.get("slides", [])
    slide_info = []

    for i, slide_data in enumerate(slides, 1):
        add_slide_from_data(prs, slide_data, warnings)

        # Collect slide info for report
        layout_idx = slide_data.get("layout", 1)
        slide_info.append({
            "number": str(i),
            "title": slide_data.get("title", "(無題)"),
            "layout": get_layout_name(prs, layout_idx),
        })

    # Determine output path
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"output_{timestamp}.pptx")
    else:
        output_path = Path(output_path)

    # Check output directory
    output_dir = output_path.parent
    if output_dir and not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise OutputError(
                "E004",
                "出力先ディレクトリを作成できません",
                f"パス: {output_dir}",
            )

    # Check existing file
    if output_path.exists() and not force:
        raise OutputError(
            "E005",
            "ファイルが既に存在します",
            f"パス: {output_path}\n--force オプションで上書きできます",
        )

    # Save presentation
    try:
        prs.save(str(output_path))
    except PermissionError:
        raise OutputError(
            "E004",
            "出力先に書き込めません",
            f"パス: {output_path}",
        )
    except Exception as e:
        raise OutputError(
            "E004",
            "ファイルの保存に失敗しました",
            str(e),
        )

    return output_path, warnings, slide_info


def format_success_output(
    output_path: Path,
    slide_info: list[dict[str, str]],
    warnings: list[str],
) -> str:
    """Format success output message."""
    lines = []

    if warnings:
        lines.append("✓ PowerPointファイルを生成しました（警告あり）")
    else:
        lines.append("✓ PowerPointファイルを生成しました")

    lines.append("")
    lines.append(f"  出力: {output_path.absolute()}")
    lines.append(f"  スライド数: {len(slide_info)}")

    if slide_info:
        lines.append("")
        lines.append("  スライド構成:")
        for info in slide_info[:10]:  # Show first 10 slides
            lines.append(f"    {info['number']}. {info['title']} ({info['layout']})")
        if len(slide_info) > 10:
            lines.append(f"    ... 他 {len(slide_info) - 10} スライド")

    if warnings:
        lines.append("")
        lines.append("  警告:")
        for warning in warnings:
            lines.append(f"    - {warning}")

    return "\n".join(lines)


def format_error_output(error: Exception) -> str:
    """Format error output message."""
    lines = []

    if isinstance(error, (DataError, TemplateError, OutputError)):
        lines.append(f"✗ エラー: {error.message}")
        lines.append("")
        lines.append(f"  コード: {error.code}")
        if error.details:
            lines.append(f"  詳細: {error.details}")
    else:
        lines.append(f"✗ エラー: {error}")

    lines.append("")
    lines.append("  対処法:")

    if isinstance(error, DataError):
        if error.code == "E002":
            lines.append("    - データファイルのパスが正しいか確認してください")
        elif error.code == "E003":
            lines.append("    - データファイルの構文を確認してください")
    elif isinstance(error, TemplateError):
        if error.code == "E001":
            lines.append("    - テンプレートファイルのパスが正しいか確認してください")
        elif error.code == "E006":
            lines.append("    - 有効な.pptxファイルか確認してください")
    elif isinstance(error, OutputError):
        if error.code == "E004":
            lines.append("    - 出力先ディレクトリの権限を確認してください")
        elif error.code == "E005":
            lines.append("    - --force オプションで上書きするか、別の出力先を指定してください")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate PowerPoint presentations from templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use template with data
  python -m scripts.generate_pptx --template report.pptx --data data.json

  # Create new presentation from data
  python -m scripts.generate_pptx --data data.json --output output.pptx

  # Overwrite existing file
  python -m scripts.generate_pptx --data data.json --output output.pptx --force
""",
    )
    parser.add_argument(
        "--template", "-t",
        help="Template .pptx file path (optional, creates new if not specified)",
    )
    parser.add_argument(
        "--data", "-d",
        required=True,
        help="Data file path (.json or .yaml)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: output_YYYYMMDD_HHMMSS.pptx)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing output file",
    )

    args = parser.parse_args()

    try:
        output_path, warnings, slide_info = generate_pptx(
            template_path=args.template,
            data_path=args.data,
            output_path=args.output,
            force=args.force,
        )
        print(format_success_output(output_path, slide_info, warnings))
        return 0

    except (DataError, TemplateError, OutputError) as e:
        print(format_error_output(e), file=sys.stderr)
        return 1

    except Exception as e:
        print(f"✗ 予期しないエラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
