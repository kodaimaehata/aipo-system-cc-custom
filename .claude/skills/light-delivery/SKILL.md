---
name: light-delivery
description: "`mini-projects/` で管理する軽量案件の produce / verify / review スキル。主エージェントとサブエージェントの責務を分け、成果物ベースで handoff しながら実装や文書作成を進める。"
---

# light-delivery

## Purpose

`plan.md` に基づいて成果物を作成し、検証し、レビューする。
対象はコード実装でも文書作成でもよい。軽量案件でも品質は落とさず、ただし AIPO より軽く進める。

## Inputs

最低限読むもの:
- `requirements.md`
- `design.md`
- `plan.md`

必要に応じて読むもの:
- `tasks/*.md`
- `handoff/*.md`
- `reviews/*.md`

## Main Agent Responsibilities

主エージェントが担うこと:
- 重要判断
- 実装順序の制御
- サブエージェントへの仕事の切り出し
- 成果物の最終統合
- 完了判定

## Subagent Responsibilities

サブエージェントに向くもの:
- 独立性の高い実装
- 特定論点の調査
- テスト追加
- 比較表作成
- 根拠収集
- 文書ドラフトの部分作成
- 校正観点の洗い出し

サブエージェントに向かないもの:
- 最終判断
- 密結合な同時編集
- スコープ変更判断

## Handoff Files

会話で文脈を長く渡さず、次を正本にする:
- `tasks/T00X_*.md`
- `handoff/T00X_input.md`
- `handoff/T00X_result.md`
- `reviews/T00X_spec_review.md`
- `reviews/T00X_quality_review.md`

## Review Order

レビュー順は固定:
1. spec review
2. quality review
3. final integration check

spec review で未解決事項がある状態で quality review に進まない。

## Execution Rules

- 小さい変更は主エージェントがそのまま実装または執筆してよい
- 大きめの副タスクは早めにサブエージェントへ切り出す
- 各タスクの Done 条件を `plan.md` または `tasks/*.md` に明記する
- テスト結果またはレビュー結果は `run_summary.md` に反映する
- 完了後も作業資産は削除せず残す

## Wrap-up

完了時に最低限更新する:
- `meta.json.status`
- `meta.json.updated_at`
- `run_summary.md`
- `mini-projects/catalog.md`

必要なら `mini-projects/active/` から `mini-projects/archive/` へ移す。
