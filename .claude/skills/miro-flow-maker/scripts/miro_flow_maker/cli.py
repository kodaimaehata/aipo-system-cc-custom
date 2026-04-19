"""CLI 引数解析モジュール。

argparse ベースの引数解析と RequestContext 生成を行う。
T004 で本実装を行う。現時点では parse_args のみ最小実装。
"""

from __future__ import annotations

import argparse

from miro_flow_maker.exceptions import InputError
from miro_flow_maker.models import AppConfig, RequestContext

__all__ = ["parse_args", "build_request_context"]

MODES = ("create", "update", "append")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"expected string-compatible CLI argument, got {type(value).__name__}")
    stripped = value.strip()
    return stripped or None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """CLI 引数を解析する。"""
    parser = argparse.ArgumentParser(
        prog="miro_flow_maker",
        description="Miro board flow maker for AIPO system — "
        "generate and update Miro boards from confirmed workflow definitions.",
    )

    parser.add_argument(
        "mode",
        choices=MODES,
        help="Execution mode: create, update, or append",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to confirmed input JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate only, do not write to Miro",
    )
    parser.add_argument(
        "--env-file",
        "--config",
        default=None,
        help="Path to .env file (default: .env in current directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging (equivalent to --log-level DEBUG when log level is omitted)",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=None,
        help="Log level (default: INFO)",
    )

    # --- create-specific options ---
    parser.add_argument(
        "--board-name",
        default=None,
        help="Board name for create mode (default: flow_group_id)",
    )

    # --- update/append-specific options ---
    parser.add_argument(
        "--board-id",
        default=None,
        help="Target board ID (falls back to MIRO_DEFAULT_BOARD_ID)",
    )
    parser.add_argument(
        "--frame-id",
        default=None,
        help="Target frame ID",
    )
    parser.add_argument(
        "--frame-link",
        default=None,
        help="Target frame link URL",
    )
    parser.add_argument(
        "--auto-frame",
        action="store_true",
        default=False,
        help=(
            "append モードで frame 未指定のとき、board 上に新規 frame を自動作成する"
            "（opt-in）"
        ),
    )
    parser.add_argument(
        "--no-auto-resize",
        action="store_true",
        default=False,
        help=(
            "append モード既定の frame 自動リサイズを無効化する"
            "（既定では frame が小さい場合に自動拡張）"
        ),
    )

    return parser.parse_args(argv)


def build_request_context(
    args: argparse.Namespace,
    config: AppConfig,
) -> RequestContext:
    """
    CLI 引数と AppConfig から RequestContext を生成する。
    board_id は args.board_id > config.default_board_id の順で解決する。
    update/append で board_id が解決できない場合は InputError を送出する。

    create モードでは新規 board を作るため、board_id は常に None とする。
    """
    mode = _optional_str(getattr(args, "mode", None))
    if mode not in MODES:
        raise InputError(f"unsupported mode: {mode!r}")

    input_path = _optional_str(getattr(args, "input", None))
    if input_path is None:
        raise InputError("--input is required")

    board_name = _optional_str(getattr(args, "board_name", None))
    cli_board_id = _optional_str(getattr(args, "board_id", None))
    frame_id = _optional_str(getattr(args, "frame_id", None))
    frame_link = _optional_str(getattr(args, "frame_link", None))
    dry_run = bool(getattr(args, "dry_run", False) or config.dry_run_override)
    auto_frame = bool(getattr(args, "auto_frame", False))
    no_auto_resize = bool(getattr(args, "no_auto_resize", False))

    if mode != "append" and (auto_frame or no_auto_resize):
        raise InputError(
            "--auto-frame / --no-auto-resize は append モードでのみ有効 "
            f"(mode={mode!r})"
        )

    if mode == "create":
        if cli_board_id is not None:
            raise InputError("--board-id is not supported in create mode")
        if frame_id is not None or frame_link is not None:
            raise InputError("--frame-id/--frame-link are not supported in create mode")
        return RequestContext(
            mode=mode,
            board_id=None,
            frame_id=None,
            frame_link=None,
            board_name=board_name,
            dry_run=dry_run,
            input_path=input_path,
        )

    if board_name is not None:
        raise InputError("--board-name is only supported in create mode")

    board_id = cli_board_id or config.default_board_id
    if board_id is None:
        raise InputError(
            f"{mode} mode requires --board-id or MIRO_DEFAULT_BOARD_ID"
        )

    if mode == "update" and frame_id is None and frame_link is None:
        raise InputError("update mode requires --frame-id or --frame-link")

    return RequestContext(
        mode=mode,
        board_id=board_id,
        frame_id=frame_id,
        frame_link=None if frame_id is not None else frame_link,
        board_name=None,
        dry_run=dry_run,
        input_path=input_path,
        auto_frame=auto_frame,
        auto_resize=not no_auto_resize,
    )
