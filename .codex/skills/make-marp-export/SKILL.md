---
name: make-marp-export
description: "Marp MarkdownファイルをPPTX/PDFにエクスポートする（marp-cli使用）。Phase 3の出力を最終成果物に変換するPhase 4。"
---

# make-marp-export（Codex CLI）

目的: marp-cliを使用してMarp Markdownファイルをプレゼンテーション形式（PPTX/PDF/HTML）にエクスポートする。

## 1) 入力パラメータ

| パラメータ | 説明 | 必須 | デフォルト |
|-----------|------|------|------------|
| input_file | Marp mdファイルパス | Yes | - |
| format | 出力形式（pptx/pdf/html） | No | pptx |
| output_file | 出力ファイルパス | No | 自動生成（入力ファイル名.{format}） |
| allow_local_files | ローカルファイル参照許可 | No | true |

## 2) 前提条件の確認

1. **Node.js環境の確認**
   ```bash
   node --version
   ```
   - エラーの場合: `volta install node` を実行するか、`.zshrc` のVolta PATH設定を確認

2. **npxの動作確認**
   ```bash
   npx --version
   ```

## 3) 入力ファイルの検証

1. **ファイル存在確認**
   - 指定されたMarpファイルが存在することを確認

2. **Marp frontmatterの確認**
   - ファイル先頭に `marp: true` が含まれていることを確認

## 4) コマンド構築と実行

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

## 5) エラーハンドリング

| エラー | 原因 | 対処 |
|--------|------|------|
| `npx: command not found` | Volta PATHが設定されていない | `.zshrc` に `export PATH="$HOME/.volta/bin:$PATH"` を追加し、`source ~/.zshrc` を実行 |
| `Error: Cannot find module` | marp-cliが初回実行 | 自動ダウンロードを待つ（初回は時間がかかる） |
| `Failed to launch browser` | Chromiumの問題（PDF生成時） | `--no-sandbox` オプションを追加 |
| `ENOENT` | 入力ファイルが見つからない | ファイルパスを確認 |
| `Invalid Marp document` | Marp frontmatterがない | ファイル先頭に `marp: true` を追加 |

## 6) 実行結果をユーザーに報告する（必須）

### 出力テンプレート

```text
Export 完了

入力ファイル: {input_file}
出力ファイル: {output_file}
フォーマット: {format}

---
次のステップ

生成されたファイルを確認してください。
- PPTX: PowerPointで開いて確認
- PDF: PDFビューアで確認
- HTML: ブラウザで開いて確認
```

### 生成ルール（必須）

- `{input_file}` と `{output_file}` は **実在するパス** に合わせる。
- `{format}` は実際に使用した形式（pptx/pdf/html）を記載する。
- エラーが発生した場合は、エラーハンドリング表を参照して対処法を提示する。

## Tips

- **画像を含むスライド**: `--allow-local-files` オプションでローカル画像を参照可能
- **カスタムテーマ**: `--theme` オプションでテーマを指定可能
- **複数ファイル**: ディレクトリを指定して一括変換も可能
- **初回実行**: marp-cliのダウンロードに時間がかかる場合がある
