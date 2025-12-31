# T005: サンプルテンプレート作成

## Goal
動作確認用の.pptxテンプレートファイルを作成する。

## Type
Implementation

## Estimate
1h

---

## Phase 1 (AI): テンプレート構造設計

### Step 1.1: スライド構成
1. **タイトルスライド**: タイトル + サブタイトル + 日付
2. **セクションスライド**: セクションタイトル
3. **コンテンツスライド**: タイトル + 箇条書き本文
4. **2カラムスライド**: タイトル + 左右2つのコンテンツ
5. **表スライド**: タイトル + 表
6. **画像スライド**: タイトル + 画像プレースホルダー

### Step 1.2: プレースホルダー命名規則
- `{{title}}` - タイトル
- `{{subtitle}}` - サブタイトル
- `{{body}}` - 本文
- `{{date}}` - 日付
- `{{author}}` - 作成者
- `{{table_data}}` - 表データ
- `{{image}}` - 画像

---

## HITL Phase (Human): テンプレート作成

### 作業内容
ユーザーがPowerPointで以下を作成：
- [ ] 上記スライド構成に従ったテンプレート
- [ ] デザイン（配色、フォント）の設定
- [ ] プレースホルダーの配置

### 代替案
AIがpython-pptxで基本テンプレートを生成し、ユーザーがデザインを調整

---

## Phase 2 (AI): テンプレート検証

### 検証項目
- プレースホルダーが正しく認識されるか
- T004のスクリプトで差し替えが動作するか

### 成果物
1. `.claude/skills/pptx-from-template/templates/sample_template.pptx`
2. `.claude/skills/pptx-from-template/templates/sample_data.json`

### 更新
- `tasks.yaml` の T005 status を `completed` に更新

---

## Instructions for aipo-deliver

1. テンプレート構造をユーザーに提案
2. ユーザーにテンプレート作成を依頼 or AIで基本テンプレートを生成
3. 作成されたテンプレートをT004のスクリプトでテスト
4. 問題があれば修正
5. テンプレートとサンプルデータを配置
