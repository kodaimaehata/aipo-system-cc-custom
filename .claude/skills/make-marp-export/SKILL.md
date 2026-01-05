---
name: make-marp-export
description: Marp MarkdownファイルをPPTX/PDFにエクスポートする（marp-cli使用）
---

# make-marp-export

## Description
marp-cliを使用してMarp Markdownファイルをプレゼンテーション形式（PPTX/PDF/HTML）にエクスポートします。
Phase 3（make-marp-slide）の出力を最終成果物に変換する **Phase 4** です。

## Usage
**Triggers**: `/marp-export`, "Marpをエクスポート", "スライドをPPTXに変換"

## Inputs

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|------------|
| input_file | Marp mdファイルパス | Yes | - |
| format | 出力形式（pptx/pdf/html） | No | pptx |
| output_file | 出力ファイルパス | No | 自動生成（入力ファイル名.{format}） |
| allow_local_files | ローカルファイル参照許可 | No | true |

## Instructions

### Step 1: 前提条件の確認

1. **Node.js環境の確認**
   ```bash
   node --version
   ```
   - エラーの場合: `volta install node` を実行するか、`.zshrc` のVolta PATH設定を確認

2. **npxの動作確認**
   ```bash
   npx --version
   ```

### Step 2: 入力ファイルの検証

1. **ファイル存在確認**
   - 指定されたMarpファイルが存在することを確認

2. **Marp frontmatterの確認**
   - ファイル先頭に `marp: true` が含まれていることを確認
   ```yaml
   ---
   marp: true
   ...
   ---
   ```

### Step 3: 出力パスの決定

- `output_file` が指定されていない場合:
  - 入力ファイルと同じディレクトリに `{basename}.{format}` として出力
  - 例: `slides.md` → `slides.pptx`

### Step 4: コマンド構築と実行

**PPTX出力**:
```bash
npx @marp-team/marp-cli {input_file} --pptx -o {output_file} --allow-local-files
```

**PDF出力**:
```bash
npx @marp-team/marp-cli {input_file} --pdf -o {output_file} --allow-local-files
```

**HTML出力**:
```bash
npx @marp-team/marp-cli {input_file} -o {output_file} --allow-local-files
```

### Step 5: 結果報告

**成功時**:
```
エクスポート完了

出力ファイル: {output_file}
フォーマット: {format}
```

**失敗時**: エラー内容とトラブルシューティングを提示

## Error Handling

| エラー | 原因 | 対処 |
|--------|------|------|
| `npx: command not found` | Volta PATHが設定されていない | `.zshrc` に `export PATH="$HOME/.volta/bin:$PATH"` を追加し、`source ~/.zshrc` を実行 |
| `Error: Cannot find module` | marp-cliが初回実行 | 自動ダウンロードを待つ（初回は時間がかかる） |
| `Failed to launch browser` | Chromiumの問題（PDF生成時） | `--no-sandbox` オプションを追加 |
| `ENOENT` | 入力ファイルが見つからない | ファイルパスを確認 |
| `Invalid Marp document` | Marp frontmatterがない | ファイル先頭に `marp: true` を追加 |

## Output Format

**成果物**:
- `{basename}.pptx` - PowerPointファイル
- `{basename}.pdf` - PDFファイル
- `{basename}.html` - HTMLファイル

## Tips

- **画像を含むスライド**: `--allow-local-files` オプションでローカル画像を参照可能
- **カスタムテーマ**: `--theme` オプションでテーマを指定可能
- **複数ファイル**: ディレクトリを指定して一括変換も可能
- **初回実行**: marp-cliのダウンロードに時間がかかる場合がある

## Related Skills

- `make-marp-slide` - Marp Markdownの生成（Phase 3）
- `make-marp-all` - 全フェーズの統合実行
