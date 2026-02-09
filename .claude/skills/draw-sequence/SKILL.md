---
name: draw-sequence
description: テキスト（メッセージ記法）からdraw.ioシーケンス図を生成する
---

# draw-sequence

## Description
メッセージ記法のテキストからdraw.io形式のシーケンス図（.drawio）を生成します。
drawpyoライブラリを使用してプログラム的にシーケンス図を構築し、draw.ioアプリで開ける非圧縮XMLファイルを出力します。

**機能範囲**:
- 参加者（アクター）の定義と配置
- 同期/非同期メッセージの矢印表現
- ライフライン（破線の垂直線）
- 自己メッセージ（同一参加者へのコール）
- 日本語ラベル対応

## Usage
**Triggers**: `/draw-sequence`, "シーケンス図を生成", "draw.ioでシーケンス図"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|-----------|
| description | シーケンス図の説明（メッセージ記法） | Yes | - |
| output_path | 出力ファイルパス | No | ./sequence.drawio |

## 入力形式（メッセージ記法）

### 参加者定義（省略可）
```
participants: User, Server, DB
```
省略した場合、メッセージに登場する参加者を出現順に自動検出します。

### メッセージ記法
```
送信者 -> 受信者: メッセージ内容
送信者 --> 受信者: メッセージ内容
```

**対応する矢印**:
| 矢印 | 意味 | スタイル |
|------|------|---------|
| `->` | 同期メッセージ | 実線、塗りつぶし矢印 |
| `->>` | 同期メッセージ（代替） | 実線、塗りつぶし矢印 |
| `-->` | 非同期/リターン | 破線、開いた矢印 |
| `-->>` | 非同期/リターン（代替） | 破線、開いた矢印 |

### コメント
`#` で始まる行はコメントとして無視されます。

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

### Step 2: シーケンス図生成
`scripts/generate_sequence.py` を使用:

```bash
python3 .claude/skills/draw-sequence/scripts/generate_sequence.py \
  --description "participants: User, Server
User -> Server: リクエスト
Server --> User: レスポンス" \
  --output "./output/sequence.drawio"
```

**オプション**:
- `-d`, `--description`: シーケンス図の説明（必須）
- `-o`, `--output`: 出力ファイルパス（デフォルト: ./sequence.drawio）
- `-f`, `--force`: 既存ファイルを上書き

### Step 3: 出力確認
生成されたファイルを確認:
1. ファイルが作成されたことを確認
2. draw.ioアプリまたは https://app.diagrams.net/ で開く

## Output Format

**成果物**: `.drawio` ファイル（非圧縮XML形式、draw.ioアプリで直接開ける）

**要素スタイル**:
| 要素 | 形状 | スタイル |
|------|------|---------|
| 参加者 | 角丸矩形 | グレー背景（#f5f5f5）、太字 |
| ライフライン | 破線 | グレー（#999999） |
| 同期メッセージ | 実線矢印 | 黒（#333333）、塗りつぶし矢印 |
| 非同期メッセージ | 破線矢印 | グレー（#666666）、開いた矢印 |

## Error Handling

| エラー | 対応 |
|--------|------|
| drawpyo未インストール | `pip install drawpyo` を案内 |
| 参加者が検出できない | 推奨入力形式を表示 |
| メッセージが検出できない | 推奨入力形式を表示 |
| ファイル既存 | `--force` オプションを案内 |
| 出力先ディレクトリなし | 自動作成 |

## Examples

**例1: 基本的なリクエスト/レスポンス**
```bash
python3 generate_sequence.py -d "participants: Client, Server
Client -> Server: HTTPリクエスト
Server --> Client: HTTPレスポンス"
```

**例2: 3層アーキテクチャ**
```bash
python3 generate_sequence.py -d "User -> API: GET /users
API -> DB: SELECT * FROM users
DB --> API: ResultSet
API --> User: JSON response"
```

**例3: 日本語ラベル**
```bash
python3 generate_sequence.py -d "participants: ユーザー, サーバー, データベース
ユーザー -> サーバー: リクエスト送信
サーバー -> データベース: クエリ実行
データベース --> サーバー: 結果
サーバー --> ユーザー: レスポンス"
```

**例4: 認証フロー**
```bash
python3 generate_sequence.py -d "participants: Browser, AuthServer, ResourceServer
Browser -> AuthServer: 認証リクエスト
AuthServer --> Browser: 認可コード
Browser -> AuthServer: トークン要求
AuthServer --> Browser: アクセストークン
Browser -> ResourceServer: API呼び出し（トークン付き）
ResourceServer --> Browser: 保護されたリソース"
```

**例5: 自己メッセージ**
```bash
python3 generate_sequence.py -d "participants: Controller
Controller -> Controller: 初期化処理"
```

## Quality Checklist
- [ ] draw.ioアプリで正常に開ける
- [ ] すべての参加者が表示される
- [ ] ライフラインが正しく描画される
- [ ] メッセージ矢印が正しく接続されている
- [ ] 日本語ラベルが正しく表示される
- [ ] 同期/非同期の矢印スタイルが区別される

## References
- `programs/draw-io-drawing-skills/sublayers/SG3_diagram_templates/documents/T004_sequence_design.md` - 設計ドキュメント
- `.claude/skills/draw-flowchart/` - フローチャート生成（参照実装）
- [drawpyo Documentation](https://merrimanind.github.io/drawpyo/)
- [draw.io Desktop](https://www.drawio.com/)
- [UML Sequence Diagram](https://www.uml-diagrams.org/sequence-diagrams.html)

## Tips
- 参加者は左から右に配置される（定義順または出現順）
- メッセージは上から下に時間順で配置される
- `-->` を使用してリターンメッセージを視覚的に区別
- 参加者名は短く、意味のある名前を使用
- 生成後にdraw.ioで微調整可能
