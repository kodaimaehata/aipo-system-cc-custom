# miro-flow-maker

## Description

業務記述テキストから Miro ボードにスイムレーン付き業務フロー図を自動生成するスキル。

ユーザーが業務プロセスを自然言語で記述すると、AI がまずフェーズ章立ての業務記述文を作成してユーザーと合意形成し、合意後にフロー構造（actors, nodes, edges, system_accesses）を持つ confirmed JSON へ変換する。最後に Miro REST API v2 を介して、指定ボードにスイムレーン付き業務フロー図を描画する。

## Usage

`/miro-flow-maker` でトリガーする。

## Instructions

以下の順序で実行する。ポイントは、**ユーザー確認は JSON ではなく自然言語の業務記述文で行う**こと。JSON はその合意を機械可読に翻訳するだけの内部表現として扱う。

### 1. 業務記述テキストの受け取り

ユーザーから業務プロセスの記述を受け取る。この時点では整理されていない（箇条書き／会話文／既存資料の抜粋など）形式でも構わない。以降の処理で以下の情報を抽出できるだけの素材が揃っていることを確認する:

- 関係者（actors）: 誰がどの役割を担うか（申請者、担当者、承認者、オーナー、外部業者 など）
- 業務ステップ: 起点、処理、判断分岐、終了
- 遷移と条件: どのステップからどのステップへ進むか、差戻や保留の経路
- システム利用: どのステップがどのシステムに書く／読むか

不足があれば、最小限の追加質問でユーザーに補ってもらう。

### 2. 業務記述文（フェーズ章立て）の生成・提示

**ここでユーザーに提示するのは JSON ではなく、章立てされた自然言語の業務記述文**である。

以下のテンプレートに沿って、フェーズごとに章立てした Markdown 文書を生成する:

```markdown
## 1. <フェーズ名>（<主管システム / 所管部署>）
1. <アクター> が <動作>
   - 入力項目 / 参照先: ...
   - 分岐: 条件 A → <遷移先> / 条件 B → <遷移先>
2. ...

## 2. <次のフェーズ>
...
```

**生成ルール**:

- **フェーズ見出し**で章立てする（受付 / 判定 / 実行 / クロージング など、業務的に意味のある粒度）
- **番号付きステップ**で時系列に上から読めるよう並べる
- **括弧書き**で主管システム、連携キー、入力項目などの補足情報を添える
- **分岐はインデント箇条書き**で表現する（承認 / 差戻 / 保留 など全経路を明示）
- **差戻し / 保留 / 保管**などのサブフロー、例外処理も省略せず書き出す
- 文末に次のような確認文を必ず添える:

  > この内容でよろしいですか？修正点があれば箇条書きでご指示ください。

この業務記述文が、後工程で生成する JSON の `confirmation_packet_ref` が指す「確認パケット」の実体となる。

### 3. ユーザーとの反復確認

ユーザーから修正指示（追加ステップ、順序入れ替え、分岐条件訂正、アクター名変更 など）を受け取ったら、業務記述文を更新して再提示する。

- 差分が分かるように、変更箇所の概要を冒頭に短く添えてもよい
- ユーザーが「OK」「この内容で確定」などの明示的合意を出すまでループする
- 大きな構造変更が入った場合は、一度全体を読み直してフェーズ構成が妥当か確認する

### 4. narrative を confirmation packet として保存

ユーザー合意が得られた業務記述文（narrative）を、以下のパスに Markdown ファイルとして保存する:

```
.claude/skills/miro-flow-maker/packets/cp-<flow_group_id>.md
```

- `<flow_group_id>` は後工程の JSON で使う `flow_group.id` と同じ値にする
- このファイルが JSON の `confirmation_packet_ref` の実体となる
- `packets/` ディレクトリは `.gitignore` 済みのため、リポジトリには commit されない

### 5. narrative → confirmed JSON 変換

合意済みの業務記述文を、以下スキーマの confirmed JSON に変換する。ユーザーに JSON を見せる必要はなく、内部変換として静かに行う。

```json
{
  "document_set": { "id": "ds-xxx", "label": "文書セット名" },
  "flow_group": { "id": "flow-xxx", "label": "フロー名" },
  "actors": [
    { "id": "a-xxx", "label": "役割名", "kind": "person|department" }
  ],
  "systems": [
    { "id": "s-xxx", "label": "システム名", "kind": "internal_system|external_system" }
  ],
  "nodes": [
    { "id": "n-xxx", "type": "start|process|decision|end", "label": "ステップ名", "actor_id": "a-xxx" }
  ],
  "edges": [
    { "id": "e-xxx", "from_node_id": "n-xxx", "to_node_id": "n-xxx", "kind": "business_flow", "label": "遷移条件" }
  ],
  "system_accesses": [
    { "id": "sa-xxx", "from_node_id": "n-xxx", "system_id": "s-xxx", "action": "アクション名", "label": "表示ラベル" }
  ],
  "status": "confirmed",
  "confirmation_packet_ref": "packets/cp-<flow_group_id>.md",
  "source_evidence": [
    { "ref": "参照パス", "description": "根拠の要約" }
  ],
  "metadata": {
    "project_id": "Pxxxx",
    "layer_id": "Pxxxx-SGx",
    "managed_by": "miro-flow-maker",
    "update_mode": "managed"
  }
}
```

**semantic_id の採番規則**:

- `actors`: `a-<役割名slug>` 形式。例: `a-applicant`, `a-manager`, `a-owner`
- `nodes`: `n-<フェーズ序数>-<役割slug>-<ステップslug>` 形式。例: `n-1-applicant-submit`, `n-2-manager-review`。複雑すぎる場合は単純に通し番号 `n-<NN>` でも可
- `edges`: `e-<通し番号>` 形式（ゼロ埋め 2 桁推奨）。例: `e-01`, `e-02`
- `system_accesses`: `sa-<通し番号>` 形式。例: `sa-01`, `sa-02`

差戻し edge は `kind=business_flow` のまま、ラベルに「差戻」「再提出」等を入れ、from→to をフロー逆方向に設定する（レイアウト側で back edge として処理される）。

### 6. (オプション) JSON を折りたたみで engineer 向けに提示

開発者・システム側レビュアーも同席している場合、生成した JSON を折りたたみ表示で一緒に提示してもよい:

```markdown
<details><summary>内部 JSON（開発者向け）</summary>

\`\`\`json
{ ... confirmed JSON ... }
\`\`\`

</details>
```

業務担当者が主なレビュアーの場合は、JSON は提示しなくてよい。

### 7. confirmed JSON の保存

確定した JSON を一時ファイルに保存する:

```bash
cat > /tmp/confirmed_input.json << 'EOF'
{ ... confirmed JSON ... }
EOF
```

### 8. miro_flow_maker の実行

**cwd は `.claude/skills/miro-flow-maker/`** で実行する。`scripts/` ではない。理由は SG4 T007 §2.2（`programs/P0006_codex-miro-api-workflow-implementation/sublayers/SG4_smoke_test_and_acceptance_validation/documents/T007_operation_handoff.md`）を参照。

dry-run を先に実行して描画計画を確認し、問題なければ本実行する:

```bash
# dry-run（描画計画の確認のみ、Miro への書き込みなし）
uv run python -m miro_flow_maker create \
  --input /tmp/confirmed_input.json \
  --board-name "フロー名" \
  --dry-run

# 本実行（Miro ボードに書き込み）
uv run python -m miro_flow_maker create \
  --input /tmp/confirmed_input.json \
  --board-name "フロー名"
```

既存 board / frame に追記する場合は `append` / `update` モードを使う（詳細は SG4 T007 §3）。

`append` には以下のオプションフラグがある:

- `--auto-frame`（opt-in）: `--frame-id` / `--frame-link` 未指定のとき、board 上に新規 frame を自動作成してその中に描画する。配置は既存 frame の右隣（`FRAME_MARGIN=200px` 空けて水平に積む）。複数 frame を 1 つの board に共存させる用途向け。
- `--no-auto-resize`（opt-out）: `append` は既定で frame が小さい場合に自動リサイズ (`PATCH /frames/{id}` で geometry 拡張) する。このフラグを付けると拡張を抑止し、従来どおり HTTP 400 `"new position is outside of parent boundaries"` で失敗する（デバッグ用途）。

例:

```bash
# 既存 board に新 frame を自動作成して追記
uv run python -m miro_flow_maker append \
  --input /tmp/confirmed_input.json \
  --board-id <既存 board_id> \
  --auto-frame

# 既存 frame に追記（frame が小さければ自動拡張）
uv run python -m miro_flow_maker append \
  --input /tmp/confirmed_input.json \
  --board-id <既存 board_id> \
  --frame-id <対象 frame_id>
```

### 9. 結果の報告

実行結果をユーザーに報告する:

- 成功時: board URL、作成した item 数（lanes, nodes, system_labels, connectors）
- dry-run 時: Drawing Plan Summary（stderr に出力される）
- 失敗時: 停止理由（`stop_reasons`）、`stopped_stage`、エラー内容、`rerun_eligible`

## Prerequisites

### 初回セットアップ（checkout 直後）

```bash
cd .claude/skills/miro-flow-maker
./scripts/bootstrap.sh   # または: cp .env.example .env && uv sync
# .env を編集して MIRO_ACCESS_TOKEN を設定
```

`scripts/bootstrap.sh` が `.env` を雛形からコピーし、`uv sync` で依存と仮想環境を同期する。

### .env ファイル

`.claude/skills/miro-flow-maker/.env` に以下を設定する:

```env
MIRO_ACCESS_TOKEN=<Miro Developer Token>
# 以下はオプション
MIRO_API_BASE_URL=https://api.miro.com/v2
MIRO_DEFAULT_BOARD_ID=<既存ボード ID（update/append 用）>
AIPO_LOG_DIR=./logs
AIPO_DRY_RUN=false
AIPO_LOG_LEVEL=INFO
AIPO_RUNNER_ID=<run log に残す任意の実行者識別子（未設定時は "miro-flow-maker"）>
```

`MIRO_ACCESS_TOKEN` は必須。Miro Developer Portal で取得する。

環境変数の仕様（`scripts/miro_flow_maker/config.py` で解釈）:

- `AIPO_LOG_DIR`: ログ出力先ディレクトリ。未指定時は `./logs`。
- `AIPO_DRY_RUN`: `true` / `false` / `1` / `0` を受け付ける。不正値は `ConfigError` で終了コード 2。未指定時は `false`。
- `AIPO_LOG_LEVEL`: `DEBUG` / `INFO` / `WARNING` / `ERROR` を受け付ける。未指定時は `INFO`。不正値は `warnings.warn` を出した上で `INFO` にフォールバック。
- `AIPO_RUNNER_ID`: 任意の実行者識別子。run log に残る。未指定時は `miro-flow-maker`。

### Python 環境

```bash
cd .claude/skills/miro-flow-maker
uv run python -m miro_flow_maker create --help
```

`uv sync` 済みであれば `uv run` が自動で仮想環境を解決する。

## Input Format

### narrative と JSON の対応

§2 で作る業務記述文と、§5 で生成する JSON フィールドの対応は以下のとおり。narrative で正しく表現できていれば JSON への変換は機械的に行える。

| narrative 表現 | JSON 表現 |
|---|---|
| 「A が B を行う」 | `node.type=process`, `actor_id=A` |
| 「条件 C で分岐」 | `node.type=decision`, 後続 edge で分岐 |
| 「X システムに登録」 | `system_accesses[].action=登録` |
| 「差戻」「戻る」 | `edge`（`kind=business_flow`, back edge） |
| 「開始」「完了」 | `node.type=start` / `end` |

confirmed JSON のスキーマ概要:

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `document_set` | `{id, label}` | Yes | 入力文書束の識別 |
| `flow_group` | `{id, label}` | Yes | 業務フローの識別 |
| `actors` | `[{id, label, kind}]` | Yes | 関係者定義 |
| `systems` | `[{id, label, kind}]` | No | システム定義 |
| `nodes` | `[{id, type, label, actor_id}]` | Yes | ノード定義 |
| `edges` | `[{id, from_node_id, to_node_id, kind, label}]` | Yes | 遷移定義 |
| `system_accesses` | `[{id, from_node_id, system_id, action, label}]` | No | システムアクセス定義 |
| `status` | `"confirmed"` | Yes | 確認状態 |
| `confirmation_packet_ref` | `string` | Yes | 確認パケット参照（`packets/cp-<flow_group_id>.md`） |
| `source_evidence` | `[{ref, description}]` | Yes | 根拠参照 |
| `metadata` | `{project_id, layer_id, managed_by, update_mode}` | Yes | 管理メタデータ |

### node.type の種類

| type | 説明 | Miro shape | 色 |
|---|---|---|---|
| `start` | 開始ノード | circle | 緑 (#D5F5E3) |
| `process` | 処理ノード | rectangle | 白 (#FFFFFF) |
| `decision` | 判断分岐 | rhombus | 黄 (#FEF9E7) |
| `end` | 終了ノード | circle | グレー (#D5D8DC) |

### レイアウト

- 横スイムレーン: actor ごとに水平行として配置（上から下）
- 左から右フロー: topological sort で rank を計算し、列位置を決定
- system_label: task ノード直下に薄青角丸 shape で配置（system lane は作成しない）
- 差戻し edge: back_edge として上端→上端で接続
- connector: elbowed（直角折れ線）

### 停止条件

- `status` が `"confirmed"` でない場合、review gate で停止
- connector の接続先 node が作成失敗している場合、即停止
- board / frame 作成失敗時、即停止
