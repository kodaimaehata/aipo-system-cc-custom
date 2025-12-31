# T004: Pythonスクリプト実装

## Goal
python-pptxを使用したPPTX生成スクリプトを実装する。

## Type
Implementation

## Estimate
4h

---

## Phase 1 (AI): コア機能実装

### Step 1.1: プロジェクト構造
```
.claude/skills/pptx-from-template/
├── SKILL.md
├── scripts/
│   ├── __init__.py
│   ├── generate_pptx.py    # メインスクリプト
│   ├── template_parser.py  # テンプレート解析
│   └── data_handler.py     # データ処理
└── pyproject.toml          # 依存定義（uv用）
```

### Step 1.2: メイン機能実装
`generate_pptx.py`:
- テンプレート読み込み
- データファイル（JSON/YAML）読み込み
- プレースホルダー差し替え
- ファイル保存

### Step 1.3: プレースホルダー処理
- タイトル/サブタイトル
- 本文テキスト（箇条書き対応）
- 表データ
- 画像差し替え（パス指定）

### Step 1.4: エラーハンドリング実装
T002で設計したエラーハンドリングを実装

---

## HITL Phase (Human): コードレビュー

### 確認事項
- [ ] コードは読みやすいか
- [ ] エラーメッセージは分かりやすいか
- [ ] 日本語処理は正常か
- [ ] 追加したい機能はあるか

---

## Phase 2 (AI): リファクタリング・最適化

### 成果物
1. `.claude/skills/pptx-from-template/scripts/*.py`
2. `.claude/skills/pptx-from-template/pyproject.toml`

### 更新
- `tasks.yaml` の T004 status を `completed` に更新

---

## Instructions for aipo-deliver

1. T001の検証結果とT002の設計を参照
2. スクリプトディレクトリを作成
3. 各モジュールを実装
4. 単体テストを実行して動作確認
5. ユーザーにコードレビューを依頼
6. フィードバックを反映してリファクタリング
