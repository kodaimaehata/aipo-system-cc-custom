# Constraints

## 技術的制約
- Claude CodeのSkill仕様に準拠する必要がある
  - SKILL.md frontmatter形式（name, description必須）
  - kebab-case命名規則
- Pythonランタイムが利用可能であること（python-pptx使用のため）
- テンプレート.pptxファイルのパスをユーザーが指定できること

## 機能要件
- 既存テンプレートのデザイン（マスタースライド、レイアウト、スタイル）を維持
- テキスト、表、画像の差し替えに対応
- 日本語テキストの正常表示

## 品質要件
- 生成されたPowerPointがMicrosoft PowerPoint、Google Slides、Keynoteで開けること
- エラー時に分かりやすいメッセージを表示

## 制限事項
- アニメーション・トランジションの動的生成は対象外（テンプレートに含まれるものは維持）
- 動画埋め込みは対象外
