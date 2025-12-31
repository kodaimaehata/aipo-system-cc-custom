# 設定例集

## 例1: 基本的な月次レポート

```json
{
  "slides": [
    {
      "layout": 0,
      "title": "2025年1月度 月次報告",
      "subtitle": "営業部\n2025年1月15日"
    },
    {
      "layout": 2,
      "title": "売上報告"
    },
    {
      "layout": 1,
      "title": "今月のハイライト",
      "content": [
        "売上目標達成率: 105%",
        "新規顧客獲得: 15社",
        "リピート率: 78%"
      ]
    },
    {
      "layout": 5,
      "title": "部門別売上",
      "table": {
        "headers": ["部門", "目標", "実績", "達成率"],
        "rows": [
          ["営業第一部", "500万", "520万", "104%"],
          ["営業第二部", "300万", "315万", "105%"],
          ["オンライン", "200万", "225万", "112%"]
        ]
      }
    },
    {
      "layout": 1,
      "title": "来月の計画",
      "content": [
        "新製品キャンペーン開始",
        "展示会出展",
        "顧客満足度調査実施"
      ]
    }
  ]
}
```

## 例2: 技術プレゼンテーション

```json
{
  "slides": [
    {
      "layout": 0,
      "title": "新システム導入提案",
      "subtitle": "IT部門"
    },
    {
      "layout": 1,
      "title": "背景と課題",
      "content": [
        "現行システムの老朽化",
        "メンテナンスコストの増加",
        "新機能追加の困難さ"
      ]
    },
    {
      "layout": 5,
      "title": "システム比較",
      "table": {
        "headers": ["項目", "現行", "新システム"],
        "rows": [
          ["処理速度", "100ms", "10ms"],
          ["可用性", "99.5%", "99.99%"],
          ["月額コスト", "50万円", "30万円"]
        ]
      }
    },
    {
      "layout": 1,
      "title": "導入スケジュール",
      "content": [
        "Phase 1: 設計 (1月)",
        "Phase 2: 開発 (2-3月)",
        "Phase 3: テスト (4月)",
        "Phase 4: 移行 (5月)"
      ]
    }
  ]
}
```

## 例3: プレースホルダー置換

テンプレートファイル（template.pptx）に以下のプレースホルダーを配置:
- `{{company_name}}`
- `{{report_title}}`
- `{{date}}`
- `{{author}}`

データファイル:
```json
{
  "placeholders": {
    "company_name": "株式会社サンプル",
    "report_title": "第4四半期決算報告",
    "date": "2025年1月20日",
    "author": "財務部 山田太郎"
  }
}
```

実行:
```bash
uv run python -m scripts.generate_pptx \
  --template template.pptx \
  --data data.json \
  --output output.pptx
```

## 例4: YAML形式

```yaml
slides:
  - layout: 0
    title: YAMLでの設定例
    subtitle: より読みやすいフォーマット

  - layout: 1
    title: YAMLのメリット
    content:
      - JSONより読みやすい
      - コメントが書ける
      - 複数行テキストが簡単

  - layout: 5
    title: 比較表
    table:
      headers:
        - 形式
        - 可読性
        - コメント
      rows:
        - [JSON, 普通, 不可]
        - [YAML, 高い, 可能]
```

※ YAML使用時は `uv add pyyaml` が必要

## 例5: フリーフォーム図形（shapes）

自由な位置に図形やテキストを配置:

```json
{
  "slides": [
    {
      "layout": 0,
      "title": "会社説明資料",
      "subtitle": "株式会社サンプル"
    },
    {
      "layout": 6,
      "shapes": [
        {
          "type": "textbox",
          "left": 0.5,
          "top": 0.3,
          "width": 9.0,
          "height": 1.0,
          "text": "会社概要",
          "font_size": 36,
          "bold": true,
          "align": "center"
        },
        {
          "type": "shape",
          "shape_type": "rounded_rectangle",
          "left": 0.5,
          "top": 1.5,
          "width": 4.0,
          "height": 2.5,
          "fill_color": "#E3F2FD",
          "text": "ミッション\n\n顧客価値の最大化",
          "font_color": "#1565C0"
        },
        {
          "type": "shape",
          "shape_type": "rounded_rectangle",
          "left": 5.0,
          "top": 1.5,
          "width": 4.0,
          "height": 2.5,
          "fill_color": "#E8F5E9",
          "text": "ビジョン\n\n業界No.1を目指す",
          "font_color": "#2E7D32"
        },
        {
          "type": "line",
          "start_x": 5.0,
          "start_y": 4.5,
          "end_x": 5.0,
          "end_y": 5.5,
          "line_color": "#666666",
          "line_width": 2
        },
        {
          "type": "shape",
          "shape_type": "down_arrow",
          "left": 4.0,
          "top": 5.0,
          "width": 2.0,
          "height": 1.5,
          "fill_color": "#FFA726",
          "text": "成長"
        }
      ]
    },
    {
      "layout": 6,
      "shapes": [
        {
          "type": "textbox",
          "left": 0.5,
          "top": 0.3,
          "width": 9.0,
          "height": 0.8,
          "text": "組織図",
          "font_size": 32,
          "bold": true,
          "align": "center"
        },
        {
          "type": "shape",
          "shape_type": "rectangle",
          "left": 3.5,
          "top": 1.2,
          "width": 3.0,
          "height": 0.8,
          "fill_color": "#1976D2",
          "text": "代表取締役",
          "font_color": "white"
        },
        {
          "type": "shape",
          "shape_type": "rectangle",
          "left": 0.5,
          "top": 2.8,
          "width": 2.5,
          "height": 0.8,
          "fill_color": "#42A5F5",
          "text": "営業部",
          "font_color": "white"
        },
        {
          "type": "shape",
          "shape_type": "rectangle",
          "left": 3.75,
          "top": 2.8,
          "width": 2.5,
          "height": 0.8,
          "fill_color": "#42A5F5",
          "text": "開発部",
          "font_color": "white"
        },
        {
          "type": "shape",
          "shape_type": "rectangle",
          "left": 7.0,
          "top": 2.8,
          "width": 2.5,
          "height": 0.8,
          "fill_color": "#42A5F5",
          "text": "管理部",
          "font_color": "white"
        },
        {
          "type": "table",
          "left": 0.5,
          "top": 4.5,
          "width": 9.0,
          "headers": ["部門", "人数", "担当"],
          "rows": [
            ["営業部", "15名", "国内・海外営業"],
            ["開発部", "25名", "製品開発・保守"],
            ["管理部", "10名", "人事・経理・総務"]
          ]
        }
      ]
    }
  ]
}
```

## 例6: 図形と画像の組み合わせ

画像と図形を組み合わせたレイアウト:

```json
{
  "slides": [
    {
      "layout": 6,
      "shapes": [
        {
          "type": "textbox",
          "left": 0.5,
          "top": 0.5,
          "width": 9.0,
          "height": 1.0,
          "text": "製品紹介",
          "font_size": 36,
          "bold": true
        },
        {
          "type": "image",
          "left": 0.5,
          "top": 1.8,
          "width": 4.5,
          "path": "images/product.png"
        },
        {
          "type": "textbox",
          "left": 5.5,
          "top": 1.8,
          "width": 4.0,
          "height": 4.0,
          "text": "主な特徴:\n\n• 高性能プロセッサ搭載\n• 省電力設計\n• コンパクトサイズ\n• 5年保証付き",
          "font_size": 18
        },
        {
          "type": "shape",
          "shape_type": "star",
          "left": 0.5,
          "top": 5.5,
          "width": 1.5,
          "height": 1.5,
          "fill_color": "#FFD700",
          "text": "NEW",
          "font_color": "#333333"
        }
      ]
    }
  ]
}
```

## カスタムテンプレートの作り方

1. **PowerPointで作成**
   - スライドマスター（表示 > スライドマスター）を編集
   - フォント、色、背景を設定
   - 各レイアウトをカスタマイズ

2. **プレースホルダーを配置**
   - テキストボックスに `{{key}}` 形式で記述
   - 例: `{{title}}`, `{{date}}`, `{{author}}`

3. **.pptx形式で保存**

4. **テスト**
   ```bash
   uv run python -m scripts.generate_pptx \
     --template my_template.pptx \
     --data test_data.json
   ```
