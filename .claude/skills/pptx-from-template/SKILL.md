---
name: pptx-from-template
description: Generate PowerPoint presentations from templates using python-pptx. Supports placeholder replacement, tables, Japanese text, and preserves template design. Triggers: /pptx, PowerPointを作成して, スライドを生成して, テンプレートからプレゼンを作って, pptxを作って
---

# pptx-from-template Skill

## Description
テンプレート.pptxファイルを基に、指定されたデータでPowerPointプレゼンテーションを生成するスキル。python-pptxライブラリを使用し、テンプレートのデザイン（フォント、色、レイアウト）を維持しながらコンテンツを差し替える。

## Usage

### スラッシュコマンド
```
/pptx <template_path> <data_path> [output_path]
```

**例:**
```
/pptx templates/monthly_report.pptx data/january.json output/report_january.pptx
```

### 自然言語トリガー
以下のフレーズでスキルが起動:
- 「PowerPointを作成して」
- 「スライドを生成して」
- 「テンプレートからプレゼンを作って」
- 「pptxを作って」

## Instructions

### Phase 1: パラメータ収集
ユーザーから以下の情報を収集する（不足していれば質問する）:

| パラメータ | 必須 | 説明 |
|-----------|------|------|
| template_path | ✓ | テンプレート.pptxファイルのパス |
| data_path | ✓ | JSONまたはYAMLデータファイルのパス |
| output_path | - | 出力ファイルのパス（省略時: `output_YYYYMMDD_HHMMSS.pptx`） |

### Phase 2: 入力検証
1. テンプレートファイルの存在確認
2. データファイルの存在確認とJSON/YAML構文検証
3. 出力先ディレクトリの書き込み権限確認
4. 既存ファイル上書きの確認（--forceフラグがない場合）

### Phase 3: データ形式
データファイルは以下のスライドベース形式に従う:

```json
{
  "metadata": {
    "title": "プレゼンテーションタイトル",
    "author": "作成者名",
    "date": "2025-12-30"
  },
  "slides": [
    {
      "layout": 0,
      "title": "メインタイトル",
      "subtitle": "サブタイトル"
    },
    {
      "layout": 1,
      "title": "セクション1",
      "content": [
        "箇条書き項目1",
        "箇条書き項目2"
      ]
    },
    {
      "layout": 5,
      "title": "表データ",
      "table": {
        "headers": ["名前", "部署", "役職"],
        "rows": [
          ["山田太郎", "開発部", "エンジニア"],
          ["鈴木花子", "営業部", "マネージャー"]
        ]
      }
    }
  ]
}
```

#### レイアウトインデックス
| Index | Name | 用途 |
|-------|------|------|
| 0 | Title Slide | タイトルページ |
| 1 | Title and Content | 本文スライド |
| 2 | Section Header | セクション区切り |
| 3 | Two Content | 2カラム |
| 5 | Title Only | タイトルのみ |
| 6 | Blank | 空白（カスタム配置用） |

### Phase 4: 生成実行
1. スクリプトを実行:
   ```bash
   uv run python .claude/skills/pptx-from-template/scripts/generate_pptx.py \
     --template <template_path> \
     --data <data_path> \
     --output <output_path>
   ```
2. 実行結果を確認し、成功/失敗をユーザーに報告

### Phase 5: 結果報告

#### 成功時
```
✓ PowerPointファイルを生成しました

  出力: /path/to/output.pptx
  スライド数: 5

  スライド構成:
    1. メインタイトル (Title Slide)
    2. セクション1 (Title and Content)
    3. 表データ (Title Only)
    ...
```

#### 警告あり成功
```
✓ PowerPointファイルを生成しました（警告あり）

  出力: /path/to/output.pptx
  スライド数: 5

  警告:
    - スライド3: 画像ファイルが見つかりません (images/chart.png)
    - スライド5: 表データが空です
```

#### 失敗時
```
✗ エラー: PowerPointの生成に失敗しました

  原因: テンプレートファイルが見つかりません
  パス: /path/to/template.pptx

  対処法:
    - ファイルパスが正しいか確認してください
    - ファイルが存在するか確認してください
```

## Error Handling

### エラーコード
| コード | 種別 | 対処法 |
|--------|------|--------|
| E001 | テンプレート不存在 | パスを確認 |
| E002 | データファイル不存在 | パスを確認 |
| E003 | JSON/YAML構文エラー | 構文を確認 |
| E004 | 書き込み権限なし | 権限を確認 |
| E005 | 既存ファイル上書き | --forceで上書き |
| E006 | テンプレート形式不正 | ファイルを確認 |

### 警告コード
| コード | 種別 | 動作 |
|--------|------|------|
| W001 | 画像ファイル不存在 | スキップして続行 |
| W002 | 表データ空 | 空の表を生成 |
| W003 | レイアウトインデックス範囲外 | デフォルト(1)を使用 |
| W004 | コンテンツ長すぎ | 切り詰めて警告 |

## Dependencies
- Python >= 3.11
- python-pptx >= 1.0.2

## File Structure
```
.claude/skills/pptx-from-template/
├── SKILL.md              # このファイル
├── scripts/
│   ├── generate_pptx.py  # メイン生成スクリプト
│   └── utils.py          # ユーティリティ
├── templates/
│   └── sample.pptx       # サンプルテンプレート
└── pyproject.toml        # 依存関係
```

## Examples

### 例1: 月次レポート生成
```
/pptx templates/monthly_report.pptx reports/january_data.json
```

### 例2: 自然言語での依頼
```
ユーザー: 「先月の売上データからPowerPointを作って」
Claude: 「どのテンプレートを使用しますか？」
ユーザー: 「templates/sales_report.pptxを使って」
Claude: 「データファイルはありますか？」
ユーザー: 「data/sales_202501.jsonを使って」
Claude: [生成実行] ✓ 完了
```

### 例3: コマンドライン直接実行
```bash
uv run python -m pptx_from_template \
  --template templates/report.pptx \
  --data data/report.json \
  --output output/final_report.pptx
```
