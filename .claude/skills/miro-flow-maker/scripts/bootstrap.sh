#!/usr/bin/env bash
# miro-flow-maker bootstrap: .env 雛形コピー + uv sync
# 実行場所: リポジトリのどこからでも OK（スクリプトは自身の場所を基準に動作する）。

set -euo pipefail

# スクリプトの親ディレクトリ = miro-flow-maker skill root
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$SKILL_ROOT"

echo "[bootstrap] skill root: $SKILL_ROOT"

# 1. .env 作成（既存なら skip）
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "[bootstrap] created .env from .env.example"
    echo "[bootstrap] WARN: edit .env to set MIRO_ACCESS_TOKEN before running the skill"
  else
    echo "[bootstrap] ERROR: .env.example not found; cannot create .env" >&2
    exit 1
  fi
else
  echo "[bootstrap] .env exists, skipping template copy"
fi

# 2. uv sync（dev extras 含む）
if ! command -v uv >/dev/null 2>&1; then
  echo "[bootstrap] ERROR: uv is not installed. Install with: brew install uv" >&2
  exit 1
fi

# --extra dev で pytest 等の dev 依存も同期（checkout 直後に 'uv run pytest tests/' が通る状態にする）
echo "[bootstrap] uv sync --extra dev ..."
uv sync --extra dev

# 3. 動作確認
echo "[bootstrap] verifying python import ..."
uv run python -c "import miro_flow_maker; print('[bootstrap] miro_flow_maker import OK')"

echo "[bootstrap] verifying pytest availability ..."
uv run python -c "import pytest; print(f'[bootstrap] pytest {pytest.__version__} OK')"

echo "[bootstrap] done. Next step: run tests with 'uv run pytest tests/'"
