"""描画計画モジュール。

ConfirmedInput から Miro item の描画計画（DrawingPlan）を組み立てる。
Miro API に依存しない純粋なデータ構造のみを扱う。

レイアウト戦略: 横スイムレーン + 左→右フロー
- 各 lane は水平行（高さ=LANE_HEIGHT 固定、幅=コンテンツ依存）
- Lane ラベルは左端 LANE_LABEL_WIDTH の領域
- node は lane 内で左→右に配置（列 rank は topological sort で決定）
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from miro_flow_maker.models import ConfirmedInput, ConnectionDef, LaneDef, NodeDef

# ---------------------------------------------------------------------------
# レイアウト定数
# ---------------------------------------------------------------------------

LANE_HEIGHT: int = 250
LANE_GAP: int = 10  # スイムレーン間の空白
LANE_LABEL_WIDTH: int = 150
NODE_WIDTH: int = 120
NODE_HEIGHT: int = 60
NODE_GAP_X: int = 60
SYSTEM_LABEL_WIDTH: int = 80
SYSTEM_LABEL_HEIGHT: int = 25
SYSTEM_LABEL_GAP: int = 5
FRAME_PADDING: int = 50

# append モード専用定数。既存 frame の占有領域下端と新規追加コンテンツとの
# 間に設ける余白（論理座標）。``append_handler.APPEND_GAP`` と同値を保持する
# — 両者は同じレイアウト概念のため、値を変更する際は両方を揃えること。
APPEND_GAP: float = 60.0

# --- 後方互換 ---
LANE_WIDTH: int = LANE_LABEL_WIDTH
NODE_GAP: int = NODE_GAP_X


# ---------------------------------------------------------------------------
# Plan 系 dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FramePlan:
    """frame の描画計画。"""

    title: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class LanePlan:
    """lane (actor_lane / system_lane) の描画計画。"""

    id: str
    type: str
    """'actor_lane' または 'system_lane'"""
    label: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    semantic_id: str


@dataclass(frozen=True)
class NodePlan:
    """node の描画計画。"""

    id: str
    type: str
    """'start', 'process', 'decision', 'end'"""
    label: str
    x: float
    y: float
    width: float
    height: float
    lane_id: str
    semantic_id: str


@dataclass(frozen=True)
class EndpointPlan:
    """system_access の終点 shape の描画計画。後方互換のため型定義を残す。"""

    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    system_id: str
    semantic_id: str


@dataclass(frozen=True)
class SystemLabelPlan:
    """system_access から派生する小 shape の描画計画。

    task node の直下に配置し、アクセス先 system を表示する。
    """

    id: str
    """'sl-{node_id}-{system_id}' 形式"""
    label: str
    """system lane の label"""
    x: float
    y: float
    width: float
    height: float
    node_id: str
    """対応する task node の id"""
    system_id: str
    """対応する system lane の id"""


@dataclass(frozen=True)
class ConnectorPlan:
    """connector の描画計画。"""

    id: str
    from_plan_id: str
    to_plan_id: str
    type: str
    """'business_flow' または 'system_access'"""
    label: str
    is_back_edge: bool = False
    """差戻し等で rank が逆行する edge"""


@dataclass(frozen=True)
class DrawingPlan:
    """Miro board の描画計画全体。"""

    board_name: str
    frame: FramePlan
    lanes: list[LanePlan] = field(default_factory=list)
    nodes: list[NodePlan] = field(default_factory=list)
    endpoints: list[EndpointPlan] = field(default_factory=list)
    connectors: list[ConnectorPlan] = field(default_factory=list)
    system_labels: list[SystemLabelPlan] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------

def _detect_back_edges(
    nodes: list[NodeDef],
    edges: list[tuple[str, str]],
) -> set[tuple[str, str]]:
    """差戻し edge（サイクルを形成し、入力順で逆行する edge）を検出する。

    ノードの入力順を自然な業務フロー順として利用する。
    サイクルに含まれる edge のうち、to の入力順 index が from より
    小さいものを back edge として返す。
    """
    node_ids = {n.id for n in nodes}
    # 入力順 index: 小さい方がフローの上流
    node_order: dict[str, int] = {n.id: i for i, n in enumerate(nodes)}

    graph: dict[str, list[str]] = defaultdict(list)
    for from_id, to_id in edges:
        graph[from_id].append(to_id)

    # DFS でサイクルに参加する edge を検出
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in node_ids}
    cycle_edges: set[tuple[str, str]] = set()

    # DFS の開始順を入力順で固定（決定的な結果を得るため）
    sorted_nodes = sorted(node_ids, key=lambda n: node_order.get(n, 0))

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in graph.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                cycle_edges.add((u, v))
            elif color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for n in sorted_nodes:
        if color[n] == WHITE:
            dfs(n)

    # サイクル edge のうち、to の入力順 < from の入力順のものを back edge とする
    # これにより「差戻し」（後ろのステップから前のステップへの逆行）を検出する
    back: set[tuple[str, str]] = set()
    for from_id, to_id in cycle_edges:
        if node_order.get(to_id, 0) < node_order.get(from_id, 0):
            back.add((from_id, to_id))

    # もしサイクル edge で to > from のものがあれば、
    # それでもサイクルが残る場合は全て back edge として扱う
    if cycle_edges and not back:
        back = cycle_edges

    return back


def _compute_ranks(
    nodes: list[NodeDef],
    connections: list[ConnectionDef],
) -> dict[str, int]:
    """business_flow connector から DAG を構築し、各 node の列 rank を返す。

    差戻し edge（サイクルを形成する edge）を検出して rank 計算から除外する。
    rank は Kahn's algorithm で最長パスとして計算する。
    """
    node_ids = {n.id for n in nodes}

    # business_flow edges のみ抽出
    biz_edges: list[tuple[str, str]] = []
    for conn in connections:
        if conn.type == "business_flow" and conn.from_id in node_ids and conn.to_id in node_ids:
            biz_edges.append((conn.from_id, conn.to_id))

    if not biz_edges:
        # edge がない場合は全 node を rank 0 に
        return {n.id: 0 for n in nodes}

    # back edge を検出して除外
    back_edges = _detect_back_edges(nodes, biz_edges)
    forward_edges = [e for e in biz_edges if e not in back_edges]

    # Kahn's algorithm で最長パス（= rank）を計算
    graph: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n_id: 0 for n_id in node_ids}

    for from_id, to_id in forward_edges:
        graph[from_id].append(to_id)
        in_degree[to_id] = in_degree.get(to_id, 0) + 1

    queue: deque[str] = deque()
    for n_id in node_ids:
        if in_degree.get(n_id, 0) == 0:
            queue.append(n_id)

    ranks: dict[str, int] = {}
    while queue:
        node_id = queue.popleft()
        if node_id not in ranks:
            ranks[node_id] = 0
        for neighbor in graph.get(node_id, []):
            new_rank = ranks[node_id] + 1
            if neighbor not in ranks or ranks[neighbor] < new_rank:
                ranks[neighbor] = new_rank
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # DAG にないノード（孤立ノード）は rank 0
    for n_id in node_ids:
        if n_id not in ranks:
            ranks[n_id] = 0

    return ranks


# ---------------------------------------------------------------------------
# build_drawing_plan
# ---------------------------------------------------------------------------

def build_drawing_plan(
    confirmed_input: ConfirmedInput,
    board_name: str,
) -> DrawingPlan:
    """ConfirmedInput から DrawingPlan を生成する。

    レイアウト戦略:
    - 全 lane（actor + system）を水平行として上から下に並べる
    - 各 lane の左端に LANE_LABEL_WIDTH のラベル領域を設ける
    - node は business_flow の DAG を topological sort して列 rank を決定
    - node を lane 内で左→右に配置
    - system_access は SystemLabelPlan として task node 直下に配置
    - endpoints は空リスト（後方互換）
    """

    # --- lane 分類（入力順を維持） ---
    all_lanes: list[LaneDef] = confirmed_input.lanes
    actor_lanes: list[LaneDef] = [l for l in all_lanes if l.type == "actor_lane"]
    system_lanes: list[LaneDef] = [l for l in all_lanes if l.type == "system_lane"]

    # system lane の label lookup
    system_label_map: dict[str, str] = {sl.id: sl.label for sl in system_lanes}

    # --- 列 rank 計算 ---
    ranks = _compute_ranks(confirmed_input.nodes, confirmed_input.connections)
    max_rank = max(ranks.values()) if ranks else 0

    # --- lane ごとのノード振り分け ---
    lane_node_map: dict[str, list[NodeDef]] = defaultdict(list)
    for node in confirmed_input.nodes:
        lane_node_map[node.actor_id].append(node)

    # --- system_access から SystemLabel 情報を収集 ---
    # node_id -> [(system_id, system_label)] のマッピング
    node_system_accesses: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen_node_system_pairs: set[tuple[str, str]] = set()
    for conn in confirmed_input.connections:
        if conn.type == "system_access" and conn.system_id:
            pair = (conn.from_id, conn.system_id)
            if pair not in seen_node_system_pairs:
                seen_node_system_pairs.add(pair)
                sys_label = system_label_map.get(conn.system_id, conn.system_id)
                node_system_accesses[conn.from_id].append((conn.system_id, sys_label))

    # --- 同一 lane 内・同一 rank のノード数を計算して lane 高さを決定 ---
    # lane ごとに、各 rank に何ノードあるかを集計
    lane_rank_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for node in confirmed_input.nodes:
        r = ranks.get(node.id, 0)
        lane_rank_counts[node.actor_id][r] += 1

    # 各 lane の最大スタック数（同一 rank で最大いくつのノードが縦にスタックするか）
    def _calc_lane_height(lane_id: str) -> float:
        rc = lane_rank_counts.get(lane_id, {})
        if not rc:
            return LANE_HEIGHT
        max_stack = max(rc.values())
        needed = max_stack * NODE_HEIGHT + (max_stack - 1) * NODE_GAP_X
        # SystemLabel の高さも考慮
        # 各ノードの下に最大いくつの SystemLabel があるか
        max_sys_labels = 0
        for node in lane_node_map.get(lane_id, []):
            n_labels = len(node_system_accesses.get(node.id, []))
            if n_labels > max_sys_labels:
                max_sys_labels = n_labels
        sys_label_extra = 0
        if max_sys_labels > 0:
            sys_label_extra = SYSTEM_LABEL_GAP + max_sys_labels * SYSTEM_LABEL_HEIGHT + (max_sys_labels - 1) * SYSTEM_LABEL_GAP
        min_height = needed + sys_label_extra + NODE_GAP_X * 2  # padding top/bottom
        return max(LANE_HEIGHT, min_height)

    # actor lane のみ配置（system lane は作らない — SystemLabelPlan で代替）
    all_lane_defs = actor_lanes
    lane_height = LANE_HEIGHT
    for ld in all_lane_defs:
        h = _calc_lane_height(ld.id)
        if h > lane_height:
            lane_height = h

    # --- lane 幅計算 ---
    content_columns = max_rank + 1
    lane_content_width = content_columns * (NODE_WIDTH + NODE_GAP_X)
    lane_width = LANE_LABEL_WIDTH + lane_content_width + FRAME_PADDING

    # --- lane 配置（水平行: 上から下に） ---
    lane_plans: list[LanePlan] = []
    current_y: float = 0.0

    # actor lanes first, then system lanes
    for lane_def in all_lane_defs:
        lane_plans.append(LanePlan(
            id=lane_def.id,
            type=lane_def.type,
            label=lane_def.label,
            kind=lane_def.kind,
            x=0.0,
            y=current_y,
            width=lane_width,
            height=lane_height,
            semantic_id=lane_def.id,
        ))
        current_y += lane_height + LANE_GAP

    # lane plan lookup
    lane_plan_map: dict[str, LanePlan] = {lp.id: lp for lp in lane_plans}

    # --- node 配置（lane 内で左→右） ---
    node_plans: list[NodePlan] = []

    # lane ごとに rank でグループ化し、同一 rank のノードは縦にスタック
    for lane_def in all_lane_defs:
        lp = lane_plan_map.get(lane_def.id)
        if lp is None:
            continue
        nodes_in_lane = lane_node_map.get(lane_def.id, [])
        if not nodes_in_lane:
            continue

        # rank ごとにグループ化（入力順を維持）
        rank_groups: dict[int, list[NodeDef]] = defaultdict(list)
        for node in nodes_in_lane:
            r = ranks.get(node.id, 0)
            rank_groups[r].append(node)

        for r, group in rank_groups.items():
            col_x = lp.x + LANE_LABEL_WIDTH + r * (NODE_WIDTH + NODE_GAP_X) + NODE_GAP_X / 2
            # 縦方向の中央揃え
            total_stack_height = len(group) * NODE_HEIGHT + (len(group) - 1) * NODE_GAP_X
            start_y = lp.y + (lp.height - total_stack_height) / 2.0

            for i, node in enumerate(group):
                node_y = start_y + i * (NODE_HEIGHT + NODE_GAP_X)
                node_plans.append(NodePlan(
                    id=node.id,
                    type=node.type,
                    label=node.label,
                    x=col_x,
                    y=node_y,
                    width=NODE_WIDTH,
                    height=NODE_HEIGHT,
                    lane_id=node.actor_id,
                    semantic_id=node.id,
                ))

    # node plan lookup
    node_plan_map: dict[str, NodePlan] = {np_.id: np_ for np_ in node_plans}

    # --- SystemLabelPlan 生成 ---
    system_label_plans: list[SystemLabelPlan] = []
    for node_id, sys_list in node_system_accesses.items():
        np_ = node_plan_map.get(node_id)
        if np_ is None:
            continue
        # node の直下に配置
        label_x = np_.x + (np_.width - SYSTEM_LABEL_WIDTH) / 2.0
        label_y = np_.y + np_.height + SYSTEM_LABEL_GAP
        for sys_id, sys_label in sys_list:
            sl_id = f"sl-{node_id}-{sys_id}"
            system_label_plans.append(SystemLabelPlan(
                id=sl_id,
                label=sys_label,
                x=label_x,
                y=label_y,
                width=SYSTEM_LABEL_WIDTH,
                height=SYSTEM_LABEL_HEIGHT,
                node_id=node_id,
                system_id=sys_id,
            ))
            label_y += SYSTEM_LABEL_HEIGHT + SYSTEM_LABEL_GAP

    # --- connector 計画 ---
    node_id_set = {np_.id for np_ in node_plans}

    connector_plans: list[ConnectorPlan] = []
    for conn in confirmed_input.connections:
        if conn.type == "business_flow":
            if conn.from_id in node_id_set and conn.to_id in node_id_set:
                # rank が逆行する edge は back_edge
                from_rank = ranks.get(conn.from_id, 0)
                to_rank = ranks.get(conn.to_id, 0)
                is_back = to_rank <= from_rank and conn.from_id != conn.to_id
                connector_plans.append(ConnectorPlan(
                    id=conn.id,
                    from_plan_id=conn.from_id,
                    to_plan_id=conn.to_id,
                    type=conn.type,
                    label=conn.label,
                    is_back_edge=is_back,
                ))
        elif conn.type == "system_access":
            # system_access の connector: from は node, to は system_label
            if conn.from_id in node_id_set and conn.system_id:
                sl_id = f"sl-{conn.from_id}-{conn.system_id}"
                connector_plans.append(ConnectorPlan(
                    id=conn.id,
                    from_plan_id=conn.from_id,
                    to_plan_id=sl_id,
                    type=conn.type,
                    label=conn.label,
                ))

    # --- endpoints: 空リスト（後方互換） ---
    endpoint_plans: list[EndpointPlan] = []

    # --- frame サイズ計算 ---
    num_lanes = len(all_lane_defs)
    if num_lanes == 0:
        num_lanes = 1
    frame_width = lane_width + FRAME_PADDING * 2
    frame_height = num_lanes * lane_height + FRAME_PADDING * 2

    frame_plan = FramePlan(
        title=confirmed_input.flow_group_label,
        x=-FRAME_PADDING,
        y=-FRAME_PADDING,
        width=frame_width,
        height=frame_height,
    )

    return DrawingPlan(
        board_name=board_name,
        frame=frame_plan,
        lanes=lane_plans,
        nodes=node_plans,
        endpoints=endpoint_plans,
        connectors=connector_plans,
        system_labels=system_label_plans,
    )


# ---------------------------------------------------------------------------
# append モード用: 必要な frame サイズの計算
# ---------------------------------------------------------------------------


def compute_required_append_frame_size(
    plan: "DrawingPlan",
    occupied_bottom: float,
    current_frame: dict[str, object],
) -> tuple[float, float, float, float]:
    """append 時に frame が最低限持つべき (center_x, center_y, width, height) を返す。

    既存 frame の **左上端を固定** し、右下方向に拡張する戦略。Miro の position は
    中心座標なので、width/height を広げた場合は center も (Δw/2, Δh/2) シフトする。

    Args:
        plan: append で追加したい DrawingPlan（frame / lanes / nodes / connectors を含む）。
            plan.frame.width / plan.frame.height は新規コンテンツの論理サイズ。
        occupied_bottom: 既存 frame 内の占有領域の下端 Y 座標（frame 左上基準）。
            空 frame の場合は 0。負値が渡された場合は 0 として扱う。
        current_frame: Miro API から取得した board item の frame dict。
            期待キー: ``"position": {"x": float, "y": float}``,
            ``"geometry": {"width": float, "height": float}``。
            キー欠損時はそれぞれ 0 として計算する。

    Returns:
        (center_x, center_y, width, height): frame の新しい geometry + position。
        既存サイズで十分な場合は現在値と同じものを返す（呼び出し側で差分判定）。
    """
    cur_pos = current_frame.get("position") or {}
    cur_geom = current_frame.get("geometry") or {}

    # dict[str, object] なので float キャストが必要
    def _f(source: object, key: str) -> float:
        if isinstance(source, dict):
            value = source.get(key, 0)
        else:
            value = 0
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    cur_w = _f(cur_geom, "width")
    cur_h = _f(cur_geom, "height")
    cur_cx = _f(cur_pos, "x")
    cur_cy = _f(cur_pos, "y")

    # 既存 frame の左上端（固定点）
    left = cur_cx - cur_w / 2.0
    top = cur_cy - cur_h / 2.0

    # 防御的: 占有領域下端が負値なら 0 とみなす
    safe_occupied_bottom = max(occupied_bottom, 0.0)

    # 必要な幅: 新規コンテンツ横幅が既存より広ければ拡張。
    #   plan.frame.width は build_drawing_plan 内で既に FRAME_PADDING*2 を
    #   含めた値（layout.py build_drawing_plan 参照）。ここで追加 padding を
    #   加えると二重計算になるため加えない。
    req_w = max(cur_w, float(plan.frame.width))
    # 必要な高さ: 占有下端 + GAP + 新規コンテンツ高さ が既存より高ければ拡張。
    #   plan.frame.height も FRAME_PADDING*2 を含むので追加 padding 不要。
    req_h = max(
        cur_h,
        safe_occupied_bottom + APPEND_GAP + float(plan.frame.height),
    )

    # 左上端固定で center を再計算
    new_cx = left + req_w / 2.0
    new_cy = top + req_h / 2.0

    return (new_cx, new_cy, req_w, req_h)
