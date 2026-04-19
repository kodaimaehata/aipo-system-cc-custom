"""MiroClient のテスト。

httpx.MockTransport を使い、実 API は叩かない。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.exceptions import ExecutionError, InputError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(
    handler: Any,
) -> httpx.MockTransport:
    """テスト用の MockTransport を生成する。"""
    return httpx.MockTransport(handler)


def _make_client(transport: httpx.MockTransport) -> MiroClient:
    """テスト用の MiroClient を生成する。

    base_url に testserver を使い、内部 httpx.Client を差し替える。
    """
    client = MiroClient(access_token="test-token-12345678", base_url="https://test.miro.com/v2")
    # 内部クライアントを MockTransport 付きに差し替え
    client._client.close()
    client._client = httpx.Client(
        headers={
            "Authorization": "Bearer test-token-12345678",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        transport=transport,
        timeout=30.0,
    )
    return client


# ---------------------------------------------------------------------------
# Board 操作: 正常系
# ---------------------------------------------------------------------------


class TestCreateBoard:
    """create_board の正常系テスト。"""

    def test_create_board_minimal(self) -> None:
        """名前のみ指定してボードを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://test.miro.com/v2/boards"
            body = json.loads(request.content)
            assert body["name"] == "Test Board"
            assert "description" not in body
            assert request.headers["Authorization"] == "Bearer test-token-12345678"
            return httpx.Response(
                201,
                json={"id": "board-001", "name": "Test Board", "viewLink": "https://miro.com/board-001"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_board("Test Board")
        assert result["id"] == "board-001"
        assert result["name"] == "Test Board"
        client.close()

    def test_create_board_with_description(self) -> None:
        """名前と説明文を指定してボードを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["name"] == "Test Board"
            assert body["description"] == "A test board"
            return httpx.Response(
                201,
                json={"id": "board-002", "name": "Test Board", "description": "A test board"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_board("Test Board", description="A test board")
        assert result["id"] == "board-002"
        assert result["description"] == "A test board"
        client.close()


class TestGetBoard:
    """get_board の正常系テスト。"""

    def test_get_board(self) -> None:
        """ボード情報を取得できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert str(request.url) == "https://test.miro.com/v2/boards/board-001"
            return httpx.Response(
                200,
                json={"id": "board-001", "name": "Test Board"},
            )

        client = _make_client(_make_transport(handler))
        result = client.get_board("board-001")
        assert result["id"] == "board-001"
        client.close()


# ---------------------------------------------------------------------------
# Frame 操作: 正常系
# ---------------------------------------------------------------------------


class TestCreateFrame:
    """create_frame の正常系テスト。"""

    def test_create_frame(self) -> None:
        """フレームを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://test.miro.com/v2/boards/board-001/frames"
            body = json.loads(request.content)
            assert body["data"]["title"] == "Flow Frame"
            assert body["data"]["format"] == "custom"
            assert body["position"] == {"x": 100.0, "y": 200.0}
            assert body["geometry"] == {"width": 800.0, "height": 600.0}
            return httpx.Response(
                201,
                json={"id": "frame-001", "type": "frame"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_frame(
            board_id="board-001",
            title="Flow Frame",
            x=100.0,
            y=200.0,
            width=800.0,
            height=600.0,
        )
        assert result["id"] == "frame-001"
        client.close()


class TestUpdateFrame:
    """update_frame の正常系 / 異常系テスト。"""

    def test_update_frame_geometry_only(self) -> None:
        """width / height のみ指定 → geometry のみ payload に含まれる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert (
                str(request.url)
                == "https://test.miro.com/v2/boards/B/frames/F"
            )
            body = json.loads(request.content)
            assert body == {"geometry": {"width": 800, "height": 500}}
            return httpx.Response(200, json={"id": "F", "type": "frame"})

        client = _make_client(_make_transport(handler))
        result = client.update_frame("B", "F", width=800, height=500)
        assert result["id"] == "F"
        client.close()

    def test_update_frame_position_only(self) -> None:
        """x / y のみ指定 → position のみ payload に含まれる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            body = json.loads(request.content)
            assert body == {"position": {"x": 100, "y": 200}}
            return httpx.Response(200, json={"id": "F"})

        client = _make_client(_make_transport(handler))
        result = client.update_frame("B", "F", x=100, y=200)
        assert result["id"] == "F"
        client.close()

    def test_update_frame_all_fields(self) -> None:
        """title / x / y / width / height 全指定時の payload。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            body = json.loads(request.content)
            assert body == {
                "data": {"title": "T"},
                "position": {"x": 1, "y": 2},
                "geometry": {"width": 3, "height": 4},
            }
            return httpx.Response(200, json={"id": "F"})

        client = _make_client(_make_transport(handler))
        result = client.update_frame(
            "B", "F", title="T", x=1, y=2, width=3, height=4
        )
        assert result["id"] == "F"
        client.close()

    def test_update_frame_partial_position(self) -> None:
        """x のみ指定時は position に x のみ含まれ y は除外される。"""

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body == {"position": {"x": 5}}
            assert "y" not in body["position"]
            assert "geometry" not in body
            assert "data" not in body
            return httpx.Response(200, json={"id": "F"})

        client = _make_client(_make_transport(handler))
        result = client.update_frame("B", "F", x=5)
        assert result["id"] == "F"
        client.close()

    def test_update_frame_empty_raises(self) -> None:
        """フィールドを一つも指定しないと InputError。"""

        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("request should not be sent")

        client = _make_client(_make_transport(handler))
        with pytest.raises(InputError, match="少なくとも 1 つ"):
            client.update_frame("B", "F")
        client.close()


# ---------------------------------------------------------------------------
# Shape 操作: 正常系
# ---------------------------------------------------------------------------


class TestCreateShape:
    """create_shape の正常系テスト。"""

    def test_create_shape_minimal(self) -> None:
        """最小パラメータでシェイプを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://test.miro.com/v2/boards/board-001/shapes"
            body = json.loads(request.content)
            assert body["data"]["shape"] == "rectangle"
            assert body["data"]["content"] == "Process A"
            assert body["position"] == {"x": 50.0, "y": 100.0}
            assert body["geometry"] == {"width": 200.0, "height": 80.0}
            assert "style" not in body
            assert "parent" not in body
            return httpx.Response(
                201,
                json={"id": "shape-001", "type": "shape"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_shape(
            board_id="board-001",
            shape="rectangle",
            content="Process A",
            x=50.0,
            y=100.0,
            width=200.0,
            height=80.0,
        )
        assert result["id"] == "shape-001"
        client.close()

    def test_create_shape_with_style_and_parent(self) -> None:
        """スタイルと parent_id を指定してシェイプを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["style"] == {"fillColor": "#ff0000"}
            assert body["parent"] == {"id": "frame-001"}
            return httpx.Response(
                201,
                json={"id": "shape-002", "type": "shape"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_shape(
            board_id="board-001",
            shape="diamond",
            content="Decision?",
            x=300.0,
            y=200.0,
            width=150.0,
            height=150.0,
            style={"fillColor": "#ff0000"},
            parent_id="frame-001",
        )
        assert result["id"] == "shape-002"
        client.close()


# ---------------------------------------------------------------------------
# Connector 操作: 正常系
# ---------------------------------------------------------------------------


class TestCreateConnector:
    """create_connector の正常系テスト。"""

    def test_create_connector_minimal(self) -> None:
        """id のみ指定（position なし）でコネクタを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            assert str(request.url) == "https://test.miro.com/v2/boards/board-001/connectors"
            body = json.loads(request.content)
            assert body["startItem"] == {"id": "shape-001"}
            assert body["endItem"] == {"id": "shape-002"}
            assert "style" not in body
            assert "captions" not in body
            return httpx.Response(
                201,
                json={"id": "conn-001", "type": "connector"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_connector(
            board_id="board-001",
            start_item={"id": "shape-001"},
            end_item={"id": "shape-002"},
        )
        assert result["id"] == "conn-001"
        client.close()

    def test_create_connector_with_position(self) -> None:
        """position 指定ありでコネクタを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["startItem"] == {
                "id": "shape-001",
                "position": {"x": 1.0, "y": 0.5},
            }
            assert body["endItem"] == {
                "id": "shape-002",
                "position": {"x": 0.0, "y": 0.5},
            }
            assert "style" not in body
            assert "captions" not in body
            return httpx.Response(
                201,
                json={"id": "conn-003", "type": "connector"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_connector(
            board_id="board-001",
            start_item={"id": "shape-001", "position": {"x": 1.0, "y": 0.5}},
            end_item={"id": "shape-002", "position": {"x": 0.0, "y": 0.5}},
        )
        assert result["id"] == "conn-003"
        client.close()

    def test_create_connector_with_style_and_captions(self) -> None:
        """endStrokeCap, strokeStyle を含むスタイルとキャプション付きでコネクタを作成できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["style"] == {
                "strokeColor": "#0000ff",
                "strokeWidth": "2",
                "endStrokeCap": "stealth",
                "strokeStyle": "normal",
            }
            assert body["captions"] == [{"content": "Yes", "position": "50%"}]
            return httpx.Response(
                201,
                json={"id": "conn-002", "type": "connector"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_connector(
            board_id="board-001",
            start_item={"id": "shape-001", "position": {"x": 1.0, "y": 0.5}},
            end_item={"id": "shape-003", "position": {"x": 0.0, "y": 0.5}},
            style={
                "strokeColor": "#0000ff",
                "strokeWidth": "2",
                "endStrokeCap": "stealth",
                "strokeStyle": "normal",
            },
            captions=[{"content": "Yes", "position": "50%"}],
        )
        assert result["id"] == "conn-002"
        client.close()

    def test_create_connector_mixed_position(self) -> None:
        """start_item に position あり、end_item に position なしの混在ケース。"""
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["startItem"] == {
                "id": "shape-001",
                "position": {"x": 0.5, "y": 1.0},
            }
            assert body["endItem"] == {"id": "shape-002"}
            return httpx.Response(
                201,
                json={"id": "conn-004", "type": "connector"},
            )

        client = _make_client(_make_transport(handler))
        result = client.create_connector(
            board_id="board-001",
            start_item={"id": "shape-001", "position": {"x": 0.5, "y": 1.0}},
            end_item={"id": "shape-002"},
        )
        assert result["id"] == "conn-004"
        client.close()


# ---------------------------------------------------------------------------
# エラーハンドリング: 4xx
# ---------------------------------------------------------------------------


class TestClientError:
    """4xx エラーのテスト。"""

    def test_400_raises_execution_error(self) -> None:
        """HTTP 400 が ExecutionError に変換される。"""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={"message": "Bad Request", "code": "badRequest"},
            )

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="クライアントエラー.*400"):
            client.get_board("invalid-board")
        client.close()

    def test_404_raises_execution_error(self) -> None:
        """HTTP 404 が ExecutionError に変換される。"""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="クライアントエラー.*404"):
            client.get_board("nonexistent")
        client.close()


# ---------------------------------------------------------------------------
# エラーハンドリング: 429 リトライ
# ---------------------------------------------------------------------------


class TestRateLimitRetry:
    """429 リトライのテスト。"""

    def test_429_retries_and_succeeds(self) -> None:
        """429 の後にリトライして成功する。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={"message": "Rate limited"},
                )
            return httpx.Response(
                200,
                json={"id": "board-001", "name": "Test Board"},
            )

        client = _make_client(_make_transport(handler))
        result = client.get_board("board-001")
        assert result["id"] == "board-001"
        assert call_count == 3  # 2 retries + 1 success
        client.close()

    def test_429_exhausts_retries(self) -> None:
        """429 が最大リトライ回数を超えると ExecutionError が発生する。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"message": "Rate limited"},
            )

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="レートリミット超過"):
            client.get_board("board-001")
        # Initial attempt + 3 retries = 4 total
        assert call_count == 4
        client.close()

    def test_429_uses_retry_after_header(self) -> None:
        """Retry-After ヘッダーの値が使用される。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0"},
                    json={"message": "Rate limited"},
                )
            return httpx.Response(200, json={"id": "board-001"})

        client = _make_client(_make_transport(handler))
        result = client.get_board("board-001")
        assert result["id"] == "board-001"
        assert call_count == 2
        client.close()


# ---------------------------------------------------------------------------
# エラーハンドリング: 5xx
# ---------------------------------------------------------------------------


class TestServerError:
    """5xx エラーのテスト。"""

    def test_500_raises_execution_error_no_retry(self) -> None:
        """HTTP 500 が ExecutionError に変換され、リトライされない。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                500,
                json={"message": "Internal Server Error"},
            )

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="サーバーエラー.*500"):
            client.get_board("board-001")
        # 5xx はリトライなし
        assert call_count == 1
        client.close()

    def test_503_raises_execution_error(self) -> None:
        """HTTP 503 が ExecutionError に変換される。"""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                503,
                json={"message": "Service Unavailable"},
            )

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="サーバーエラー.*503"):
            client.create_board("Test")
        client.close()


# ---------------------------------------------------------------------------
# エラーハンドリング: 接続エラー
# ---------------------------------------------------------------------------


class TestConnectionError:
    """接続エラーのテスト。"""

    def test_connection_error_raises_execution_error(self) -> None:
        """接続エラーが ExecutionError に変換される。"""
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = _make_client(_make_transport(handler))
        with pytest.raises(ExecutionError, match="接続エラー"):
            client.get_board("board-001")
        client.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    """コンテキストマネージャのテスト。"""

    def test_context_manager(self) -> None:
        """with 文で使用できる。"""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "board-001"})

        transport = _make_transport(handler)
        with _make_client(transport) as client:
            result = client.get_board("board-001")
            assert result["id"] == "board-001"


# ---------------------------------------------------------------------------
# __init__.py エクスポート
# ---------------------------------------------------------------------------


class TestExport:
    """パッケージエクスポートのテスト。"""

    def test_miro_client_exported(self) -> None:
        """MiroClient が __init__.py からインポートできる。"""
        from miro_flow_maker import MiroClient as Imported
        assert Imported is MiroClient


# ---------------------------------------------------------------------------
# Board item 一覧取得
# ---------------------------------------------------------------------------


class TestGetItemsOnBoard:
    """get_items_on_board の正常系テスト。"""

    def test_get_items_on_board_single_page(self) -> None:
        """cursor が返らない単一ページのレスポンスを取得できる。"""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            assert request.method == "GET"
            assert request.url.path == "/v2/boards/board-001/items"
            assert request.url.params.get("limit") == "50"
            # cursor は未指定（初回リクエスト）
            assert "cursor" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "item-001", "type": "shape"},
                        {"id": "item-002", "type": "connector"},
                    ],
                    "total": 2,
                    "size": 2,
                },
            )

        client = _make_client(_make_transport(handler))
        items = client.get_items_on_board("board-001")
        assert len(items) == 2
        assert items[0]["id"] == "item-001"
        assert items[1]["id"] == "item-002"
        assert len(captured) == 1
        client.close()

    def test_get_items_on_board_multiple_pages(self) -> None:
        """cursor が返る限り次ページを取得し、全ページの data を結合する。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                assert "cursor" not in request.url.params
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "item-001"}, {"id": "item-002"}],
                        "cursor": "cursor-page-2",
                    },
                )
            if call_count == 2:
                assert request.url.params.get("cursor") == "cursor-page-2"
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "item-003"}, {"id": "item-004"}],
                        "cursor": "cursor-page-3",
                    },
                )
            # 最終ページ: cursor なし
            assert request.url.params.get("cursor") == "cursor-page-3"
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "item-005"}],
                },
            )

        client = _make_client(_make_transport(handler))
        items = client.get_items_on_board("board-001")
        assert len(items) == 5
        assert [item["id"] for item in items] == [
            "item-001",
            "item-002",
            "item-003",
            "item-004",
            "item-005",
        ]
        assert call_count == 3
        client.close()

    def test_get_items_on_board_with_item_type_filter(self) -> None:
        """item_type 指定で type クエリパラメータが付与される。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/v2/boards/board-001/items"
            assert request.url.params.get("limit") == "25"
            assert request.url.params.get("type") == "shape"
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "shape-001", "type": "shape"}],
                },
            )

        client = _make_client(_make_transport(handler))
        items = client.get_items_on_board(
            "board-001", limit=25, item_type="shape"
        )
        assert len(items) == 1
        assert items[0]["type"] == "shape"
        client.close()


# ---------------------------------------------------------------------------
# Connector 一覧取得
# ---------------------------------------------------------------------------


class TestGetConnectorsOnBoard:
    """get_connectors_on_board の正常系テスト。"""

    def test_get_connectors_on_board_single_page(self) -> None:
        """単一ページのレスポンスを取得できる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/v2/boards/board-001/connectors"
            assert request.url.params.get("limit") == "50"
            assert "cursor" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "conn-001", "type": "connector"},
                        {"id": "conn-002", "type": "connector"},
                    ],
                },
            )

        client = _make_client(_make_transport(handler))
        connectors = client.get_connectors_on_board("board-001")
        assert len(connectors) == 2
        assert connectors[0]["id"] == "conn-001"
        client.close()

    def test_get_connectors_on_board_multiple_pages(self) -> None:
        """複数ページにまたがるレスポンスを全取得できる。"""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                assert "cursor" not in request.url.params
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "conn-001"}],
                        "cursor": "c2",
                    },
                )
            assert request.url.params.get("cursor") == "c2"
            return httpx.Response(
                200,
                json={"data": [{"id": "conn-002"}, {"id": "conn-003"}]},
            )

        client = _make_client(_make_transport(handler))
        connectors = client.get_connectors_on_board("board-001", limit=10)
        assert len(connectors) == 3
        assert [c["id"] for c in connectors] == [
            "conn-001",
            "conn-002",
            "conn-003",
        ]
        assert call_count == 2
        client.close()


# ---------------------------------------------------------------------------
# Shape 更新 / 削除
# ---------------------------------------------------------------------------


class TestUpdateShape:
    """update_shape の正常系テスト。"""

    def test_update_shape_all_fields(self) -> None:
        """全フィールド指定で PATCH リクエストを送信できる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert (
                str(request.url)
                == "https://test.miro.com/v2/boards/board-001/shapes/shape-001"
            )
            body = json.loads(request.content)
            assert body["data"] == {
                "shape": "rectangle",
                "content": "Updated",
            }
            assert body["position"] == {"x": 10.0, "y": 20.0}
            assert body["geometry"] == {"width": 300.0, "height": 120.0}
            assert body["style"] == {"fillColor": "#00ff00"}
            assert body["parent"] == {"id": "frame-001"}
            return httpx.Response(
                200,
                json={"id": "shape-001", "type": "shape"},
            )

        client = _make_client(_make_transport(handler))
        result = client.update_shape(
            "board-001",
            "shape-001",
            data={"shape": "rectangle", "content": "Updated"},
            position={"x": 10.0, "y": 20.0},
            geometry={"width": 300.0, "height": 120.0},
            style={"fillColor": "#00ff00"},
            parent={"id": "frame-001"},
        )
        assert result["id"] == "shape-001"
        client.close()

    def test_update_shape_partial_fields(self) -> None:
        """None のフィールドは payload に含まれない。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            body = json.loads(request.content)
            # data のみ指定
            assert body == {"data": {"content": "New Text"}}
            assert "position" not in body
            assert "geometry" not in body
            assert "style" not in body
            assert "parent" not in body
            return httpx.Response(
                200,
                json={"id": "shape-002"},
            )

        client = _make_client(_make_transport(handler))
        result = client.update_shape(
            "board-001",
            "shape-002",
            data={"content": "New Text"},
        )
        assert result["id"] == "shape-002"
        client.close()


class TestDeleteShape:
    """delete_shape の正常系テスト。"""

    def test_delete_shape_returns_empty_dict_on_204(self) -> None:
        """204 No Content の場合は空 dict を返す。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert (
                str(request.url)
                == "https://test.miro.com/v2/boards/board-001/shapes/shape-xyz"
            )
            return httpx.Response(204)

        client = _make_client(_make_transport(handler))
        result = client.delete_shape("board-001", "shape-xyz")
        assert result == {}
        client.close()


# ---------------------------------------------------------------------------
# Connector 更新 / 削除
# ---------------------------------------------------------------------------


class TestUpdateConnector:
    """update_connector の正常系テスト。"""

    def test_update_connector_reconnect(self) -> None:
        """接続先変更（startItem / endItem の再設定）ができる。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "PATCH"
            assert (
                str(request.url)
                == "https://test.miro.com/v2/boards/board-001/connectors/conn-001"
            )
            body = json.loads(request.content)
            assert body["startItem"] == {"id": "shape-010"}
            assert body["endItem"] == {
                "id": "shape-020",
                "position": {"x": 0.0, "y": 0.5},
            }
            # 未指定フィールドは含まれない
            assert "style" not in body
            assert "captions" not in body
            assert "shape" not in body
            return httpx.Response(
                200,
                json={"id": "conn-001", "type": "connector"},
            )

        client = _make_client(_make_transport(handler))
        result = client.update_connector(
            "board-001",
            "conn-001",
            start_item={"id": "shape-010"},
            end_item={
                "id": "shape-020",
                "position": {"x": 0.0, "y": 0.5},
            },
        )
        assert result["id"] == "conn-001"
        client.close()


class TestDeleteConnector:
    """delete_connector の正常系テスト。"""

    def test_delete_connector_returns_empty_dict_on_204(self) -> None:
        """204 No Content の場合は空 dict を返す。"""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert (
                str(request.url)
                == "https://test.miro.com/v2/boards/board-001/connectors/conn-999"
            )
            return httpx.Response(204)

        client = _make_client(_make_transport(handler))
        result = client.delete_connector("board-001", "conn-999")
        assert result == {}
        client.close()
