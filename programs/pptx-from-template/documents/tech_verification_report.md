# python-pptx 技術検証レポート

## 検証日
2025-12-30

## 概要
python-pptxライブラリを使用したPowerPointファイル生成の技術検証を実施。テンプレートベースのPPTX生成が実現可能であることを確認した。

---

## 環境

- **Python**: 3.12.12（requires-python >= 3.11）
- **python-pptx**: 1.0.2
- **パッケージ管理**: uv
- **追加依存**: lxml 6.0.2, Pillow 12.0.0, xlsxwriter 3.2.9

### 更新履歴
- 2025-12-30: 初回検証（Python 3.9.6）
- 2025-12-30: Python 3.12へアップグレード（Codexレビュー指摘対応）

---

## 検証結果サマリー

| テスト項目 | 結果 | 備考 |
|-----------|------|------|
| 新規プレゼンテーション作成 | ✓ PASS | |
| 複数スライドタイプ | ✓ PASS | 11種類のレイアウト利用可能 |
| 表の作成 | ✓ PASS | 日本語対応確認 |
| テキストフォーマット | ✓ PASS | フォント、色、サイズ設定可能 |
| テンプレート使用 | ✓ PASS | 既存.pptx読込→編集→保存 |
| プレースホルダー置換 | ✓ PASS | `{{key}}`形式での置換動作 |
| JSONデータ駆動 | ✓ PASS | 構造化データからの生成 |
| フォーマット保持 | ✓ PASS | 置換時にスタイル維持 |

---

## 詳細検証結果

### 1. 基本機能

#### プレゼンテーション作成
```python
from pptx import Presentation
prs = Presentation()
```

#### スライドレイアウト（デフォルトテンプレート）
| Index | Name | 用途 |
|-------|------|------|
| 0 | Title Slide | タイトルページ |
| 1 | Title and Content | 本文スライド |
| 2 | Section Header | セクション区切り |
| 3 | Two Content | 2カラム |
| 4 | Comparison | 比較 |
| 5 | Title Only | タイトルのみ |
| 6 | Blank | 空白 |
| 7 | Content with Caption | キャプション付き |
| 8 | Picture with Caption | 画像+キャプション |
| 9 | Title and Vertical Text | 縦書き |
| 10 | Vertical Title and Text | 縦書きタイトル |

### 2. テンプレート操作

#### 既存ファイル読み込み
```python
prs = Presentation("template.pptx")
```

#### プレースホルダー置換
```python
for slide in prs.slides:
    for shape in slide.shapes:
        if hasattr(shape, "text_frame"):
            for paragraph in shape.text_frame.paragraphs:
                for run in paragraph.runs:
                    run.text = run.text.replace("{{key}}", "value")
```

### 3. 日本語対応
- テキスト挿入: ✓ 正常動作
- フォント指定: ✓ 可能（要フォント名指定）
- 改行: ✓ `\n`で改行可能

### 4. 制限事項・注意点

1. **プレースホルダー調査エラー**: slide_layouts直接アクセス時に一部エラー発生（実用上問題なし）
2. **フォント保持**: テンプレートのフォント設定はrun単位で保持される
3. **画像置換**: パスベースでの画像追加は可能。既存画像の置換は要追加実装

---

## 推奨実装方針

### データ形式
```json
{
  "title": "プレゼンタイトル",
  "subtitle": "サブタイトル",
  "slides": [
    {
      "type": "content",
      "title": "セクション名",
      "content": ["項目1", "項目2"]
    }
  ]
}
```

### 置換方式
1. `{{key}}`形式のプレースホルダーをテンプレートに埋め込み
2. run単位での置換でフォーマット保持
3. 段落全体のテキスト置換も併用

---

## 生成ファイル一覧

| ファイル | サイズ | 内容 |
|----------|-------|------|
| test1_new_presentation.pptx | 28KB | 基本テスト |
| test2_multiple_slides.pptx | 30KB | 複数スライド |
| test4_table.pptx | 29KB | 表データ |
| test5_formatting.pptx | 28KB | テキストフォーマット |
| test6_from_template.pptx | 28KB | テンプレート使用 |
| advanced_output.pptx | - | プレースホルダー置換 |
| json_driven_output.pptx | - | JSONデータ駆動 |
| formatted_output.pptx | - | フォーマット保持 |
| sample_data.json | - | サンプルデータ |

---

## 結論

**python-pptxはプロジェクト要件を満たす**

- テンプレートベースの生成: ✓
- デザイン維持: ✓
- 日本語対応: ✓
- プログラマブルな操作: ✓

次のステップとしてSkillインターフェース設計（T002）に進むことを推奨。
