---
name: pptx-from-template
description: Generate PowerPoint presentations from templates using python-pptx. Supports placeholder replacement, tables, Japanese text, and preserves template design. Triggers: /pptx, PowerPointを作成して, スライドを生成して, テンプレートからプレゼンを作って, pptxを作って
---

# pptx-from-template Skill

## Description
テンプレート.pptxファイルを基に、PowerPointプレゼンテーションを生成するスキル。

**2つの動作モード:**
1. **コンテキスト生成モード**: ユーザーの自然言語入力からスライドデータを自動生成
2. **データファイルモード**: 既存のJSON/YAMLデータファイルを使用

python-pptxライブラリを使用し、テンプレートのデザイン（フォント、色、レイアウト）を維持しながらコンテンツを生成する。

## Usage

### スラッシュコマンド
```
/pptx [template_path] [data_path] [output_path]
```

**例:**
```
# フルパス指定
/pptx templates/monthly_report.pptx data/january.json output/report_january.pptx

# デフォルトテンプレート使用
/pptx - data/january.json

# コンテキストから生成（データファイルなし）
/pptx
```

### 自然言語トリガー
以下のフレーズでスキルが起動:
- 「PowerPointを作成して」
- 「スライドを生成して」
- 「テンプレートからプレゼンを作って」
- 「pptxを作って」
- 「プレゼン資料を作って」
- 「〜についてのスライドを作って」

## Instructions

### Phase 0: モード判定
ユーザーの入力を分析し、動作モードを決定する:

| 条件 | モード |
|------|--------|
| データファイル（.json/.yaml）が指定されている | データファイルモード |
| 具体的なコンテンツ/トピックが提示されている | コンテキスト生成モード |
| 不明確な場合 | ユーザーに確認 |

### Phase 1: パラメータ収集

#### 必須パラメータ
| パラメータ | 必須 | 説明 |
|-----------|------|------|
| content | ✓* | プレゼンの内容（コンテキスト生成モード時） |
| data_path | ✓* | JSONまたはYAMLデータファイルのパス（データファイルモード時） |

*いずれか一方が必須

#### オプションパラメータ
| パラメータ | デフォルト | 説明 |
|-----------|------------|------|
| template_path | `templates/default.pptx` | テンプレート.pptxファイルのパス |
| output_path | `output_YYYYMMDD_HHMMSS.pptx` | 出力ファイルのパス |

#### デフォルトテンプレート
テンプレートが指定されない場合、以下の優先順位で検索:
1. `.claude/skills/pptx-from-template/templates/default.pptx`（ユーザーカスタマイズ可能）
2. 上記が存在しない場合は新規プレゼンテーションを作成

**カスタムデフォルトテンプレートの設定:**
```
.claude/skills/pptx-from-template/templates/default.pptx
```
このファイルを自社テンプレートに置き換えることで、デフォルトのデザインをカスタマイズできます。

### Phase 1b: コンテキスト解析（コンテキスト生成モード時）

ユーザーから提供されたコンテキストを分析し、適切なスライド構成を設計する。

#### 収集すべき情報
1. **プレゼンの目的**: 報告、提案、説明、教育など
2. **対象読者**: 経営層、チーム、顧客など
3. **主要なメッセージ**: 伝えたい核心的な内容
4. **含めるべきデータ**: 数値、表、図解が必要な情報

#### コンテキスト解析のガイドライン

**ユーザー入力例と解析:**
```
入力: 「来月の新製品発表会用のプレゼンを作って。製品名はX-100、特徴は省電力と高性能、価格は5万円」

解析結果:
- 目的: 製品発表（説得・興味喚起）
- 対象: 顧客・プレス
- 構成案:
  1. タイトルスライド: 製品名と発表日
  2. 製品概要: X-100の位置づけ
  3. 特徴1: 省電力性能
  4. 特徴2: 高性能
  5. 価格・発売情報
  6. まとめ/CTA
```

#### スライド構成の原則
- **1スライド1メッセージ**: 情報過多を避ける
- **視覚的バランス**: テキストと図形/画像の適切な配分
- **論理的な流れ**: 導入→本論→結論の構成
- **適切なレイアウト選択**: 内容に合ったlayout indexを選ぶ

#### 生成するJSONの構造決定

コンテキストから以下を判断:
1. 必要なスライド数（通常5-15枚）
2. 各スライドのレイアウト
3. タイトルと本文の内容
4. 表が必要な箇所
5. フリーフォーム（shapes）が効果的な箇所

### Phase 2: 入力検証
1. テンプレートファイルの存在確認（指定時）またはデフォルトテンプレートの確認
2. データファイルの存在確認とJSON/YAML構文検証（データファイルモード時）
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
| 6 | Blank | 空白（フリーフォーム用） |

### Phase 3b: フリーフォームレイアウト（shapes配列）
`layout: 6`（Blank）と`shapes`配列を使用して、図形・画像・テキストを自由に配置:

```json
{
  "slides": [
    {
      "layout": 6,
      "shapes": [
        {
          "type": "textbox",
          "left": 1.0,
          "top": 0.5,
          "width": 8.0,
          "height": 1.0,
          "text": "カスタムタイトル",
          "font_size": 32,
          "bold": true,
          "align": "center"
        },
        {
          "type": "image",
          "left": 1.5,
          "top": 2.0,
          "width": 4.0,
          "path": "images/diagram.png"
        },
        {
          "type": "shape",
          "shape_type": "rectangle",
          "left": 6.0,
          "top": 2.0,
          "width": 3.0,
          "height": 2.0,
          "fill_color": "#3366CC",
          "text": "ボックス",
          "font_color": "white"
        }
      ]
    }
  ]
}
```

#### shapesタイプ
| type | 説明 | 主なパラメータ |
|------|------|---------------|
| textbox | テキストボックス | left, top, width, height, text, font_size, bold, align, fill_color |
| image | 画像 | left, top, path, width/height |
| shape | 図形 | left, top, width, height, shape_type, fill_color, text |
| table | 表 | left, top, width, headers, rows |
| line | 線 | start_x, start_y, end_x, end_y, line_color, line_width |

#### shape_type一覧
rectangle, rounded_rectangle, oval, circle, triangle, right_arrow, left_arrow, up_arrow, down_arrow, pentagon, hexagon, star, callout, cloud, heart, lightning

### Phase 4: 生成実行

#### コンテキスト生成モードの場合
1. Phase 1bで設計したスライド構成に基づき、JSONデータを生成
2. 一時ファイルにJSONを保存
3. スクリプトを実行

#### 実行コマンド
```bash
# テンプレート指定あり
uv run python .claude/skills/pptx-from-template/scripts/generate_pptx.py \
  --template <template_path> \
  --data <data_path> \
  --output <output_path>

# デフォルトテンプレート使用（--templateを省略）
uv run python .claude/skills/pptx-from-template/scripts/generate_pptx.py \
  --data <data_path> \
  --output <output_path>
```

スクリプトは以下の順序でテンプレートを検索:
1. `--template`で指定されたパス
2. `.claude/skills/pptx-from-template/templates/default.pptx`
3. 上記いずれも存在しない場合、新規プレゼンテーションを作成

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
| W002 | 表データ空 | 表を生成しない |
| W003 | レイアウトインデックス範囲外 | デフォルト(1)を使用 |
| W004 | コンテンツ長すぎ | 警告のみ（切り詰めなし） |

## Dependencies
- Python >= 3.11
- python-pptx >= 1.0.2

## File Structure
```
.claude/skills/pptx-from-template/
├── SKILL.md              # このファイル
├── pyproject.toml        # 依存関係
├── scripts/
│   ├── generate_pptx.py  # メイン生成スクリプト
│   ├── data_handler.py   # データ処理
│   └── template_parser.py # テンプレート解析
├── templates/
│   ├── default.pptx      # デフォルトテンプレート（ユーザー置換可）
│   ├── sample_template.pptx  # サンプルテンプレート
│   └── sample_data.json      # サンプルデータ
└── docs/
    ├── usage.md          # 使用方法詳細
    ├── examples.md       # 設定例集
    └── troubleshooting.md # トラブルシューティング
```

### デフォルトテンプレートのカスタマイズ
`templates/default.pptx`を自社のテンプレートに置き換えることで、`/pptx`実行時のデフォルトデザインを変更できます。

## Examples

### 例1: コンテキスト生成モード（推奨）
```
ユーザー: 「新製品X-100の発表用プレゼンを作って。特徴は省電力と高性能、価格は5万円」

Claude: 以下の構成でプレゼンを作成します:
  1. タイトル: 新製品X-100発表
  2. 製品概要
  3. 特徴1: 省電力性能
  4. 特徴2: 高性能
  5. 価格・発売情報
  6. まとめ

  よろしいですか？

ユーザー: 「OK」

Claude: [JSONデータ生成 → スクリプト実行]
  ✓ PowerPointファイルを生成しました
  出力: output_20251231_143052.pptx
```

### 例2: データファイルモード
```
/pptx templates/monthly_report.pptx reports/january_data.json
```

### 例3: デフォルトテンプレート使用
```
ユーザー: 「data/quarterly_report.jsonからプレゼンを作って」
Claude: デフォルトテンプレートを使用して生成します。
  [生成実行] ✓ 完了
```

### 例4: 詳細なコンテキスト指定
```
ユーザー: 「経営会議向けに、以下の内容でプレゼンを作って:
- 2024年度の売上実績（前年比115%）
- 主要3製品の貢献度
- 2025年度の目標と戦略
- 投資計画」

Claude: 経営層向けのフォーマルな構成で作成します:

  1. タイトル: 2024年度実績報告
  2. エグゼクティブサマリー
  3. 売上実績: 前年比115%達成
  4. 製品別貢献度（表形式）
  5. 2025年度目標
  6. 成長戦略
  7. 投資計画
  8. まとめ

  [生成実行後]
  ✓ 8枚のスライドを生成しました
```

### 例5: フリーフォーム図形を活用
```
ユーザー: 「組織図を含むプレゼンを作って」

Claude: shapesを使用して組織図スライドを作成します。

[生成されるJSON（抜粋）]
{
  "layout": 6,
  "shapes": [
    {"type": "shape", "shape_type": "rectangle", "left": 4, "top": 1, ...},
    {"type": "shape", "shape_type": "rectangle", "left": 1, "top": 3, ...},
    ...
  ]
}
```

### 例6: コマンドライン直接実行
```bash
cd .claude/skills/pptx-from-template

# デフォルトテンプレート使用
uv run python -m scripts.generate_pptx \
  --data data/report.json \
  --output output/final_report.pptx

# テンプレート指定
uv run python -m scripts.generate_pptx \
  --template templates/custom.pptx \
  --data data/report.json \
  --output output/final_report.pptx
```
