---
name: light-workflow
description: "軽量なツール・小規模アプリ・PoC・文書成果物を `mini-projects/` 配下で進めるための全体オーケストレーションスキル。AIPO を使うほどではないが、brief / requirements / design / plan / produce / review の流れと HITL 品質ゲートは残したい場合に使う。"
---

# light-workflow

## Overview

AIPO は長期・多段・正式案件向け。
このスキルは、より軽い開発案件や文書成果物案件を `mini-projects/` 配下に保存しながら進めるための入口です。

対象:
- 小規模ツール
- 小アプリ
- PoC
- 単発自動化
- 調査レポート
- 仕様メモ
- 提案書や手順書の草案
- 1〜8 個程度の主要タスクで進められる軽量成果物案件

非対象:
- 日を跨ぐ大規模案件
- SubLayer が自然に必要になる案件
- 継続的な進捗管理や棚卸しが主目的の案件

その場合は `aipo-*` を使います。

## Canonical Storage

保存先は `mini-projects/` を使う。

- 進行中: `mini-projects/active/M{NNNN}_{slug}/`
- 完了後保管: `mini-projects/archive/M{NNNN}_{slug}/`
- 一覧: `mini-projects/catalog.md`（先頭に `next_id: M{NNNN}` を保持）

ID (`M0001` 等) はプロジェクト通し番号。active/archive を移動しても ID は変更しない。
slug は日本語でも英数ハイフンでもよい（例: `M0001_請求書CSVクリーナー`, `M0002_clipboard-helper`）。

`mini-projects/` は Git 管理対象外だが、後続案件のコンテキスト源として残す。
削除前提にはしない。

詳細は `references/mini-projects-spec.md` を参照。

## Standard Flow

1. Brief / Intake
2. Context / Requirements
3. Design
4. Plan
5. Produce / Verify / Review
6. Wrap-up / Archive

## Required Artifacts

最低限の作業ファイル:
- `README.md`
- `meta.json`
- `brief.md`
- `context.md`
- `requirements.md`
- `design.md`
- `plan.md`
- `run_summary.md`

必要に応じて作るディレクトリ:
- `tasks/`
- `handoff/`
- `artifacts/`
- `reviews/`

## HITL Gates

最低でも次の確認を入れる:
- Goal / Scope 確認
- Requirements 確認
- Design 確認
- Build 着手前確認
- 最終確認

## Startup Procedure

### 1. 対象 run を決める

- ユーザーが既存 run を指定したらそれを使う
- 未指定なら新規採番してディレクトリを作る:
  1. `mini-projects/catalog.md` の `next_id` を確認して使う ID を決める
     - catalog が未作成なら `templates/catalog.md` を写して `next_id: M0001` から始める
  2. `mini-projects/active/M{NNNN}_{slug}/` を作成する
  3. `catalog.md` の `next_id` を次の番号（例: `M0002`）に更新する
- slug はゴールを短く要約。日本語可、英数ハイフン可。単語は空白ではなく `-` または日本語のまま

### 2. 初期ファイルを作る

テンプレート:
- `templates/meta.json`
- `templates/catalog.md`

### 3. catalog を更新する

`mini-projects/catalog.md` に以下を追記または更新:
- id（`M0001` 等）
- title
- goal
- status
- path
- updated_at
- reuse_value

## Rules

- `mini-projects/` の成果物は Git ignore でも、できるだけ構造化して残す
- AIPO の `layer.yaml/context.yaml/tasks.yaml/commands` をそのまま持ち込まない
- ただし、背景整理・要件整理・設計・レビューの考え方は維持する
- サブエージェントへの引き継ぎは会話ではなく `tasks/` `handoff/` `reviews/` を正本とする
- Produce 中の review は spec → quality の順で行う

## Recommended Companion Skills

- `light-planning`: brief/context/requirements/design/plan を作る
- `light-delivery`: 実装、文書作成、検証、レビューを進める
