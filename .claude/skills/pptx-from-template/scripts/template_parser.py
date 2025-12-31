"""Template parsing for pptx-from-template.

Handles template loading and placeholder replacement.
"""

import re
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN


class TemplateError(Exception):
    """Template handling error."""

    def __init__(self, code: str, message: str, details: str = ""):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")


def load_template(template_path: str | Path) -> Presentation:
    """Load a PowerPoint template.

    Args:
        template_path: Path to the template file

    Returns:
        Presentation object

    Raises:
        TemplateError: If file not found or invalid
    """
    path = Path(template_path)

    if not path.exists():
        raise TemplateError(
            "E001",
            "テンプレートファイルが見つかりません",
            f"パス: {path}",
        )

    if path.suffix.lower() != ".pptx":
        raise TemplateError(
            "E006",
            "有効なPPTXファイルではありません",
            f"拡張子: {path.suffix}",
        )

    try:
        return Presentation(str(path))
    except Exception as e:
        raise TemplateError(
            "E006",
            "テンプレートの読み込みに失敗しました",
            str(e),
        )


def create_new_presentation() -> Presentation:
    """Create a new empty presentation.

    Returns:
        New Presentation object
    """
    return Presentation()


def replace_placeholders(prs: Presentation, replacements: dict[str, str]) -> None:
    """Replace {{key}} placeholders in all slides.

    Args:
        prs: Presentation object
        replacements: Dictionary of placeholder key -> replacement value
    """
    pattern = re.compile(r"\{\{(\w+)\}\}")

    for slide in prs.slides:
        for shape in slide.shapes:
            if not hasattr(shape, "text_frame"):
                continue

            for paragraph in shape.text_frame.paragraphs:
                # Try run-level replacement first (preserves formatting)
                for run in paragraph.runs:
                    for key, value in replacements.items():
                        placeholder = f"{{{{{key}}}}}"
                        if placeholder in run.text:
                            run.text = run.text.replace(placeholder, value)

                # Fallback to paragraph-level if runs are empty
                if not paragraph.runs:
                    for key, value in replacements.items():
                        placeholder = f"{{{{{key}}}}}"
                        if placeholder in paragraph.text:
                            paragraph.text = paragraph.text.replace(placeholder, value)


def add_slide_from_data(prs: Presentation, slide_data: dict[str, Any], warnings: list[str]) -> None:
    """Add a slide based on data specification.

    Args:
        prs: Presentation object
        slide_data: Slide specification dictionary
        warnings: List to append warnings to
    """
    # Get layout index (default: 1 = Title and Content)
    layout_idx = slide_data.get("layout", 1)
    if not isinstance(layout_idx, int) or layout_idx < 0:
        layout_idx = 1

    # Ensure layout index is within bounds
    if layout_idx >= len(prs.slide_layouts):
        layout_idx = min(1, len(prs.slide_layouts) - 1)

    slide_layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(slide_layout)

    # Set title
    if "title" in slide_data and slide.shapes.title:
        slide.shapes.title.text = str(slide_data["title"])

    # Set subtitle (for title slide layout)
    if "subtitle" in slide_data:
        try:
            if len(slide.placeholders) > 1:
                slide.placeholders[1].text = str(slide_data["subtitle"])
        except (KeyError, IndexError):
            pass

    # Set content (bullet points)
    if "content" in slide_data:
        content = slide_data["content"]
        if isinstance(content, list) and len(slide.placeholders) > 1:
            try:
                body = slide.placeholders[1]
                tf = body.text_frame
                tf.clear()

                for i, item in enumerate(content):
                    if i == 0:
                        tf.paragraphs[0].text = str(item)
                    else:
                        p = tf.add_paragraph()
                        p.text = str(item)
                        p.level = 0
            except (KeyError, IndexError, AttributeError):
                pass
        elif isinstance(content, str):
            try:
                if len(slide.placeholders) > 1:
                    slide.placeholders[1].text = content
            except (KeyError, IndexError):
                pass

    # Add table
    if "table" in slide_data:
        _add_table_to_slide(slide, slide_data["table"], warnings)

    # Add image
    if "image" in slide_data:
        _add_image_to_slide(slide, slide_data["image"], warnings)


def _add_table_to_slide(slide, table_data: dict[str, Any], warnings: list[str]) -> None:
    """Add a table to the slide.

    Args:
        slide: Slide object
        table_data: Table specification with headers and rows
        warnings: List to append warnings to
    """
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])

    if not headers and not rows:
        return

    # Calculate dimensions
    cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    row_count = len(rows) + (1 if headers else 0)

    if cols == 0 or row_count == 0:
        return

    # Add table shape
    left = Inches(0.5)
    top = Inches(2.0)
    width = Inches(9.0)
    height = Inches(0.8 * row_count)

    table = slide.shapes.add_table(row_count, cols, left, top, width, height).table

    # Set column widths
    col_width = Inches(9.0 / cols)
    for i in range(cols):
        table.columns[i].width = col_width

    # Fill headers
    if headers:
        for i, header in enumerate(headers):
            cell = table.cell(0, i)
            cell.text = str(header)
            # Bold header
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True

    # Fill rows
    start_row = 1 if headers else 0
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            if col_idx < cols:
                table.cell(start_row + row_idx, col_idx).text = str(value)


def _add_image_to_slide(slide, image_path: str, warnings: list[str]) -> None:
    """Add an image to the slide.

    Args:
        slide: Slide object
        image_path: Path to the image file
        warnings: List to append warnings to
    """
    path = Path(image_path)
    if not path.exists():
        # Warning already added in validate_data
        return

    try:
        # Add image centered on slide
        left = Inches(1.5)
        top = Inches(2.0)
        width = Inches(7.0)
        slide.shapes.add_picture(str(path), left, top, width=width)
    except Exception as e:
        warnings.append(f"W001: 画像の追加に失敗しました: {e}")


def get_layout_name(prs: Presentation, layout_idx: int) -> str:
    """Get the name of a slide layout.

    Args:
        prs: Presentation object
        layout_idx: Layout index

    Returns:
        Layout name or "Unknown"
    """
    try:
        if 0 <= layout_idx < len(prs.slide_layouts):
            return prs.slide_layouts[layout_idx].name
    except Exception:
        pass
    return "Unknown"
