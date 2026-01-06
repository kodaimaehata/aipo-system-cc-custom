---
name: codex-review
description: Run Codex CLI as a reviewer from Claude Code and save the review report. Automatically chooses the best method (code review vs document review) based on what changed.
---

# Codex Review（Claude Code）

目的: Claude Code の作業結果（差分/成果物）に対して Codex CLI のレビューを実行し、レポートを保存する。

## 自動判定（重要）

- **デフォルト（主にドキュメント等（md/yaml/json中心）**の場合を想定）: 対象ファイルと観点をプロンプトに含めて `codex exec` でレビュー（対象を絞れる）
- **ユーザーからコード変更に対するレビューを指示された**場合: 差分レビュー（Codex が `git diff` を参照してレビュー）を優先


## 実行（推奨: script）

```bash
python3 .claude/skills/codex-review/scripts/codex_review.py --path "<repo_or_layer_dir>" --lang <ja|en>
```

## 出力フォーマット（重要）

- `--lang ja` の場合、見出し/固定ラベルは **日本語**に統一する（例: `概要`, `質問`, `次のアクション（提案）`）。
- `--lang en` の場合、英語に統一する。

## 安全策（重要）

- Never include（常に除外）:
  - `.env*`, `.secrets*`, `settings.local.json`
  - `.npmrc`, `.netrc`
  - `secrets/`（または `.secrets/`）配下
  - `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.crt` 等
  - SSH鍵/known_hosts 等（`id_rsa*`, `id_ed25519*`, `authorized_keys`, `known_hosts`）
  - `*.tfstate*`, `*.sqlite*`, `*.db`
  - `**/.git/**`
  - `node_modules/`, `dist/`, `build/`, `.venv/`
- prompt-based 入力では、代表的な秘密値を簡易マスキングする（例: private key ブロック / `sk-` / `ghp_` / `github_pat_` / `xox*` / `AKIA` / JWT / `Bearer ...`）。

## オプション（抜粋）

- `--method auto|review|prompt`（既定: auto）
- `--dry-run`（方式/除外の確認のみ）
- `--keep-tmp`（prompt-based の一時ディレクトリを残す）
- `--timeout <sec>`（Codex 実行のタイムアウト）

### 代表的な使い方

- Claude Code が作業したリポジトリでそのまま実行（未コミット差分）
- AIPOレイヤーで実行（`programs/<project>/` など）

## 出力

- デフォルト出力先:
  - `<repo_or_layer_dir>/codex_review/`
- ファイル名: `codex_review_YYYY-MM-DD[_N].md`

## 言語

- `--lang ja|en` を指定する（推奨）。
- ユーザー指定が無い場合は **チャットで使用している言語**（日本語/英語）に合わせて `--lang` を決める。
  - 日本語の指示で進行しているなら `--lang ja`
  - 英語の指示で進行しているなら `--lang en`
- 手元でスクリプトを単体実行する場合は `--lang auto` でもよい（環境変数や内容から推定）。
