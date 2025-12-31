# T001: python-pptx技術検証

## Goal
python-pptxライブラリの動作検証を行い、テンプレートベースのPowerPoint生成が実現可能か確認する。

## Type
HITL (Human-in-the-Loop)

## Estimate
4h

---

## Phase 1 (AI): 環境セットアップと基本検証

### Step 1.1: Python環境構築
```bash
cd programs/pptx-from-template
uv init pptx-skill-dev
cd pptx-skill-dev
uv add python-pptx
uv sync
```

### Step 1.2: 基本動作確認スクリプト作成
以下の機能を検証するPythonスクリプトを作成：
1. 新規プレゼンテーション作成
2. 既存.pptxファイルの読み込み
3. スライドレイアウトの取得
4. プレースホルダーへのテキスト挿入
5. ファイル保存

### Step 1.3: テンプレート操作検証
- マスタースライドの構造確認
- プレースホルダーの種類と位置の取得
- テキスト・表・画像の差し替え方法調査

---

## HITL Phase (Human): 検証結果確認

### 確認事項
- [ ] python-pptxが正常にインストールされたか
- [ ] テンプレートのデザイン（フォント、色、レイアウト）が維持されるか
- [ ] 日本語テキストが正常に表示されるか
- [ ] 生成されたファイルがPowerPointで開けるか

### 判断ポイント
- python-pptxで要件を満たせない場合、代替ライブラリ（pptx-template等）の検討が必要

---

## Phase 2 (AI): 検証結果のドキュメント化

### 成果物
1. `documents/tech_verification_report.md` - 技術検証レポート
2. `pptx-skill-dev/` - 検証用Pythonプロジェクト
3. サンプルコードスニペット

### 更新
- `tasks.yaml` の T001 status を `completed` に更新

---

## Instructions for aipo-deliver

1. `programs/pptx-from-template/` ディレクトリに移動
2. uv を使用してPython環境を構築
3. python-pptxの基本機能を検証するスクリプトを作成・実行
4. 検証結果をレポートにまとめる
5. 問題があればユーザーに報告し判断を仰ぐ
