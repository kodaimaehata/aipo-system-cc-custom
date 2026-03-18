---
name: save-to-flow
description: 会話のアウトプットをflows/フォルダに日付ベースで保存する
---

# save-to-flow

## Description
会話中のアウトプットを `flows/{date}/{title}/` に保存します。
日付ベースのアドホック作業フォルダとして、調査結果・アイディア・メモ等を整理して保管できます。

## Usage
**Triggers**: `/flow`, "flowに保存", "flowsに保存", "フローに保存"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|-----------|
| title | 保存フォルダのタイトル（日本語/英語） | Yes | - |
| content | 保存するコンテンツ（会話中のアウトプット） | Yes | - |
| format | ファイル形式 (md/txt/yaml/json等) | No | md |

## Instructions

### Step 1: 日付とタイトルの決定
1. 今日の日付を `YYYY-MM-DD` 形式で取得
2. タイトルはユーザー指定、または会話内容から簡潔に自動生成
3. タイトル内のスペースはアンダースコア `_` に置換

### Step 2: ディレクトリ作成
```bash
mkdir -p "flows/{date}/{title}"
```

### Step 3: コンテンツ保存
1. デフォルトのファイル名は `output.{format}`（デフォルト: `output.md`）
2. 複数ファイルがある場合はすべて同フォルダに保存
3. コンテンツが会話中の特定のアウトプットの場合、そのアウトプットをそのまま保存

### Step 4: 結果報告
保存先パスをユーザーに報告:
```
保存しました: flows/{date}/{title}/output.md
```

## Output Format

**ディレクトリ構造**:
```
flows/
└── YYYY-MM-DD/
    └── {title}/
        └── output.md
```

## Error Handling

| エラー | 対応 |
|--------|------|
| titleが未指定 | 会話内容から簡潔なタイトルを自動生成 |
| 同名フォルダが存在 | ファイル名にサフィックス（_2, _3...）を付与 |
| contentが不明確 | ユーザーに保存対象を確認 |

## Examples

**例1: タイトル指定**
```
/flow AM業務改善アイディア
→ flows/2026-03-18/AM業務改善アイディア/output.md
```

**例2: 複数ファイル保存**
```
/flow 調査レポート
→ flows/2026-03-18/調査レポート/output.md
→ flows/2026-03-18/調査レポート/data.json
```

**例3: フォーマット指定**
```
flowにYAML形式で保存して
→ flows/2026-03-18/{auto_title}/output.yaml
```
