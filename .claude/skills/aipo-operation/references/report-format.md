# Weekly Review Report Format（AIPO Operation）

このレポートは `programs/*` のAIPO成果物を入力にして生成する。

## 必須セクション

1. **Project Goal**
   - root layer の `layer.yaml.goal.description`
2. **Project Structure**
   - root + sublayers を表形式で列挙（親子構造が分かる表現にする）
   - 目的（`goal.description`）、作業概要（タスク内容の要約＝「目的達成のために何をするか」）、可能なら最終成果物（`goal.deliverable` or `documents/`）を記載
   - 推奨列:
     - `Depth/階層`: 0,1,2...（親子の深さ）
     - `Layer/レイヤー`: 識別子と名前（例: `` `SG1` Site Infrastructure ``）
     - `Work Summary/作業概要`: 端的な1〜2文で「目的達成のために何をするか」を要約（固定の書き出しやタスク名の羅列は避ける）
3. **Progress**
    - 各 Layer の `tasks.yaml.tasks[]` を表形式で列挙
    - status / estimate / 参照コマンド / 成果物リンクを含める
4. **ETA（90%）**
   - 未完了タスクの `estimate` を集計し、90%信頼区間のレンジを出す（可能な範囲で）
   - `estimate` が欠ける場合は信頼係数（coverage）を併記し、レンジの精度が低い旨を明記する

## 言語（重要）

- レポートは **単一言語（日本語または英語）** に統一する。
- ユーザーが指定しない場合は、チャット言語に合わせて選ぶ。
- 見出し/固定文言は `--lang` に従う。
- `goal.description` / `layer_name` / `tasks[].name` などの入力が混在していると本文も混在するため、必要ならAIPO成果物側の文言を揃える（スクリプトは自由文の自動翻訳をしない）。

## 成果物リンクの扱い（推奨）

- `documents/` 配下のファイルは相対リンクで列挙する
- `commands/*.md` の `## Outputs` からファイルパスを推定できる場合はリンクに含める
- それでも特定できない場合は、`—`（未記載）として扱う

## 推奨の保存先

- `<layer_dir>/weekly_review/weekly_review_YYYY-MM-DD.md`
