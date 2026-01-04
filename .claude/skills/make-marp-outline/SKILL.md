---
name: make-marp-outline
description: Marpスライドの構成案（Outline）と材料束（Input Bundle）を生成する
---

# make-marp-outline

## Description
プレゼンテーションのテーマ、想定時間、対象聴衆から、Marpスライド作成のための構成案（Outline）と材料束（Input Bundle）を生成します。

これはMarpスライド作成の**Phase 1**です。

## Usage
**Triggers**: `/marp-outline`, "構成案を作成", "Outlineを生成"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|----------|
| theme | プレゼンテーマ/タイトル | Yes | - |
| duration | 想定時間（分） | Yes | 10 |
| audience | 対象聴衆 | Yes | - |
| tone | トーン（casual/formal/technical/storytelling） | No | casual |
| key_points | 必ず含めたいポイント（箇条書き） | No | - |
| output_dir | 出力ディレクトリ | No | ./marp-output |

## Instructions

### Step 1: 入力情報の収集
ユーザーから以下の情報を収集（未指定の場合は確認）:
- テーマ/タイトル
- 想定時間
- 対象聴衆
- トーン（オプション）
- 含めたいキーポイント（オプション）

### Step 2: テンプレート参照
以下のテンプレートを読み込み:
- `references/template_outline.md`
- `references/template_input_bundle.md`

### Step 3: 時間配分の設計
想定時間に基づいて、各セクションの時間配分を設計:

**10分の場合の目安**:
1. 導入（0:45）- フック、自己紹介
2. 問題提起（2:00）- 課題の明確化
3. 転換点（1:30）- 視点の転換
4. 解決策（2:30）- ソリューション提示
5. 具体例（2:00）- 実例/デモ
6. 展望（1:00）- 将来像
7. クロージング（0:15）- CTA/締め

### Step 4: Outline生成
以下の形式でOutlineを作成:

```markdown
# {theme} - Outline

## メタ情報
- **想定時間**: {duration}分
- **対象聴衆**: {audience}
- **トーン**: {tone}
- **作成日**: YYYY-MM-DD

---

## 構成

### 1. 導入（X分）
- **狙い**: 聴衆の注意を引き、共感を得る
- **フック**:
- **自己紹介**:

### 2. 問題提起（X分）
- **狙い**: 解決すべき課題を明確にする
- **ポイント**:

### 3. 転換点（X分）
- **狙い**: 視点の転換、気づきを提供
- **ポイント**:

### 4. 解決策（X分）
- **狙い**: 具体的な解決策を提示
- **ポイント**:

### 5. 具体例（X分）
- **狙い**: 実例で説得力を増す
- **ポイント**:

### 6. 展望（X分）
- **狙い**: 将来像を示す
- **ポイント**:

### 7. クロージング（X分）
- **狙い**: 印象的に締める
- **CTA/メッセージ**:

---

## 1スライド1メッセージ原則
- 各スライドは1つの主張のみ
- 最大2ポイントまで
- 補足はスピーカーノートへ
```

### Step 5: Input Bundle生成
以下の形式でInput Bundleを作成:

```markdown
# {theme} - Input Bundle

## 参照Outline
- (Outlineへのリンクまたは埋め込み)

---

## 核となるメッセージ（決めゼリフ）
-

---

## セクション別材料

### 1. 導入
-

### 2. 問題提起
-

### 3. 転換点
-

### 4. 解決策
-

### 5. 具体例
-

### 6. 展望
-

### 7. クロージング
-

---

## トーン / 禁止事項
- **トーン**: {tone}
- **禁止**:

---

## 追加素材（画像、データ等）
-
```

### Step 6: ファイル出力
1. `{output_dir}/outline.md` にOutlineを保存
2. `{output_dir}/input_bundle.md` にInput Bundleを保存
3. ユーザーに完了を報告

## Output Format

**成果物**:
1. `outline.md` - プレゼンテーション構成案
2. `input_bundle.md` - 材料束

**次のステップ**:
- `/marp-script` を実行して台本を生成

## References
- `references/template_outline.md` - Outlineテンプレート
- `references/template_input_bundle.md` - Input Bundleテンプレート
- `references/marp_expression_guide.md` - Marp表現技法（参考）
