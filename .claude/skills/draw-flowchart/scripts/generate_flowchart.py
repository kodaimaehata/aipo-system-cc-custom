#!/usr/bin/env python3
"""
draw-flowchart: テキストからdraw.ioフローチャートを生成する

Usage:
    python generate_flowchart.py --description "開始 → 処理1 → 終了" --output flowchart.drawio
    python generate_flowchart.py -d "開始 → 条件判断 → (Yes) 処理A → 終了" -o output.drawio

ループ対応:
    同じラベルのノードへの参照はループバックとして既存ノードを再利用します。
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


def check_drawpyo() -> bool:
    """drawpyoのインストール確認"""
    try:
        import drawpyo
        return True
    except ImportError:
        return False


@dataclass
class Node:
    """フローチャートのノード"""
    id: str
    label: str
    node_type: str  # 'start', 'end', 'process', 'decision'


@dataclass
class Edge:
    """ノード間の接続"""
    source_id: str
    target_id: str
    label: str = ""


@dataclass
class FlowchartData:
    """パースされたフローチャートデータ"""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


class ParseError(Exception):
    """パースエラー"""
    pass


class TextParser:
    """テキストからフローチャートデータを抽出

    MVP対応形式: 矢印記法のみ
    - 横矢印: →, ->, ⇒
    - 縦矢印: ↓
    - 分岐ラベル: (Yes), (No)

    ループ対応:
    - 既存ノードラベルへの参照はループバックとして扱う
    - 同一ラベルでも別ノードが必要な場合は末尾に数字を付ける
    """

    # ノードタイプを判定するキーワード
    START_KEYWORDS_JA = ['開始', 'スタート', '始め', '始まり']
    START_KEYWORDS_EN = ['start', 'begin']
    END_KEYWORDS_JA = ['終了', 'エンド', '完了', '終わり', 'おわり']
    END_KEYWORDS_EN = ['end', 'finish', 'done']
    DECISION_KEYWORDS_JA = ['もし', '条件', '判断', '分岐', '確認', 'チェック', '判定']
    DECISION_KEYWORDS_EN = ['if', 'check', 'verify']

    # 矢印パターン（分割用）
    ARROW_PATTERN = re.compile(r'\s*(?:→|->|⇒|↓)\s*')

    # 矢印検出用
    ARROW_CHARS = ['→', '->', '⇒', '↓']

    def __init__(self):
        self.node_counter = 0
        self.prev_node: Optional[Node] = None  # 前のノード（↓接続用）
        self.nodes_by_label: dict[str, Node] = {}  # ラベルでノードをトラッキング

    def parse(self, text: str) -> FlowchartData:
        """テキストをパースしてFlowchartDataを返す

        Raises:
            ParseError: パースに失敗した場合
        """
        data = FlowchartData()
        self.prev_node = None
        self.nodes_by_label = {}  # リセット

        # テキストを正規化
        text = self._normalize_text(text)

        # 行に分割（↓も含めて）
        lines = self._split_into_lines_with_arrows(text)

        # 各行を処理
        for line in lines:
            self._process_line(line, data)

        # 検証: ノードが0の場合はエラー
        if not data.nodes:
            raise ParseError(
                "ノードが検出できませんでした。\n"
                "推奨入力形式: 開始 → 処理1 → 処理2 → 終了"
            )

        # 検証: ノード1つでエッジ0の場合は警告
        if len(data.nodes) == 1 and len(data.edges) == 0:
            print("警告: ノードが1つだけで接続がありません。", file=sys.stderr)

        return data

    def _normalize_text(self, text: str) -> str:
        """テキストの正規化"""
        # 全角記号を半角に
        text = text.replace('：', ':').replace('（', '(').replace('）', ')')
        return text.strip()

    def _split_into_lines_with_arrows(self, text: str) -> list[str]:
        """テキストを処理可能な行に分割（↓も保持）"""
        lines = text.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if line:
                result.append(line)
        return result

    def _process_line(self, line: str, data: FlowchartData):
        """1行を処理してノードとエッジを抽出"""
        # ↓のみの行は接続マーカーとして扱う（次の行との接続を維持）
        if line == '↓':
            # prev_nodeはそのまま維持（次のノードと接続される）
            return

        # 矢印が含まれているかチェック（↓は単独行で処理済み）
        has_horizontal_arrow = any(arrow in line for arrow in ['→', '->', '⇒'])

        if has_horizontal_arrow:
            self._parse_arrow_flow(line, data)
        else:
            # 単一ノードとして処理（ループバック対応）
            line_stripped = line.strip()
            existing_node = self.nodes_by_label.get(line_stripped)

            if existing_node:
                # 既存ノードを再利用（ループバック）
                node = existing_node
            else:
                node = self._create_node(line_stripped)
                if node:
                    data.nodes.append(node)
                    self.nodes_by_label[line_stripped] = node

            if node:
                # 前のノードがあれば接続（↓による暗黙接続）
                if self.prev_node:
                    edge = Edge(self.prev_node.id, node.id)
                    data.edges.append(edge)
                self.prev_node = node

    def _parse_arrow_flow(self, line: str, data: FlowchartData):
        """矢印で区切られたフローをパース

        ループバック対応:
        - 既存ラベルへの参照は同一ノードを再利用（ループ構造を実現）
        - 行の最初が既存ノードの場合は分岐継続（前行からのエッジなし）
        """
        # 矢印パターンで分割（→, ->, ⇒, ↓ を正しく処理）
        parts = self.ARROW_PATTERN.split(line)

        prev_node: Optional[Node] = self.prev_node  # 前の行からの継続
        current_label = ""
        is_first_node_in_line = True  # 行内の最初のノードかどうか

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 分岐ラベル (Yes) (No) をチェック
            branch_match = re.match(r'^\((.*?)\)\s*(.*)', part)
            if branch_match:
                current_label = branch_match.group(1)
                part = branch_match.group(2).strip()
                if not part:
                    continue

            # 既存ノードをチェック（ループバック対応）
            existing_node = self.nodes_by_label.get(part)

            if existing_node:
                # 既存ノードを再利用（ループバック）
                node = existing_node
                # 行の最初が既存ノードの場合は分岐継続
                # 前行からの不要なエッジを作らない
                if is_first_node_in_line:
                    prev_node = None  # リセットして分岐の起点とする
            else:
                # 新規ノードを作成
                node = self._create_node(part)
                if node:
                    data.nodes.append(node)
                    self.nodes_by_label[part] = node

            if node:
                # 前のノードとエッジを作成
                if prev_node:
                    edge = Edge(prev_node.id, node.id, current_label)
                    data.edges.append(edge)
                    current_label = ""

                prev_node = node
                is_first_node_in_line = False

        # 最後のノードを保持（次の行との接続用）
        self.prev_node = prev_node

    def _create_node(self, text: str) -> Optional[Node]:
        """テキストからノードを作成"""
        text = text.strip()
        if not text:
            return None

        # 箇条書き記号を除去
        text = re.sub(r'^[-・*]\s*', '', text)
        text = re.sub(r'^\d+\.\s*', '', text)

        if not text:
            return None

        node_type = self._determine_node_type(text)
        node_id = f"node-{self.node_counter}"
        self.node_counter += 1

        return Node(id=node_id, label=text, node_type=node_type)

    def _determine_node_type(self, text: str) -> str:
        """テキストからノードタイプを判定"""
        text_lower = text.lower()

        # 日本語キーワード（部分一致）
        for keyword in self.START_KEYWORDS_JA:
            if keyword in text:
                return 'start'

        for keyword in self.END_KEYWORDS_JA:
            if keyword in text:
                return 'end'

        for keyword in self.DECISION_KEYWORDS_JA:
            if keyword in text:
                return 'decision'

        # 英語キーワード（単語境界を考慮）
        for keyword in self.START_KEYWORDS_EN:
            if re.search(rf'\b{keyword}\b', text_lower):
                return 'start'

        for keyword in self.END_KEYWORDS_EN:
            if re.search(rf'\b{keyword}\b', text_lower):
                return 'end'

        for keyword in self.DECISION_KEYWORDS_EN:
            if re.search(rf'\b{keyword}\b', text_lower):
                return 'decision'

        # ?や？で終わる場合は判断ノード
        if text.rstrip().endswith('?') or text.rstrip().endswith('？'):
            return 'decision'

        # デフォルトは処理ノード
        return 'process'


class FlowchartGenerator:
    """drawpyoを使用してフローチャートを生成"""

    # スタイル定義
    STYLES = {
        'start': "rounded=1;whiteSpace=wrap;html=1;arcSize=50;fillColor=#d5e8d4;strokeColor=#82b366;",
        'end': "rounded=1;whiteSpace=wrap;html=1;arcSize=50;fillColor=#f8cecc;strokeColor=#b85450;",
        'process': "rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
        'decision': "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    }

    # サイズ定義
    SIZES = {
        'start': (100, 40),
        'end': (100, 40),
        'process': (120, 50),
        'decision': (120, 80),
    }

    EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;"

    def __init__(self):
        # 横方向レイアウト（左から右へ流れる）
        self.x_spacing = 160  # ノード間の横間隔
        self.y_center = 200   # 縦方向の基準位置
        self.branch_offset = 120  # 分岐時の縦オフセット

    def generate(self, data: FlowchartData, output_path: str) -> str:
        """フローチャートを生成してファイルに保存"""
        import drawpyo
        from drawpyo.diagram import objects, edges

        # ファイルとページの作成
        file = drawpyo.File()
        page = drawpyo.Page(file=file, name="Flowchart")

        # ノードオブジェクトを保持
        node_objects: dict[str, objects.Object] = {}

        # ノードのレイアウト計算
        positions = self._calculate_layout(data)

        # ノードを作成
        for node in data.nodes:
            pos = positions.get(node.id, (50, self.y_center))
            size = self.SIZES.get(node.node_type, (120, 50))
            style = self.STYLES.get(node.node_type, self.STYLES['process'])

            obj = objects.Object(
                page=page,
                value=node.label,
                position=pos,
                size=size,
                style_string=style
            )
            node_objects[node.id] = obj

        # エッジを作成
        for edge in data.edges:
            source = node_objects.get(edge.source_id)
            target = node_objects.get(edge.target_id)

            if source and target:
                e = edges.Edge(
                    page=page,
                    source=source,
                    target=target,
                    style_string=self.EDGE_STYLE
                )
                if edge.label:
                    e.value = edge.label

        # 出力ディレクトリが存在しない場合は作成
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # ファイル保存
        file.file_path = os.path.dirname(os.path.abspath(output_path)) or "."
        file.file_name = os.path.basename(output_path)
        file.write()

        return output_path

    def _calculate_layout(self, data: FlowchartData) -> dict[str, tuple[int, int]]:
        """ノードのレイアウトを計算（分岐対応）"""
        positions: dict[str, tuple[int, int]] = {}

        # エッジからグラフ構造を構築
        children: dict[str, list[tuple[str, str]]] = {}
        parents: dict[str, list[str]] = {}

        for edge in data.edges:
            if edge.source_id not in children:
                children[edge.source_id] = []
            children[edge.source_id].append((edge.target_id, edge.label))

            if edge.target_id not in parents:
                parents[edge.target_id] = []
            parents[edge.target_id].append(edge.source_id)

        # ルートノードを特定（親がないノード）
        root_nodes = [n.id for n in data.nodes if n.id not in parents]
        if not root_nodes:
            root_nodes = [data.nodes[0].id] if data.nodes else []

        # BFSでレベルを割り当て
        levels: dict[str, int] = {}
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(root, 0) for root in root_nodes]

        while queue:
            node_id, level = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            levels[node_id] = level

            for child_id, _ in children.get(node_id, []):
                if child_id not in visited:
                    queue.append((child_id, level + 1))

        # 訪問されなかったノードにレベルを割り当て
        for node in data.nodes:
            if node.id not in levels:
                levels[node.id] = len(levels)

        # 同じレベルのノードをグループ化
        level_nodes: dict[int, list[str]] = {}
        for node_id, level in levels.items():
            if level not in level_nodes:
                level_nodes[level] = []
            level_nodes[level].append(node_id)

        # 判断ノードの子を上下に配置（横方向レイアウトなので分岐は縦方向）
        node_types = {n.id: n.node_type for n in data.nodes}
        branch_y_offsets: dict[str, int] = {}

        for node_id, child_list in children.items():
            if node_types.get(node_id) == 'decision' and len(child_list) >= 2:
                # Yes/No分岐を検出（Yesは上、Noは下）
                for i, (child_id, label) in enumerate(child_list):
                    label_lower = label.lower() if label else ""
                    if any(yes in label_lower for yes in ['yes', 'はい', 'true', 'ok']):
                        branch_y_offsets[child_id] = -self.branch_offset
                    elif any(no in label_lower for no in ['no', 'いいえ', 'false', 'ng']):
                        branch_y_offsets[child_id] = self.branch_offset
                    elif i == 0:
                        branch_y_offsets[child_id] = -self.branch_offset
                    else:
                        branch_y_offsets[child_id] = self.branch_offset

        # 位置を計算（横方向: x が進行方向、y が分岐方向）
        for level, nodes_at_level in sorted(level_nodes.items()):
            x = 50 + level * self.x_spacing  # 横方向に進む

            # 分岐オフセットを適用
            for node_id in nodes_at_level:
                y_offset = branch_y_offsets.get(node_id, 0)

                if y_offset != 0:
                    positions[node_id] = (x, self.y_center + y_offset)
                else:
                    # 同じレベルの他ノードと重ならないように配置
                    existing_y = [pos[1] for nid, pos in positions.items()
                                  if levels.get(nid) == level]
                    y = self.y_center
                    while y in existing_y:
                        y += 100
                    positions[node_id] = (x, y)

        return positions


def validate_output(filepath: str) -> dict:
    """生成ファイルの検証"""
    results = {
        "file_exists": False,
        "valid_xml": False,
        "has_mxfile": False,
        "has_mxGraphModel": False,
        "cell_count": 0,
        "errors": []
    }

    if not os.path.exists(filepath):
        results["errors"].append("ファイルが存在しません")
        return results
    results["file_exists"] = True

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        results["valid_xml"] = True
    except ET.ParseError as e:
        results["errors"].append(f"XMLパースエラー: {e}")
        return results

    if root.tag == "mxfile":
        results["has_mxfile"] = True

    model = root.find(".//mxGraphModel")
    if model is not None:
        results["has_mxGraphModel"] = True

    cells = root.findall(".//mxCell")
    results["cell_count"] = len(cells)

    return results


def main():
    parser = argparse.ArgumentParser(
        description='テキストからdraw.ioフローチャートを生成する',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
入力形式（矢印記法）:
  横矢印: →, ->, ⇒
  縦矢印: ↓
  分岐ラベル: (Yes), (No)

Examples:
  %(prog)s -d "開始 → 処理1 → 処理2 → 終了"
  %(prog)s -d "開始 → 条件判断 → (Yes) 処理A → 終了"
  %(prog)s -d "開始 → データ入力 → 入力チェック → (Yes) 保存 → 終了
入力チェック → (No) エラー表示 → データ入力"
        """
    )

    parser.add_argument(
        '-d', '--description',
        required=True,
        help='フローチャートの説明（矢印記法）'
    )

    parser.add_argument(
        '-o', '--output',
        default='./flowchart.drawio',
        help='出力ファイルパス（デフォルト: ./flowchart.drawio）'
    )

    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='既存ファイルを上書き'
    )

    args = parser.parse_args()

    # 既存ファイルチェック
    if os.path.exists(args.output) and not args.force:
        print(f"Error: ファイルが既に存在します: {args.output}", file=sys.stderr)
        print("上書きするには --force オプションを使用してください。", file=sys.stderr)
        sys.exit(1)

    # drawpyoのインストール確認
    if not check_drawpyo():
        print("Error: drawpyoがインストールされていません。", file=sys.stderr)
        print("インストール方法: pip install drawpyo", file=sys.stderr)
        sys.exit(1)

    print(f"入力テキスト: {args.description}")
    print(f"出力先: {args.output}")
    print()

    # テキストをパース
    print("テキストを解析中...")
    try:
        parser_obj = TextParser()
        data = parser_obj.parse(args.description)
    except ParseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  - 検出ノード数: {len(data.nodes)}")
    for node in data.nodes:
        print(f"    [{node.node_type}] {node.label}")
    print(f"  - 検出エッジ数: {len(data.edges)}")
    for edge in data.edges:
        label_str = f" ({edge.label})" if edge.label else ""
        print(f"    {edge.source_id} -> {edge.target_id}{label_str}")
    print()

    # フローチャートを生成
    print("フローチャートを生成中...")
    generator = FlowchartGenerator()
    output_file = generator.generate(data, args.output)

    # 出力を検証
    validation = validate_output(output_file)
    if validation["errors"]:
        print(f"警告: 検証エラー: {validation['errors']}", file=sys.stderr)

    print()
    print(f"Success: フローチャートを生成しました")
    print(f"  出力ファイル: {os.path.abspath(output_file)}")
    print(f"  ノード数: {validation['cell_count'] - 2}")  # mxCell id=0,1 を除く
    print()
    print("確認方法:")
    print("  1. draw.ioアプリで開く")
    print("  2. draw.io Online (https://app.diagrams.net/) でインポート")


if __name__ == "__main__":
    main()
