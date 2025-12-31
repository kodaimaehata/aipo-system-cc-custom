# Command Template の扱い（Codex CLI版）

## 目的

`tasks.yaml` の各Taskにある `command_template_ref` は、Discover（03）で **実行用コマンド（`commands/*.md`）を生成するための参照先**。

- `command_template_ref = null` の場合は、Discoverで「新規に」コマンドを設計する
- 参照先がある場合は、テンプレの構造/観点を流用してコマンドを作る

## このリポジトリでのテンプレ参照方法

テンプレの実体は `src/aipo (AI-PO) system/CTX_command_templates/` にある（Notion由来の長いファイル名のため検索前提）。

よく使うカテゴリ:
- `Discovery_templates/`: 事業・プロダクトの発見（ペルソナ、課題定義、仮説、ソリューション等）
- `Research _templates/`: 調査（競合、市場規模、顧客調査等）
- `project_management_templates/`: プロジェクト憲章、初期化など
- `system_building_templates/`: MVP実装（DB/UI/AIロジック/運用コマンド等）

検索例:

```bash
rg -n \"CMD_prj_02_ペルソナ\" \"src/aipo (AI-PO) system/CTX_command_templates/Discovery_templates\"
rg -n \"競合調査\" \"src/aipo (AI-PO) system/CTX_command_templates/Research _templates\"
rg -n \"プロジェクト憲章\" \"src/aipo (AI-PO) system/CTX_command_templates/project_management_templates\"
```

## `command_template_ref` の書き方（推奨）

厳密なパスではなく「人間が辿れる参照」を優先する（例: `Discovery_templates/01_ペルソナ作成`）。

Discoverでやること:
1. `command_template_ref` からカテゴリを特定
2. `rg` でテンプレ実体を見つける
3. テンプレの構造を残しつつ、プロジェクト文脈に合わせて `commands/{task}.md` を生成する
