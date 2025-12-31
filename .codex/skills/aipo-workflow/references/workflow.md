# AIPO Workflow（Codex CLI向け）

## 使い分け（開始/継続）

1. **新規開始**: `programs/{project名}/` が無い → Sense（`layer.yaml`/`context.yaml`）から作る
2. **継続**: 既に存在 → `tasks.yaml` と `commands/` の状況から次アクションを決める

補足（Git前提）:
- `programs/{project名}/` は各プロジェクトの独立リポジトリとして扱う
- 大きめの更新（Focus/Discover/Deliver）ごとにコミットして履歴を残すと運用しやすい

## Sense（01）

目的: プロジェクトの前提を固め、以降の分解に耐える「Index」を作る。

出力（最低限）:
- `layer.yaml`: Goal / mode / owner / deadline / workflow_preset
- `context.yaml`: 参照ドキュメントの一覧（`context/` 配下のファイルを指す）

運用:
- 収集した情報は **`context/` にMarkdownで保存**し、`context.yaml` に要約＋パスを追記する。
- 既存リポジトリを扱う場合は、必ず「現状」と「制約」を分けて記録する（例: `01_overview.md`, `02_constraints.md`）。

## Focus（02）

目的: Goal を **SubLayer（委譲可能なサブゴール）** と **Task（このレイヤーで完結）** に分ける。

### Focus戦略（必須）

`tasks.yaml` に以下を必ず記録する:
- `focus_strategy`: `product_manager` / `system_architect` / `content_strategist` / `generic`
- `focus_strategy_reason`: 1〜2行
- `focus_strategy_confirmed_by`: `user` / `ai`

推奨:
- `workflow_preset = discovery` の場合は、原則 `product_manager` をデフォルトにする（ユーザー指定があれば優先）。

### Taskの必須要件

- `type` が `management` / `coordination` / `verification` の場合のみ `command: null` を許可
- 上記以外は必ず `command` を設定（例: `"T004_競合調査"`）
- 可能なら `command_template_ref` を設定し、無理なら `null`（Discoverで新規作成）

### セッション分割（推奨）

以下に該当する場合は、SubLayer単位でスレッド/セッションを分割して進める：
- SubLayer数 3以上
- タスク数 10以上
- 見積 2時間超
- 階層 3以上

## Discover（03）

目的: `tasks.yaml` から **実行手順（commands）** を生成する。

出力:
- `commands/{task_id}_{task_name}.md`

推奨フォーマット（最小）:
- 目的 / Doneの定義
- 入力（必要な情報・ファイル）
- 手順（コマンド例を含む）
- 成果物（生成/更新するファイル）
- リスク/注意点

## Deliver（04）

目的: `commands/*.md` に従ってタスクを実行し、成果物と進捗を残す。

運用:
- 実行した変更はリポジトリに反映し、`tasks.yaml` の `status` を更新する。
- 調査結果は `documents/` または `context/` に保存して、`context.yaml` から参照できるようにする。

## Operation（05）

目的: 反復処理をコマンド化し、同じ型の作業を量産できる状態にする。

例:
- 週次レビュー（未完了タスクの棚卸し）
- 競合調査の定期更新
- MVP要件の更新（学び反映）
