---
name: aipo-operation
description: AIPO Operation phase for Claude Code. Generate a weekly review / inventory report for an AIPO program under `programs/*`, including project goal, layer structure, per-layer task progress with deliverables links, and an ETA range (90% confidence) based on task estimates. Use for weekly reviews, progress reporting, and operationalizing recurring project updates.
---

# AIPO Operation（Claude Code）

目的: 週次レビュー/棚卸しを **一定フォーマットのレポート**として保存し、継続運用をしやすくする。

## 対象レイヤーを決める

- ルール: `.claude/skills/aipo-core/SKILL.md` の「Layer Directory Resolution」
- 以降、対象フォルダを `<layer_dir>` とする（`layer.yaml` が存在する場所）。

## レポート生成（推奨: script）

プロジェクト全体（root + nested sublayers）を対象に週次レポートを生成する:

```bash
python3 .claude/skills/aipo-operation/scripts/weekly_review.py --path "<layer_dir>" --lang <ja|en>
```

`programs/<project_name>/` を直接指定する場合:

```bash
python3 .claude/skills/aipo-operation/scripts/weekly_review.py --project "<project_name>" --lang <ja|en>
```

## 出力

- デフォルト出力先: `<layer_dir>/weekly_review/weekly_review_YYYY-MM-DD.md`
- 内容仕様: `.claude/skills/aipo-operation/references/report-format.md`

## 言語の統一（重要）

- ユーザーが言語指定しない場合、**チャットで使用している言語**（日本語/英語）に合わせてレポート言語を選ぶ。
  - 日本語の指示で進行しているなら `--lang ja`
  - 英語の指示で進行しているなら `--lang en`
- ユーザーが `lang: ja|en` のように指定した場合はそれを優先する。
- 手元でスクリプトを単体実行する場合は `--lang auto` でもよい（入力内容から推定）。
- レポートの見出し/固定ラベルは `--lang` で **単一言語**に固定する。
- `layer.yaml` / `tasks.yaml` の `goal` / `name` / `notes` が日本語/英語で混在している場合、レポート本文も混在するため、**成果物側の記述言語も揃える**（必要ならSense/Focusで文言を更新する）。
- スクリプトは「見出し/固定ラベル/一部のステータス表示」は統一するが、`goal.description` や `tasks[].name` 等の自由文を自動翻訳はしない（必要ならユーザーが文言を整える）。

## 精度を上げるための推奨（任意）

- 各 Task に `estimate`（例: `2h`, `1d`, `30m`）を入れる（ETAの信頼性が上がる）。
- 各 Layer の最終成果物を明示したい場合は、`layer.yaml` に次の任意フィールドを追加する:
  - `goal.deliverable`: "最終成果物の説明（例: MVP仕様書、LP、プロトタイプなど）"
  - 追加フィールドは validator により拒否されない（必須キーは維持すること）。

