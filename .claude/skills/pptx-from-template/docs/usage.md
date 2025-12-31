# 使用方法詳細

## コマンドラインオプション

```
python -m scripts.generate_pptx [OPTIONS]

オプション:
  -t, --template PATH   テンプレート.pptxファイル（省略時: 新規作成）
  -d, --data PATH       データファイル（JSON/YAML）[必須]
  -o, --output PATH     出力ファイルパス（省略時: output_日時.pptx）
  -f, --force           既存ファイルを上書き
```

## データファイル形式

### 基本構造

```json
{
  "metadata": {
    "title": "プレゼン全体のタイトル",
    "author": "作成者",
    "date": "2025-01-01"
  },
  "placeholders": {
    "key": "value"
  },
  "slides": [...]
}
```

### スライドオブジェクト

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| layout | number | - | スライドレイアウト（0-10、デフォルト:1） |
| title | string | - | スライドタイトル |
| subtitle | string | - | サブタイトル（layout 0用） |
| content | array | - | 箇条書きコンテンツ |
| table | object | - | 表データ |
| image | string | - | 画像ファイルパス |
| shapes | array | - | フリーフォーム図形配列（下記参照） |

### 表データ形式

```json
{
  "table": {
    "headers": ["列1", "列2", "列3"],
    "rows": [
      ["行1データ1", "行1データ2", "行1データ3"],
      ["行2データ1", "行2データ2", "行2データ3"]
    ]
  }
}
```

### プレースホルダー置換

テンプレート内の`{{key}}`を`placeholders`の値で置換:

```json
{
  "placeholders": {
    "title": "月次報告",
    "date": "2025-01-15"
  }
}
```

### フリーフォーム図形（shapes配列）

`layout: 6`（Blank）と`shapes`配列を使用して、図形・画像・テキストを自由に配置できます。

```json
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
```

#### shapesタイプ一覧

| type | 説明 | 主なパラメータ |
|------|------|---------------|
| textbox | テキストボックス | left, top, width, height, text, font_size, bold, align, fill_color |
| image | 画像 | left, top, path, width, height |
| shape | 図形 | left, top, width, height, shape_type, fill_color, text, font_color |
| table | 表 | left, top, width, headers, rows |
| line | 線 | start_x, start_y, end_x, end_y, line_color, line_width |

#### shape_type一覧

`shape`タイプで使用可能な図形:
- 基本: rectangle, rounded_rectangle, oval, circle, triangle
- 矢印: right_arrow, left_arrow, up_arrow, down_arrow
- その他: pentagon, hexagon, star, callout, cloud, heart, lightning

#### 座標・サイズ単位

すべての座標とサイズはインチ単位です。標準的なスライドサイズは10インチ×7.5インチです。

## レイアウトインデックス詳細

| Index | Name | 説明 | 使用可能フィールド |
|-------|------|------|------------------|
| 0 | Title Slide | タイトルページ | title, subtitle |
| 1 | Title and Content | 本文スライド | title, content |
| 2 | Section Header | セクション区切り | title |
| 3 | Two Content | 2カラム | title, content |
| 4 | Comparison | 比較レイアウト | title, content |
| 5 | Title Only | タイトルのみ | title, table, image |
| 6 | Blank | 空白（フリーフォーム用） | shapes, table, image |
| 7 | Content with Caption | キャプション付き | title, content |
| 8 | Picture with Caption | 画像+キャプション | title, image |
| 9 | Title and Vertical Text | 縦書き | title, content |
| 10 | Vertical Title and Text | 縦書きタイトル | title, content |

## 出力メッセージ

### 成功時
```
✓ PowerPointファイルを生成しました

  出力: /path/to/output.pptx
  スライド数: 5

  スライド構成:
    1. タイトル (Title Slide)
    2. セクション1 (Title and Content)
    ...
```

### 警告あり
```
✓ PowerPointファイルを生成しました（警告あり）

  警告:
    - スライド3: 画像ファイルが見つかりません (images/chart.png)
```

### エラー時
```
✗ エラー: テンプレートファイルが見つかりません

  コード: E001
  詳細: パス: /nonexistent/template.pptx

  対処法:
    - ファイルパスが正しいか確認してください
```
