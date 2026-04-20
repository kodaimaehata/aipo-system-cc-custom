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
    M0001_請求書CSVクリーナー/
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
- `mini-projects/active/M{NNNN}_{slug}/`
- `mini-projects/archive/M{NNNN}_{slug}/`

ID (`M{NNNN}`):
- `M0001` から順に採番する通し番号
- `mini-projects/catalog.md` の `next_id` が正本
- active → archive へ移しても ID は変更しない

slug 推奨:
- 日本語または英数小文字
- 英数の場合は単語を `-` で区切る
- 長くなりすぎない範囲で要点がわかる名前にする
- パスにスペースを含めない（日本語は中黒・括弧なども避けると安全）

例:
- `M0001_請求書CSVクリーナー`
- `M0002_clipboard-helper`
- `M0003_invoice-csv-cleaner`

## ID Allocation

`catalog.md` の `next_id` が採番の正本。新規 run 作成時は次の順で操作する:

1. `catalog.md` の `next_id` を読む（未作成なら `M0001` から開始）
2. その ID でディレクトリを作る（`M{NNNN}_{slug}`）
3. `catalog.md` の `next_id` を 1 増やして保存する
4. `meta.json` の `id` にも同じ値を記録する

ID は active → archive を移動しても変更しない。
欠番は気にしない（誤って採番した場合は catalog にメモを残すだけで十分）。

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
- `id`（`M0001` 形式）
- `title`
- `slug`（日本語可・英数可）
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
