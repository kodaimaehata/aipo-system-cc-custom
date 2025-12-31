# Development Environment

## Python環境（uv）

このプロジェクトでは **uv** を使用してPython環境を管理します。

### 新規プロジェクトセットアップ

```bash
# プロジェクト初期化
uv init pptx-skill-dev
cd pptx-skill-dev

# python-pptxを追加
uv add python-pptx

# 開発依存を追加
uv add pytest --dev

# 環境セットアップ
uv sync

# 実行
uv run python script.py
```

### 生成されるファイル

- `pyproject.toml` - 依存定義・メタデータ
- `uv.lock` - ロックファイル
- `.venv/` - 仮想環境（Git管理対象外）

### .gitignore に追加

```
.venv/
__pycache__/
*.pyc
```

## 確認コマンド

```bash
# uvバージョン確認
uv --version

# Pythonバージョン確認
uv run python --version

# インストール済みパッケージ確認
uv pip list
```

## 原則

- 新規Pythonプロジェクトは `pyproject.toml + uv.lock` で管理
- `pip install --user` / `pipx` は使用しない
- 既存プロジェクトで `.python-version` がある場合のみ pyenv を考慮
