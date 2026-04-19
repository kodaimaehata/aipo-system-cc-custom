"""Miro REST API v2 クライアント。

Board / Frame / Shape / Connector の最小 CRUD 操作を提供する。
httpx 同期クライアントを使用。

設計判断:
- container は使わない。全 item は frame の子として配置する
- lane は shape で論理表現する
- item metadata API は使わない（Miro v2 に存在しない）
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from miro_flow_maker.exceptions import ExecutionError, InputError

logger = logging.getLogger(__name__)

__all__ = ["MiroClient"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_INITIAL_BACKOFF_SEC = 1.0
_BACKOFF_MULTIPLIER = 2.0
_MAX_PAGES = 100


# ---------------------------------------------------------------------------
# MiroClient
# ---------------------------------------------------------------------------


class MiroClient:
    """Miro REST API v2 の同期クライアント。

    Parameters
    ----------
    access_token:
        Miro OAuth2 / Developer token。
    base_url:
        API ベース URL。末尾スラッシュなし。
    """

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.miro.com/v2",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def close(self) -> None:
        """HTTP クライアントを閉じる。"""
        self._client.close()

    def __enter__(self) -> MiroClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal: request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """HTTP リクエストを送信し、JSON レスポンスを返す。

        - 429 (Rate Limit): Retry-After ヘッダー + 指数バックオフで最大 3 回リトライ
        - 4xx: ExecutionError
        - 5xx: ExecutionError（リトライなし）
        - 接続エラー: ExecutionError
        """
        url = f"{self._base_url}{path}"
        backoff = _INITIAL_BACKOFF_SEC

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = self._client.request(
                    method,
                    url,
                    json=json,
                    params=params,
                )
            except httpx.HTTPError as exc:
                raise ExecutionError(
                    f"Miro API 接続エラー: {method} {url} — {exc}"
                ) from exc

            # --- Success ---
            if response.status_code < 400:
                # Some endpoints return 204 with no body
                if response.status_code == 204 or not response.content:
                    return {}
                return response.json()  # type: ignore[no-any-return]

            # --- Rate limit (429) ---
            if response.status_code == 429:
                if attempt >= _MAX_RETRIES:
                    raise ExecutionError(
                        f"Miro API レートリミット超過: {method} {path} — "
                        f"{_MAX_RETRIES} 回リトライ後も 429。"
                        f" Response: {response.text}"
                    )
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    wait = float(retry_after)
                else:
                    wait = backoff
                logger.warning(
                    "Miro API 429 — %s %s — リトライ %d/%d (%.1f 秒待機)",
                    method,
                    path,
                    attempt + 1,
                    _MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                backoff *= _BACKOFF_MULTIPLIER
                continue

            # --- Client error (4xx) ---
            if 400 <= response.status_code < 500:
                raise ExecutionError(
                    f"Miro API クライアントエラー: {method} {path} — "
                    f"HTTP {response.status_code}。"
                    f" Response: {response.text}"
                )

            # --- Server error (5xx) ---
            raise ExecutionError(
                f"Miro API サーバーエラー: {method} {path} — "
                f"HTTP {response.status_code}。"
                f" Response: {response.text}"
            )

        # Should never reach here, but satisfy type checker
        raise ExecutionError(  # pragma: no cover
            f"Miro API リクエスト失敗: {method} {path} — リトライ上限到達"
        )

    # ------------------------------------------------------------------
    # Internal: pagination helper
    # ------------------------------------------------------------------

    def _paginate(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """cursor ベースのページネーションを実行し、全ページの ``data`` を結合して返す。

        Miro API v2 の list 系エンドポイントは以下の形式でレスポンスを返す:

        - ``data``: list[dict] — 各ページのアイテム配列
        - ``cursor``: str | None — 次ページのカーソル（最終ページでは省略または null）

        安全上限として最大 ``_MAX_PAGES`` (=100) ページでループを抜ける。
        """
        collected: list[dict[str, Any]] = []
        current_params: dict[str, Any] = dict(params) if params else {}
        current_params.pop("cursor", None)

        for _page_index in range(_MAX_PAGES):
            response = self._request(method, path, params=current_params)
            page_data = response.get("data") or []
            if isinstance(page_data, list):
                collected.extend(page_data)

            next_cursor = response.get("cursor")
            if not next_cursor:
                break
            current_params["cursor"] = next_cursor
        else:
            logger.warning(
                "Miro API pagination reached safety limit: %s %s (%d pages)",
                method,
                path,
                _MAX_PAGES,
            )

        return collected

    # ------------------------------------------------------------------
    # Board 操作
    # ------------------------------------------------------------------

    def create_board(self, name: str, description: str = "") -> dict[str, Any]:
        """ボードを作成する。

        Parameters
        ----------
        name:
            ボード名。
        description:
            ボードの説明文。

        Returns
        -------
        dict
            Miro API のレスポンス（id, name, viewLink 等を含む）。
        """
        payload: dict[str, Any] = {"name": name}
        if description:
            payload["description"] = description
        return self._request("POST", "/boards", json=payload)

    def get_board(self, board_id: str) -> dict[str, Any]:
        """ボード情報を取得する。

        Parameters
        ----------
        board_id:
            対象ボードの ID。

        Returns
        -------
        dict
            Miro API のレスポンス。
        """
        return self._request("GET", f"/boards/{board_id}")

    # ------------------------------------------------------------------
    # Frame 操作
    # ------------------------------------------------------------------

    def create_frame(
        self,
        board_id: str,
        title: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict[str, Any]:
        """フレームを作成する。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        title:
            フレームのタイトル。
        x, y:
            フレームの中心座標。
        width, height:
            フレームのサイズ。

        Returns
        -------
        dict
            Miro API のレスポンス（id 等を含む）。
        """
        payload: dict[str, Any] = {
            "data": {"title": title, "format": "custom"},
            "position": {"x": x, "y": y},
            "geometry": {"width": width, "height": height},
        }
        return self._request(
            "POST", f"/boards/{board_id}/frames", json=payload
        )

    def update_frame(
        self,
        board_id: str,
        frame_id: str,
        *,
        title: str | None = None,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> dict[str, Any]:
        """フレームを部分更新する。

        ``PATCH /boards/{board_id}/frames/{frame_id}`` を使用する。
        指定された非 None フィールドのみ payload に含める。

        API: https://developers.miro.com/reference/update-frame-item

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        frame_id:
            対象フレームの ID。
        title:
            フレームのタイトル。指定すると ``data.title`` として送信する。
        x, y:
            フレームの中心座標。少なくとも一方を指定すると ``position`` として送信する。
        width, height:
            フレームのサイズ。少なくとも一方を指定すると ``geometry`` として送信する。

        Returns
        -------
        dict
            Miro API のレスポンス。

        Raises
        ------
        InputError
            全フィールドが None（更新対象が空）の場合。
        """
        payload: dict[str, Any] = {}
        if title is not None:
            payload["data"] = {"title": title}
        if x is not None or y is not None:
            payload["position"] = {
                k: v for k, v in (("x", x), ("y", y)) if v is not None
            }
        if width is not None or height is not None:
            payload["geometry"] = {
                k: v
                for k, v in (("width", width), ("height", height))
                if v is not None
            }
        if not payload:
            raise InputError(
                "update_frame: 少なくとも 1 つのフィールドを指定してください"
            )
        return self._request(
            "PATCH",
            f"/boards/{board_id}/frames/{frame_id}",
            json=payload,
        )

    # ------------------------------------------------------------------
    # Shape 操作
    # ------------------------------------------------------------------

    def create_shape(
        self,
        board_id: str,
        shape: str,
        content: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        style: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> dict[str, Any]:
        """シェイプを作成する。

        node, lane label, start/end すべてを shape で表現する。
        parent_id に frame の ID を指定すると frame 内に配置される。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        shape:
            シェイプの種類（'rectangle', 'circle', 'diamond', 等）。
        content:
            シェイプ内のテキスト。
        x, y:
            シェイプの位置（parent 基準の相対座標）。
        width, height:
            シェイプのサイズ。
        style:
            スタイル辞書（fillColor, borderColor 等）。
        parent_id:
            親 frame の ID。指定すると frame の子として配置。

        Returns
        -------
        dict
            Miro API のレスポンス（id 等を含む）。
        """
        payload: dict[str, Any] = {
            "data": {"shape": shape, "content": content},
            "position": {"x": x, "y": y},
            "geometry": {"width": width, "height": height},
        }
        if style is not None:
            payload["style"] = style
        if parent_id is not None:
            payload["parent"] = {"id": parent_id}
        return self._request(
            "POST", f"/boards/{board_id}/shapes", json=payload
        )

    # ------------------------------------------------------------------
    # Connector 操作
    # ------------------------------------------------------------------

    def create_connector(
        self,
        board_id: str,
        start_item: dict[str, Any],
        end_item: dict[str, Any],
        *,
        shape: str | None = None,
        style: dict[str, Any] | None = None,
        captions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """コネクタを作成する。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        start_item:
            接続元アイテム。``{"id": "..."}`` 形式。
            接続面の相対位置を指定する場合は
            ``{"id": "...", "position": {"x": "0%"-"100%", "y": "0%"-"100%"}}``。
        end_item:
            接続先アイテム。フォーマットは start_item と同一。
        shape:
            コネクタの線形。``"straight"``（直線）、``"elbowed"``（直角折れ線）、
            ``"curved"``（曲線）のいずれか。リクエストボディのルートレベルに配置。
        style:
            スタイル辞書（strokeColor, strokeWidth, endStrokeCap,
            strokeStyle 等）。
        captions:
            キャプションのリスト。各要素は
            ``{"content": "...", "position": "50%"}`` 形式。

        Returns
        -------
        dict
            Miro API のレスポンス（id 等を含む）。
        """
        payload: dict[str, Any] = {
            "startItem": start_item,
            "endItem": end_item,
        }
        if shape is not None:
            payload["shape"] = shape
        if style is not None:
            payload["style"] = style
        if captions is not None:
            payload["captions"] = captions
        return self._request(
            "POST", f"/boards/{board_id}/connectors", json=payload
        )

    # ------------------------------------------------------------------
    # Board item 一覧取得
    # ------------------------------------------------------------------

    def get_items_on_board(
        self,
        board_id: str,
        *,
        limit: int = 50,
        item_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """ボード上の item 一覧を取得する。

        ``GET /boards/{board_id}/items`` を使用し、cursor ベースの
        ページネーションで全ページを自動取得する。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        limit:
            1 ページあたりの取得件数（Miro API v2 の上限は 50）。
        item_type:
            絞り込み対象の type（``"shape"``, ``"connector"`` 等）。
            None の場合は全 type を取得する。

        Returns
        -------
        list[dict]
            全ページの ``data`` を結合したリスト。
        """
        params: dict[str, Any] = {"limit": limit}
        if item_type is not None:
            params["type"] = item_type
        return self._paginate(
            "GET", f"/boards/{board_id}/items", params=params
        )

    def get_connectors_on_board(
        self,
        board_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """ボード上の connector 一覧を取得する。

        ``GET /boards/{board_id}/connectors`` を使用し、cursor ベースの
        ページネーションで全ページを自動取得する。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        limit:
            1 ページあたりの取得件数。

        Returns
        -------
        list[dict]
            全ページの ``data`` を結合したリスト。
        """
        params: dict[str, Any] = {"limit": limit}
        return self._paginate(
            "GET", f"/boards/{board_id}/connectors", params=params
        )

    # ------------------------------------------------------------------
    # Shape 更新 / 削除
    # ------------------------------------------------------------------

    def update_shape(
        self,
        board_id: str,
        item_id: str,
        *,
        data: dict[str, Any] | None = None,
        position: dict[str, Any] | None = None,
        geometry: dict[str, Any] | None = None,
        style: dict[str, Any] | None = None,
        parent: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """シェイプを部分更新する。

        ``PATCH /boards/{board_id}/shapes/{item_id}`` を使用する。
        指定されたフィールドのみ payload に含める（None は除外）。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        item_id:
            対象シェイプの ID。
        data:
            ``{"shape": "...", "content": "..."}`` 形式。
        position:
            ``{"x": ..., "y": ...}`` 形式。
        geometry:
            ``{"width": ..., "height": ...}`` 形式。
        style:
            スタイル辞書。
        parent:
            ``{"id": "frame-..."}`` 形式。

        Returns
        -------
        dict
            Miro API のレスポンス。
        """
        payload: dict[str, Any] = {}
        if data is not None:
            payload["data"] = data
        if position is not None:
            payload["position"] = position
        if geometry is not None:
            payload["geometry"] = geometry
        if style is not None:
            payload["style"] = style
        if parent is not None:
            payload["parent"] = parent
        return self._request(
            "PATCH",
            f"/boards/{board_id}/shapes/{item_id}",
            json=payload,
        )

    def delete_shape(
        self,
        board_id: str,
        item_id: str,
    ) -> dict[str, Any]:
        """シェイプを削除する。

        ``DELETE /boards/{board_id}/shapes/{item_id}`` を使用する。
        204 No Content の場合は空 dict を返す（``_request`` で対応済み）。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        item_id:
            対象シェイプの ID。

        Returns
        -------
        dict
            Miro API のレスポンス（通常は空 dict）。
        """
        return self._request(
            "DELETE",
            f"/boards/{board_id}/shapes/{item_id}",
        )

    # ------------------------------------------------------------------
    # Connector 更新 / 削除
    # ------------------------------------------------------------------

    def update_connector(
        self,
        board_id: str,
        connector_id: str,
        *,
        start_item: dict[str, Any] | None = None,
        end_item: dict[str, Any] | None = None,
        style: dict[str, Any] | None = None,
        captions: list[dict[str, Any]] | None = None,
        shape: str | None = None,
    ) -> dict[str, Any]:
        """コネクタを部分更新する。

        ``PATCH /boards/{board_id}/connectors/{connector_id}`` を使用する。
        指定されたフィールドのみ payload に含める（None は除外）。
        ``start_item`` / ``end_item`` は Miro API 上 ``startItem`` / ``endItem``
        にマッピングされる。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        connector_id:
            対象コネクタの ID。
        start_item:
            接続元アイテム。``{"id": "..."}`` 形式。
        end_item:
            接続先アイテム。``{"id": "..."}`` 形式。
        style:
            スタイル辞書。
        captions:
            キャプションのリスト。
        shape:
            コネクタの線形（``"straight"`` / ``"elbowed"`` / ``"curved"``）。

        Returns
        -------
        dict
            Miro API のレスポンス。
        """
        payload: dict[str, Any] = {}
        if start_item is not None:
            payload["startItem"] = start_item
        if end_item is not None:
            payload["endItem"] = end_item
        if style is not None:
            payload["style"] = style
        if captions is not None:
            payload["captions"] = captions
        if shape is not None:
            payload["shape"] = shape
        return self._request(
            "PATCH",
            f"/boards/{board_id}/connectors/{connector_id}",
            json=payload,
        )

    def delete_connector(
        self,
        board_id: str,
        connector_id: str,
    ) -> dict[str, Any]:
        """コネクタを削除する。

        ``DELETE /boards/{board_id}/connectors/{connector_id}`` を使用する。
        204 No Content の場合は空 dict を返す。

        Parameters
        ----------
        board_id:
            対象ボードの ID。
        connector_id:
            対象コネクタの ID。

        Returns
        -------
        dict
            Miro API のレスポンス（通常は空 dict）。
        """
        return self._request(
            "DELETE",
            f"/boards/{board_id}/connectors/{connector_id}",
        )
