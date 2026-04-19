"""miro_flow_maker 共通定数モジュール。

handler / reconciler / run_log / tests が共有する ``action`` / ``result`` /
``stopped_stage`` の文字列リテラルを一箇所に集約する。

T008 (P2-B) で新設。互換性維持のため文字列値は既存のままとする（値を変えると
既存 run log や外部連携先の読み取りが壊れる）。

Python の ``Enum`` ではなく素朴な定数クラスを採用する理由:
- 既存コードは str 比較 / dict 値として参照しているため、クラス属性参照で
  そのまま置換できる方が差分が小さい
- JSON シリアライズで値がそのまま文字列として出力される
- 列挙値は頻繁に追加される想定ではないため、``Enum`` の型安全性は過剰

使用例::

    from miro_flow_maker._constants import ItemAction, ItemResultStatus

    if action == ItemAction.SKIP:
        result_status = ItemResultStatus.SKIPPED_FRAME_OUTSIDE
"""

from __future__ import annotations

__all__ = [
    "ItemAction",
    "ItemResultStatus",
    "SkipReason",
    "StoppedStage",
    "UpdateMode",
]


class ItemAction:
    """ReconcileAction.action および ItemResult.action の取りうる値。"""

    CREATE = "create"
    UPDATE = "update"
    SKIP = "skip"
    STOP = "stop"
    ORPHANED = "orphaned"


class ItemResultStatus:
    """ItemResult.result の取りうる値。"""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    """connector 等、reconciler 以前の段階で skip する場合に使用する汎用値。"""

    # reconciler 判定由来の skip 理由
    SKIPPED_MANUAL_DETACHED = "skipped_manual_detached"
    SKIPPED_UNMANAGED = "skipped_unmanaged"
    SKIPPED_FRAME_OUTSIDE = "skipped_frame_outside"
    SKIPPED_FLOW_GROUP_MISMATCH = "skipped_flow_group_mismatch"
    SKIPPED_ORPHANED = "skipped_orphaned"
    """orphaned item を ItemResult として記録する際の値。"""

    # 後続 stage 由来の skip 理由
    SKIPPED_CONNECTOR_DEPENDENCY = "skipped_connector_dependency"
    """connector の接続先 shape が skip 扱いのため connector も skip する場合。"""

    # dry-run
    DRY_RUN_SKIPPED = "dry_run_skipped"


class StoppedStage:
    """ExecutionResult.stopped_stage の取りうる値。"""

    RESOLVE_BOARD = "resolve_board"
    RESOLVE_FRAME = "resolve_frame"
    RECONCILE = "reconcile"
    UPSERT_SHAPES = "upsert_shapes"
    UPSERT_CONNECTORS = "upsert_connectors"
    FLOW_GROUP_COLLISION = "flow_group_collision"


class UpdateMode:
    """ItemMetadata.update_mode / ReconcileAction.update_mode の取りうる値。"""

    MANAGED = "managed"
    MANUAL_DETACHED = "manual_detached"
    UNMANAGED = "unmanaged"


class SkipReason:
    """ReconcileAction.skip_reason の取りうる値。

    reconciler 側で skip 判定を下した根拠を構造化してラベル付けする。
    従来は ``reason`` 文字列の部分一致で分類していたが、文言変更に脆弱だった
    ため、P2 指摘（新規 2 回目）で本フィールドを追加した。

    後段の ``update_handler._classify_skip_status`` は本値を参照して
    ``ItemResultStatus`` にマッピングする。値は JSON / run log 上での可読性を
    重視した snake_case 文字列とする。
    """

    # update_mode=manual_detached による保護（reconcile 時に判定）
    MANUAL_DETACHED = "manual_detached"
    # update_mode=unmanaged による保護（reconcile 時に判定）
    UNMANAGED = "unmanaged"
    # board 上で別 frame の子になっている場合
    FRAME_OUTSIDE = "frame_outside"
    # run log / plan 間で flow_group_id が一致しない場合
    FLOW_GROUP_MISMATCH = "flow_group_mismatch"
    # DrawingPlan から消えたが run log に残っている managed item
    ORPHANED = "orphaned"
