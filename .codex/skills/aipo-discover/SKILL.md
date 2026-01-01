---
name: aipo-discover
description: "AIPO Discover phase for Codex CLI. Generate or refine per-task execution command files under `commands/` from `tasks.yaml`, using `command_template_ref` when available. Use when you need executable steps, command templates, or to turn tasks into runnable instructions."
---

# AIPO Discover（Codex CLI）

目的: `tasks.yaml` を **実行可能な手順（commands）** に落とし、`commands/*.md` を整備する。

## 0) 対象レイヤーを決める

- ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md`
- 対象フォルダを `<layer_dir>` とする。

## 1) `commands/*.md` を生成（雛形）

```bash
python3 .codex/skills/aipo-workflow/scripts/generate_commands.py --path "<layer_dir>"
```

## 2) テンプレ参照（`command_template_ref`）

- テンプレの実体は `src/aipo (AI-PO) system/CTX_command_templates/` にある（検索前提）。
- 参照方法: `.codex/skills/aipo-workflow/references/command-templates.md`

検索例（パスにスペースがあるので必ずクォートする）:

```bash
rg -n "CMD_prj_02_ペルソナ" "src/aipo (AI-PO) system/CTX_command_templates/Discovery_templates"
```

## 3) 各 `commands/*.md` を埋める

- Goal / Done / Inputs / Steps / Outputs をプロジェクト文脈に合わせて具体化する。
- `command_template_ref` があれば、テンプレの構造・観点を流用して埋める（丸写しではなく適用）。

## 4) 検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```

