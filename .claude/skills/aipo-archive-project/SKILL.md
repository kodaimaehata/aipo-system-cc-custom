---
name: aipo-archive-project
description: Archive an AIPO project in Claude Code by moving a project folder under programs/archived and recording purpose + activities (and artifact summary) into programs/archived_projects.md.
---

# AIPO Project Archive（Claude Code）

## Description
終了・保留・中断した AIPO プロジェクトをアーカイブします。
対象プロジェクトを `programs/archived` に移動し、`programs/archived_projects.md` に内容要約を追記します。

既定の対象ルートは `programs` です。必要に応じて `--base-dir` で別のルートを指定できます。

## Usage
Run this skill when the user asks to archive, retire, suspend, or close a project under `programs/`.

## Command

```bash
python3 .claude/skills/aipo-archive-project/scripts/archive_project.py "<project-or-path>"
```

オプション:
- `--base-dir "programs"`: プロジェクト検索ルート（既定: `programs`）
- `--archive-dir "programs/archived"`: アーカイブ先（既定: `--base-dir/archived`）
- `--record-file "programs/archived_projects.md"`: 履歴記録先（既定）
- `--note "..."`: 履歴メモ
- `--purpose "..."`: プロジェクト目的（省略時は `layer.yaml` 等から推定）
- `--activities "..."`: 実施内容（省略時は主要ファイル構成・タスク情報から推定）

## Instructions

1. 対象プロジェクトを決める。
   - フルパス（既存ディレクトリ）
   - `programs` 配下のフォルダ名
2. アーカイブ操作はディレクトリ移動を伴うので、対象が曖昧な場合や複数候補がある場合は実行前に確認する。
3. 次を実行する。
   ```bash
   python3 .claude/skills/aipo-archive-project/scripts/archive_project.py "<project-or-path>"
   ```
4. 実行すると、対象が `programs/archived` へ移動される。
5. 同時に `programs/archived_projects.md` に記録を追記する。
   追記項目: `archived_at`, `project_name`, `purpose`, `activities`, `source_path`, `archive_path`, `summary`, `note`
6. 結果を報告し、必要なら `programs/archived_projects.md` を確認する。

## aipo-sense 連携

`aipo-sense` では、Sense 作業時に `programs/archived_projects.md` の過去エントリを参照して、
類似案件の失敗条件・制約・成功基準・アーティファクト構成をコンテキストに追加できます。
