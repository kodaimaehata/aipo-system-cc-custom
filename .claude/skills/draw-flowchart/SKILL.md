---
name: draw-flowchart
description: テキスト（矢印記法）からdraw.ioフローチャートを生成する
---

# draw-flowchart

## Description
矢印記法のテキストからdraw.io形式のフローチャート（.drawio）を生成します。
drawpyoライブラリを使用してプログラム的にフローチャートを構築し、draw.ioアプリで開ける非圧縮XMLファイルを出力します。

**MVP対応範囲**: フローチャートのみ（シーケンス図等はMVP後）
**ループ対応**: 同じラベルへの参照は既存ノードを再利用（ループ構造を実現）

## Usage
**Triggers**: `/draw-flowchart`, "フローチャートを生成", "draw.ioでフローチャート"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|-----------|
| description | フローチャートの説明（矢印記法） | Yes | - |
| output_path | 出力ファイルパス | No | ./flowchart.drawio |

## 入力形式（矢印記法）

**対応する矢印**:
- 横矢印: `→`, `->`, `⇒`
- 縦矢印: `↓`（改行区切りで使用）

**分岐ラベル**:
- `(Yes)`, `(No)`, `(はい)`, `(いいえ)` を矢印の後に記述

**ノードタイプの自動判定**:
| キーワード | ノードタイプ |
|-----------|-------------|
| 開始, スタート, 始め | 開始ノード（緑） |
| 終了, エンド, 完了, 終わり | 終了ノード（赤） |
| もし, 条件, 判断, 分岐, チェック, ? | 判断ノード（黄、ひし形） |
| その他 | 処理ノード（青、矩形） |

## Instructions

### Step 1: 依存確認
drawpyoのインストール確認:
```bash
python3 -c "import drawpyo; print(f'drawpyo {drawpyo.__version__}')"
```

未インストールの場合:
```bash
pip install drawpyo
```

### Step 2: フローチャート生成
`scripts/generate_flowchart.py` を使用:

```bash
python3 .claude/skills/draw-flowchart/scripts/generate_flowchart.py \
  --description "開始 → 処理1 → 処理2 → 終了" \
  --output "./output/flowchart.drawio"
```

**オプション**:
- `-d`, `--description`: フローチャートの説明（必須）
- `-o`, `--output`: 出力ファイルパス（デフォルト: ./flowchart.drawio）
- `-f`, `--force`: 既存ファイルを上書き

### Step 3: 出力確認
生成されたファイルを確認:
1. ファイルが作成されたことを確認
2. draw.ioアプリまたは https://app.diagrams.net/ で開く

## Output Format

**成果物**: `.drawio` ファイル（非圧縮XML形式、draw.ioアプリで直接開ける）

**ノードスタイル**:
| ノードタイプ | 形状 | 塗りつぶし色 |
|-------------|------|-------------|
| 開始 | 角丸矩形（arcSize=50） | 緑（#d5e8d4） |
| 終了 | 角丸矩形（arcSize=50） | 赤（#f8cecc） |
| 処理 | 矩形 | 青（#dae8fc） |
| 判断 | ひし形 | 黄（#fff2cc） |

## Error Handling

| エラー | 対応 |
|--------|------|
| drawpyo未インストール | `pip install drawpyo` を案内 |
| ノードが検出できない | 推奨入力形式を表示 |
| ファイル既存 | `--force` オプションを案内 |
| 出力先ディレクトリなし | 自動作成 |

## Examples

**例1: シンプルなフロー**
```bash
python3 generate_flowchart.py -d "開始 → データ入力 → 処理 → 終了"
```

**例2: 分岐あり**
```bash
python3 generate_flowchart.py -d "開始 → 条件チェック → (Yes) 処理A → 終了
条件チェック → (No) 処理B → 終了"
```

**例3: 縦矢印を使用**
```
開始
↓
ユーザー入力
↓
入力チェック
→ (Yes) 保存 → 終了
→ (No) エラー表示 → ユーザー入力
```

**例4: ループ**
```bash
python3 generate_flowchart.py -d "開始 → データ取得 → 処理 → 完了か判断 → (Yes) 終了
完了か判断 → (No) データ取得"
```

## 未対応（MVP後）

以下の機能はMVP後に対応予定:
- 自然言語からの推論（「から」「へ」「then」等）
- `Yes:` 形式の分岐ラベル
- シーケンス図、アーキテクチャ図等の他の図タイプ
- 既存draw.ioファイルの編集

## Quality Checklist
- [ ] draw.ioアプリで正常に開ける
- [ ] すべてのノードが表示される
- [ ] コネクタが正しく接続されている
- [ ] 日本語ラベルが正しく表示される
- [ ] 分岐ラベル（Yes/No）が表示される

## References
- `programs/draw-io-drawing-skills/documents/T001_xml_format_research.md` - XMLフォーマット詳細
- [drawpyo Documentation](https://merrimanind.github.io/drawpyo/)
- [draw.io Desktop](https://www.drawio.com/)

## Tips
- 各ステップは `→` で区切って明示的に接続
- 分岐は `(Yes)` `(No)` を使用
- 同じラベルは同一ノードとして再利用（ループ構造を実現）
- 別ノードにしたい場合はラベルを少し変える（例: 「入力1」「入力2」）
- 生成後にdraw.ioで微調整可能
