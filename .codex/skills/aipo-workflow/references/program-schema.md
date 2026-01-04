# AIPO（Codex CLI版）成果物スキーマ

## 保存先（必須）

すべての成果物は `programs/{project名}/` に保存する。

## ディレクトリ構造（推奨）

```text
programs/{project名}/
  README.md
  .gitignore
  layer.yaml
  context.yaml
  tasks.yaml
  context/
    01_overview.md
    02_constraints.md
    ...
  commands/
    T001_*.md
    T002_*.md
    ...
  sublayers/
    SG1_*/
      layer.yaml
      context.yaml
      tasks.yaml
      context/
      commands/
      sublayers/
  documents/
    (成果物・レポート・仕様書など任意)
```

## Git運用（前提）

`programs/{project名}/` は **プロジェクトごとの独立リポジトリ**として扱う（各プロジェクトで `git init` する）。

- 親リポジトリ側は `programs/*` を追跡しない運用を推奨（親にGitを導入する場合は `.gitignore` で除外）
- 目的: プロジェクト単位で履歴・レビュー・リリースを独立させるため

推奨 `.gitignore`（最小）:

```text
.DS_Store
**/.DS_Store
```

## YAML運用ルール（重要）

このスキルでは、`layer.yaml` / `context.yaml` / `tasks.yaml` を **JSON互換YAML（= 純JSON）** として扱う。

- 理由: Codex同梱環境で YAML パーサ依存を避け、`python3` 標準ライブラリ `json` で検証/更新できるようにするため
- 運用: 末尾カンマなし、ダブルクオート、`null/true/false` を使用する（JSON準拠）

## `layer.yaml`（最小スキーマ）

必須フィールド:
- `version`
- `project_name`
- `layer_id`
- `layer_name`
- `workflow_preset`（`general` / `discovery`）
- `goal.description`
- `mode`（`concrete` / `abstract`）
- `owner`
- `deadline`（ISO日付 or `null`）

例:

```json
{
  "version": "1.0",
  "project_name": "example-project",
  "layer_id": "L001",
  "layer_name": "Root",
  "workflow_preset": "general",
  "goal": {
    "description": "ゴールを1行で書く",
    "success_criteria": []
  },
  "mode": "concrete",
  "owner": "owner-name",
  "deadline": null,
  "parent_layer_id": null,
  "created_at": "2025-12-29",
  "updated_at": "2025-12-29"
}
```

## `context.yaml`（Index）

必須フィールド:
- `version`
- `project_name`
- `layer_id`
- `generated_at`
- `context_documents[]`（`path` と `summary` を持つ）

オプションフィールド（v1.1）:
- `context_collection` - コンテキスト収集方法の設定
- `context_documents[].source_method` - 各ドキュメントの収集元

例:

```json
{
  "version": "1.1",
  "project_name": "example-project",
  "layer_id": "L001",
  "generated_at": "2025-12-29",
  "parent_context_dir": null,
  "context_collection": {
    "methods": ["local_workspace", "web_search"],
    "local_workspace_config": {
      "priority_folders": ["src/", "docs/"],
      "perspectives": ["technical", "business"]
    },
    "web_search_config": {
      "prefer_primary_sources": true,
      "keywords": []
    },
    "external_paths_config": {
      "paths": []
    },
    "collected_at": "2025-12-29",
    "confirmed_by": "user"
  },
  "context_documents": [
    {
      "name": "Overview",
      "path": "context/01_overview.md",
      "summary": "背景・目的・スコープの要約",
      "source_method": "local_workspace"
    },
    {
      "name": "Constraints",
      "path": "context/02_constraints.md",
      "summary": "制約（期限・予算・技術・法務など）",
      "source_method": "local_workspace"
    }
  ]
}
```

### `context_collection` フィールド詳細

| フィールド | 説明 |
|-----------|------|
| `methods` | 選択された収集方法の配列: `local_workspace`, `web_search`, `external_paths` |
| `local_workspace_config` | ワークスペース検索の設定（優先フォルダ、検索観点） |
| `web_search_config` | Web検索の設定（一次情報優先、キーワード） |
| `external_paths_config` | 外部パスの設定（対象パス一覧） |
| `collected_at` | 収集実行日（ISO日付） |
| `confirmed_by` | 選択確認者（`user`, `ai`, `cli`）|

## `tasks.yaml`（タスク分解 + コマンド生成設定）

必須フィールド:
- `version`
- `project_name`
- `layer_id`
- `generated_at`
- `decomposition_type`（`recursive` 推奨）
- `focus_strategy`（`product_manager` / `system_architect` / `content_strategist` / `generic`）
- `focus_strategy_reason`
- `focus_strategy_confirmed_by`（`user` / `ai`）
- `sublayers[]`
- `tasks[]`
- `command_generation.enabled`

ルール:
- `type` が `management` / `coordination` / `verification` のタスクのみ `command: null` を許可
- 上記以外は `command` を必須（例: `"T003_競合調査"`）

例:

```json
{
  "version": "2.2",
  "project_name": "example-project",
  "layer_id": "L001",
  "generated_at": "2025-12-29",
  "decomposition_type": "recursive",
  "focus_strategy": "generic",
  "focus_strategy_reason": "Goalが複合的で特定フレームに固定しない",
  "focus_strategy_confirmed_by": "ai",
  "sublayers": [
    {
      "id": "SG1",
      "goal": "SubGoal",
      "priority": "P0",
      "status": "pending_init",
      "mode": "concrete",
      "path": "sublayers/SG1_subgoal"
    }
  ],
  "tasks": [
    {
      "id": "T001",
      "name": "全体進捗モニタリング設定",
      "type": "management",
      "status": "pending",
      "estimate": "2h",
      "command": null,
      "command_template_ref": null,
      "notes": ""
    },
    {
      "id": "T002",
      "name": "ペルソナ作成",
      "type": "research",
      "status": "pending",
      "estimate": "4h",
      "command": "T002_ペルソナ作成",
      "command_template_ref": "Discovery_templates/01_ペルソナ作成",
      "notes": ""
    }
  ],
  "command_generation": {
    "enabled": true,
    "target_dir": "commands",
    "naming_pattern": "{task_id}_{task_name}.md"
  },
  "summary": {
    "sublayer_count": 1,
    "task_count": 2,
    "next_action": "discover: commands生成"
  }
}
```
