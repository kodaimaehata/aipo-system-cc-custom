# AIPO Workflow（Codex CLI / Claude Code）

このリポジトリは、AIPO（AI Product Owner）方式のドキュメント一式（`src/`）と、Codex CLI および Claude Code で同様の進め方を行うためのリポジトリ内スキルを提供します。

## 謝辞・オリジナル

本システムは、**みやっちさん（[@miyatti](https://x.com/miyatti)）** が公開した **Notion AI 用の AIPO システム** をベースに、Codex CLI および Claude Code の Agent Skills として動作するよう改変したものです。

- オリジナル: [AIPO (AI-PO) system - Notion](https://explaza.notion.site/aipo-AI-PO-system-af526889dc9e4c089d95a6df90e20946)

---

## Codex CLI の場合

### スキル構成（AIPO）

- 置き場所: `.codex/skills/`
- Codex は REPO スコープとして `$CWD/.codex/skills` / `$REPO_ROOT/.codex/skills` を探索します。基本はこのリポジトリ内で `codex` を起動するだけで自動認識されます（反映には再起動が必要）。
- 目的: Sense→Focus→Discover→Deliver（→Operation）を、**ファイル成果物**として残しながら回す。

```
.codex/skills/
├── aipo-core/        # 共通ルール（スキーマ/ディレクトリ解決/JSON互換YAML）
├── aipo-sense/       # Sense フェーズ（初期化/前提整備）
├── aipo-focus/       # Focus フェーズ（分解して tasks.yaml 更新）
├── aipo-discover/    # Discover フェーズ（commands 雛形生成＋テンプレ適用）
├── aipo-deliver/     # Deliver フェーズ（タスク実行＋status更新）
└── aipo-workflow/    # エンジン（scripts + references）
```

### 使い方（エージェントへの指示テンプレ）

前提:
- **Pythonコマンドを手元で叩かず**、Codex（エージェント）に作業させる想定です。
- 意図的にスキルを使いたいときは、プロンプト先頭に **`$aipo-sense` / `$aipo-focus` / `$aipo-discover` / `$aipo-deliver`** を付けてください（スキル強制トリガー）。
- 状況確認やフェーズ横断の相談（次アクション提示など）は **`$aipo-workflow`** を使うとまとめて扱えます。
- 成果物は `programs/<project名>/` に作成します（各プロジェクトは **独立Gitリポジトリ**、親リポジトリは追跡しません）。

### ユースケース1: aipo-sense（新規プロジェクト開始: 汎用）
プロンプト例:
```
$aipo-sense
project: <project名>
goal: <Goalを1行で>
# preset: general        # 推奨（省略時も汎用）
# owner: <owner名>       # 任意（省略可）
# deadline: <YYYY-MM-DD> # 任意（省略可）
```

実行すると何が起こるか:
- `programs/<project>/` を作成し、AIPOの成果物一式（JSON互換YAML）を初期化する（必要に応じて `git init`）。
- 次にやるべきフェーズ（例: Focusで分解、Discoverでcommands生成）の提案が出る。

生成される成果物（例）:
- `programs/<project>/layer.yaml`: Goal / owner / deadline / preset など、レイヤー定義
- `programs/<project>/context.yaml`: `context/*.md` の一覧（要約とパス）＋親文脈参照（rootは `null`）
- `programs/<project>/tasks.yaml`: 初期の分解計画（空の tasks/sublayers、`focus_strategy` の初期値など）
- `programs/<project>/context/01_overview.md` / `02_constraints.md`: 前提情報の記入用テンプレ

### ユースケース2: aipo-sense（新規事業ディスカバリー開始: 市場調査→MVP）
プロンプト例:
```
$aipo-sense
preset: discovery
project: <project名>
goal: <例: ◯◯市場で△△を解決するMVPを作る>
# owner: <owner名>       # 任意
# deadline: <YYYY-MM-DD> # 任意
```

実行すると何が起こるか:
- `programs/<project>/` をディスカバリー前提で初期化し、調査〜MVPに繋げやすい状態にする（`focus_strategy` もディスカバリー向け初期値になる）。

生成される成果物（例）:
- `programs/<project>/layer.yaml`: `workflow_preset: "discovery"` を含むレイヤー定義
- `programs/<project>/tasks.yaml`: `focus_strategy` がディスカバリー向け（例: `product_manager`）の初期値になる
- `programs/<project>/context/01_overview.md`: 背景/目的/スコープの叩き台
- `programs/<project>/context/02_constraints.md`: 期限/予算/技術/法務などの制約の叩き台

### ユースケース3: aipo-focus（タスク分解を作る / 更新する）
プロンプト例:
```
$aipo-focus
layer: programs/<project名>/
# constraints: <期限/予算/技術/法務など> # 任意（あれば書く）
```

実行すると何が起こるか:
- Goalを SubLayer / Task に分解し、`tasks.yaml` を更新する（`focus_strategy*` を必ず埋める）。
- SubLayer を作った場合、必要に応じて sublayer フォルダ雛形も生成する（`sync_sublayers.py`）。

生成される成果物（例）:
- `programs/<project>/tasks.yaml`: 分解結果（`sublayers[]` と `tasks[]`、各Taskの `command`/`command_template_ref` など）
- `programs/<project>/sublayers/<SG...>/layer.yaml` など: SubLayerの雛形（生成する場合）

### ユースケース4: aipo-discover（commands生成）
プロンプト例:
```
$aipo-discover
layer: programs/<project名>/
```

実行すると何が起こるか:
- `tasks.yaml` から、実行手順の雛形 `commands/*.md` を生成し、必要ならテンプレ（`command_template_ref`）を探して内容を具体化する。

生成される成果物（例）:
- `programs/<project>/commands/Txxx_....md`: Goal / Done / Inputs / Steps / Outputs / Notes を含むタスク実行手順書

### ユースケース5: aipo-deliver（特定タスクを実行）
プロンプト例:
```
$aipo-deliver
layer: programs/<project名>/
task: <例: T003>
```

実行すると何が起こるか:
- 対象Taskの `commands/*.md`（無ければDiscoverで生成）に沿って作業を進め、成果物を保存し、`tasks.yaml.status` を更新する。

生成される成果物（例）:
- `programs/<project>/documents/<...>`: 調査結果/仕様/成果物など（タスク内容に依存）
- `programs/<project>/tasks.yaml`: 対象Taskが `completed` になる（必要に応じて `notes` も更新）
- `programs/<project>/context/<...>.md`: 調査ログ等を残す場合（`context.yaml` から参照追加）

### ユースケース6: aipo-workflow（既存プロジェクト再開: 状況確認→次アクション提示）
プロンプト例:
```
$aipo-workflow
programs/<project名>/ を再開して、現状と次のアクションを提案して。
```

実行すると何が起こるか:
- `layer.yaml` / `context.yaml` / `tasks.yaml` を読み、破綻や不足があれば修正案を出す。
- 未着手タスクや優先度の高いSubLayerを要約し、次にやるべき候補（Focus/Discover/Deliver等）を提示する。

生成される成果物:
- 原則は「状況レポート（テキスト）」が中心。必要に応じて `programs/<project>/` 配下の `.yaml` を修正/補完する。

### ユースケース7: aipo-workflow（週次レビュー / 棚卸し）
プロンプト例:
```
$aipo-workflow
programs/<project名>/ の週次レビュー（棚卸し）をして、次の1週間の推奨プランを出して。
```

実行すると何が起こるか:
- 完了/未完了/高優先度SubLayerの整理、ブロッカーの列挙、次の1週間の推奨プラン（最大5項目）を提示する。

生成される成果物:
- 原則は「レビュー結果（テキスト）」が中心。必要なら `documents/` に週次レポートを保存する提案/作成を行う。

### 参照（スキーマ/ルール）

- 成果物スキーマ: `.codex/skills/aipo-workflow/references/program-schema.md`
- Codex CLI向けワークフロー: `.codex/skills/aipo-workflow/references/workflow.md`
- 新規事業ディスカバリーの分解テンプレ: `.codex/skills/aipo-workflow/references/discovery-playbook.md`
- 対象レイヤーの解決ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md`
- command_template_ref の辿り方: `.codex/skills/aipo-workflow/references/command-templates.md`

### 注意（YAML形式）

`layer.yaml` / `context.yaml` / `tasks.yaml` は **JSON互換YAML（=純JSON）** として運用します（パーサ依存を避け、`python3` の `json` で検証・更新するため）。

---

## Claude Code の場合

### スキル構成

Claude Code では `.claude/` ディレクトリにスキルとコマンドが配置されています。

```
.claude/
├── commands/              # スラッシュコマンド定義
│   ├── sense.md           # /sense - プロジェクト/サブレイヤー初期化
│   ├── focus.md           # /focus - ゴールをタスクに分解
│   ├── discover.md        # /discover - 実行コマンド生成
│   └── deliver.md         # /deliver - タスク実行
├── skills/                # 各フェーズのスキル定義
│   ├── aipo-core/         # コアスキーマ・ルール
│   ├── aipo-sense/        # Sense フェーズ
│   ├── aipo-focus/        # Focus フェーズ
│   ├── aipo-discover/     # Discover フェーズ
│   ├── aipo-deliver/      # Deliver フェーズ
│   └── pptx-from-template/ # PowerPoint生成スキル（追加機能）
├── scripts/               # ヘルパースクリプト
│   ├── init_program.py    # プロジェクト初期化
│   ├── validate_program.py # YAML検証
│   ├── generate_commands.py # コマンド自動生成
│   ├── sync_sublayers.py  # サブレイヤー同期
│   └── validate_skill.py  # スキル検証
├── prompts/               # カスタムプロンプト（現在空）
└── settings.local.json    # ローカル設定（権限許可リスト等）
```

> **Note**: Operation フェーズは Claude Code ではスラッシュコマンドとして未実装です。週次レビュー等は手動で依頼してください（例: 「programs/my-project の進捗をレビューして」）。

### 使い方（スラッシュコマンド）

Claude Code ではスラッシュコマンドで各フェーズを実行できます。

#### 新規プロジェクト開始（Sense）

```
/sense "<Goal>" "<project_name>"
```

例:
```
/sense "市場調査からMVPを作る" "my-project"
```

→ `programs/my-project/` に `layer.yaml`、`context.yaml`、`tasks.yaml` を生成

#### サブレイヤー作成（Sense）

親レイヤーのディレクトリ内で実行:
```
/sense "<SubGoal>" "<sublayer_name>"
```

#### タスク分解（Focus）

```
/focus [LayerPath]
```

例:
```
/focus programs/my-project
```

→ `tasks.yaml` を作成・更新し、SubLayer と Task に分解

#### 実行コマンド生成（Discover）

```
/discover [LayerPath]
```

→ `commands/` ディレクトリに各タスクの実行手順を生成

#### タスク実行（Deliver）

```
/deliver [TaskID] [LayerPath]
```

例:
```
/deliver T001 programs/my-project
```

→ 指定タスクを実行し、成果物を生成、`tasks.yaml` のステータスを更新

### Codex CLI との違い

| 項目 | Codex CLI | Claude Code |
|------|-----------|-------------|
| スキル配置場所 | `.codex/skills/` | `.claude/skills/` |
| トリガー | `$aipo-sense` 等のスキルプレフィックス（または自然言語） | `/sense`、`/focus` 等のスラッシュコマンド |
| スキル構造 | コア + フェーズ別 + エンジン（`aipo-core`/`aipo-sense`…/`aipo-workflow`） | フェーズ別スキル（`aipo-sense`、`aipo-focus` 等） |
| コマンド定義 | スキル内に統合 | `.claude/commands/` に分離 |
| Operation | テンプレで対応 | 未実装（手動依頼） |
