---
name: aipo-deliver
description: "AIPO Deliver phase for Codex CLI. Execute a selected task using `commands/*.md` (or create it if missing), produce deliverables under the target layer, and update `tasks.yaml` status. Use when implementing, researching, writing docs, or otherwise completing an AIPO task."
---

# AIPO Deliver（Codex CLI）

目的: 1つのTaskを完了させ、成果物と進捗（`tasks.yaml.status`）を残す。

## 0) 対象レイヤーを決める

- ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md`
- 対象フォルダを `<layer_dir>` とする。

## 1) 実行対象タスクを決める

- `<layer_dir>/tasks.yaml` を読み、`status: pending` のTaskから1つ選ぶ。
- `command` がある場合は対応する `commands/*.md` を探す（`tasks.yaml.command_generation.*` も参照）。

## 2) Command に従って実行する

- `commands/*.md` が存在する場合は、その手順に従う。
- 無い場合は、まず Discover（`aipo-discover`）で雛形を作ってから実行する。

## 3) 成果物を保存する

- 生成物は `<layer_dir>/documents/` または関連する場所に保存する。
- 調査ログ/意思決定ログが必要なら `<layer_dir>/context/` に追加し、`context.yaml` から参照できるようにする。

## 4) `tasks.yaml` を更新する

- 完了したTaskの `status` を `completed` に更新する（必要なら `notes` も追記する）。

## 5) 検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```

