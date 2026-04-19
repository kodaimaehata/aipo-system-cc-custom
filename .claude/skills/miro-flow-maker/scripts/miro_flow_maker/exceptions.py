"""miro_flow_maker パッケージの例外クラス階層。

終了コードと 1:1 対応する例外を定義する。
"""

from __future__ import annotations


class MiroFlowMakerError(Exception):
    """miro_flow_maker パッケージの基底例外。"""

    exit_code: int = 4  # default fallback

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class InputError(MiroFlowMakerError):
    """入力データに関するエラー。終了コード 1。"""

    exit_code = 1


class ConfigError(MiroFlowMakerError):
    """設定に関するエラー。終了コード 2。"""

    exit_code = 2


class GateStoppedError(MiroFlowMakerError):
    """review gate が停止を判断した場合のエラー。終了コード 3。"""

    exit_code = 3

    def __init__(self, message: str = "", stop_reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.stop_reasons: list[str] = stop_reasons or []


class ExecutionError(MiroFlowMakerError):
    """Miro 反映中のエラー。終了コード 4。"""

    exit_code = 4
