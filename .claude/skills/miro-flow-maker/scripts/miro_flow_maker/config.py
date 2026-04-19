"""設定読み込みモジュール。

.env と環境変数から AppConfig を生成する。
読み込み優先順位: CLI > 環境変数 > .env > デフォルト値
（CLI オーバーライドは cli.py の責務。本モジュールは環境変数/.env/デフォルトを扱う。）
"""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

from miro_flow_maker.exceptions import ConfigError
from miro_flow_maker.models import AppConfig as Config, _mask_token

logger = logging.getLogger(__name__)

__all__ = ["Config", "load_config"]

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_TRUTHY = frozenset({"true", "1"})
_FALSY = frozenset({"false", "0"})

# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _parse_bool(raw: str, key: str) -> bool:
    """文字列を bool に変換する。不正な値の場合は ConfigError を送出。"""
    normalised = raw.strip().lower()
    if normalised in _TRUTHY:
        return True
    if normalised in _FALSY:
        return False
    raise ConfigError(
        f"環境変数 {key} の値 '{raw}' は不正です。"
        f" true/false/1/0 のいずれかを指定してください。"
    )


def _resolve_log_level(raw: str | None) -> str:
    """ログレベル文字列を正規化する。不正な値は WARNING を出して INFO にフォールバック。"""
    if raw is None:
        return "INFO"
    normalised = raw.strip().upper()
    if normalised in _VALID_LOG_LEVELS:
        return normalised
    warnings.warn(
        f"AIPO_LOG_LEVEL='{raw}' は不正なログレベルです。"
        f" DEBUG/INFO/WARNING/ERROR のいずれかを指定してください。INFO にフォールバックします。",
        stacklevel=2,
    )
    return "INFO"


def _non_empty_or_none(value: str | None) -> str | None:
    """空文字列を None として扱う。"""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def load_config(env_file: str | None = None) -> Config:
    """.env と環境変数から AppConfig を生成する。

    Parameters
    ----------
    env_file:
        .env ファイルのパス。``None`` の場合はカレントディレクトリの ``.env`` を探す。
        ファイルが存在しない場合は環境変数のみで動作する（CI 環境を想定）。

    Returns
    -------
    AppConfig
        イミュータブルな設定オブジェクト。

    Raises
    ------
    ConfigError
        必須キーの欠落や不正な値が検出された場合（終了コード 2）。
    """
    # --- .env ファイルの読み込み ---
    # python-dotenv が利用可能な場合のみインポートする。
    # インストールされていない環境でも環境変数のみで動作する。
    try:
        from dotenv import load_dotenv as _load_dotenv  # type: ignore[import-untyped]
    except ImportError:
        _load_dotenv = None

    if _load_dotenv is not None:
        if env_file is not None:
            env_path = Path(env_file)
        else:
            env_path = Path.cwd() / ".env"

        if env_path.is_file():
            # override=False: 既存の環境変数は上書きしない（環境変数 > .env の優先順位を保証）
            _load_dotenv(dotenv_path=str(env_path), override=False)
            logger.debug(".env ファイルを読み込みました: %s", env_path)
        else:
            logger.debug(".env ファイルが見つかりません: %s — 環境変数のみで動作します", env_path)
    else:
        logger.debug("python-dotenv が未インストールのため .env の読み込みをスキップします")

    # --- 環境変数から値を取得 ---
    raw_token = os.environ.get("MIRO_ACCESS_TOKEN")
    raw_api_base = os.environ.get("MIRO_API_BASE_URL")
    raw_log_dir = os.environ.get("AIPO_LOG_DIR")
    raw_runner_id = os.environ.get("AIPO_RUNNER_ID")
    raw_board_id = os.environ.get("MIRO_DEFAULT_BOARD_ID")
    raw_dry_run = os.environ.get("AIPO_DRY_RUN")
    raw_log_level = os.environ.get("AIPO_LOG_LEVEL")

    # --- バリデーション: 必須キー ---
    token = _non_empty_or_none(raw_token)
    if token is None:
        raise ConfigError(
            "MIRO_ACCESS_TOKEN が設定されていません。"
            " .env ファイルまたは環境変数で設定してください。"
        )

    # --- 型変換 & デフォルト値 ---
    api_base_url = (raw_api_base or "").strip() or "https://api.miro.com/v2"
    log_dir = (raw_log_dir or "").strip() or "./logs"
    runner_id = (raw_runner_id or "").strip() or "miro-flow-maker"
    default_board_id = _non_empty_or_none(raw_board_id)
    dry_run_override = _parse_bool(raw_dry_run, "AIPO_DRY_RUN") if raw_dry_run is not None else False
    log_level = _resolve_log_level(raw_log_level)

    # --- AppConfig 構築 ---
    config = Config(
        miro_access_token=token,
        miro_api_base_url=api_base_url,
        log_dir=log_dir,
        runner_id=runner_id,
        default_board_id=default_board_id,
        dry_run_override=dry_run_override,
        log_level=log_level,
    )

    logger.info(
        "設定を読み込みました: token=%s, api_base_url=%s, runner_id=%s, "
        "default_board_id=%s, dry_run_override=%s, log_level=%s",
        _mask_token(config.miro_access_token),
        config.miro_api_base_url,
        config.runner_id,
        config.default_board_id,
        config.dry_run_override,
        config.log_level,
    )

    return config
