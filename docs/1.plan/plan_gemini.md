# AIPO (AI-PO) System for Codex CLI Implementation Plan

## プロジェクト概要
`src/aipo (AI-PO) system` で定義されている **AIPO (AI Product Owner)** システムを、**Codex CLI (Claude Code)** 環境で実行可能な形式（Skills, Slash Commands）として実装します。これにより、Codex CLI上で`/sense`や`/focus`などのコマンドを通じて、自律的なプロジェクト管理・タスク推進が可能になります。

## ゴール
1. Codex CLI (`codex`) から AIPO の各フェーズ（Sense, Focus, Discover, Deliver）を実行可能にする。
2. AIPOの思想（再帰的構造、コンテキスト継承）を Claude Code の機能（Skills, Subagents）で再現する。

## アーキテクチャ設計

`src/aipo (AI-PO) system/AIPOとClaude Codeの対応関係` に基づき、以下のマッピングで実装します。

| AIPO Component | Claude Code Feature | 実装内容 |
| :--- | :--- | :--- |
| **Command Templates** | **Skills** | 各AIPOコマンドのロジック・知識を Skill として定義 (`.claude/skills/`) |
| **01_sense / 02_focus** | **Slash Commands** | ワークフロー開始トリガー (`.claude/commands/`) |
| **03_discover** | **Skills (Dynamic)** | タスクに応じたコマンド生成スキル |
| **04_deliver** | **Subagents / Tools** | 実行エージェント（親コンテキスト継承） |

## 実装計画 (Tasks)

### Phase 1: 環境セットアップ
- [ ] `.claude` ディレクトリ構造の作成
    - `.claude/commands/`: Slash Commands用
    - `.claude/skills/`: Skills用
    - `.claude/prompts/`: 共通プロンプト（必要に応じて）

### Phase 2: Core Skills の実装 (AIPOロジックの移植)
AIPOのMarkdown定義ファイルを、Claude Codeが解釈可能な Skill 定義に変換します。

- [ ] **Skill: AIPO Core (`.claude/skills/aipo-core`)**
    - AIPOの基本概念（Layer, Context, Goal）を理解させるための共通コンテキスト。
- [ ] **Skill: Sense (`.claude/skills/aipo-sense`)**
    - `CMD_aipo_01_sense` のロジックを移植。
    - プロジェクト初期化、Context収集、`layer.yaml` 等の生成プロセスを定義。
- [ ] **Skill: Focus (`.claude/skills/aipo-focus`)**
    - `CMD_aipo_02_focus` のロジックを移植。
    - タスク分解、SubLayer特定プロセスを定義。

### Phase 3: Slash Commands の実装
ユーザーがターミナルから呼び出すためのコマンドを定義します。

- [ ] **Command: `/sense`**
    - `.claude/skills/aipo-sense` を呼び出し、Senseフェーズを実行する。
    - 引数: Goal, Layer Name
- [ ] **Command: `/focus`**
    - `.claude/skills/aipo-focus` を呼び出し、Focusフェーズを実行する。
    - 引数: Target Layer

### Phase 4: Discover & Deliver (Advanced)
- [ ] **Command: `/discover`** (`CMD_aipo_03_discover`)
    - 具体的な実行コマンド（Tasks）を生成するフロー。
- [ ] **Command: `/deliver`** (`CMD_aipo_04_deliver`)
    - 生成されたタスクを実行する。Subagent的な振る舞いを定義。

## 検証計画
- [ ] **構造検証**: `.claude` 配下のファイルが正しく配置されているか確認。
- [ ] **コマンド認識**: `codex` 上で `/sense` や `/help` でコマンドが認識されるか（可能なら確認）。
- [ ] **ドライラン**: ユーザーに実際に `/sense` を実行してもらい、`programs/` 配下に成果物が生成されるか確認する（ユーザー協力を依頼）。

## 成果物
- `docs/1.plan/plan_gemini.md` (本計画書)
- `.claude/` ディレクトリ一式

## 備考
- AIPOのMarkdownファイルは「仕様書」として扱い、そこに書かれているプロンプトや手順を Skill の `instructions` に変換して記述します。
