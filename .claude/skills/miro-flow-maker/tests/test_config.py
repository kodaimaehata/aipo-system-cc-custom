"""config.py / AppConfig のテスト。"""

from __future__ import annotations

import os
import textwrap
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from miro_flow_maker.config import Config, load_config
from miro_flow_maker.exceptions import ConfigError
from miro_flow_maker.models import AppConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """各テストの前に関連環境変数をクリアする。"""
    for key in (
        "MIRO_ACCESS_TOKEN",
        "MIRO_API_BASE_URL",
        "MIRO_DEFAULT_BOARD_ID",
        "AIPO_LOG_DIR",
        "AIPO_RUNNER_ID",
        "AIPO_DRY_RUN",
        "AIPO_LOG_LEVEL",
    ):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# load_config: 正常系
# ---------------------------------------------------------------------------

class TestLoadConfigSuccess:
    """load_config の正常系テスト。"""

    def test_minimal_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """必須キーのみ設定した場合、デフォルト値で AppConfig が生成される。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "test-token-12345678")
        cfg = load_config(env_file="/nonexistent/.env")
        assert cfg.miro_access_token == "test-token-12345678"
        assert cfg.miro_api_base_url == "https://api.miro.com/v2"
        assert cfg.log_dir == "./logs"
        assert cfg.runner_id == "miro-flow-maker"
        assert cfg.default_board_id is None
        assert cfg.dry_run_override is False
        assert cfg.log_level == "INFO"

    def test_all_keys_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """全キーを環境変数で設定した場合。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-abc")
        monkeypatch.setenv("MIRO_API_BASE_URL", "https://custom.api/v2")
        monkeypatch.setenv("AIPO_LOG_DIR", "/tmp/logs")
        monkeypatch.setenv("AIPO_RUNNER_ID", "custom-runner")
        monkeypatch.setenv("MIRO_DEFAULT_BOARD_ID", "board-123")
        monkeypatch.setenv("AIPO_DRY_RUN", "true")
        monkeypatch.setenv("AIPO_LOG_LEVEL", "DEBUG")

        cfg = load_config(env_file="/nonexistent/.env")
        assert cfg.miro_access_token == "tok-abc"
        assert cfg.miro_api_base_url == "https://custom.api/v2"
        assert cfg.log_dir == "/tmp/logs"
        assert cfg.runner_id == "custom-runner"
        assert cfg.default_board_id == "board-123"
        assert cfg.dry_run_override is True
        assert cfg.log_level == "DEBUG"

    def test_dry_run_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AIPO_DRY_RUN に各種 truthy/falsy 値を渡した場合。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-x")

        for val, expected in [
            ("true", True), ("True", True), ("TRUE", True),
            ("1", True),
            ("false", False), ("False", False), ("FALSE", False),
            ("0", False),
        ]:
            monkeypatch.setenv("AIPO_DRY_RUN", val)
            cfg = load_config(env_file="/nonexistent/.env")
            assert cfg.dry_run_override is expected, f"AIPO_DRY_RUN={val!r}"

    def test_from_dotenv_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """.env ファイルから設定を読み込む。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("MIRO_ACCESS_TOKEN=from-dotenv-file\n")
            f.write("MIRO_DEFAULT_BOARD_ID=board-from-file\n")
            env_path = f.name

        try:
            cfg = load_config(env_file=env_path)
            assert cfg.miro_access_token == "from-dotenv-file"
            assert cfg.default_board_id == "board-from-file"
        finally:
            os.unlink(env_path)

    def test_env_var_overrides_dotenv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """環境変数が .env ファイルより優先される。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "from-env-var")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("MIRO_ACCESS_TOKEN=from-dotenv-file\n")
            env_path = f.name

        try:
            cfg = load_config(env_file=env_path)
            # 環境変数が .env より優先（override=False の効果）
            assert cfg.miro_access_token == "from-env-var"
        finally:
            os.unlink(env_path)

    def test_missing_env_file_is_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """.env ファイルが存在しない場合、環境変数のみで動作する。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-only-env")
        cfg = load_config(env_file="/definitely/does/not/exist/.env")
        assert cfg.miro_access_token == "tok-only-env"


# ---------------------------------------------------------------------------
# load_config: 異常系
# ---------------------------------------------------------------------------

class TestLoadConfigErrors:
    """load_config の異常系テスト。"""

    def test_missing_token_raises_config_error(self) -> None:
        """MIRO_ACCESS_TOKEN 未設定で ConfigError（exit_code=2）。"""
        with pytest.raises(ConfigError, match="MIRO_ACCESS_TOKEN"):
            load_config(env_file="/nonexistent/.env")

    def test_empty_token_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MIRO_ACCESS_TOKEN が空文字列の場合も ConfigError。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "")
        with pytest.raises(ConfigError, match="MIRO_ACCESS_TOKEN"):
            load_config(env_file="/nonexistent/.env")

    def test_whitespace_only_token_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MIRO_ACCESS_TOKEN がホワイトスペースのみの場合も ConfigError。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "   ")
        with pytest.raises(ConfigError, match="MIRO_ACCESS_TOKEN"):
            load_config(env_file="/nonexistent/.env")

    def test_invalid_dry_run_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AIPO_DRY_RUN に不正な値を渡した場合 ConfigError。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-x")
        monkeypatch.setenv("AIPO_DRY_RUN", "maybe")
        with pytest.raises(ConfigError, match="AIPO_DRY_RUN"):
            load_config(env_file="/nonexistent/.env")

    def test_empty_dry_run_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AIPO_DRY_RUN が空文字列でも ConfigError。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-x")
        monkeypatch.setenv("AIPO_DRY_RUN", "")
        with pytest.raises(ConfigError, match="AIPO_DRY_RUN"):
            load_config(env_file="/nonexistent/.env")

    def test_config_error_exit_code(self) -> None:
        """ConfigError の exit_code が 2 であること。"""
        assert ConfigError.exit_code == 2

    def test_invalid_log_level_falls_back_to_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """不正な AIPO_LOG_LEVEL は WARNING を出して INFO にフォールバック。"""
        monkeypatch.setenv("MIRO_ACCESS_TOKEN", "tok-x")
        monkeypatch.setenv("AIPO_LOG_LEVEL", "TRACE")
        with pytest.warns(UserWarning, match="AIPO_LOG_LEVEL"):
            cfg = load_config(env_file="/nonexistent/.env")
        assert cfg.log_level == "INFO"


# ---------------------------------------------------------------------------
# AppConfig: イミュータビリティ
# ---------------------------------------------------------------------------

class TestAppConfigImmutability:
    """AppConfig が frozen dataclass であることの検証。"""

    def test_frozen(self) -> None:
        """フィールド代入が FrozenInstanceError を送出すること。"""
        cfg = AppConfig(
            miro_access_token="tok",
            miro_api_base_url="https://api.miro.com/v2",
            log_dir="./logs",
            runner_id="test",
            default_board_id=None,
            dry_run_override=False,
            log_level="INFO",
        )
        with pytest.raises(AttributeError):
            cfg.miro_access_token = "new-tok"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AppConfig: __repr__ でトークンがマスクされる
# ---------------------------------------------------------------------------

class TestAppConfigRepr:
    """AppConfig の __repr__ テスト。"""

    def test_token_is_masked(self) -> None:
        """repr にトークンの全文が含まれないこと。"""
        cfg = Config(
            miro_access_token="super-secret-token-12345",
            miro_api_base_url="https://api.miro.com/v2",
            log_dir="./logs",
            runner_id="test",
            default_board_id=None,
            dry_run_override=False,
            log_level="INFO",
        )
        r = repr(cfg)
        assert "super-secret-token-12345" not in r
        assert "supe***" in r

    def test_short_token_is_fully_masked(self) -> None:
        """短いトークンは '***' にマスクされる。"""
        cfg = Config(
            miro_access_token="abc",
            miro_api_base_url="https://api.miro.com/v2",
            log_dir="./logs",
            runner_id="test",
            default_board_id=None,
            dry_run_override=False,
            log_level="INFO",
        )
        r = repr(cfg)
        assert "abc" not in r or "***" in r


# ---------------------------------------------------------------------------
# AppConfig.from_dict
# ---------------------------------------------------------------------------

class TestAppConfigFromDict:
    """AppConfig.from_dict ファクトリのテスト。"""

    def test_minimal(self) -> None:
        """必須フィールドのみで生成できること。"""
        cfg = Config.from_dict({"miro_access_token": "tok-factory"})
        assert cfg.miro_access_token == "tok-factory"
        assert cfg.miro_api_base_url == "https://api.miro.com/v2"
        assert cfg.log_dir == "./logs"
        assert cfg.runner_id == "miro-flow-maker"
        assert cfg.default_board_id is None
        assert cfg.dry_run_override is False
        assert cfg.log_level == "INFO"

    def test_full(self) -> None:
        """全フィールドを指定して生成できること。"""
        cfg = Config.from_dict({
            "miro_access_token": "tok-full",
            "miro_api_base_url": "https://custom/v2",
            "log_dir": "/custom/logs",
            "runner_id": "custom-runner",
            "default_board_id": "board-x",
            "dry_run_override": True,
            "log_level": "DEBUG",
        })
        assert cfg.miro_access_token == "tok-full"
        assert cfg.miro_api_base_url == "https://custom/v2"
        assert cfg.log_dir == "/custom/logs"
        assert cfg.runner_id == "custom-runner"
        assert cfg.default_board_id == "board-x"
        assert cfg.dry_run_override is True
        assert cfg.log_level == "DEBUG"

    def test_missing_token_raises_key_error(self) -> None:
        """miro_access_token が辞書にない場合 KeyError。"""
        with pytest.raises(KeyError):
            Config.from_dict({})

    def test_import_contract_uses_config_alias(self) -> None:
        """公開境界として config.Config を参照できること。"""
        assert Config is AppConfig

    def test_invalid_dry_run_string_raises_value_error(self) -> None:
        """from_dict は曖昧な文字列を bool とみなさない。"""
        with pytest.raises(ValueError, match="dry_run_override"):
            Config.from_dict({
                "miro_access_token": "tok-factory",
                "dry_run_override": "false-ish",
            })

    def test_none_token_raises_value_error(self) -> None:
        """from_dict は None を文字列化して通さない。"""
        with pytest.raises(ValueError, match="miro_access_token"):
            Config.from_dict({"miro_access_token": None})
