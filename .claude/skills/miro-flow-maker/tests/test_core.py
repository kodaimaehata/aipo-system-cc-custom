"""core.py の dispatch / _resolve_mode_handler テスト。

T006 で update / append が dispatch に登録されたことを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from miro_flow_maker.append_handler import AppendHandler
from miro_flow_maker.core import _resolve_mode_handler
from miro_flow_maker.create_handler import CreateHandler
from miro_flow_maker.exceptions import InputError
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.update_handler import UpdateHandler


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock(spec=MiroClient)


class TestResolveModeHandler:
    """_resolve_mode_handler が各モードに正しい handler を返すこと。"""

    def test_create_returns_create_handler(self, mock_client: MagicMock) -> None:
        handler = _resolve_mode_handler("create", mock_client)
        assert isinstance(handler, CreateHandler)

    def test_update_returns_update_handler(self, mock_client: MagicMock) -> None:
        handler = _resolve_mode_handler("update", mock_client)
        assert isinstance(handler, UpdateHandler)

    def test_append_returns_append_handler(self, mock_client: MagicMock) -> None:
        handler = _resolve_mode_handler("append", mock_client)
        assert isinstance(handler, AppendHandler)

    def test_unsupported_mode_raises_input_error(
        self, mock_client: MagicMock
    ) -> None:
        with pytest.raises(InputError, match="unsupported mode"):
            _resolve_mode_handler("delete", mock_client)
