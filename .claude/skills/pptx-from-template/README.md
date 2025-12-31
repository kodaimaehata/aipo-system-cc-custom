# pptx-from-template

テンプレートからPowerPointプレゼンテーションを生成するClaude Code skill。

## 概要

- テンプレート.pptxを基にしたPPTX生成
- JSON/YAMLデータからの自動スライド生成
- プレースホルダー（`{{key}}`）の置換
- 表・画像のサポート
- 日本語完全対応

## クイックスタート

### 1. スラッシュコマンド

```
/pptx templates/report.pptx data/report.json output/result.pptx
```

### 2. 自然言語

```
「PowerPointを作成して」
「スライドを生成して」
「テンプレートからプレゼンを作って」
```

### 3. 直接実行

```bash
cd .claude/skills/pptx-from-template
uv run python -m scripts.generate_pptx --data data.json --output output.pptx
```

## データ形式

```json
{
  "slides": [
    {
      "layout": 0,
      "title": "プレゼンタイトル",
      "subtitle": "サブタイトル"
    },
    {
      "layout": 1,
      "title": "コンテンツスライド",
      "content": ["箇条書き1", "箇条書き2"]
    },
    {
      "layout": 5,
      "title": "表スライド",
      "table": {
        "headers": ["列1", "列2"],
        "rows": [["データ1", "データ2"]]
      }
    }
  ]
}
```

## レイアウト

| Index | Name | 用途 |
|-------|------|------|
| 0 | Title Slide | タイトルページ |
| 1 | Title and Content | 本文スライド |
| 2 | Section Header | セクション区切り |
| 5 | Title Only | タイトルのみ（表・画像用） |
| 6 | Blank | 空白 |

## インストール

```bash
cd .claude/skills/pptx-from-template
uv sync
```

YAML対応が必要な場合:
```bash
uv add pyyaml
```

## ドキュメント

- [使用方法詳細](docs/usage.md)
- [設定例集](docs/examples.md)
- [トラブルシューティング](docs/troubleshooting.md)

## 依存関係

- Python >= 3.11
- python-pptx >= 1.0.2
- PyYAML >= 6.0 (オプション)
