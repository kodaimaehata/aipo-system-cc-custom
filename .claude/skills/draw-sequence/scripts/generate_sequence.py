#!/usr/bin/env python3
"""
draw-sequence: テキストからdraw.ioシーケンス図を生成する

Usage:
    python generate_sequence.py --description "participants: User, Server
User -> Server: リクエスト
Server --> User: レスポンス" --output sequence.drawio

入力形式:
    participants: Participant1, Participant2, ...  (省略可、自動検出)
    Sender -> Receiver: メッセージ     (同期メッセージ)
    Sender --> Receiver: メッセージ    (非同期/リターンメッセージ)
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
class Participant:
    """シーケンス図の参加者（アクター）"""
    id: str
    name: str
    position: tuple[int, int] = field(default_factory=lambda: (0, 0))


@dataclass
class Message:
    """参加者間のメッセージ"""
    id: str
    from_participant: str
    to_participant: str
    label: str
    arrow_type: str  # 'sync', 'async'


@dataclass
class SequenceData:
    """パースされたシーケンス図データ"""
    participants: list[Participant] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)


class ParseError(Exception):
    """パースエラー"""
    pass


class SequenceParser:
    """テキストからシーケンス図データを抽出"""

    PARTICIPANTS_PATTERN = re.compile(
        r'^participants?\s*:\s*(.+)$',
        re.IGNORECASE
    )

    MESSAGE_PATTERN = re.compile(
        r'^([^\s\-]+)\s*(--?>>?)\s*([^\s:]+)\s*:\s*(.*)$',
        re.UNICODE
    )

    def __init__(self):
        self.message_counter = 0

    def parse(self, text: str) -> SequenceData:
        """テキストをパースしてSequenceDataを返す"""
        data = SequenceData()
        participant_order: list[str] = []
        self.message_counter = 0

        text = self._normalize_text(text)
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            participants_match = self.PARTICIPANTS_PATTERN.match(line)
            if participants_match:
                names = [n.strip() for n in participants_match.group(1).split(',')]
                participant_order = names
                continue

            msg_match = self.MESSAGE_PATTERN.match(line)
            if msg_match:
                sender, arrow, receiver, label = msg_match.groups()

                for p in [sender, receiver]:
                    if p not in participant_order:
                        participant_order.append(p)

                arrow_type = 'async' if arrow.startswith('--') else 'sync'

                message = Message(
                    id=f"msg-{self.message_counter}",
                    from_participant=sender,
                    to_participant=receiver,
                    label=label.strip(),
                    arrow_type=arrow_type
                )
                data.messages.append(message)
                self.message_counter += 1

        for i, name in enumerate(participant_order):
            data.participants.append(Participant(
                id=f"participant-{i}",
                name=name
            ))

        if not data.participants:
            raise ParseError(
                "参加者が検出できませんでした。\n"
                "推奨入力形式:\n"
                "  participants: User, Server, DB\n"
                "  User -> Server: リクエスト"
            )

        if not data.messages:
            raise ParseError(
                "メッセージが検出できませんでした。\n"
                "推奨入力形式:\n"
                "  User -> Server: リクエスト"
            )

        return data

    def _normalize_text(self, text: str) -> str:
        text = text.replace('：', ':').replace('、', ',')
        return text.strip()


class SequenceGenerator:
    """シーケンス図を生成（XML直接生成）"""

    # レイアウト定数
    PARTICIPANT_WIDTH = 80
    PARTICIPANT_HEIGHT = 40
    HORIZONTAL_SPACING = 150
    MESSAGE_VERTICAL_SPACING = 60
    LEFT_MARGIN = 50
    TOP_MARGIN = 30

    def __init__(self):
        self.cell_id_counter = 2  # 0, 1 are reserved

    def _next_id(self) -> str:
        """次のセルIDを生成"""
        cell_id = str(self.cell_id_counter)
        self.cell_id_counter += 1
        return cell_id

    def generate(self, data: SequenceData, output_path: str) -> str:
        """シーケンス図を生成してファイルに保存"""
        self.cell_id_counter = 2

        # 参加者の位置を計算
        participant_positions: dict[str, tuple[int, int]] = {}
        for i, p in enumerate(data.participants):
            x = self.LEFT_MARGIN + i * self.HORIZONTAL_SPACING
            y = self.TOP_MARGIN
            participant_positions[p.name] = (x, y)

        # ライフラインの長さを計算
        lifeline_length = (len(data.messages) + 2) * self.MESSAGE_VERTICAL_SPACING

        # XML構築
        mxfile = ET.Element('mxfile', {
            'host': 'Drawpyo',
            'modified': '2026-01-28T12:00:00',
            'agent': 'Python draw-sequence',
            'version': '21.6.5',
            'type': 'device'
        })

        diagram = ET.SubElement(mxfile, 'diagram', {
            'name': 'Sequence Diagram',
            'id': 'sequence-1'
        })

        graph_model = ET.SubElement(diagram, 'mxGraphModel', {
            'dx': '1000',
            'dy': '600',
            'grid': '1',
            'gridSize': '10',
            'guides': '1',
            'tooltips': '1',
            'connect': '1',
            'arrows': '1',
            'fold': '1',
            'page': '1',
            'pageScale': '1',
            'pageWidth': '850',
            'pageHeight': '1100',
            'math': '0',
            'shadow': '0'
        })

        root = ET.SubElement(graph_model, 'root')

        # 基本セル
        ET.SubElement(root, 'mxCell', {'id': '0'})
        ET.SubElement(root, 'mxCell', {'id': '1', 'parent': '0'})

        # 参加者ボックスとライフラインを作成
        participant_ids: dict[str, str] = {}
        lifeline_x: dict[str, int] = {}

        for p in data.participants:
            pos = participant_positions[p.name]
            cell_id = self._next_id()
            participant_ids[p.name] = cell_id
            lifeline_x[p.name] = pos[0] + self.PARTICIPANT_WIDTH // 2

            # 参加者ボックス
            cell = ET.SubElement(root, 'mxCell', {
                'id': cell_id,
                'value': p.name,
                'style': 'rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;fontStyle=1;',
                'vertex': '1',
                'parent': '1'
            })
            ET.SubElement(cell, 'mxGeometry', {
                'x': str(pos[0]),
                'y': str(pos[1]),
                'width': str(self.PARTICIPANT_WIDTH),
                'height': str(self.PARTICIPANT_HEIGHT),
                'as': 'geometry'
            })

            # ライフライン（破線）
            lifeline_id = self._next_id()
            lifeline_start_y = pos[1] + self.PARTICIPANT_HEIGHT
            lifeline_cell = ET.SubElement(root, 'mxCell', {
                'id': lifeline_id,
                'value': '',
                'style': 'endArrow=none;dashed=1;html=1;strokeColor=#999999;strokeWidth=1;',
                'edge': '1',
                'parent': '1'
            })
            geometry = ET.SubElement(lifeline_cell, 'mxGeometry', {
                'relative': '1',
                'as': 'geometry'
            })
            ET.SubElement(geometry, 'mxPoint', {
                'x': str(lifeline_x[p.name]),
                'y': str(lifeline_start_y),
                'as': 'sourcePoint'
            })
            ET.SubElement(geometry, 'mxPoint', {
                'x': str(lifeline_x[p.name]),
                'y': str(lifeline_start_y + lifeline_length),
                'as': 'targetPoint'
            })

        # メッセージ矢印を作成
        for i, msg in enumerate(data.messages):
            msg_y = (
                self.TOP_MARGIN +
                self.PARTICIPANT_HEIGHT +
                (i + 1) * self.MESSAGE_VERTICAL_SPACING
            )

            from_x = lifeline_x[msg.from_participant]
            to_x = lifeline_x[msg.to_participant]

            # 矢印スタイル
            if msg.arrow_type == 'async':
                style = 'endArrow=open;html=1;dashed=1;strokeColor=#666666;'
            else:
                style = 'endArrow=block;endFill=1;html=1;strokeColor=#333333;'

            # 自己メッセージの場合
            if msg.from_participant == msg.to_participant:
                self._create_self_message(root, from_x, msg_y, msg.label, style)
                continue

            # メッセージエッジ
            msg_id = self._next_id()
            msg_cell = ET.SubElement(root, 'mxCell', {
                'id': msg_id,
                'value': msg.label,
                'style': style,
                'edge': '1',
                'parent': '1'
            })
            geometry = ET.SubElement(msg_cell, 'mxGeometry', {
                'relative': '1',
                'as': 'geometry'
            })
            ET.SubElement(geometry, 'mxPoint', {
                'x': str(from_x),
                'y': str(msg_y),
                'as': 'sourcePoint'
            })
            ET.SubElement(geometry, 'mxPoint', {
                'x': str(to_x),
                'y': str(msg_y),
                'as': 'targetPoint'
            })

        # 出力ディレクトリ作成
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # XMLを整形して保存
        self._indent_xml(mxfile)
        tree = ET.ElementTree(mxfile)
        tree.write(output_path, encoding='utf-8', xml_declaration=False)

        return output_path

    def _create_self_message(self, root, x: int, y: int, label: str, style: str):
        """自己メッセージを作成"""
        loop_width = 40
        loop_height = 30

        msg_id = self._next_id()
        msg_cell = ET.SubElement(root, 'mxCell', {
            'id': msg_id,
            'value': label,
            'style': style + 'edgeStyle=orthogonalEdgeStyle;rounded=1;',
            'edge': '1',
            'parent': '1'
        })
        geometry = ET.SubElement(msg_cell, 'mxGeometry', {
            'relative': '1',
            'as': 'geometry'
        })
        ET.SubElement(geometry, 'mxPoint', {
            'x': str(x),
            'y': str(y),
            'as': 'sourcePoint'
        })
        ET.SubElement(geometry, 'mxPoint', {
            'x': str(x),
            'y': str(y + loop_height),
            'as': 'targetPoint'
        })
        # 中間点で右に突き出す
        points = ET.SubElement(geometry, 'Array', {'as': 'points'})
        ET.SubElement(points, 'mxPoint', {'x': str(x + loop_width), 'y': str(y)})
        ET.SubElement(points, 'mxPoint', {'x': str(x + loop_width), 'y': str(y + loop_height)})

    def _indent_xml(self, elem, level=0):
        """XMLを整形"""
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent


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
        description='テキストからdraw.ioシーケンス図を生成する',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
入力形式:
  participants: User, Server, DB  (省略可、自動検出)
  User -> Server: メッセージ      (同期メッセージ)
  Server --> User: メッセージ     (非同期/リターン)

Examples:
  %(prog)s -d "participants: User, Server
User -> Server: リクエスト
Server --> User: レスポンス"
        """
    )

    parser.add_argument(
        '-d', '--description',
        required=True,
        help='シーケンス図の説明（メッセージ記法）'
    )

    parser.add_argument(
        '-o', '--output',
        default='./sequence.drawio',
        help='出力ファイルパス（デフォルト: ./sequence.drawio）'
    )

    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='既存ファイルを上書き'
    )

    args = parser.parse_args()

    if os.path.exists(args.output) and not args.force:
        print(f"Error: ファイルが既に存在します: {args.output}", file=sys.stderr)
        print("上書きするには --force オプションを使用してください。", file=sys.stderr)
        sys.exit(1)

    print(f"入力テキスト:")
    print(args.description)
    print(f"\n出力先: {args.output}")
    print()

    print("テキストを解析中...")
    try:
        parser_obj = SequenceParser()
        data = parser_obj.parse(args.description)
    except ParseError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  - 検出参加者数: {len(data.participants)}")
    for p in data.participants:
        print(f"    [{p.id}] {p.name}")
    print(f"  - 検出メッセージ数: {len(data.messages)}")
    for msg in data.messages:
        arrow = "-->" if msg.arrow_type == "async" else "->"
        print(f"    {msg.from_participant} {arrow} {msg.to_participant}: {msg.label}")
    print()

    print("シーケンス図を生成中...")
    generator = SequenceGenerator()
    output_file = generator.generate(data, args.output)

    validation = validate_output(output_file)
    if validation["errors"]:
        print(f"警告: 検証エラー: {validation['errors']}", file=sys.stderr)

    print()
    print(f"Success: シーケンス図を生成しました")
    print(f"  出力ファイル: {os.path.abspath(output_file)}")
    print(f"  要素数: {validation['cell_count'] - 2}")
    print()
    print("確認方法:")
    print("  1. draw.ioアプリで開く")
    print("  2. draw.io Online (https://app.diagrams.net/) でインポート")


if __name__ == "__main__":
    main()
