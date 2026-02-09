---
name: draw-architecture
description: テキスト（矢印記法）からdraw.ioアーキテクチャ図を生成する
---

# draw-architecture

## Description
矢印記法のテキストからdraw.io形式のアーキテクチャ図（.drawio）を生成します。
drawpyoライブラリを使用してプログラム的にアーキテクチャ図を構築し、draw.ioアプリで開ける非圧縮XMLファイルを出力します。

**特徴**:
- コンポーネントタイプの自動判定（キーワードベース）
- 明示的なタイプ指定（括弧記法）
- 横方向レイアウト（左から右へ）
- 双方向接続のサポート

## Usage
**Triggers**: `/draw-architecture`, "アーキテクチャ図を生成", "draw.ioでアーキテクチャ図"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|-----------|
| description | アーキテクチャの説明（矢印記法） | Yes | - |
| output_path | 出力ファイルパス | No | ./architecture.drawio |

## 入力形式（矢印記法）

**対応する矢印**:
- 単方向: `->`, `→`
- 双方向: `<->`, `↔`

**コンポーネントタイプ指定**:
コンポーネント名の後に `(type)` を付けて形状を指定:

| タイプ指定 | 説明 | 形状 |
|-----------|------|------|
| `(db)`, `(database)` | データベース | シリンダー（青） |
| `(cache)`, `(redis)` | キャッシュ | シリンダー（緑） |
| `(external)`, `(ext)`, `(cloud)` | 外部サービス | 雲（グレー） |
| `(container)`, `(docker)`, `(k8s)` | コンテナ | 立方体（紫） |
| `(queue)`, `(mq)` | メッセージキュー | 角丸矩形（オレンジ） |
| `(storage)`, `(s3)` | ストレージ | シリンダー（黄） |
| `(user)`, `(client)` | ユーザー | 人型（グレー） |
| `(lb)`, `(loadbalancer)` | ロードバランサー | 平行四辺形（緑） |
| なし | サービス/アプリ | 矩形（青） |

**自動タイプ判定**:
名前に特定のキーワードが含まれる場合、タイプを自動判定:
- `MySQL`, `PostgreSQL`, `MongoDB`, `DynamoDB` → database
- `Redis`, `Memcached`, `ElastiCache` → cache
- `S3`, `Storage`, `Bucket` → storage
- `SQS`, `Kafka`, `RabbitMQ` → queue
- `Docker`, `K8s`, `ECS`, `Fargate` → container
- `CloudFront`, `CDN`, `Gateway` → external
- `ALB`, `ELB`, `Nginx` → loadbalancer

**ラベル付き接続**:
```
Component1 --(HTTP)--> Component2
Component1 --(REST API)--> Component2
```

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

### Step 2: アーキテクチャ図生成
`scripts/generate_architecture.py` を使用:

```bash
python3 .claude/skills/draw-architecture/scripts/generate_architecture.py \
  --description "User(client) -> LoadBalancer(lb) -> WebServer -> Database(db)" \
  --output "./output/architecture.drawio"
```

**オプション**:
- `-d`, `--description`: アーキテクチャの説明（必須）
- `-o`, `--output`: 出力ファイルパス（デフォルト: ./architecture.drawio）
- `-f`, `--force`: 既存ファイルを上書き

### Step 3: 出力確認
生成されたファイルを確認:
1. ファイルが作成されたことを確認
2. draw.ioアプリまたは https://app.diagrams.net/ で開く

## Output Format

**成果物**: `.drawio` ファイル（非圧縮XML形式、draw.ioアプリで直接開ける）

**コンポーネントスタイル**:
| タイプ | 形状 | 塗りつぶし色 |
|--------|------|-------------|
| database | シリンダー | 青（#dae8fc） |
| cache | シリンダー | 緑（#d5e8d4） |
| storage | シリンダー | 黄（#fff2cc） |
| external | 雲 | グレー（#f5f5f5） |
| container | 立方体 | 紫（#e1d5e7） |
| queue | 角丸矩形 | オレンジ（#ffe6cc） |
| user | 人型 | グレー（#f5f5f5） |
| loadbalancer | 平行四辺形 | 緑（#d5e8d4） |
| default | 矩形 | 青（#dae8fc） |

## Error Handling

| エラー | 対応 |
|--------|------|
| drawpyo未インストール | `pip install drawpyo` を案内 |
| コンポーネントが検出できない | 推奨入力形式を表示 |
| 接続が検出できない | 矢印記法の使用を案内 |
| ファイル既存 | `--force` オプションを案内 |
| 出力先ディレクトリなし | 自動作成 |

## Examples

**例1: シンプルなWebアーキテクチャ**
```bash
python3 generate_architecture.py -d "User(client) -> WebServer -> Database(db)"
```

**例2: 3層アーキテクチャ**
```bash
python3 generate_architecture.py -d "Browser(user) -> LoadBalancer(lb) -> WebServer -> API Server -> PostgreSQL(db)
API Server -> Redis(cache)"
```

**例3: マイクロサービス構成**
```bash
python3 generate_architecture.py -d "Client(user) -> API Gateway(external) -> Auth Service(container)
API Gateway -> User Service(container) -> UserDB(db)
API Gateway -> Order Service(container) -> OrderDB(db)
Order Service -> MessageQueue(queue) -> Notification Service(container)"
```

**例4: AWS構成図**
```bash
python3 generate_architecture.py -d "Browser(client) -> CloudFront(cdn) -> ALB(lb) -> ECS(container) -> RDS(db)
ECS -> ElastiCache(cache)
ECS -> SQS(queue) -> Lambda(container)"
```

**例5: ラベル付き接続**
```bash
python3 generate_architecture.py -d "Mobile(client) --(HTTPS)--> API Gateway(external) --(gRPC)--> Microservice(container) --(SQL)--> MySQL(db)"
```

## Quality Checklist
- [ ] draw.ioアプリで正常に開ける
- [ ] すべてのコンポーネントが表示される
- [ ] コネクタが正しく接続されている
- [ ] 日本語ラベルが正しく表示される
- [ ] 各コンポーネントが適切な形状で表示される

## References
- `programs/draw-io-drawing-skills/sublayers/SG3_diagram_templates/documents/T001_architecture_design.md` - 設計ドキュメント
- `.claude/skills/draw-flowchart/` - フローチャート生成（参照実装）
- [drawpyo Documentation](https://merrimanind.github.io/drawpyo/)
- [draw.io Desktop](https://www.drawio.com/)

## Tips
- コンポーネントタイプを明示的に指定することで意図した形状を使用可能
- 名前にサービス名（MySQL, Redis等）を含めると自動判定が効く
- 複数行で記述すると複雑なアーキテクチャを表現可能
- 生成後にdraw.ioで微調整可能
