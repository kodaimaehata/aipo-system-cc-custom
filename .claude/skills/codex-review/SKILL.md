---
name: codex-review
description: Run Codex CLI as a reviewer from Claude Code and save the review report.
---

# Codex Review（Claude Code）

目的: Claude Code の作業結果に対して Codex CLI のレビューを実行し、レポートを保存する。

## 実行方法

Claude Code がプロンプトとファイルリストを渡してスクリプトを実行する:

```bash
python3 .claude/skills/codex-review/scripts/codex_review.py \
  --path "<repo>" \
  --lang <ja|en> \
  --files file1.py file2.js ... \
  --prompt - <<'EOF'
<生成したプロンプト>
EOF
```

## Claude Code の責務

1. **変更の意図を分析** - このセッションで何を行ったかを振り返る
2. **レビュープロンプトを生成** - 下記ガイドラインに従う
3. **対象ファイルを特定** - 変更したファイル、関連ファイルをリストアップ
4. **スクリプトを実行** - 上記コマンドを実行

### プロンプト生成ガイドライン

以下を含むプロンプトを生成する:

1. **変更の意図** - 何を達成しようとした変更か
2. **レビュー観点** - 特に確認してほしいポイント
3. **出力フォーマット** - 必要なセクション構造

例:
```
あなたはシニアレビュアーです。
以下の変更をレビューしてください。

## 変更の意図
Chrome拡張のパフォーマンス改善として、並列処理を追加しました。

## 特に確認してほしい点
- 並列処理のエラーハンドリングは適切か
- Promise.all の使い方に問題はないか
- メモリリークの可能性はないか

## 出力フォーマット
- 概要
- P0（必ず修正）
- P1（修正推奨）
- 質問
- 次のアクション（提案）
```

スクリプトが自動的にファイル内容と除外ファイルリストを追記します。

## スクリプトの責務

- **ファイル読み込みガード**: 機密ファイル・バイナリ・大きすぎるファイルを除外
- **ファイル内容取得**: 安全なファイルの内容を読み込み
- **機密値マスキング**: トークン等を自動マスク
- **Codex 呼び出し**: read-only モードで実行
- **レポート保存**: `<repo>/codex_review/` に出力

## 安全策

Never include（常に除外）:
- `.env*`, `.secrets*`, `settings.local.json`
- `.npmrc`, `.netrc`, SSH鍵
- `*.pem`, `*.key` 等の証明書
- `*.sqlite*`, `*.db`, `*.tfstate*`
- `node_modules/`, `dist/`, `build/`, `.venv/`
- バイナリファイル、10MB超のファイル

## オプション

- `--keep-tmp`: 一時ディレクトリを残す（デバッグ用）
- `--timeout <sec>`: Codex 実行のタイムアウト
- `--dry-run`: 検証のみ（Codex 実行しない）

## 言語

- `--lang ja|en` を指定する（推奨）。
- ユーザー指定が無い場合は **チャットで使用している言語**（日本語/英語）に合わせて `--lang` を決める。

## 出力

- `<repo>/codex_review/codex_review_YYYY-MM-DD_HH-MM-SS.md`
