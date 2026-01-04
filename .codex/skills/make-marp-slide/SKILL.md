---
name: make-marp-slide
description: 台本からMarp Markdown形式のスライドを生成する（marp_expression_guide準拠）
---

# make-marp-slide

## Description
プレゼンテーション台本（スクリプト）から、Marp Markdown形式のスライドを生成します。スピーカーノートはHTMLコメントとして埋め込みます。

これはMarpスライド作成の**Phase 3**です。

## Usage
**Triggers**: `/marp-slide`, "スライドを生成", "Marpを作成"

## Inputs

| パラメータ | 説明 | 必須 | ソース |
|-----------|------|------|--------|
| script | 台本の内容またはファイルパス | Yes | Phase 2出力 |
| outline | Outlineの内容（補助情報） | No | Phase 1出力 |
| theme | Marpテーマ（default/gaia/uncover） | No | default |
| output_path | 出力ファイルパス | No | ./marp-output/slides.md |

## Instructions

### Step 1: 入力の取得
1. 台本（script）を読み込む
2. Outline（オプション）を読み込む
3. テーマを確認

### Step 2: marp_expression_guide参照
`make-marp-outline/references/marp_expression_guide.md` を読み込み、以下を確認:
- 基本構文とフロントマター
- レイアウトテクニック
- スタイリングオプション
- ページディレクティブ

### Step 3: フロントマター生成
```yaml
---
marp: true
theme: {theme}
paginate: true
backgroundColor: #fafafa
style: |
  section {
    font-family: 'Hiragino Sans', 'Noto Sans JP', sans-serif;
    font-size: 28px;
    padding: 60px;
  }
  h1 {
    font-size: 48px;
    color: #2e3440;
    border-bottom: 3px solid #5e81ac;
    padding-bottom: 10px;
  }
  h2 {
    font-size: 36px;
    color: #3b4252;
  }
  .columns {
    display: flex;
    gap: 2em;
  }
  .columns > div {
    flex: 1;
  }
  section.lead {
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
---
```

### Step 4: スライド変換ルール

**1. タイトルスライド**:
```markdown
<!-- _class: lead -->

# {プレゼンタイトル}
## {サブタイトル}

**発表者名**
日付

<!--
スピーカーノート:
{台本の導入部分の話す内容}
-->
```

**2. コンテンツスライド**:
```markdown
---

# {セクションタイトル}

- ポイント1
- ポイント2

<!--
スピーカーノート:
{台本の話す内容}

演出メモ:
{演出メモがあれば記載}
-->
```

**3. 2カラムスライド**（比較・対比用）:
```markdown
---

# {タイトル}

<div class="columns">
<div>

## 左側
- 項目1
- 項目2

</div>
<div>

## 右側
- 項目3
- 項目4

</div>
</div>

<!-- スピーカーノート: ... -->
```

**4. クロージングスライド**:
```markdown
---

<!-- _class: lead -->

# ありがとうございました

{CTAまたは締めのメッセージ}

<!-- スピーカーノート: ... -->
```

### Step 5: 1スライド1メッセージ原則の適用
- 各スライドは1つの主要メッセージのみ
- 最大2ポイントまで
- 詳細はスピーカーノートへ
- 10分想定で10〜15枚

### Step 6: スピーカーノート埋め込み
台本の「話す内容」をHTMLコメントとして埋め込み:
```markdown
<!--
スピーカーノート:
{話す内容をここに記載}

想定時間: X分
-->
```

### Step 7: ファイル出力
1. `{output_path}` にMarp Markdownを保存
2. ユーザーに完了を報告

### Step 8: 検証案内
```
スライドが生成されました。

確認方法:
1. Marp Web Editor (https://web.marp.app/) で開く
2. VS Code + Marp拡張でプレビュー
3. marp-cli でPDF/PPTXにエクスポート

出力ファイル: {output_path}
```

## Output Format

**成果物**:
- `slides.md` - Marp Markdown形式のスライド

**ファイル構造**:
```markdown
---
marp: true
theme: default
paginate: true
...
---

<!-- _class: lead -->
# タイトル
...

---

# スライド1
...

<!-- スピーカーノート: ... -->

---

# スライド2
...

---

<!-- _class: lead -->
# ありがとうございました
```

## Quality Checklist
- [ ] Marp Web Editorでエラーなく表示
- [ ] 日本語フォントが正しく設定
- [ ] スピーカーノートが全スライドに含まれる
- [ ] 1スライド1メッセージ原則を遵守
- [ ] ページ番号が表示される

## References
- `../make-marp-outline/references/marp_expression_guide.md` - Marp表現技法ガイド

## Tips
- 画像を含める場合: `![bg right:40%](image.png)`
- 強調: `**太字**` または `==ハイライト==`
- コードブロック: 言語指定でシンタックスハイライト
- 数式: KaTeX記法 `$E = mc^2$`
