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
