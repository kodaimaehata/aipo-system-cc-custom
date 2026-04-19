"""共通レンダリングヘルパー。

create_handler.py と update_handler.py の両方で参照する座標変換関数と
スタイル定数を集約する。Miro API のリクエスト payload 構築に用いる値を
保持するが、Miro API 自体は呼ばない（純粋データ/純関数のみ）。

設計方針:
- create_handler.py の公開シグネチャを変えないため、create_handler.py 側は
  本モジュールの値を re-export する
- update_handler.py は直接本モジュールから import する
- ロジックは最小限。過度な抽象化は行わない
"""

from __future__ import annotations

from typing import Any

from miro_flow_maker.layout import FramePlan

# ---------------------------------------------------------------------------
# 座標変換ヘルパー
# ---------------------------------------------------------------------------
# layout.py は左上基準の論理座標を使う。
# Miro API は中心基準の座標を使い、parent_id 指定時は frame 左上基準の中心座標。


def to_center(x: float, y: float, w: float, h: float) -> tuple[float, float]:
    """左上基準 (x, y, w, h) → 中心座標 (cx, cy)。"""
    return x + w / 2.0, y + h / 2.0


def to_frame_local_center(
    frame: FramePlan,
    item_x: float,
    item_y: float,
    item_w: float,
    item_h: float,
) -> tuple[float, float]:
    """item の左上論理座標を frame 左上基準の中心座標に変換する。

    Miro API の frame 内座標系:
    - frame 左上が (0, 0)
    - position.x, y は item の中心点
    - frame 中心基準ではない

    layout.py: frame.x, frame.y は frame の左上座標（通常 -PADDING）
    item_x, item_y は item の左上座標（content 領域内）
    """
    return (
        item_x - frame.x + item_w / 2.0,
        item_y - frame.y + item_h / 2.0,
    )


# ---------------------------------------------------------------------------
# Lane スタイル
# ---------------------------------------------------------------------------
ACTOR_LANE_STYLE: dict[str, Any] = {
    "fillColor": "#f5f5f5",
    "borderColor": "#cccccc",
    "borderWidth": "1.0",
    "fillOpacity": "0.5",
    "fontFamily": "arial",
    "fontSize": "24",
    "textAlign": "left",
    "textAlignVertical": "top",
    "color": "#a9a9a9",  # DarkGray
}

# Miro API は fontStyle をサポートしない。太字は content を <b> タグで囲む
LANE_BOLD_WRAP: bool = True

SYSTEM_LANE_STYLE: dict[str, Any] = {
    "fillColor": "#e8f0fe",
    "borderColor": "#a0c4ff",
    "borderWidth": "1.0",
    "fillOpacity": "0.5",
    "fontFamily": "arial",
    "fontSize": "14",
    "textAlign": "center",
    "textAlignVertical": "top",
}

# ---------------------------------------------------------------------------
# Node スタイル（type 別）
# ---------------------------------------------------------------------------
NODE_STYLE_BASE: dict[str, Any] = {
    "fontFamily": "arial",
    "fontSize": "14",
    "textAlign": "center",
    "textAlignVertical": "middle",
    "borderWidth": "2.0",
}

NODE_STYLES: dict[str, dict[str, Any]] = {
    "start": {**NODE_STYLE_BASE, "fillColor": "#D5F5E3", "borderColor": "#27AE60"},
    "process": {**NODE_STYLE_BASE, "fillColor": "#FFFFFF", "borderColor": "#2C3E50"},
    "decision": {**NODE_STYLE_BASE, "fillColor": "#FEF9E7", "borderColor": "#F39C12"},
    "end": {**NODE_STYLE_BASE, "fillColor": "#D5D8DC", "borderColor": "#808B96"},
}

ENDPOINT_STYLE: dict[str, Any] = {
    **NODE_STYLE_BASE,
    "fillColor": "#e8eaf6",
    "borderColor": "#5c6bc0",
}

# ---------------------------------------------------------------------------
# SystemLabel スタイル
# ---------------------------------------------------------------------------
SYSTEM_LABEL_STYLE: dict[str, Any] = {
    "fillColor": "#EBF5FB",
    "borderColor": "#3498DB",
    "fontSize": "10",
    "textAlign": "center",
    "textAlignVertical": "middle",
    "borderWidth": "1.0",
    "fontFamily": "arial",
}

# ---------------------------------------------------------------------------
# Connector スタイル
# ---------------------------------------------------------------------------
CONNECTOR_STYLE: dict[str, Any] = {
    "endStrokeCap": "stealth",
    "strokeColor": "#2C3E50",
    "strokeWidth": "2.0",
}

BACK_EDGE_CONNECTOR_STYLE: dict[str, Any] = {
    "endStrokeCap": "stealth",
    "strokeColor": "#2C3E50",
    "strokeWidth": "2.0",
}

# ---------------------------------------------------------------------------
# node type -> Miro shape 種別のマッピング
# ---------------------------------------------------------------------------

NODE_SHAPE_MAP: dict[str, str] = {
    "start": "circle",
    "process": "rectangle",
    "decision": "rhombus",
    "end": "circle",
}


def node_shape(node_type: str) -> str:
    """node type に対応する Miro shape 種別を返す。"""
    return NODE_SHAPE_MAP.get(node_type, "rectangle")


__all__ = [
    "to_center",
    "to_frame_local_center",
    "ACTOR_LANE_STYLE",
    "LANE_BOLD_WRAP",
    "SYSTEM_LANE_STYLE",
    "NODE_STYLE_BASE",
    "NODE_STYLES",
    "ENDPOINT_STYLE",
    "SYSTEM_LABEL_STYLE",
    "CONNECTOR_STYLE",
    "BACK_EDGE_CONNECTOR_STYLE",
    "NODE_SHAPE_MAP",
    "node_shape",
]
