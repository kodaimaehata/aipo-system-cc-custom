from __future__ import annotations

import argparse

import pytest

from miro_flow_maker.cli import build_request_context, parse_args
from miro_flow_maker.exceptions import InputError
from miro_flow_maker.models import AppConfig


def _config(**overrides: object) -> AppConfig:
    base: dict[str, object] = {
        "miro_access_token": "tok-1234",
        "miro_api_base_url": "https://api.miro.com/v2",
        "log_dir": "./logs",
        "runner_id": "miro-flow-maker",
        "default_board_id": None,
        "dry_run_override": False,
        "log_level": "INFO",
    }
    base.update(overrides)
    return AppConfig.from_dict(base)


def test_parse_args_supports_config_alias_and_verbose() -> None:
    args = parse_args(["create", "--input", "input.json", "--config", ".env.test", "--verbose"])
    assert args.mode == "create"
    assert args.input == "input.json"
    assert args.env_file == ".env.test"
    assert args.verbose is True


def test_build_request_context_create_uses_board_name_and_dry_run_override() -> None:
    args = argparse.Namespace(
        mode="create",
        input="input.json",
        board_name="Review Board",
        board_id=None,
        frame_id=None,
        frame_link=None,
        dry_run=False,
    )
    context = build_request_context(args, _config(dry_run_override=True))
    assert context.mode == "create"
    assert context.board_id is None
    assert context.board_name == "Review Board"
    assert context.dry_run is True


def test_build_request_context_update_uses_cli_board_id_and_frame_id_priority() -> None:
    args = argparse.Namespace(
        mode="update",
        input="input.json",
        board_name=None,
        board_id="board-cli",
        frame_id="frame-123",
        frame_link="https://miro.example/frame",
        dry_run=True,
    )
    context = build_request_context(args, _config(default_board_id="board-default"))
    assert context.mode == "update"
    assert context.board_id == "board-cli"
    assert context.frame_id == "frame-123"
    assert context.frame_link is None
    assert context.dry_run is True


def test_build_request_context_append_falls_back_to_default_board_id() -> None:
    args = argparse.Namespace(
        mode="append",
        input="input.json",
        board_name=None,
        board_id=None,
        frame_id=None,
        frame_link=None,
        dry_run=False,
    )
    context = build_request_context(args, _config(default_board_id="board-default"))
    assert context.mode == "append"
    assert context.board_id == "board-default"
    assert context.frame_id is None
    assert context.frame_link is None


def test_build_request_context_update_requires_board_id() -> None:
    args = argparse.Namespace(
        mode="update",
        input="input.json",
        board_name=None,
        board_id=None,
        frame_id="frame-123",
        frame_link=None,
        dry_run=False,
    )
    with pytest.raises(InputError, match="board-id"):
        build_request_context(args, _config())


def test_build_request_context_update_requires_frame_locator() -> None:
    args = argparse.Namespace(
        mode="update",
        input="input.json",
        board_name=None,
        board_id="board-123",
        frame_id=None,
        frame_link=None,
        dry_run=False,
    )
    with pytest.raises(InputError, match="frame-id"):
        build_request_context(args, _config())


def test_build_request_context_rejects_board_name_outside_create() -> None:
    args = argparse.Namespace(
        mode="append",
        input="input.json",
        board_name="illegal",
        board_id="board-123",
        frame_id=None,
        frame_link=None,
        dry_run=False,
    )
    with pytest.raises(InputError, match="board-name"):
        build_request_context(args, _config())


# ---------------------------------------------------------------------------
# --auto-frame / --no-auto-resize flags (Wave2)
# ---------------------------------------------------------------------------


class TestAutoFrameResizeFlags:
    """Wave2: --auto-frame / --no-auto-resize の parse + build_request_context。"""

    def test_auto_frame_flag_parses_append(self) -> None:
        args = parse_args([
            "append", "--input", "f.json",
            "--board-id", "B", "--auto-frame",
        ])
        assert args.auto_frame is True
        assert args.no_auto_resize is False

    def test_no_auto_resize_flag_parses_append(self) -> None:
        args = parse_args([
            "append", "--input", "f.json",
            "--board-id", "B", "--no-auto-resize",
        ])
        assert args.no_auto_resize is True
        assert args.auto_frame is False

    def test_defaults_both_false_on_cli(self) -> None:
        args = parse_args([
            "append", "--input", "f.json", "--board-id", "B",
        ])
        assert args.auto_frame is False
        assert args.no_auto_resize is False

    def test_build_context_append_auto_frame_opt_in(self) -> None:
        args = argparse.Namespace(
            mode="append",
            input="input.json",
            board_name=None,
            board_id="B",
            frame_id=None,
            frame_link=None,
            dry_run=False,
            auto_frame=True,
            no_auto_resize=False,
        )
        context = build_request_context(args, _config())
        assert context.mode == "append"
        assert context.auto_frame is True
        assert context.auto_resize is True

    def test_build_context_append_no_auto_resize(self) -> None:
        args = argparse.Namespace(
            mode="append",
            input="input.json",
            board_name=None,
            board_id="B",
            frame_id="F",
            frame_link=None,
            dry_run=False,
            auto_frame=False,
            no_auto_resize=True,
        )
        context = build_request_context(args, _config())
        assert context.auto_frame is False
        # 反転: --no-auto-resize → auto_resize=False
        assert context.auto_resize is False

    def test_build_context_append_defaults(self) -> None:
        args = argparse.Namespace(
            mode="append",
            input="input.json",
            board_name=None,
            board_id="B",
            frame_id="F",
            frame_link=None,
            dry_run=False,
            auto_frame=False,
            no_auto_resize=False,
        )
        context = build_request_context(args, _config())
        assert context.auto_frame is False
        assert context.auto_resize is True

    def test_build_context_create_auto_frame_raises(self) -> None:
        args = argparse.Namespace(
            mode="create",
            input="input.json",
            board_name=None,
            board_id=None,
            frame_id=None,
            frame_link=None,
            dry_run=False,
            auto_frame=True,
            no_auto_resize=False,
        )
        with pytest.raises(InputError, match="auto-frame"):
            build_request_context(args, _config())

    def test_build_context_update_no_auto_resize_raises(self) -> None:
        args = argparse.Namespace(
            mode="update",
            input="input.json",
            board_name=None,
            board_id="B",
            frame_id="F",
            frame_link=None,
            dry_run=False,
            auto_frame=False,
            no_auto_resize=True,
        )
        with pytest.raises(InputError, match="auto-resize"):
            build_request_context(args, _config())

    def test_build_context_update_auto_frame_raises(self) -> None:
        args = argparse.Namespace(
            mode="update",
            input="input.json",
            board_name=None,
            board_id="B",
            frame_id="F",
            frame_link=None,
            dry_run=False,
            auto_frame=True,
            no_auto_resize=False,
        )
        with pytest.raises(InputError, match="auto-frame"):
            build_request_context(args, _config())
