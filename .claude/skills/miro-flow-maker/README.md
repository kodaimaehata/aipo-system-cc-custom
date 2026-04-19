# miro-flow-maker

業務記述テキストから Miro ボードに横スイムレーン業務フローを自動生成する Claude Code skill。

使用方法は [`SKILL.md`](./SKILL.md) を参照。`/miro-flow-maker` slash command でトリガーする。

## Setup（初回 / git checkout 直後）

```bash
cd .claude/skills/miro-flow-maker
./scripts/bootstrap.sh
```

または手動で:

```bash
cd .claude/skills/miro-flow-maker
cp .env.example .env            # 作成後、MIRO_ACCESS_TOKEN を記入
uv sync --extra dev             # 仮想環境 (.venv) 作成 + 依存インストール（pytest 含む）
uv run pytest tests/            # 動作確認（すべて pass を期待）
```

`.env` / `.venv/` / `logs/` / `packets/` はすべて `.gitignore` 済み。

## 依存の更新

`pyproject.toml` を変更した後は `uv sync --extra dev` で再同期する。

本番的な実行のみで pytest 等の dev tooling が不要な場合は `uv sync`（`--extra dev` なし）でよい。`scripts/bootstrap.sh` は常に `--extra dev` を付けて同期する（checkout 直後に pytest が通る状態を保証するため）。

## ディレクトリ構成

| パス | 役割 | git 管理 |
|------|------|---------|
| `scripts/miro_flow_maker/` | Python パッケージ本体 | yes |
| `scripts/bootstrap.sh` | 初回セットアップスクリプト | yes |
| `tests/` | pytest スイート | yes |
| `tests/fixtures/` | 正式 fixture（`confirmed_minimal.json`, `confirmed_representative.json`, `rejected_candidate.json`） | 正式 3 件のみ yes、派生 fixture は no |
| `.env` | 認証情報（`MIRO_ACCESS_TOKEN` 等） | no |
| `.env.example` | `.env` の雛形 | yes |
| `pyproject.toml`, `uv.lock` | 依存定義（commit 対象） | yes |
| `.venv/` | uv が管理する仮想環境 | no |
| `logs/` | CLI 実行時の run log | no |
| `packets/` | 業務記述文 (`cp-<flow_group_id>.md`) 保存先 | no |

## トラブルシュート / 運用詳細

SG4 の運用引き継ぎドキュメントを参照:

- `programs/P0006_codex-miro-api-workflow-implementation/sublayers/SG4_smoke_test_and_acceptance_validation/documents/T007_operation_handoff.md`
