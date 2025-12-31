# T007: ドキュメント整備

## Goal
使用方法、設定例、トラブルシューティングのドキュメントを作成する。

## Type
Documentation

## Estimate
1h

---

## Phase 1 (AI): ドキュメント作成

### Step 1.1: README.md
`.claude/skills/pptx-from-template/README.md`:
- 概要
- インストール方法（uv add python-pptx）
- クイックスタート
- 使用例

### Step 1.2: 使用方法詳細
`docs/usage.md`:
- 入力パラメータの詳細説明
- データ形式のリファレンス
- 各スライドタイプの使い方

### Step 1.3: 設定例集
`docs/examples.md`:
- 基本的な使用例
- カスタムテンプレートの作り方
- 複雑なデータ構造の例

### Step 1.4: トラブルシューティング
`docs/troubleshooting.md`:
- よくあるエラーと対処法
- FAQ

---

## HITL Phase (Human): ドキュメントレビュー

### 確認事項
- [ ] 説明は分かりやすいか
- [ ] 例は十分か
- [ ] 誤字脱字はないか
- [ ] 追加すべき内容はあるか

---

## Phase 2 (AI): 修正・公開

### 成果物
1. `.claude/skills/pptx-from-template/README.md`
2. `.claude/skills/pptx-from-template/docs/`

### 更新
- `tasks.yaml` の T007 status を `completed` に更新

---

## Instructions for aipo-deliver

1. skill全体の使用方法をドキュメント化
2. 具体的な使用例を複数作成
3. トラブルシューティングガイドを作成
4. ユーザーにレビューを依頼
5. フィードバックを反映
