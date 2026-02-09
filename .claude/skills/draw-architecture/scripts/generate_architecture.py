#!/usr/bin/env python3
"""
draw-architecture: テキストからdraw.ioアーキテクチャ図を生成する

Usage:
    python generate_architecture.py --description "User -> WebServer -> Database(db)" --output architecture.drawio
    python generate_architecture.py -d "Client(user) -> API Gateway -> Service -> DB(database)" -o output.drawio

コンポーネントタイプ:
    (db), (database)  - データベース（シリンダー）
    (cache)           - キャッシュ（シリンダー）
    (external), (ext) - 外部サービス（雲）
    (container)       - コンテナ（立方体）
    (queue), (mq)     - メッセージキュー（角丸矩形）
    (storage), (s3)   - ストレージ（シリンダー）
    (user), (client)  - ユーザー（人型）
    (lb)              - ロードバランサー（平行四辺形）
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
class Component:
    """アーキテクチャ図のコンポーネント"""
    id: str
    name: str
    component_type: str  # 'database', 'cache', 'external', 'container', 'queue', 'storage', 'user', 'loadbalancer', 'default'


@dataclass
class Connection:
    """コンポーネント間の接続"""
    source_id: str
    target_id: str
    label: str = ""
    bidirectional: bool = False


@dataclass
class ArchitectureData:
    """パースされたアーキテクチャデータ"""
    components: list[Component] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)


class ParseError(Exception):
    """パースエラー"""
    pass


class ArchitectureTextParser:
    """テキストからアーキテクチャデータを抽出

    対応形式:
    - 矢印: ->, →, <->, ↔
    - タイプ指定: Component(type)
    - ラベル付き接続: --(label)-->
    """

    # コンポーネントタイプ判定キーワード
    TYPE_KEYWORDS = {
        'database': ['db', 'database', 'mysql', 'postgresql', 'postgres', 'mongodb', 'dynamodb', 'rds', 'aurora'],
        'cache': ['redis', 'memcached', 'cache', 'elasticache'],
        'storage': ['s3', 'storage', 'bucket', 'blob', 'gcs'],
        'queue': ['queue', 'sqs', 'rabbitmq', 'kafka', 'sns', 'mq', 'messagequeue'],
        'user': ['user', 'client', 'browser', 'mobile', 'app'],
        'loadbalancer': ['lb', 'loadbalancer', 'alb', 'elb', 'nlb', 'nginx', 'haproxy'],
        'external': ['external', 'third-party', 'gateway', 'cdn', 'cloudfront', 'cloudflare'],
        'container': ['docker', 'container', 'k8s', 'kubernetes', 'pod', 'ecs', 'fargate'],
    }

    # タイプエイリアス（明示的な指定用）
    TYPE_ALIASES = {
        'db': 'database',
        'database': 'database',
        'cache': 'cache',
        'redis': 'cache',
        'external': 'external',
        'ext': 'external',
        'cloud': 'external',
        'container': 'container',
        'docker': 'container',
        'k8s': 'container',
        'queue': 'queue',
        'mq': 'queue',
        'storage': 'storage',
        's3': 'storage',
        'user': 'user',
        'client': 'user',
        'lb': 'loadbalancer',
        'loadbalancer': 'loadbalancer',
    }

    # 矢印パターン
    ARROW_PATTERN = re.compile(r'\s*(?:<->|↔|->|→)\s*')
    BIDIRECTIONAL_ARROWS = ['<->', '↔']

    # ラベル付き矢印パターン: --(label)-->
    LABELED_ARROW_PATTERN = re.compile(r'--\(?([^)>]+)\)?-->')

    def __init__(self):
        self.component_counter = 0
        self.components_by_name: dict[str, Component] = {}

    def parse(self, text: str) -> ArchitectureData:
        """テキストをパースしてArchitectureDataを返す"""
        data = ArchitectureData()
        self.components_by_name = {}

        # テキストを正規化
        text = self._normalize_text(text)

        # 行に分割
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # 各行を処理
        for line in lines:
            self._process_line(line, data)

        # 検証
        if not data.components:
            raise ParseError(
                "コンポーネントが検出できませんでした。\n"
                "推奨入力形式: User -> WebServer -> Database(db)"
            )

        if not data.connections:
            raise ParseError(
                "接続（->）が検出できませんでした。\n"
                "推奨入力形式: Component1 -> Component2 -> Component3(type)"
            )

        return data

    def _normalize_text(self, text: str) -> str:
        """テキストの正規化"""
        # 全角記号を半角に
        text = text.replace('：', ':').replace('（', '(').replace('）', ')')
        return text.strip()

    def _process_line(self, line: str, data: ArchitectureData):
        """1行を処理してコンポーネントと接続を抽出"""
        # 矢印が含まれているかチェック
        if not any(arrow in line for arrow in ['->', '→', '<->', '↔']):
            return

        # ラベル付き矢印を処理
        line, labels = self._extract_labels(line)

        # 双方向矢印の位置を記録
        bidirectional_positions = set()
        for i, arrow in enumerate(re.findall(r'<->|↔|->|→', line)):
            if arrow in self.BIDIRECTIONAL_ARROWS:
                bidirectional_positions.add(i)

        # 矢印で分割
        parts = self.ARROW_PATTERN.split(line)

        prev_component: Optional[Component] = None
        connection_index = 0

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # コンポーネントを取得または作成
            component = self._get_or_create_component(part, data)

            if component and prev_component:
                # 接続を作成
                label = labels.get(connection_index, "")
                is_bidirectional = connection_index in bidirectional_positions
                connection = Connection(
                    source_id=prev_component.id,
                    target_id=component.id,
                    label=label,
                    bidirectional=is_bidirectional
                )
                data.connections.append(connection)
                connection_index += 1

            if component:
                prev_component = component

    def _extract_labels(self, line: str) -> tuple[str, dict[int, str]]:
        """ラベル付き矢印からラベルを抽出して通常の矢印に置換"""
        labels = {}
        index = 0

        def replace_labeled_arrow(match):
            nonlocal index
            label = match.group(1).strip()
            labels[index] = label
            index += 1
            return ' -> '

        # ラベル付き矢印を処理
        processed = self.LABELED_ARROW_PATTERN.sub(replace_labeled_arrow, line)

        # 残りの矢印のインデックスを調整
        remaining_arrows = len(re.findall(r'<->|↔|->|→', processed))
        for i in range(index, index + remaining_arrows):
            if i not in labels:
                labels[i] = ""

        return processed, labels

    def _get_or_create_component(self, text: str, data: ArchitectureData) -> Optional[Component]:
        """コンポーネントを取得または作成"""
        text = text.strip()
        if not text:
            return None

        # タイプ指定をパース: Name(type) または Name
        name, explicit_type = self._parse_component_spec(text)

        if not name:
            return None

        # 既存のコンポーネントをチェック
        if name in self.components_by_name:
            return self.components_by_name[name]

        # タイプを決定
        if explicit_type:
            component_type = self.TYPE_ALIASES.get(explicit_type.lower(), 'default')
        else:
            component_type = self._determine_type_from_name(name)

        # 新しいコンポーネントを作成
        component_id = f"component-{self.component_counter}"
        self.component_counter += 1

        component = Component(
            id=component_id,
            name=name,
            component_type=component_type
        )
        data.components.append(component)
        self.components_by_name[name] = component

        return component

    def _parse_component_spec(self, text: str) -> tuple[str, Optional[str]]:
        """コンポーネント指定をパース: Name(type) -> (Name, type)"""
        match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', text)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return text.strip(), None

    def _determine_type_from_name(self, name: str) -> str:
        """名前からタイプを自動判定"""
        name_lower = name.lower()

        for component_type, keywords in self.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return component_type

        return 'default'


class ArchitectureGenerator:
    """drawpyoを使用してアーキテクチャ図を生成"""

    # シェイプスタイル定義
    SHAPE_STYLES = {
        'rectangle': "rounded=0;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};",
        'cylinder': "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fillColor={fill};strokeColor={stroke};",
        'cloud': "ellipse;shape=cloud;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};",
        'cube': "shape=cube;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;darkOpacity=0.05;darkOpacity2=0.1;fillColor={fill};strokeColor={stroke};",
        'queue': "rounded=1;whiteSpace=wrap;html=1;arcSize=30;fillColor={fill};strokeColor={stroke};",
        'storage': "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=10;fillColor={fill};strokeColor={stroke};",
        'user': "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor={fill};strokeColor={stroke};",
        'parallelogram': "shape=parallelogram;perimeter=parallelogramPerimeter;whiteSpace=wrap;html=1;fixedSize=1;fillColor={fill};strokeColor={stroke};",
    }

    # タイプからシェイプへのマッピング
    TYPE_TO_SHAPE = {
        'database': 'cylinder',
        'cache': 'cylinder',
        'storage': 'storage',
        'external': 'cloud',
        'container': 'cube',
        'queue': 'queue',
        'user': 'user',
        'loadbalancer': 'parallelogram',
        'default': 'rectangle',
    }

    # タイプ別カラー
    TYPE_COLORS = {
        'database': {'fill': '#dae8fc', 'stroke': '#6c8ebf'},
        'cache': {'fill': '#d5e8d4', 'stroke': '#82b366'},
        'storage': {'fill': '#fff2cc', 'stroke': '#d6b656'},
        'external': {'fill': '#f5f5f5', 'stroke': '#666666'},
        'container': {'fill': '#e1d5e7', 'stroke': '#9673a6'},
        'queue': {'fill': '#ffe6cc', 'stroke': '#d79b00'},
        'user': {'fill': '#f5f5f5', 'stroke': '#666666'},
        'loadbalancer': {'fill': '#d5e8d4', 'stroke': '#82b366'},
        'default': {'fill': '#dae8fc', 'stroke': '#6c8ebf'},
    }

    # サイズ定義
    SIZES = {
        'rectangle': (120, 60),
        'cylinder': (80, 80),
        'cloud': (120, 80),
        'cube': (100, 70),
        'queue': (100, 50),
        'storage': (100, 60),
        'user': (40, 60),
        'parallelogram': (120, 50),
    }

    # エッジスタイル
    EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;endArrow=classic;endFill=1;"
    BIDIRECTIONAL_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;startArrow=classic;startFill=1;endArrow=classic;endFill=1;"

    def __init__(self):
        # 横方向レイアウト（左から右へ）
        self.x_spacing = 180  # コンポーネント間の横間隔
        self.y_center = 200   # 縦方向の基準位置
        self.y_spacing = 120  # 同レベルのコンポーネント間の縦間隔

    def generate(self, data: ArchitectureData, output_path: str) -> str:
        """アーキテクチャ図を生成してファイルに保存"""
        import drawpyo
        from drawpyo.diagram import objects, edges

        # ファイルとページの作成
        file = drawpyo.File()
        page = drawpyo.Page(file=file, name="Architecture")

        # コンポーネントオブジェクトを保持
        component_objects: dict[str, objects.Object] = {}

        # レイアウト計算
        positions = self._calculate_layout(data)

        # コンポーネントを作成
        for component in data.components:
            pos = positions.get(component.id, (50, self.y_center))
            shape = self.TYPE_TO_SHAPE.get(component.component_type, 'rectangle')
            size = self.SIZES.get(shape, (120, 60))
            colors = self.TYPE_COLORS.get(component.component_type, self.TYPE_COLORS['default'])
            style_template = self.SHAPE_STYLES.get(shape, self.SHAPE_STYLES['rectangle'])
            style = style_template.format(fill=colors['fill'], stroke=colors['stroke'])

            obj = objects.Object(
                page=page,
                value=component.name,
                position=pos,
                size=size,
            )
            # Apply style string after creation
            obj.apply_style_string(style)
            component_objects[component.id] = obj

        # 接続を作成
        for connection in data.connections:
            source = component_objects.get(connection.source_id)
            target = component_objects.get(connection.target_id)

            if source and target:
                e = edges.Edge(
                    page=page,
                    source=source,
                    target=target,
                    endArrow='classic',
                )
                # Set bidirectional arrow if needed
                if connection.bidirectional:
                    e.startArrow = 'classic'
                if connection.label:
                    e.label = connection.label

        # 出力ディレクトリが存在しない場合は作成
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # ファイル保存
        file.file_path = os.path.dirname(os.path.abspath(output_path)) or "."
        file.file_name = os.path.basename(output_path)
        file.write()

        return output_path

    def _calculate_layout(self, data: ArchitectureData) -> dict[str, tuple[int, int]]:
        """コンポーネントのレイアウトを計算（横方向: 左から右）"""
        positions: dict[str, tuple[int, int]] = {}

        # 接続グラフを構築
        children: dict[str, list[str]] = {}
        parents: dict[str, list[str]] = {}

        for conn in data.connections:
            if conn.source_id not in children:
                children[conn.source_id] = []
            children[conn.source_id].append(conn.target_id)

            if conn.target_id not in parents:
                parents[conn.target_id] = []
            parents[conn.target_id].append(conn.source_id)

            # 双方向の場合は逆方向も追加
            if conn.bidirectional:
                if conn.target_id not in children:
                    children[conn.target_id] = []
                children[conn.target_id].append(conn.source_id)

                if conn.source_id not in parents:
                    parents[conn.source_id] = []
                parents[conn.source_id].append(conn.target_id)

        # ルートノードを特定（親がないノード）
        root_nodes = [c.id for c in data.components if c.id not in parents]
        if not root_nodes:
            root_nodes = [data.components[0].id] if data.components else []

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

            for child_id in children.get(node_id, []):
                if child_id not in visited:
                    queue.append((child_id, level + 1))

        # 訪問されなかったノードにレベルを割り当て
        for component in data.components:
            if component.id not in levels:
                levels[component.id] = len(levels)

        # 同じレベルのノードをグループ化
        level_nodes: dict[int, list[str]] = {}
        for node_id, level in levels.items():
            if level not in level_nodes:
                level_nodes[level] = []
            level_nodes[level].append(node_id)

        # 位置を計算
        for level, nodes_at_level in sorted(level_nodes.items()):
            x = 50 + level * self.x_spacing

            # 同レベルのノードを縦に配置
            total_height = (len(nodes_at_level) - 1) * self.y_spacing
            start_y = self.y_center - total_height // 2

            for i, node_id in enumerate(nodes_at_level):
                y = start_y + i * self.y_spacing
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
        description='テキストからdraw.ioアーキテクチャ図を生成する',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
入力形式:
  矢印: ->, →, <->, ↔
  タイプ指定: Component(type)
  対応タイプ: db, cache, external, container, queue, storage, user, lb

Examples:
  %(prog)s -d "User -> WebServer -> Database(db)"
  %(prog)s -d "Client(user) -> API Gateway(external) -> Service(container) -> DB(database)"
  %(prog)s -d "Browser(client) -> LoadBalancer(lb) -> WebServer -> API -> Cache(redis)
API -> DB(postgresql)"
        """
    )

    parser.add_argument(
        '-d', '--description',
        required=True,
        help='アーキテクチャの説明（矢印記法）'
    )

    parser.add_argument(
        '-o', '--output',
        default='./architecture.drawio',
        help='出力ファイルパス（デフォルト: ./architecture.drawio）'
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
        parser_obj = ArchitectureTextParser()
        data = parser_obj.parse(args.description)
    except ParseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  - 検出コンポーネント数: {len(data.components)}")
    for component in data.components:
        print(f"    [{component.component_type}] {component.name}")
    print(f"  - 検出接続数: {len(data.connections)}")
    for conn in data.connections:
        arrow = "<->" if conn.bidirectional else "->"
        label_str = f" ({conn.label})" if conn.label else ""
        print(f"    {conn.source_id} {arrow} {conn.target_id}{label_str}")
    print()

    # アーキテクチャ図を生成
    print("アーキテクチャ図を生成中...")
    generator = ArchitectureGenerator()
    output_file = generator.generate(data, args.output)

    # 出力を検証
    validation = validate_output(output_file)
    if validation["errors"]:
        print(f"警告: 検証エラー: {validation['errors']}", file=sys.stderr)

    print()
    print(f"Success: アーキテクチャ図を生成しました")
    print(f"  出力ファイル: {os.path.abspath(output_file)}")
    print(f"  コンポーネント数: {validation['cell_count'] - 2}")  # mxCell id=0,1 を除く
    print()
    print("確認方法:")
    print("  1. draw.ioアプリで開く")
    print("  2. draw.io Online (https://app.diagrams.net/) でインポート")


if __name__ == "__main__":
    main()
