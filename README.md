# AIPO Workflow（Codex CLI）

このリポジトリは、AIPO（AI Product Owner）方式のドキュメント一式（`src/`）と、Codex CLI で同様の進め方を行うためのリポジトリ内スキル（`.codex/skills/`）を提供します。

## スキル（`aipo-workflow`）

- 置き場所: `.codex/skills/aipo-workflow/`
- Codex は REPO スコープとして `$CWD/.codex/skills` / `$REPO_ROOT/.codex/skills` を探索します。基本はこのリポジトリ内で `codex` を起動するだけで自動認識されます（反映には再起動が必要）。
- 目的: Sense→Focus→Discover→Deliver→Operation を、**ファイル成果物**として残しながら回す。

## 使い方（エージェントへの指示テンプレ）

前提:
- **Pythonコマンドを手元で叩かず**、Codex（エージェント）に作業させる想定です。
- 意図的にスキルを使いたいときは、プロンプト先頭に **`$aipo-workflow`** を付けてください（スキル強制トリガー）。
- 成果物は `programs/<project名>/` に作成します（各プロジェクトは **独立Gitリポジトリ**、親リポジトリは追跡しません）。

### ユースケース1: 新規プロジェクト開始（汎用）

```
$aipo-workflow
新規プロジェクトを開始してください。

project: <project名>  # programs/<project名>/ を作る
preset: general       # 汎用
goal: <Goalを1行で>
owner: <owner名>
deadline: <YYYY-MM-DD or null>

要件:
- programs/<project>/ を初期化し、layer.yaml/context.yaml/tasks.yaml を作成
- programs/<project>/ は独立Gitリポジトリとして git init（不要なら確認してからスキップ）
- 次にやるべきSense/FocusのNext Actionを提案
```

### ユースケース2: 新規プロジェクト開始（新規事業ディスカバリー: 市場調査→MVP）

```
$aipo-workflow
新規事業ディスカバリー用の新規プロジェクトを開始してください。

project: <project名>
preset: discovery
goal: <例: ◯◯市場で△△を解決するMVPを作る>
owner: <owner名>
deadline: <YYYY-MM-DD or null>

要件:
- programs/<project>/ を初期化（独立Gitリポジトリ）
- discovery前提で、最初に埋めるべきcontext項目（市場/顧客/競合/制約）を context/ に作成
- Focusの分解方針（推奨: product_manager）を tasks.yaml に記録する準備をする
```

### ユースケース3: 既存プロジェクトを再開（状況確認→次アクション提示）

```
$aipo-workflow
programs/<project名>/ を再開してください。

やってほしいこと:
1) layer.yaml/context.yaml/tasks.yaml を読み、破綻（必須フィールド不足など）があれば修正案を提示
2) 未着手のP0タスクとブロッカーを要約
3) 次のアクション候補を3つ提示（例: Focusで再分解 / Discoverでcommands生成 / DeliverでTxxx実行）
```

### ユースケース4: Focus（タスク分解を作る / 更新する）

```
$aipo-workflow
Focusを実行して、tasks.yaml を更新してください（SubLayerとTaskに分解）。

対象: programs/<project名>/
制約/前提: <あれば箇条書き>

要件:
- focus_strategy / focus_strategy_reason / focus_strategy_confirmed_by を必ず埋める
- 実行系Taskは command を必須（management/coordination/verification のみ command:null 可）
- まず分解案を提示→こちらのOK後に tasks.yaml を確定更新
```

### ユースケース5: Discover（commands生成）

```
$aipo-workflow
Discoverを実行して、programs/<project名>/commands/ を生成してください。

対象: programs/<project名>/
範囲: P0のtasksのみ（まずは最小）

要件:
- tasks.yaml の command / command_template_ref を使って commands/*.md を作成
- テンプレ参照が必要なら src/aipo (AI-PO) system/CTX_command_templates/ を検索して流用
- 生成後、次に実行すべきタスク候補（Deliver）を提示
```

### ユースケース6: Deliver（特定タスクを実行）

```
$aipo-workflow
Deliverを実行して、次のタスクを完了させてください。

対象: programs/<project名>/
タスク: <例: T003_競合調査>

要件:
- commands/<タスク>.md の手順に沿って実行（不足があれば補完してから）
- 成果物は programs/<project名>/documents/ 等に保存
- tasks.yaml の status を更新し、必要なら context.yaml に参照を追加
```

### ユースケース7: Operation（週次レビュー / 棚卸し）

```
$aipo-workflow
週次レビューを実行してください（Operation）。

対象: programs/<project名>/
出力:
- 進捗サマリ（完了/未完了/P0）
- ブロッカーと次に外すべき順序
- 次の1週間の推奨プラン（最大5項目）
```

## 参照（スキーマ/ルール）

- 成果物スキーマ: `.codex/skills/aipo-workflow/references/program-schema.md`
- Codex CLI向けワークフロー: `.codex/skills/aipo-workflow/references/workflow.md`
- 新規事業ディスカバリーの分解テンプレ: `.codex/skills/aipo-workflow/references/discovery-playbook.md`

## 注意（YAML形式）

`layer.yaml` / `context.yaml` / `tasks.yaml` は **JSON互換YAML（=純JSON）** として運用します（パーサ依存を避け、`python3` の `json` で検証・更新するため）。
