---
name: aipo-workflow
description: "AIPO (AI Product Owner) workflow for Codex CLI. Use to run Sense→Focus→Discover→Deliver→Operation as file-based artifacts under programs/{project} (layer.yaml/context.yaml/tasks.yaml/commands). Triggers: project planning/execution with AIPO terms, generating/updating those YAML files, or new business discovery (市場調査・課題仮説・検証計画・MVP定義/開発計画)."
---

# AIPO Workflow

## Overview

AIPO（AI Product Owner）の進め方を、Codex CLI上で「ファイル（成果物）を残しながら」回すためのスキルです。
成果物は必ず `programs/{project名}/` に生成・更新します。

## Quick Start

### 1) 新規開始（program作成）

リポジトリ直下から実行（このリポジトリにあるスクリプトを使う場合）:

```bash
python3 .codex/skills/aipo-workflow/scripts/init_program.py \
  --project "<project名>" \
  --goal "<Goalを1行で>" \
  --preset general
```

新規事業ディスカバリー（市場調査→MVP）:

```bash
python3 .codex/skills/aipo-workflow/scripts/init_program.py \
  --project "<project名>" \
  --goal "<Goalを1行で>" \
  --preset discovery
```

補足:
- `programs/{project名}/` は **プロジェクトごとの独立Gitリポジトリ**として扱います（`init_program.py` はデフォルトで `git init` します）。
- Git初期化を行わない場合は `--no-git-init` を付けてください。

### 2) 生成物の検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --project "<project名>"
```

### 3) commands 雛形生成（Discoverの補助）

```bash
python3 .codex/skills/aipo-workflow/scripts/generate_commands.py --project "<project名>"
```

## Workflow（Sense→Focus→Discover→Deliver→Operation）

このスキルでは、AIPOの成果物を以下の順で更新していく。

1. **Sense（01）**: `layer.yaml` / `context.yaml` を作る・更新する（詳細は `references/program-schema.md` と `references/workflow.md`）
2. **Focus（02）**: `tasks.yaml` を作る・更新する（`focus_strategy*` と `command` 要件を満たす）
3. **Discover（03）**: `commands/*.md` を生成・整備する（テンプレ参照は `references/command-templates.md`）
4. **Deliver（04）**: タスクを実行し、成果物＋進捗（`tasks.yaml.status`）を更新する
5. **Operation（05）**: 繰り返し作業を定型化し、同型タスクを量産できるようにする

## References（必要なときだけ読む）

- `references/program-schema.md`: 成果物の保存先・ディレクトリ構造・JSON互換YAMLスキーマ
- `references/workflow.md`: AIPO各フェーズの運用ルール（Codex CLI版）
- `references/discovery-playbook.md`: 新規事業ディスカバリーの分解テンプレ
- `references/command-templates.md`: `command_template_ref` の辿り方（`src/` 内テンプレの検索方法）

## Scripts

- `scripts/init_program.py`: `programs/{project名}/` を初期化（`layer.yaml`/`context.yaml`/`tasks.yaml` と最低限のフォルダ）
- `scripts/validate_program.py`: program 配下のJSON互換YAMLを検証
- `scripts/generate_commands.py`: `tasks.yaml` から `commands/*.md` 雛形を生成

## Notes（重要）

- このスキルの `.yaml` は JSON互換運用（=純JSON）です。YAML拡張記法（アンカー等）は使わないでください。
