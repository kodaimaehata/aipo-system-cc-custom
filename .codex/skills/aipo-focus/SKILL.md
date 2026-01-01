---
name: aipo-focus
description: "AIPO Focus phase for Codex CLI. Decompose a layer goal into SubLayers and Tasks and generate/update `tasks.yaml` (JSON-compatible) under `programs/*`. Use when planning work, choosing `focus_strategy`, and deciding what becomes a sublayer vs an atomic task."
---

# AIPO Focus（Codex CLI）

目的: Goal を **SubLayer（委譲可能なサブゴール）** と **Task（このレイヤーで完結）** に分解し、`tasks.yaml` を更新する。

## 0) 対象レイヤーを決める

- ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md`
- 対象フォルダを `<layer_dir>` とする。

## 1) 前提を読む

- `<layer_dir>/layer.yaml` と `<layer_dir>/context.yaml` を読む。
- `context.yaml.parent_context_dir` があれば必要に応じて親Contextも参照する。

## 2) Focus Strategy（必須）

`tasks.yaml` に必ず記録する:
- `focus_strategy`: `product_manager` / `system_architect` / `content_strategist` / `generic`
- `focus_strategy_reason`: 1〜2行
- `focus_strategy_confirmed_by`: `user` / `ai`

詳細: `.codex/skills/aipo-workflow/references/workflow.md`

## 3) 分解ルール（SubLayer vs Task）

- **SubLayer**: 複雑 / 独立した文脈が必要 / 複数タスクに割れる / 委譲可能
- **Task**: 1〜2日で完了できる / 単一の成果物に落ちる / このレイヤー内で完結

## 4) `tasks.yaml` 更新（JSON互換YAML）

- `tasks.yaml.tasks[]` の必須:
  - `type` が `management` / `coordination` / `verification` の場合のみ `command: null` を許可
  - それ以外は `command` を必須（例: `"T003_競合調査"`）
  - `command_template_ref` は分かれば設定、無ければ `null`

スキーマ/例: `.codex/skills/aipo-workflow/references/program-schema.md`

## 5) SubLayer 実体化（任意・推奨）

`tasks.yaml.sublayers[]` を更新したら、親レイヤーで sublayer フォルダを生成する:

```bash
python3 .codex/skills/aipo-workflow/scripts/sync_sublayers.py --path "<layer_dir>"
```

## 6) 検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```

