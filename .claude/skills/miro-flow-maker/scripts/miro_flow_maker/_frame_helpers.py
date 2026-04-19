"""frame 関連の共通ヘルパー。

update_handler と append_handler の両方が使用する frame_link 解析を
一箇所に集約する。T008 (P1-A) で追加。

設計方針:
- Miro API 自体は呼ばない（純関数のみ）
- 共通ヘルパーのみを集めるため、import は最小限に留める
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

__all__ = ["extract_frame_id_from_link"]


# `#/frames/<id>` 形式を検出する正規表現
_FRAGMENT_FRAME_RE = re.compile(r"/frames/([^/?#]+)")


def extract_frame_id_from_link(frame_link: str) -> str | None:
    """frame のリンク URL から frame_id を抽出する。

    Miro の frame link は以下のような形式をとる:
    - ``https://miro.com/app/board/<board>/?moveToWidget=<frame_id>``
    - ``https://miro.com/app/board/<board>/#/frames/<frame_id>``
    - 上記混在パターン

    Args:
        frame_link: frame のリンク URL。空文字列や不正な URL でも例外を投げない。

    Returns:
        抽出できた frame_id。解析失敗時は None。
    """
    if not frame_link:
        return None

    try:
        parsed = urlparse(frame_link)
    except Exception:
        return None

    # クエリ文字列 moveToWidget を優先
    qs = parse_qs(parsed.query)
    widget = qs.get("moveToWidget")
    if widget:
        return widget[0]

    # fragment (#/frames/<id>)
    fragment = parsed.fragment or ""
    m = _FRAGMENT_FRAME_RE.search(fragment)
    if m:
        return m.group(1)

    # URL 全体からも探す（パス側に `/frames/<id>` が含まれるケース）
    m = _FRAGMENT_FRAME_RE.search(frame_link)
    if m:
        return m.group(1)

    return None
