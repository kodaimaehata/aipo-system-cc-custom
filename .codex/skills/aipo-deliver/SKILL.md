---
name: aipo-deliver
description: "AIPO Deliver phase for Codex CLI. Execute a selected task using `commands/*.md` (or create it if missing), produce deliverables under the target layer, and update `tasks.yaml` status. Use when implementing, researching, writing docs, or otherwise completing an AIPO task."
---

# AIPO Deliver（Codex CLI）

目的: 1つのTaskを完了させ、成果物と進捗（`tasks.yaml.status`）を残す。

## 0) 対象レイヤーを決める

- ルール: `.codex/skills/aipo-core/references/layer-directory-resolution.md`
- 対象フォルダを `<layer_dir>` とする。

## 1) 実行対象タスクを決める

- `<layer_dir>/tasks.yaml` を読み、`status: pending` のTaskから1つ選ぶ。
- `command` がある場合は対応する `commands/*.md` を探す（`tasks.yaml.command_generation.*` も参照）。

## 2) Command に従って実行する

- `commands/*.md` が存在する場合は、その手順に従う。
- 無い場合は、まず Discover（`aipo-discover`）で雛形を作ってから実行する。

## 2.5) サブエージェントを積極活用する

- 実行前に、作業を次の2つに分けて考える:
  - 主エージェントが持つべきクリティカルパス
  - 並列で進められる独立した副タスク
- 次のような、境界が明確で具体的な副タスクはサブエージェント活用を優先する:
  - 特定論点に絞ったコード探索
  - 別ファイルや別モジュールで閉じる実装
  - 既知入力からの文書草案作成
  - 競合しない範囲のテスト追加
  - 根拠収集、比較表作成、検証観点の洗い出し
- 独立タスクが複数ある場合は、メイン作業が詰まってからではなく早めに並列起動する。
- サブエージェント実行中も、主エージェントは統合作業と重要判断を進める。
- サブエージェントの結果は取り込む前にレビューし、必要な修正を入れてから成果物に反映する。

ガードレール:
- 最終判断、最終編集、Task 完了判定は委譲しない。
- 書き込み範囲が重なる密結合な変更は、分離が明確でない限り委譲しない。
- 有益なローカル作業が残っているのに待機しない。
- Task が小さい場合は無理に委譲せず、そのままローカルで完了させる。

推奨オーケストレーション（複数 Task をまとめて進める Deliver のとき）:
- まず Command 群を読み、独立性の高い塊にまとめる。
  - 例: 設計文書群、実装群、検証群
- 競合しない塊は早めに別サブエージェントへ並列委譲する。
- 主エージェントは待たずに、統合確認・追加読解・検証準備を進める。
- 実装や文書作成のあとに、必ず独立レビュアーを別サブエージェントで走らせる。
  - 1段目: spec / acceptance criteria 準拠レビュー
  - 2段目: 品質・整合性・下流 handoff 品質レビュー
- レビューで指摘が出たら、修正も別サブエージェントに切り出し、修正後に再レビューする。
- `tasks.yaml` の `status: completed` 更新は、成果物作成だけでなく独立レビュー通過と主要検証通過のあとに行う。
- 文書 Deliver でも、可能なら実物（生成ファイル、import check、validator、smoke test）で裏取りしてから完了扱いにする。

## 3) 成果物を保存する

- 生成物は `<layer_dir>/documents/` または関連する場所に保存する。
- 調査ログ/意思決定ログが必要なら `<layer_dir>/context/` に追加し、`context.yaml` から参照できるようにする。

## 4) `tasks.yaml` を更新する

- 完了したTaskの `status` を `completed` に更新する（必要なら `notes` も追記する）。

## 5) 検証（任意・推奨）

```bash
python3 .codex/skills/aipo-workflow/scripts/validate_program.py --path "<layer_dir>"
```
