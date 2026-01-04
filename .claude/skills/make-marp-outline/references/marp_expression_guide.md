# Marp 表現技法ガイド

**目的**: Marpでのプレゼンテーション資料作成における表現技法をまとめたガイド

---

## 基本構文とフロントマター

### 必須フロントマター

```yaml
---
marp: true
theme: default  # default | gaia | uncover
paginate: true  # ページ番号表示
backgroundColor: #fafafa
---
```

### 主要設定項目

```yaml
---
marp: true
theme: default
paginate: true
backgroundColor: #fafafa
color: #333333
size: 16:9  # または 4:3
header: 'ヘッダーテキスト'
footer: 'フッターテキスト'
style: |
  /* カスタムCSSをここに記述 */
  section {
    font-size: 28px;
  }
---
```

---

## レイアウトテクニック

### 1. 2カラムレイアウト（FlexBox）

**用途**: 左右に情報を並べて比較・対比を表現

```markdown
---
style: |
  .columns {
    display: flex;
    gap: 2em;
  }
  .columns > div {
    flex: 1;
  }
---

# タイトル

<div class="columns">
  <div>

## 左カラム
- 項目1
- 項目2

  </div>
  <div>

## 右カラム
- 項目3
- 項目4

  </div>
</div>
```

### 2. 3カラムレイアウト

**用途**: 3つの要素を均等に配置

```markdown
---
style: |
  .three-columns {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1.5em;
  }
---

<div class="three-columns">
  <div>

### カラム1内容

  </div>
  <div>

### カラム2内容

  </div>
  <div>

### カラム3内容

  </div>
</div>
```

### 3. 画像とテキストの横並び

**用途**: 画像と説明文を効果的に配置

```markdown
---
style: |
  .image-text {
    display: flex;
    align-items: center;
    gap: 2em;
  }
  .image-text img {
    width: 40%;
  }
  .image-text .text {
    flex: 1;
  }
---

<div class="image-text">
  <img src="image.png" alt="説明" />
  <div class="text">

### テキスト説明文がここに入ります。

  </div>
</div>
```

### 4. グリッドレイアウト（2×2）

**用途**: 4つのボックスを整然と配置

```markdown
---
style: |
  .grid-4 {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1em;
  }
---

<div class="grid-4">
  <div>

#### Box 1

  </div>
  <div>

#### Box 2

  </div>
  <div>

#### Box 3

  </div>
  <div>

#### Box 4

  </div>
</div>
```

---

## スタイリングとカスタムCSS

### 1. テキスト装飾クラス

```markdown
---
style: |
  .highlight {
    background: linear-gradient(transparent 60%, #ffeb3b 60%);
    font-weight: bold;
  }
  .emphasis {
    color: #ff5252;
    font-size: 1.2em;
  }
  .small {
    font-size: 0.8em;
    color: #666;
  }
  .center {
    text-align: center;
  }
---

<span class="highlight">重要なポイント</span>
<span class="emphasis">強調テキスト</span>
<span class="small">補足説明</span>
```

### 2. 情報ボックス（Info / Warning / Success）

```markdown
---
style: |
  .info-box {
    background: #e3f2fd;
    border-left: 4px solid #2196f3;
    padding: 1em;
    border-radius: 4px;
  }
  .warning-box {
    background: #fff3e0;
    border-left: 4px solid #ff9800;
    padding: 1em;
    border-radius: 4px;
  }
  .success-box {
    background: #e8f5e9;
    border-left: 4px solid #4caf50;
    padding: 1em;
    border-radius: 4px;
  }
---

<div class="info-box">**情報**: 重要な情報がここに入ります</div>
<div class="warning-box">**注意**: 注意事項がここに入ります</div>
<div class="success-box">**成功**: 成功メッセージがここに入ります</div>
```

### 3. フォント設定（日本語対応）

```markdown
---
style: |
  section {
    font-family: 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', sans-serif;
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
  h3 {
    font-size: 30px;
    color: #434c5e;
  }
  code {
    font-family: 'Fira Code', 'Consolas', monospace;
    background: #eceff4;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 24px;
  }
---
```

### 4. カラーパレット定義（CSS変数）

```markdown
---
style: |
  :root {
    --primary: #667eea;
    --secondary: #764ba2;
    --accent: #ffd700;
    --success: #28a745;
    --warning: #ffc107;
    --danger: #dc3545;
    --text-primary: #ffffff;
    --text-secondary: #cccccc;
  }
  .primary { color: var(--primary); }
  .accent { color: var(--accent); }
  .success { color: var(--success); }
---
```

---

## ページディレクティブとクラス指定

### 1. 組み込みページクラス

```markdown
<!-- _class: lead -->
# タイトルスライド

---

<!-- _class: invert -->
# 反転カラースキーム
```

### 2. カスタムページクラス定義

```markdown
---
style: |
  section.lead {
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  section.impact {
    background-color: #1e293b;
    color: white;
    font-size: 2em;
  }
  section.image-bg {
    background-image: url('background.jpg');
    background-size: cover;
    color: white;
    text-shadow: 0 2px 4px rgba(0,0,0,0.5);
  }
---

<!-- _class: impact -->
# インパクトスライド

---

<!-- _class: image-bg -->
# 背景画像付きスライド
```

### 3. ページごとの背景色・文字色変更

```markdown
<!-- _backgroundColor: #f0f0f0 -->
# このページだけ背景色が変わる

---

<!-- _color: #ff0000 -->
# このページだけ文字色が赤

---

<!-- _style: "background: linear-gradient(to right, #667eea, #764ba2);" -->
# グラデーション背景のスライド
```

---

## 画像・メディアの配置

### 1. 画像サイズ調整

```markdown
![width:300px](image.png)
![height:200px](image.png)
![width:50%](image.png)
![w:400](image.png)  # 短縮記法
![h:300](image.png)  # 短縮記法
```

### 2. 画像の配置指定

```markdown
![center](image.png)
![right](image.png)
![left](image.png)

![bg](background.jpg)
![bg cover](background.jpg)
![bg fit](background.jpg)
![bg opacity:0.5](background.jpg)
![bg right](background.jpg)
![bg left](background.jpg)
```

### 3. 複数画像の横並び

```markdown
---
style: |
  .images {
    display: flex;
    gap: 1em;
    justify-content: center;
    align-items: center;
  }
  .images img {
    width: 30%;
    object-fit: cover;
  }
---

<div class="images">

![](image1.png)
![](image2.png)
![](image3.png)

</div>
```

### 4. 画像とキャプション

```markdown
---
style: |
  .image-with-caption {
    text-align: center;
  }
  .image-with-caption img {
    display: block;
    margin: 0 auto;
  }
  .image-with-caption figcaption {
    font-size: 0.8em;
    color: #666;
    margin-top: 0.5em;
  }
---

<figure class="image-with-caption">

![width:400px](chart.png)

<figcaption>図1: 2024年度売上推移</figcaption>
</figure>
```

---

## テーマのカスタマイズ

### 1. グラデーション背景テーマ

```markdown
---
marp: true
theme: default
style: |
  section {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    font-size: 28px;
    padding: 60px;
  }
  h1 {
    font-size: 48px;
    border-bottom: 3px solid #ffd700;
    padding-bottom: 10px;
  }
  code {
    background: rgba(255, 255, 255, 0.2);
    padding: 2px 6px;
    border-radius: 3px;
  }
  blockquote {
    border-left: 4px solid #ffd700;
    padding-left: 1em;
    background: rgba(255, 255, 255, 0.1);
    padding: 1em;
  }
---
```

### 2. ダークテーマ

```markdown
---
style: |
  section { background: #1e1e1e; color: #d4d4d4; }
  h1, h2, h3 { color: #4ec9b0; }
  code { background: #2d2d2d; color: #ce9178; }
  a { color: #3794ff; }
  blockquote { border-left: 4px solid #4ec9b0; background: #252526; }
---
```

### 3. ミニマルライトテーマ

```markdown
---
style: |
  section {
    background: #ffffff;
    color: #333333;
    font-family: 'Helvetica Neue', Arial, sans-serif;
  }
  h1 {
    color: #000000;
    font-weight: 300;
    border-bottom: 1px solid #e0e0e0;
  }
  h2 {
    color: #424242;
    font-weight: 400;
  }
  ul, ol {
    line-height: 1.8;
  }
---
```

---

## テーブル・リスト・引用

### 1. スタイル付きテーブル

```markdown
---
style: |
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 24px;
  }
  th {
    background: linear-gradient(to right, #667eea, #764ba2);
    color: white;
    padding: 12px;
    border: none;
  }
  td {
    background: rgba(255, 255, 255, 0.05);
    padding: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }
  tr:hover td {
    background: rgba(255, 255, 255, 0.1);
  }
---

| 機能 | 状態 | 担当者 |
|------|------|--------|
| ログイン | 完了 | 田中 |
| ダッシュボード | 進行中 | 佐藤 |
| レポート | 計画中 | 鈴木 |
```

### 2. カスタムリストマーカー

```markdown
---
style: |
  ul { list-style: none; }
  ul li::before {
    content: "▶";
    color: #667eea;
    font-weight: bold;
    display: inline-block;
    width: 1em;
    margin-left: -1em;
  }
  ol { counter-reset: custom-counter; list-style: none; }
  ol li { counter-increment: custom-counter; }
  ol li::before {
    content: "Step " counter(custom-counter);
    color: #667eea;
    font-weight: bold;
    margin-right: 0.5em;
  }
---
```

### 3. 装飾付き引用

```markdown
---
style: |
  blockquote {
    border-left: 4px solid #3b82f6;
    padding-left: 1em;
    font-style: italic;
    background: #f0f9ff;
    padding: 1em;
    border-radius: 4px;
    margin: 1em 0;
  }
---

> デザインは単なる見た目ではなく、どう機能するかだ
> — Steve Jobs
```

---

## 実践的なテクニック集

### 1. プログレスバー

```markdown
---
style: |
  section::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    height: 4px;
    width: calc(100% * var(--paginate) / var(--total-pages));
    background: linear-gradient(to right, #667eea, #764ba2);
  }
---
```

### 2. カスタムページ番号

```markdown
---
paginate: true
style: |
  section::after {
    content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total);
    position: absolute;
    bottom: 20px;
    right: 20px;
    font-size: 20px;
    color: #666;
    background: rgba(255, 255, 255, 0.8);
    padding: 4px 12px;
    border-radius: 4px;
  }
---
```

### 3. タイムライン

```markdown
---
style: |
  .timeline {
    position: relative;
    padding-left: 2em;
  }
  .timeline::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    background: #667eea;
  }
  .timeline-item {
    position: relative;
    margin-bottom: 2em;
  }
  .timeline-item::before {
    content: '';
    position: absolute;
    left: -2.5em;
    top: 0.3em;
    width: 1em;
    height: 1em;
    border-radius: 50%;
    background: #667eea;
    border: 3px solid white;
  }
---

<div class="timeline">
  <div class="timeline-item">**2023年1月**: プロジェクト開始</div>
  <div class="timeline-item">**2023年6月**: ベータ版リリース</div>
  <div class="timeline-item">**2023年12月**: 正式リリース</div>
</div>
```

### 4. カードレイアウト

```markdown
---
style: |
  .cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5em;
  }
  .card {
    background: white;
    border-radius: 8px;
    padding: 1.5em;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transition: transform 0.2s;
  }
  .card h3 {
    margin-top: 0;
    color: #667eea;
    font-size: 1.2em;
  }
  .card p {
    color: #666;
    font-size: 0.9em;
  }
---

<div class="cards">
  <div class="card">

### Feature 1
説明文がここに入ります

  </div>
  <div class="card">

### Feature 2
説明文がここに入ります

  </div>
  <div class="card">

### Feature 3
説明文がここに入ります

  </div>
</div>
```

### 5. ステップ表示（矢印付き）

```markdown
---
style: |
  .steps {
    display: flex;
    justify-content: space-between;
    margin: 2em 0;
  }
  .step {
    flex: 1;
    text-align: center;
    position: relative;
  }
  .step-number {
    display: inline-block;
    width: 2.5em;
    height: 2.5em;
    line-height: 2.5em;
    border-radius: 50%;
    background: #667eea;
    color: white;
    font-weight: bold;
    font-size: 1.2em;
  }
  .step::after {
    content: '→';
    position: absolute;
    right: -1.5em;
    top: 0.7em;
    font-size: 2em;
    color: #667eea;
  }
  .step:last-child::after { display: none; }
---

<div class="steps">
  <div class="step">
    <div class="step-number">1</div>
    **計画**
  </div>
  <div class="step">
    <div class="step-number">2</div>
    **実行**
  </div>
  <div class="step">
    <div class="step-number">3</div>
    **検証**
  </div>
</div>
```

### 6. Before/After比較

```markdown
# Before vs After

<div class="columns">
  <div>

## Before
- 問題点1
- 問題点2
- 問題点3

**状態**: 非効率

  </div>
  <div>

## After
- 改善点1
- 改善点2
- 改善点3

**状態**: 最適化

  </div>
</div>
```

---

## よくあるパターンテンプレート

### 1. タイトルスライド

```markdown
<!-- _class: lead -->
<!-- _backgroundColor: linear-gradient(135deg, #667eea 0%, #764ba2 100%) -->
<!-- _color: white -->

# プレゼンテーションタイトル
## サブタイトル

**発表者名**
**所属**
2025-11-18
```

### 2. セクション区切りスライド

```markdown
<!-- _class: lead -->
<!-- _backgroundColor: #1e293b -->
<!-- _color: white -->

# 第2章
## データ分析結果
```

### 3. アジェンダスライド

```markdown
# アジェンダ
## 本日の内容

1. **背景と課題** - 現状分析
2. **提案ソリューション** - 解決策
3. **実装計画** - ロードマップ
4. **まとめ** - 次のステップ

<div class="small">所要時間: 約30分</div>
```

### 4. まとめスライド

```markdown
# まとめ
## 今日学んだこと

1. **ポイント1**: 説明文
2. **ポイント2**: 説明文
3. **ポイント3**: 説明文

### Next Step
次のアクションを明記
```

### 5. 質問・Thank Youスライド

```markdown
<!-- _class: lead -->

# ありがとうございました
## 質問タイム

<div style="font-size: 0.8em; margin-top: 2em; color: #666;">
email@example.com
@username
example.com
</div>
```

---

## エクスポート設定

### PDFエクスポート用設定

```markdown
---
marp: true
theme: default
paginate: true
size: 16:9
pdf: true
printBackground: true
style: |
  @media print {
    section {
      break-inside: avoid;
    }
  }
---
```

### PowerPoint互換設定

```markdown
---
marp: true
size: 16:9  # PowerPointの標準サイズ
backgroundColor: white
style: |
  section {
    font-family: Arial, sans-serif;
    font-size: 24px;
  }
---
```

---

## ベストプラクティス

### プレゼンテーション全体の構成

```markdown
---
marp: true
theme: default
paginate: true
backgroundColor: #fafafa
style: |
  section {
    font-size: 28px;
    padding: 60px;
  }
  h1 {
    font-size: 48px;
    color: #2e3440;
    border-bottom: 3px solid #5e81ac;
  }
  .columns {
    display: flex;
    gap: 2em;
  }
  .columns > div {
    flex: 1;
  }
  .highlight {
    background: linear-gradient(transparent 60%, #ffeb3b 60%);
    font-weight: bold;
  }
  section.lead {
    text-align: center;
    justify-content: center;
  }
---

<!-- _class: lead -->
# タイトル
## サブタイトル
発表者名

---

# アジェンダ

---

# 本編スライド

---

<!-- _class: lead -->
# ありがとうございました
```

---

## 注意事項

1. **スタイルの一貫性**: 色・フォント・余白を統一する
2. **シンプルに保つ**: 過度な装飾は避け、メッセージを明確に
3. **画像最適化**: ファイルサイズに注意
4. **テストと確認**: 必ずプレビューで確認してからエクスポート
5. **バージョン管理**: バージョンを残して更新する

---

## 参考リソース

- [Marp公式ドキュメント](https://marpit.marp.app/)
- [Marp CLI](https://github.com/marp-team/marp-cli)
- [Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode)
