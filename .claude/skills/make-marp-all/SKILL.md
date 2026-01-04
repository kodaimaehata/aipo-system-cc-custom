---
name: make-marp-all
description: テーマから完成Marpスライドまで一気通貫で生成（3フェーズ統合）
---

# make-marp-all

## Description
プレゼンテーションのテーマから完成したMarpスライドまで、3つのフェーズを一気通貫で実行します。

- **Phase 1**: Outline + Input Bundle生成（make-marp-outline）
- **Phase 2**: 台本生成（make-marp-script）
- **Phase 3**: Marpスライド生成（make-marp-slide）

## Usage
**Triggers**: `/marp`, "スライドを作って", "Marpで資料作成"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|----------|
| theme | プレゼンテーマ/タイトル | Yes | - |
| duration | 想定時間（分） | Yes | 10 |
| audience | 対象聴衆 | Yes | - |
| tone | トーン（casual/formal/technical/storytelling） | No | casual |
| key_points | 必ず含めたいポイント | No | - |
| marp_theme | Marpテーマ（default/gaia/uncover） | No | default |
| output_dir | 出力ディレクトリ | No | ./marp-output |
| skip_hitl | HITL確認をスキップ | No | false |

## Workflow

```
[入力] テーマ・尺・聴衆
    │
    ▼
┌─────────────────────────────┐
│ Phase 1: Outline生成        │
│ → outline.md               │
│ → input_bundle.md          │
└─────────────────────────────┘
    │
    ▼ [HITL] Outline確認 (skip_hitl=falseの場合)
    │
┌─────────────────────────────┐
│ Phase 2: Script生成         │
│ → script.md                │
└─────────────────────────────┘
    │
    ▼ [HITL] 台本確認・A/B選択 (skip_hitl=falseの場合)
    │
┌─────────────────────────────┐
│ Phase 3: Slide生成          │
│ → slides.md                │
└─────────────────────────────┘
    │
    ▼
[出力] Marp Markdown + スピーカーノート
```

## Instructions

### Phase 1: Outline生成

1. **入力情報の確認**
   - テーマ、想定時間、対象聴衆を確認
   - 不足情報があればユーザーに確認

2. **Outline生成**
   - `make-marp-outline` スキルの手順に従う
   - 時間配分を設計
   - 各セクションの狙いを定義

3. **Input Bundle生成**
   - 材料を整理
   - 核となるメッセージを定義

4. **[HITL] 確認ポイント** (skip_hitl=falseの場合)
   ```
   === Phase 1 完了 ===

   生成したOutline:
   {Outlineの概要}

   この構成で進めてよろしいですか？
   [Y] はい、続行
   [N] いいえ、修正したい

   選択: _
   ```

### Phase 2: Script生成

1. **オープニングスタイル選択** (skip_hitl=falseの場合)
   ```
   オープニングのスタイルを選択:
   [A] 質問から始める
   [B] 驚きの事実から始める
   [C] ストーリーから始める

   選択 (A/B/C): _
   ```

2. **クロージングスタイル選択** (skip_hitl=falseの場合)
   ```
   クロージングのスタイルを選択:
   [A] 質疑応答への誘導
   [B] 強いCTAで締める
   [C] 余韻を残す

   選択 (A/B/C): _
   ```

3. **台本生成**
   - `make-marp-script` スキルの手順に従う
   - スピーカーノート付きの台本を生成

4. **[HITL] 確認ポイント** (skip_hitl=falseの場合)
   ```
   === Phase 2 完了 ===

   生成した台本（抜粋）:
   {台本の冒頭部分}

   この台本で進めてよろしいですか？
   [Y] はい、続行
   [N] いいえ、修正したい

   選択: _
   ```

### Phase 3: Slide生成

1. **Marp変換**
   - `make-marp-slide` スキルの手順に従う
   - marp_expression_guideを参照
   - スピーカーノートを埋め込み

2. **品質チェック**
   - 1スライド1メッセージ原則
   - 日本語フォント設定
   - ページ番号表示

3. **ファイル出力**
   - `{output_dir}/slides.md`

### 完了報告

```
=== Marpスライド生成完了 ===

生成ファイル:
- {output_dir}/outline.md
- {output_dir}/input_bundle.md
- {output_dir}/script.md
- {output_dir}/slides.md

確認方法:
1. Marp Web Editor (https://web.marp.app/) で slides.md を開く
2. VS Code + Marp拡張でプレビュー
3. marp-cli でPDF/PPTXにエクスポート

スライド枚数: X枚
想定時間: X分
```

## Output Format

**成果物** (すべて `{output_dir}/` に保存):
1. `outline.md` - 構成案
2. `input_bundle.md` - 材料束
3. `script.md` - 台本
4. `slides.md` - Marp Markdown

## HITL Integration Points

| フェーズ | 確認ポイント | スキップ可能 |
|---------|-------------|-------------|
| Phase 1後 | Outline確認 | Yes (skip_hitl=true) |
| Phase 2 | オープニング選択 | Yes (デフォルトA) |
| Phase 2 | クロージング選択 | Yes (デフォルトA) |
| Phase 2後 | 台本確認 | Yes (skip_hitl=true) |

## Quick Mode (skip_hitl=true)

HITLをスキップする場合のデフォルト値:
- オープニング: A（質問から始める）
- クロージング: A（質疑応答への誘導）
- 各フェーズの確認はスキップして自動続行

## References
- `.claude/skills/make-marp-outline/SKILL.md`
- `.claude/skills/make-marp-script/SKILL.md`
- `.claude/skills/make-marp-slide/SKILL.md`
- `.claude/skills/make-marp-outline/references/marp_expression_guide.md`
