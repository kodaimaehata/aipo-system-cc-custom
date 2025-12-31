#!/usr/bin/env python3
"""Integration tests for pptx-from-template skill."""

import json
import os
import tempfile
from pathlib import Path

from .generate_pptx import generate_pptx, DataError, TemplateError, OutputError


def test_basic_generation():
    """Test basic PPTX generation."""
    print("\n=== テスト: 基本動作 ===")

    data = {
        "slides": [
            {"layout": 0, "title": "テスト", "subtitle": "基本動作確認"},
            {"layout": 1, "title": "内容", "content": ["項目1", "項目2"]},
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists(), "出力ファイルが存在しません"
        assert len(slide_info) == 2, f"スライド数が不正: {len(slide_info)}"
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_japanese_text():
    """Test Japanese text handling."""
    print("\n=== テスト: 日本語テキスト ===")

    data = {
        "slides": [
            {
                "layout": 0,
                "title": "日本語タイトルテスト",
                "subtitle": "サブタイトル：漢字、ひらがな、カタカナ"
            },
            {
                "layout": 1,
                "title": "日本語コンテンツ",
                "content": [
                    "これは日本語のテストです",
                    "漢字：東京都渋谷区",
                    "カタカナ：パワーポイント",
                    "ひらがな：ぷれぜんてーしょん"
                ]
            },
            {
                "layout": 5,
                "title": "日本語表データ",
                "table": {
                    "headers": ["名前", "部署", "役職"],
                    "rows": [
                        ["山田太郎", "開発部", "エンジニア"],
                        ["佐藤花子", "営業部", "マネージャー"]
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists()
        assert len(slide_info) == 3
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_long_text():
    """Test long text handling."""
    print("\n=== テスト: 長文テキスト ===")

    long_text = "これは非常に長いテキストです。" * 50  # ~1000 chars

    data = {
        "slides": [
            {
                "layout": 1,
                "title": "長文テスト",
                "content": [long_text]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists()
        # W004 warning should be present for long content (>500 chars)
        has_w004 = any("W004" in w for w in warnings)
        assert has_w004, f"W004警告が発生すべき: {warnings}"
        print(f"  ✓ PASS: {result_path}")
        print(f"    警告: {warnings}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_empty_data():
    """Test empty data fields."""
    print("\n=== テスト: 空データ ===")

    data = {
        "slides": [
            {"layout": 0, "title": "タイトルのみ"},  # no subtitle
            {"layout": 1, "title": "コンテンツなし"},  # no content
            {"layout": 5, "title": "空の表", "table": {"headers": [], "rows": []}},
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists()
        print(f"  ✓ PASS: {result_path}")
        if warnings:
            print(f"    警告: {warnings}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_special_characters():
    """Test special characters."""
    print("\n=== テスト: 特殊文字 ===")

    data = {
        "slides": [
            {
                "layout": 1,
                "title": "特殊文字テスト <>&\"'",
                "content": [
                    "HTMLエスケープ: <script>alert('XSS')</script>",
                    "アンパサンド: A & B",
                    "引用符: \"quoted\" と 'single'",
                    "数学記号: α β γ δ ε",
                    "絵文字: 🎉 🚀 ✅ ❌"
                ]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists()
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_nonexistent_template():
    """Test error handling for nonexistent template."""
    print("\n=== テスト: テンプレート不存在 ===")

    data = {"slides": [{"layout": 0, "title": "Test"}]}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        data_path = f.name

    try:
        generate_pptx(
            template_path="/nonexistent/template.pptx",
            data_path=data_path,
            output_path="output.pptx",
        )
        print("  ✗ FAIL: エラーが発生すべき")
        return False
    except TemplateError as e:
        if e.code == "E001":
            print(f"  ✓ PASS: 正しいエラー発生 ({e.code})")
            return True
        print(f"  ✗ FAIL: 不正なエラーコード ({e.code})")
        return False
    except Exception as e:
        print(f"  ✗ FAIL: 予期しないエラー: {e}")
        return False
    finally:
        os.unlink(data_path)


def test_invalid_json():
    """Test error handling for invalid JSON."""
    print("\n=== テスト: 無効なJSON ===")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json}")
        data_path = f.name

    try:
        generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path="output.pptx",
        )
        print("  ✗ FAIL: エラーが発生すべき")
        return False
    except DataError as e:
        if e.code == "E003":
            print(f"  ✓ PASS: 正しいエラー発生 ({e.code})")
            return True
        print(f"  ✗ FAIL: 不正なエラーコード ({e.code})")
        return False
    except Exception as e:
        print(f"  ✗ FAIL: 予期しないエラー: {e}")
        return False
    finally:
        os.unlink(data_path)


def test_nonexistent_data():
    """Test error handling for nonexistent data file."""
    print("\n=== テスト: データファイル不存在 ===")

    try:
        generate_pptx(
            template_path=None,
            data_path="/nonexistent/data.json",
            output_path="output.pptx",
        )
        print("  ✗ FAIL: エラーが発生すべき")
        return False
    except DataError as e:
        if e.code == "E002":
            print(f"  ✓ PASS: 正しいエラー発生 ({e.code})")
            return True
        print(f"  ✗ FAIL: 不正なエラーコード ({e.code})")
        return False
    except Exception as e:
        print(f"  ✗ FAIL: 予期しないエラー: {e}")
        return False


def test_file_exists():
    """Test error handling for existing output file."""
    print("\n=== テスト: 既存ファイル上書き ===")

    data = {"slides": [{"layout": 0, "title": "Test"}]}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        data_path = f.name

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = f.name

    try:
        # Should fail without --force
        generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=False,
        )
        print("  ✗ FAIL: エラーが発生すべき")
        return False
    except OutputError as e:
        if e.code == "E005":
            print(f"  ✓ PASS: 正しいエラー発生 ({e.code})")
            return True
        print(f"  ✗ FAIL: 不正なエラーコード ({e.code})")
        return False
    except Exception as e:
        print(f"  ✗ FAIL: 予期しないエラー: {e}")
        return False
    finally:
        os.unlink(data_path)
        os.unlink(output_path)


def test_with_template():
    """Test PPTX generation with existing template."""
    print("\n=== テスト: テンプレート使用 ===")

    # Use sample template from templates directory
    script_dir = Path(__file__).parent.parent
    template_path = script_dir / "templates" / "sample_template.pptx"

    if not template_path.exists():
        print(f"  ✗ SKIP: テンプレートが見つかりません: {template_path}")
        return True  # Skip but don't fail

    data = {
        "slides": [
            {"layout": 0, "title": "テンプレートテスト", "subtitle": "既存テンプレート使用"},
            {"layout": 1, "title": "コンテンツ", "content": ["項目A", "項目B"]},
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=str(template_path),
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists(), "出力ファイルが存在しません"
        assert len(slide_info) == 2, f"スライド数が不正: {len(slide_info)}"
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_placeholder_replacement():
    """Test placeholder replacement in template."""
    print("\n=== テスト: プレースホルダー置換 ===")

    # Use sample template
    script_dir = Path(__file__).parent.parent
    template_path = script_dir / "templates" / "sample_template.pptx"

    if not template_path.exists():
        print(f"  ✗ SKIP: テンプレートが見つかりません: {template_path}")
        return True

    data = {
        "placeholders": {
            "title": "置換後タイトル",
            "subtitle": "置換後サブタイトル",
        },
        "slides": []
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=str(template_path),
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists(), "出力ファイルが存在しません"
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_freeform_shapes():
    """Test free-form shapes (textbox, shape, line)."""
    print("\n=== テスト: フリーフォーム図形 ===")

    data = {
        "slides": [
            {
                "layout": 6,  # Blank
                "shapes": [
                    {
                        "type": "textbox",
                        "left": 1.0,
                        "top": 0.5,
                        "width": 8.0,
                        "height": 1.0,
                        "text": "カスタムタイトル",
                        "font_size": 32,
                        "bold": True,
                        "align": "center"
                    },
                    {
                        "type": "shape",
                        "shape_type": "rectangle",
                        "left": 1.0,
                        "top": 2.0,
                        "width": 3.0,
                        "height": 2.0,
                        "fill_color": "#3366CC",
                        "text": "青い四角形",
                        "font_color": "white"
                    },
                    {
                        "type": "shape",
                        "shape_type": "oval",
                        "left": 5.0,
                        "top": 2.0,
                        "width": 2.0,
                        "height": 2.0,
                        "fill_color": "red",
                        "text": "円"
                    },
                    {
                        "type": "textbox",
                        "left": 1.0,
                        "top": 5.0,
                        "width": 8.0,
                        "height": 1.0,
                        "text": "説明テキスト：図形を自由に配置できます",
                        "font_size": 14,
                        "fill_color": "#EEEEEE"
                    },
                    {
                        "type": "shape",
                        "shape_type": "right_arrow",
                        "left": 4.0,
                        "top": 3.0,
                        "width": 1.0,
                        "height": 0.5,
                        "fill_color": "green"
                    }
                ]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists(), "出力ファイルが存在しません"
        assert len(slide_info) == 1, f"スライド数が不正: {len(slide_info)}"
        print(f"  ✓ PASS: {result_path}")
        if warnings:
            print(f"    警告: {warnings}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_freeform_table():
    """Test free-form table at custom position."""
    print("\n=== テスト: フリーフォーム表 ===")

    data = {
        "slides": [
            {
                "layout": 6,  # Blank
                "shapes": [
                    {
                        "type": "textbox",
                        "left": 0.5,
                        "top": 0.5,
                        "width": 9.0,
                        "height": 0.8,
                        "text": "カスタム位置の表",
                        "font_size": 24,
                        "bold": True
                    },
                    {
                        "type": "table",
                        "left": 0.5,
                        "top": 1.5,
                        "width": 5.0,
                        "headers": ["項目", "値", "備考"],
                        "rows": [
                            ["A", "100", "テスト"],
                            ["B", "200", "サンプル"]
                        ]
                    },
                    {
                        "type": "textbox",
                        "left": 6.0,
                        "top": 1.5,
                        "width": 3.5,
                        "height": 2.0,
                        "text": "表の横に配置された\n説明テキスト",
                        "font_size": 12
                    }
                ]
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        data_path = f.name

    try:
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            output_path = f.name

        result_path, warnings, slide_info = generate_pptx(
            template_path=None,
            data_path=data_path,
            output_path=output_path,
            force=True,
        )

        assert result_path.exists(), "出力ファイルが存在しません"
        print(f"  ✓ PASS: {result_path}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False
    finally:
        os.unlink(data_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("pptx-from-template 統合テスト")
    print("=" * 60)

    tests = [
        ("基本動作", test_basic_generation),
        ("日本語テキスト", test_japanese_text),
        ("長文テキスト", test_long_text),
        ("空データ", test_empty_data),
        ("特殊文字", test_special_characters),
        ("テンプレート使用", test_with_template),
        ("プレースホルダー置換", test_placeholder_replacement),
        ("フリーフォーム図形", test_freeform_shapes),
        ("フリーフォーム表", test_freeform_table),
        ("テンプレート不存在", test_nonexistent_template),
        ("無効なJSON", test_invalid_json),
        ("データファイル不存在", test_nonexistent_data),
        ("既存ファイル上書き", test_file_exists),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, "PASS" if result else "FAIL"))
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append((name, f"ERROR: {e}"))

    print("\n" + "=" * 60)
    print("テスト結果サマリー")
    print("=" * 60)

    passed = sum(1 for _, r in results if r == "PASS")
    failed = sum(1 for _, r in results if r == "FAIL" or r.startswith("ERROR"))

    for name, status in results:
        symbol = "✓" if status == "PASS" else "✗"
        print(f"  {symbol} {name}: {status}")

    print(f"\n合計: {passed}/{len(results)} PASS")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
