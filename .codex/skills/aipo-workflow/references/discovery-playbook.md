# 新規事業ディスカバリー（市場調査→MVP）テンプレ

## 想定（workflow_preset = `discovery`）

このプリセットは「新規事業の仮説検証〜MVP計画/開発」向け。原則 `focus_strategy = product_manager` を推奨する。

## 分解の基本形（推奨）

Root Goal を以下の SubLayer に分ける（必要に応じて省略/統合）：

- **SG1: 市場/顧客リサーチ**（市場規模、競合、顧客課題の一次情報）
- **SG2: 課題・仮説の定義**（課題定義、仮説マップ、検証計画）
- **SG3: ソリューション/ポジショニング**（価値提案、差別化、ソリューションマップ）
- **SG4: MVP定義→実装計画**（MVPスコープ、PRD、KPI、バックログ/WBS）
- **SG5: MVP開発（必要なら）**（設計→実装→計測→学習）

## Root Layer に置きやすい Task（例）

管理・統括（command=null 許可）:
- T001: プロジェクト憲章/スコープ確定
- T002: 成功指標（KPI）と判断基準の定義
- T003: リサーチ設計（調査方針・質問票・対象）

実行系（command必須）:
- T010: 市場規模推定（TAM/SAM/SOM）
- T011: 競合調査（比較軸＋示唆）
- T012: ペルソナ作成
- T013: 課題定義（Problem Statement）
- T014: 仮説マップ作成
- T015: ソリューションマップ作成
- T016: ポジショニングステートメント作成
- T020: MVPスコープ定義（must/should/could）
- T021: MVP計測設計（イベント/KPI/ログ要件）
- T022: MVPバックログ作成（優先度付き）

## 代表成果物（documents/ 推奨）

- `documents/market_landscape.md`
- `documents/competitor_matrix.md`
- `documents/personas.md`
- `documents/problem_hypotheses.md`
- `documents/solution_options.md`
- `documents/positioning.md`
- `documents/mvp_spec.md`
- `documents/experiment_plan.md`

## 既存テンプレ（このリポジトリ内）の探し方

必要なときだけ `src/` から参照する（ファイル名はNotion由来で長いので検索前提）。

例:

```bash
rg -n \"ペルソナ\" \"src/aipo (AI-PO) system/CTX_command_templates/Discovery_templates\"
rg -n \"課題定義\" \"src/aipo (AI-PO) system/CTX_command_templates/Discovery_templates\"
rg -n \"競合調査\" \"src/aipo (AI-PO) system/CTX_command_templates/Research _templates\"
rg -n \"市場規模\" \"src/aipo (AI-PO) system/CTX_command_templates/Research _templates\"
```

## 注意（ネットワーク制約）

市場/競合リサーチでWeb参照が必要な場合は、ネットワーク権限が必要になることがある。

その場合は:
- ユーザーから参考URL/資料をもらう（最優先）
- もしくは、ネットワーク実行の許可を求めてから進める
