# Layer Directory Resolution（AIPO共通ルール）

目的: フェーズ実行（Sense/Focus/Discover/Deliver）時に **対象レイヤー（= `layer.yaml` を含むフォルダ）** を一意に決める。

## 優先順位

1. **ユーザー指定のパス**があれば最優先で使う
   - 条件: 指定フォルダに `layer.yaml` が存在すること
2. それ以外で、**カレントディレクトリ**に `layer.yaml` があればそこを使う
3. それ以外は `programs/` 配下を探索して候補を列挙する
   - `programs/{project}/` 直下だけでなく `sublayers/**/layer.yaml` も含む
4. 候補が複数ある場合は、**ユーザーに選択**させる
   - 選択基準（例）: project_name / layer_id / layer_name / 目的（goal.description）
5. `Flow/` はこのリポジトリではレガシー扱い
   - ユーザーが明示した場合のみ扱う

## 最小チェック（安全策）

- ルートと判断したフォルダに `layer.yaml` が存在すること
- `context.yaml` / `tasks.yaml` が無い場合は、どのフェーズの前提かを確認してから生成/更新する

