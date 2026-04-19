"""モード実行オーケストレーションモジュール。

create/update/append の dispatch を行う。
create は SG2 で実装済み。update/append は SG3 で本実装する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from miro_flow_maker.append_handler import AppendHandler
from miro_flow_maker.create_handler import CreateHandler
from miro_flow_maker.exceptions import GateStoppedError, InputError
from miro_flow_maker.gate import validate
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.models import (
    AppConfig,
    ConfirmedInput,
    ExecutionResult,
    RequestContext,
)
from miro_flow_maker.update_handler import UpdateHandler

_SUPPORTED_MODES = ("create", "update", "append")


class ModeHandler(Protocol):
    """SG2/SG3 が実装する mode handler のプロトコル。"""

    def execute(
        self,
        confirmed_input: ConfirmedInput,
        context: RequestContext,
        config: AppConfig,
    ) -> ExecutionResult:
        """
        mode に応じた Miro 反映を実行する。
        dry_run の場合は検証のみ行い、実書き込みしない。
        """
        ...


def _load_input_data(input_path: str) -> dict[str, object]:
    path = Path(input_path)
    if not path.is_file():
        raise InputError(f"input file not found: {input_path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise InputError(f"input file is not valid JSON: {input_path}") from exc
    if not isinstance(data, dict):
        raise InputError("input JSON must be an object")
    return data


def _resolve_mode_handler(mode: str, client: MiroClient) -> ModeHandler:
    if mode == "create":
        return CreateHandler(client)
    if mode == "update":
        return UpdateHandler(client)
    if mode == "append":
        return AppendHandler(client)
    raise InputError(
        f"unsupported mode: {mode!r}. supported modes: {_SUPPORTED_MODES}"
    )


def dispatch(
    mode: str,
    input_path: str,
    config: AppConfig,
    context: RequestContext,
) -> ExecutionResult:
    """
    mode に対応する ModeHandler を解決し、
    review gate を通過した入力を handler に渡す。
    """
    if mode != context.mode:
        raise InputError(f"mode mismatch: dispatch={mode!r}, context={context.mode!r}")

    input_data = _load_input_data(input_path)
    review_result = validate(input_data, context)
    if not review_result.passed or review_result.normalized_input is None:
        raise GateStoppedError(
            "review gate blocked execution",
            stop_reasons=review_result.stop_reasons,
        )

    client = MiroClient(config.miro_access_token, config.miro_api_base_url)
    handler = _resolve_mode_handler(mode, client)
    return handler.execute(review_result.normalized_input, context, config)
