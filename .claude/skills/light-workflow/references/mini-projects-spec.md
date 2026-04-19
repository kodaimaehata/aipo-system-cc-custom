# mini-projects Spec

## Purpose

`mini-projects/` は、AIPO の `programs/` とは別に、小規模なツール・小アプリ・PoC・単発自動化・文書成果物の作業資産を残すための保存先。

性質:
- Git ignore
- 削除前提ではない
- 後続案件のコンテキスト源として再利用可能
- AIPO ほど重い artifact 制約は持たない

## Directory Layout

```text
mini-projects/
  active/
    2026-04-18_example-tool/
      README.md
      meta.json
      brief.md
      context.md
      requirements.md
      design.md
      plan.md
      run_summary.md
      tasks/
      handoff/
      artifacts/
      reviews/
  archive/
    ...
  catalog.md
```

## Run Naming

標準:
- `mini-projects/active/{YYYY-MM-DD}_{slug}/`
- `mini-projects/archive/{YYYY-MM-DD}_{slug}/`

slug 推奨:
- 英数小文字
- 単語は `-` で区切る
- 4〜8 語程度まで

例:
- `2026-04-18_clipboard-helper`
- `2026-04-18_invoice-csv-cleaner`

## Required Files

### `README.md`
簡単な概要。

最低限:
- タイトル
- ゴール
- 現在状態
- 主要ファイル一覧

### `meta.json`
検索・再利用用の索引。

必須キー:
- `title`
- `slug`
- `goal`
- `status`
- `created_at`
- `updated_at`
- `path`
- `keywords`
- `summary`
- `important_files`
- `reuse_value`

推奨キー:
- `repo_paths`
- `tech_stack`
- `related_runs`
- `notes`

### `brief.md`
何を作るか、誰が使うか、何をしないか。

### `context.md`
背景・制約・既存コード・関連資料。

### `requirements.md`
機能要件、非機能要件、成功条件、非ゴール。

### `design.md`
構成、入出力、データの流れ、技術方針、テスト方針。

### `plan.md`
実装順序、タスク分割、対象ファイル、Done 条件。

### `run_summary.md`
実施内容、レビュー結果、未解決事項、次に見るべきファイル。

## Optional Directories

### `tasks/`
タスク定義。

例:
- `T001_setup.md`
- `T002_parser.md`

### `handoff/`
主エージェント / サブエージェント間の受け渡し。

例:
- `T001_input.md`
- `T001_result.md`

### `artifacts/`
中間生成物、比較表、出力サンプル、試作品。

### `reviews/`
レビュー記録。

例:
- `T001_spec_review.md`
- `T001_quality_review.md`
- `final_review.md`

## Lifecycle

1. 新規開始時に `active/` に run を作る
2. 作業中は成果物を上書き更新する
3. 完了後も原則削除しない
4. 一段落したら必要に応じて `archive/` へ移す
5. `catalog.md` と `meta.json` は更新する

## HITL Standard Points

最低限の確認ポイント:
- brief 確定
- requirements 確定
- design 確定
- build 着手可否
- 最終確認

## Subagent Handoff Standard

会話に長文で文脈を積まず、次を正本にする:
- `tasks/*.md`
- `handoff/*`
- `reviews/*`

推奨順序:
1. 実装
2. spec review
3. quality review
4. 統合反映

## AIPO との違い

AIPO で持つもの:
- 長期プロジェクト管理
- recursive decomposition
- SubLayer
- formal artifact set

mini-projects で持つもの:
- 軽量だが検索可能な作業資産
- ファイルベース handoff
- 要件 / 設計 / 計画 / produce / review
- Git ignore 前提のローカル知識蓄積
