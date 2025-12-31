# Resources

## 技術スタック

### 推奨ライブラリ
- **python-pptx**: Pythonで最も成熟したPowerPoint操作ライブラリ
  - ドキュメント: https://python-pptx.readthedocs.io/
  - テンプレートベースの生成をサポート
  - スライドレイアウト、プレースホルダー、図形、表、グラフに対応

### 代替手法（検討済み）
- **pptx-template**: Jinja2ライクなプレースホルダー方式
- **pptx-renderer**: ノートにPythonコードを埋め込む方式
- **HTML→変換**: デザイン自由度は高いが変換ロスあり

## 参考リソース
- [python-pptx Concepts](https://python-pptx.readthedocs.io/en/latest/user/concepts.html)
- [Working with Presentations](https://python-pptx.readthedocs.io/en/latest/user/presentations.html)
- [Practical Business Python - Creating PowerPoint](https://pbpython.com/creating-powerpoint.html)

## 既存のClaude Code Skills
- `.claude/skills/` ディレクトリにAIPO関連スキルが存在
- 命名規則: kebab-case、小文字、64文字以内
