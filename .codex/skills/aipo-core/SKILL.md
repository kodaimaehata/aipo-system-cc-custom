---
name: aipo-core
description: "Core schemas, directory layout, and operating rules for the AIPO (AI Product Owner) workflow in Codex CLI. Use when working with AIPO artifacts under `programs/*` (`layer.yaml`, `context.yaml`, `tasks.yaml`, `commands/`, `sublayers/`), resolving the target layer directory, or enforcing JSON-compatible YAML rules. Foundation for phase skills (aipo-sense/aipo-focus/aipo-discover/aipo-deliver)."
---

# AIPO Core（Codex CLI）

このスキルは AIPO（AI Product Owner）運用の**共通定義**（用語・成果物・ルール）を提供する。

## Core Model（Fractal Decomposition）

- すべての目標を **Layer** として扱う（再帰的に分解する）。
- 複雑で独立した文脈が必要なら **SubLayer**（委譲可能なサブゴール）にする。
- このレイヤー内で1〜2日程度で完結できる粒度は **Task** にする。

## Canonical Artifacts（保存先）

- すべてのAIPO成果物は `programs/P####_{project_name}/` 配下に保存する。
- 推奨ディレクトリ構造と `.yaml` スキーマは以下を参照する:
  - `programs/` 構造と schema: `.codex/skills/aipo-workflow/references/program-schema.md`
  - フェーズ運用: `.codex/skills/aipo-workflow/references/workflow.md`

## Context Collection Methods（v1.2）

Senseフェーズで使用可能なコンテキスト収集方法:

| ID | 名称 | 説明 |
|----|------|------|
| `local_workspace` | ローカル検索（ワークスペース） | ワークスペース内のGoal関連情報を検索。`src/` `docs/` に加え、`flows/` の作業ログやメモも必要に応じて含める |
| `active_projects` | ローカル検索（進行中AIPOプロジェクト） | `programs/` 配下の**archivedを除く現行プロジェクト/サブレイヤー**から、Goal関連情報・制約・既存成果物を収集 |
| `web_search` | Web検索 | インターネットからGoal関連情報を収集 |
| `external_paths` | ローカル検索（指定フォルダ） | ユーザー指定フォルダ/ファイルから収集 |

`context.yaml` の `context_collection` フィールドに選択結果を記録する（詳細は `program-schema.md` 参照）。

推奨:
- Senseでは `local_workspace` に加えて、必要に応じて `active_projects` を使い、過去のアーカイブ知見だけでなく**進行中プロジェクトの類似成果物や制約**も参照する。
- 外部環境に依存するGoal（市場、規制、競合、製品仕様、価格、トレンドなど）は `web_search` を併用する。特に時間変化しやすい情報は、ワークスペース内資料だけで完結させない。
- `flows/` は会話由来のメモ、調査下書き、途中整理の置き場として有効なため、Senseでは通常のワークスペース資料と同様に参照候補へ含める。

## JSON-Compatible YAML（必須）

- `layer.yaml` / `context.yaml` / `tasks.yaml` は **JSON互換YAML（=純JSON）** として扱う（ダブルクオート、末尾カンマなし、`null/true/false`）。
- 検証は以下を使用する:

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --project "<project_name>"
# or
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```

## Layer Directory Resolution（重要ルール）

フェーズスキル（Sense/Focus/Discover/Deliver）が対象レイヤーを特定できないときは、必ず次の順で解決する。

1. ユーザーがレイヤーパスを指定したらそれを使う（`layer.yaml` があること）。
2. それ以外で、カレントディレクトリに `layer.yaml` があればそこをレイヤールートにする。
3. それ以外は `programs/` 配下から `layer.yaml` を探索する（`sublayers/` のネストも含む）。
4. 候補が複数ある場合はユーザーに選ばせる（勝手に決めない）。
5. `Flow/` はこのリポジトリではレガシー扱い（ユーザーが明示しない限り使わない）。

詳細: `.codex/skills/aipo-core/references/layer-directory-resolution.md`

## Canonical Scripts（推奨）

- Program作成: `python3 .codex/skills/aipo-workflow/scripts/init_program.py --project "<project_name>" --goal "<goal>" --preset general`
- SubLayer雛形生成: `python3 .codex/skills/aipo-workflow/scripts/sync_sublayers.py --project "P0001_<project_name>"`
- commands雛形生成: `python3 .codex/skills/aipo-workflow/scripts/generate_commands.py --project "P0001_<project_name>"`
