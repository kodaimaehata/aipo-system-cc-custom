---
name: aipo-sense
description: "AIPO Sense phase for Codex CLI. Initialize a new AIPO program (root layer) or refresh a layer's context by creating/updating `layer.yaml`, `context.yaml`, and `context/*.md` under `programs/*`. Use when starting an AIPO project, collecting constraints/context, or preparing a layer for Focus."
---

# AIPO Sense（Codex CLI）

目的: 後続の分解（Focus）に耐える **Layerの前提情報** を `context/` と `context.yaml` に残す。

## 0) 対象レイヤーを決める

- ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md` に従って解決する。
- 以降、対象フォルダを `<layer_dir>` とする（`layer.yaml` が存在する場所）。

## 1) モード判定

- **新規 Program（Root Layer）作成**: `programs/{project_name}/` がまだ無い
- **既存 Layer の前提整備**: すでに `<layer_dir>` がある（`context/` 追加・`context.yaml` 更新など）
- **SubLayer の初期化**: 親レイヤーの `tasks.yaml.sublayers` に定義があり、まだ実体フォルダが無い

## 2) 新規 Program を作る（推奨: script）

```bash
python3 .codex/skills/aipo-workflow/scripts/init_program.py \
  --project "<project_name>" \
  --goal "<goal_1line>" \
  --preset general
```

- `--preset discovery` は新規事業ディスカバリー用途
- `--no-git-init` を付けると `programs/{project_name}/` で `git init` をしない

## 3) SubLayer を初期化する（推奨: script）

前提: 親レイヤー（`<parent_layer_dir>`）の `tasks.yaml.sublayers[]` に `id` と `goal` がある。

```bash
python3 .codex/skills/aipo-workflow/scripts/sync_sublayers.py --path "<parent_layer_dir>"
```

## 4) Context を収集して `context.yaml` を更新する

- `context/` に前提情報をMarkdownで追加・更新する（例: `01_overview.md`, `02_constraints.md`, `03_resources.md`）。
- `context.yaml.context_documents[]` に「パス」と「要約」を追加・更新する。
- 必要に応じて親の文脈を参照できるように `context.yaml.parent_context_dir` を維持する（SubLayerの場合は script が設定する）。

## 5) 検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```

## 6) 実行結果をユーザーに報告する（必須）

Sense 実行後、ユーザーへの最終返信は **以下のフォーマット**に揃える（内容は実際に作成/更新したものに合わせて調整する）。

### 出力テンプレート

```text
Sense Phase 完了

プロジェクト <project_name> を初期化しました。
# 既存 Layer の場合: レイヤー <layer_dir> のコンテキストを更新しました。
# SubLayer の場合: SubLayer <layer_dir> を初期化しました。

作成されたディレクトリ構造

<layer_dir>/
├── layer.yaml           # レイヤー定義（ゴール・成功基準）
├── context.yaml         # コンテキストインデックス
├── tasks.yaml           # タスク計画（Focus phaseで更新）
├── context/
│   ├── <doc1>.md        # <要約>
│   └── <doc2>.md        # <要約>
├── documents/           # 成果物（レポート等）
├── commands/            # タスク実行コマンド
└── sublayers/           # サブレイヤー

収集したコンテキスト（context.yaml）

| ドキュメント | 内容 |
|---|---|
| <doc1>.md | <要約> |
| <doc2>.md | <要約> |

成功基準（layer.yaml）

1. <success_criteria_1>
2. <success_criteria_2>
3. ...

---
次のステップ

/focus を実行して、ゴールをサブレイヤーとタスクに分解してください。
```

### 生成ルール（必須）

- `<layer_dir>` とツリーは **実在するパス/構造**に合わせる（存在しないファイルは書かない）。
- 「収集したコンテキスト」は `context.yaml.context_documents[]` を優先して表にする（`path` と `summary`）。
- 「成功基準」は `layer.yaml.goal.success_criteria[]` をそのまま列挙する（無い場合は `layer.yaml.goal` から補う）。
- 「次のステップ」は原則 `/focus`（ユーザーが別フェーズを指定している場合のみ従う）。
