---
name: light-planning
description: "`mini-projects/` で進める軽量案件の planning スキル。brief / context / requirements / design / plan を作り、各段階で HITL 確認を入れる。開発だけでなく、調査レポートや仕様書などの文書成果物にも適用できる。"
---

# light-planning

## Purpose

軽量案件でも、いきなり実装や執筆に入らず、次を残す:
- brief
- context
- requirements
- design
- plan

ただし AIPO のような `layer.yaml` / `tasks.yaml` / `commands/*.md` フルセットは作らない。
コード成果物にも文書成果物にも使える、軽量な planning レイヤーとして扱う。

## Output Files

標準出力先は対象 run directory 配下:
- `brief.md`
- `context.md`
- `requirements.md`
- `design.md`
- `plan.md`

必要に応じて:
- `non_goals.md`
- `interfaces.md`
- `tasks/T00X_*.md`

## Process

### 1. Brief

書くこと:
- 何を作るか
- 誰が使うか
- なぜ必要か
- 何をしないか
- 成功条件

HITL:
- Goal / Scope 確認

### 2. Context

集めること:
- 関連ファイル
- 既存実装
- 既存文書
- 外部依存
- 制約
- 参考になる過去成果物
  - `programs/`
  - `flows/`
  - `mini-projects/archive/`

### 3. Requirements

整理すること:
- 機能要件
- 非機能要件
- 成功基準
- 非ゴール
- Open questions

HITL:
- Requirements 確認

### 4. Design

整理すること:
- 機能分割
- 入出力
- データフロー
- 章構成や論理展開（文書案件の場合）
- 技術選定
- テスト方針
- リスク

HITL:
- Design 確認

### 5. Plan

`writing-plans` の原則を軽量適用する:
- タスクは小さく切る
- 対象ファイルを明示する
- テスト方法またはレビュー方法を明示する
- Done 条件を書く

HITL:
- Build 着手前確認

## Rules

- requirements より前に design を固定しない
- design より前に implementation task を確定しすぎない
- plan は長大な一枚ではなく、必要なら `tasks/` に分割する
- 後から reuse できるように略語だけのメモで済ませない
