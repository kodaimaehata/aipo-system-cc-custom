# T002: Skillインターフェース設計

## Goal
Claude Code skillの入力パラメータ、出力形式、エラーハンドリング方針を設計する。

## Type
HITL (Human-in-the-Loop)

## Estimate
2h

---

## Phase 1 (AI): インターフェース設計案作成

### Step 1.1: 入力パラメータ設計
以下の入力パラメータを定義：

```yaml
# 必須パラメータ
template_path: string  # テンプレート.pptxファイルのパス
output_path: string    # 出力ファイルのパス

# データ指定方法（いずれか）
data_file: string      # JSON/YAMLデータファイルのパス
data_inline: object    # インラインでのデータ指定

# オプション
overwrite: boolean     # 既存ファイルの上書き許可（default: false）
```

### Step 1.2: データ形式設計
プレースホルダー差し替え用のデータ形式：

```json
{
  "slides": {
    "1": {
      "title": "プレゼンテーションタイトル",
      "subtitle": "サブタイトル"
    },
    "2": {
      "title": "セクション1",
      "body": ["箇条書き1", "箇条書き2"]
    }
  },
  "global": {
    "author": "作成者名",
    "date": "2025-12-30"
  }
}
```

### Step 1.3: 出力形式設計
- 成功時: 生成されたファイルパスとサマリー
- 失敗時: エラーメッセージと対処方法

### Step 1.4: エラーハンドリング設計
| エラー種別 | 対応 |
|-----------|------|
| テンプレートファイル不存在 | 明確なエラーメッセージ |
| 無効なデータ形式 | バリデーションエラー詳細 |
| プレースホルダー不一致 | 警告＋スキップ or エラー |
| 書き込み権限なし | パス確認を促すメッセージ |

---

## HITL Phase (Human): 設計レビュー

### 確認事項
- [ ] 入力パラメータは十分か／過剰か
- [ ] データ形式は直感的か
- [ ] エラーハンドリングは適切か
- [ ] 追加したい機能はあるか

### 判断ポイント
- シンプルさと柔軟性のバランス
- 将来の拡張性

---

## Phase 2 (AI): 設計ドキュメント確定

### 成果物
1. `documents/interface_design.md` - インターフェース設計書

### 更新
- `tasks.yaml` の T002 status を `completed` に更新

---

## Instructions for aipo-deliver

1. T001の技術検証結果を踏まえてインターフェースを設計
2. 設計案をユーザーに提示し、フィードバックを収集
3. フィードバックを反映して設計書を確定
4. 設計書を `documents/interface_design.md` に保存
