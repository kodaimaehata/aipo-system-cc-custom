# Codex CLI版 AIPO スキル化：プロジェクト計画

## 1. 目的（ゴール）

`/Users/kodai/projects/aipo-system/src` にある **AIPO（AI Product Owner）システム**のワークフロー（Sense→Focus→Discover→Deliver→Operation）を、Codex CLI でも **Skills（+必要に応じてスクリプト/参照資料）**として再現できる状態にする。

最終的に「Goalだけ渡せば、CodexがAIPO流に分解→計画→実行→更新まで進められる」ことを狙う（ただし自動化しすぎず、編集可能な成果物を残す）。

## 2. 現状分析（`src/` の構造と示唆）

`src/aipo (AI-PO) system/` は Notion Export 由来の Markdown 群（全94ファイル）で、概ね以下で構成される：

- **コアコマンド**: `CMD_aipo_01_sense`〜`CMD_aipo_05_operation`
- **共通ルール**: `CTX_execution_rules`, `CTX_session_rules`, `CTX_next_action_rules`, `CTX_abstract_mode_rules`
- **Focus戦略テンプレ**: `CTX_roles_templates/*_focus`（system_architect / product_manager / content_strategist / generic）
- **コマンドテンプレ集**: `CTX_command_templates/`（project/task/research/system_building/content 等のカテゴリ）
- **対応関係メモ**: `AIPOとClaude Codeの対応関係…md`（Skills/Subagents/Slash Commands との概念対応）

示唆：
- 既存ドキュメントは Notion 前提（`<aside>`、mention、Database運用等）なので、Codex CLI向けに **ファイルベースの成果物**へ写像する必要がある。
- 一方で「段階的ロード（Progressive Disclosure）」や「テンプレ参照→実行コマンド生成」の発想は、Codex Skills と親和性が高い。

## 3. スコープ

### 対象（やる）
- AIPO 01〜05 を **Codex Skills**として利用できる形に再設計（MVP→拡張）。
- AIPO の成果物（`layer.yaml`/`context.yaml`/`tasks.yaml`/Commands相当）を **ローカルファイル**として生成・更新できるようにする。
- テンプレ群を「参照資料（references/）」として整理し、必要時のみロードできる構成にする。
- スキルの配布（`.skill`パッケージ化）とインストール手順を整備する。

### 非対象（当面やらない）
- Notion Database/Form 連携の完全再現（Codex側の外部連携が必要なため）。
- タスク分解の完全自動化（人が修正できる前提でMVPを作る）。
- Claude Code の Subagent 相当の並列実行の再現（Codexの機能範囲に合わせる）。

## 4. 成果物（Deliverables）

1. **スキル一式（MVP）**
   - `aipo-workflow`（まずは1スキルで全体を扱い、必要なら後で分割）
2. **スキル同梱リソース**
   - `references/`: AIPO要点抜粋（+必要なら `src/` からの最小限コピー/再構成）
   - `scripts/`: レイヤー雛形作成、YAML検証、テンプレ検索などの補助
3. **ファイルベースのAIPO運用フォーマット（案）**
   - 成果物保存先: `programs/{project名}/`
   - Git運用: `programs/{project名}/` はプロジェクトごとの独立リポジトリとして扱う（各プロジェクトで `git init`）
   - 例: `programs/{project名}/layer.yaml` / `context.yaml` / `tasks.yaml` / `commands/*.md`
4. **パッケージ**
   - `package_skill.py` による `.skill` 生成（配布可能状態）

## 5. 設計方針（Codex Skillsとしての落とし込み）

### 5.1 スキル設計（Progressive Disclosure）

- **SKILL.md（本体）は薄く**し、詳細は `references/` に分離（目安：SKILL.md本文は500行未満）。
- 「テンプレ一覧・長文ルール」は references 側に置き、SKILL.md には
  - 実行フロー（01〜05）
  - どの参照をいつ読むか（検索パターン含む）
  - 成果物のファイル規約
  だけを書く。

### 5.2 AIPO→Codex CLI の写像（MVP）

- **01 Sense**: 目的・制約・対象リポジトリ情報を収集し、`layer.yaml`/`context.yaml` を作る
- **02 Focus**: Focus戦略（role template）を選び、`tasks.yaml` を作る（各Taskに `command`/`command_template_ref` を必須化）
- **03 Discover**: `tasks.yaml` を読み、`commands/` に実行手順（チェックリスト/コマンド例）を生成
- **04 Deliver**: 選択Taskを実行（Codexのツール実行 + 変更適用）し、`tasks.yaml` を更新
- **05 Operation**: 繰り返し作業（例：複数タスクのバッチ実行、フォーマット統一、レポート生成）をコマンド化

### 5.3 ドメイン（2種類）

- **汎用**: どのプロジェクトにも適用できるAIPOワークフロー（Focus戦略は動的選択）
- **新規事業ディスカバリー**: 市場調査→課題/仮説→検証→MVP計画/開発までを想定（テンプレ参照をDiscovery/Research中心に寄せる）
- スキル分割が必要になった場合の命名案:
  - `aipo-workflow-general`
  - `aipo-workflow-discovery`

## 6. 実施計画（WBS）

### Phase 0: 要件確定（0.5〜1日）
- 代表ユースケースを3つ定義（例：新規機能開発、リファクタ、ドキュメント整備）
- 成果物の保存先を確定（`programs/{project名}`）
- 対象ドメインを確定（汎用 / 新規事業ディスカバリー）
- スキルの粒度を確定（まずは単一 `aipo-workflow`、必要なら分割）

### Phase 1: 参照資料の再構成（1〜2日）
- `CMD_aipo_*` と `CTX_*` から **Codex実行に必要な最小ルール**を抽出して `references/` 化
- `CTX_command_templates/` を「検索しやすい索引」にまとめる（カテゴリ/代表テンプレ/用途）
- Notion依存記法（mention等）を、CLIで使える表現に置き換えた例を作る

### Phase 2: スキルMVP作成（1日）
- `init_skill.py` でスキル雛形を生成（例：`aipo-workflow/`）
- SKILL.md を作成（実行フロー、入出力、例、参照ファイルへの導線）
- 補助スクリプトを追加（必要最小限）
  - `init_layer`（雛形生成）
  - `validate_tasks`（必須フィールド検証）
  - `find_template`（テンプレ候補検索）

### Phase 3: 動作検証（0.5〜1日）
- 小さなサンプルGoalで「01→02→03→04」まで通す（1タスク実行まで）
- トリガー文言（description）を調整し、意図したときにスキルが使われることを確認
- references が肥大化しないか確認（必要なら分割）

### Phase 4: パッケージ化・配布（0.5日）
- `quick_validate.py` と `package_skill.py` で `.skill` を生成
- インストール手順を整理（REPO: `$REPO_ROOT/.codex/skills` / `$CWD/.codex/skills`、USER: `$CODEX_HOME/skills`=通常`~/.codex/skills`）
  - ※ `skill-installer` はネットワークが必要なため、運用方針を決める

### Phase 5: 拡張（継続）
- スキルを 01〜05 に分割してロード効率を改善（必要なら）
- テンプレを追加しやすい運用にする（references の構造、索引更新の自動化）
- 外部連携（Issueトラッカー、CI等）が必要なら別プロジェクトで検討

## 7. リスクと対策

- **スキルが発火しない/しすぎる**: description をユースケース駆動で具体化し、必要ならスキル名指定（`$aipo-workflow`）を運用に入れる
- **参照が長すぎてコンテキスト圧迫**: references を小分けにし、索引 + `rg`検索前提にする
- **`src/` のファイル名が複雑（空白/日本語/Notion ID）**: スキル同梱用には「整理したコピー」を作り、元は不変で保持する

## 8. 完了条件（Definition of Done）

- `.skill` として配布可能で、インストール後に再起動で認識される
- 代表ユースケース1つで、以下が再現できる：
  - `layer.yaml`/`context.yaml`/`tasks.yaml` の生成
  - `commands/` の生成
  - 1つのTaskを実行し、成果物とステータス更新が残る

## 9. 決定事項

1. スキル名: `aipo-workflow`
2. 成果物保存先: `programs/{project名}`
3. 対象ドメイン: 汎用 / 新規事業ディスカバリー（必要なら `aipo-workflow-general` と `aipo-workflow-discovery` に分割）
