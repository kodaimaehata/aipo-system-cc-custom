# T003: SKILL.md作成

## Goal
Claude Code skill定義ファイル（SKILL.md）を作成する。

## Type
Implementation

## Estimate
1h

---

## Phase 1 (AI): SKILL.md作成

### Step 1.1: ディレクトリ作成
```bash
mkdir -p .claude/skills/pptx-from-template
```

### Step 1.2: SKILL.md作成
以下の形式で作成：

```markdown
---
name: pptx-from-template
description: Generate PowerPoint presentations from templates. Use when creating PPTX files from existing templates with custom data, or when the user asks to create slides, presentations, or PowerPoint files.
---

# PPTX from Template

## Description
テンプレート.pptxファイルを基に、指定されたデータでプレースホルダーを差し替えてPowerPointファイルを生成します。

## Usage
...（T002の設計に基づく）
```

### Step 1.3: frontmatter要件確認
- `name`: kebab-case、小文字、64文字以内
- `description`: 1024文字以内、トリガー条件を含む

---

## HITL Phase (Human): レビュー

### 確認事項
- [ ] description は分かりやすいか
- [ ] トリガー条件は適切か
- [ ] 使用方法の説明は十分か

---

## Phase 2 (AI): 確定・配置

### 成果物
1. `.claude/skills/pptx-from-template/SKILL.md`

### 更新
- `tasks.yaml` の T003 status を `completed` に更新

---

## Instructions for aipo-deliver

1. T002のインターフェース設計を参照
2. `.claude/skills/pptx-from-template/` ディレクトリを作成
3. SKILL.mdを作成（frontmatter + 使用方法）
4. ユーザーにレビューを依頼
5. フィードバックを反映
