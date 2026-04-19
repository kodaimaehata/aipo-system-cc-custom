"""公開データモデル定義。

全モジュールが共有する型定義。実装ロジックを持たない。
T001 仕様書に準拠。
"""

from __future__ import annotations

from dataclasses import dataclass, field

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


# ---------------------------------------------------------------------------
# Helper: token masking
# ---------------------------------------------------------------------------

def _mask_token(token: str) -> str:
    """トークンをマスクする。先頭 4 文字 + '***' の形式。"""
    if len(token) <= 4:
        return "***"
    return token[:4] + "***"


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """アプリケーション設定。.env と環境変数から読み込む。"""

    miro_access_token: str
    miro_api_base_url: str
    log_dir: str
    runner_id: str
    default_board_id: str | None
    dry_run_override: bool
    log_level: str

    def __post_init__(self) -> None:
        token = self.miro_access_token.strip()
        if not token:
            raise ValueError("miro_access_token must be a non-empty string")
        if self.log_level not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {self.log_level!r}"
            )
        if not isinstance(self.dry_run_override, bool):
            raise TypeError("dry_run_override must be a bool")

    # ----- repr: シークレットをマスク -----

    def __repr__(self) -> str:
        masked = _mask_token(self.miro_access_token)
        return (
            f"AppConfig("
            f"miro_access_token='{masked}', "
            f"miro_api_base_url='{self.miro_api_base_url}', "
            f"log_dir='{self.log_dir}', "
            f"runner_id='{self.runner_id}', "
            f"default_board_id={self.default_board_id!r}, "
            f"dry_run_override={self.dry_run_override!r}, "
            f"log_level='{self.log_level}'"
            f")"
        )

    # ----- ファクトリ: テスト用 -----

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AppConfig:
        """辞書から AppConfig を生成する。テストやプログラム的な構築に使用。

        キーは AppConfig フィールド名。省略可能なフィールドにはデフォルト値が適用される。
        ``miro_access_token`` は必須。
        """
        token = data["miro_access_token"]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("miro_access_token must be a non-empty string")

        def _optional_str(key: str) -> str | None:
            value = data.get(key)
            if value is None:
                return None
            if not isinstance(value, str):
                raise TypeError(f"{key} must be a string or None")
            stripped = value.strip()
            return stripped or None

        def _required_str(key: str, default: str) -> str:
            value = data.get(key, default)
            if not isinstance(value, str):
                raise TypeError(f"{key} must be a string")
            stripped = value.strip()
            if not stripped:
                raise ValueError(f"{key} must be a non-empty string")
            return stripped

        def _parse_bool(value: object) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, int) and value in (0, 1):
                return bool(value)
            if isinstance(value, str):
                normalised = value.strip().lower()
                if normalised in {"true", "1"}:
                    return True
                if normalised in {"false", "0"}:
                    return False
            raise ValueError(
                "dry_run_override must be a bool or one of 'true', 'false', '1', '0'"
            )

        return cls(
            miro_access_token=token.strip(),
            miro_api_base_url=_required_str("miro_api_base_url", "https://api.miro.com/v2"),
            log_dir=_required_str("log_dir", "./logs"),
            runner_id=_required_str("runner_id", "miro-flow-maker"),
            default_board_id=_optional_str("default_board_id"),
            dry_run_override=_parse_bool(data.get("dry_run_override", False)),
            log_level=_required_str("log_level", "INFO").upper(),
        )


# ---------------------------------------------------------------------------
# RequestContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestContext:
    """実行リクエストのコンテキスト情報。cli.py が生成し、全レイヤーに伝播する。"""

    mode: str
    """'create', 'update', 'append' のいずれか"""

    board_id: str | None
    """対象 board ID。create の場合は None"""

    frame_id: str | None
    """対象 frame ID。create の場合は None"""

    frame_link: str | None
    """対象 frame のリンク URL。frame_id が優先"""

    board_name: str | None
    """create 時の新規 board 名。create 以外では None"""

    dry_run: bool
    """True の場合、実書き込みせず検証のみ行う"""

    input_path: str
    """confirmed 入力 JSON ファイルへのパス"""

    auto_frame: bool = False
    """Stage 3 opt-in: append モードで frame 未指定時に board 上へ新規 frame を自動作成する"""

    auto_resize: bool = True
    """Stage 2B default on: append 時に既存 frame が content 収容不可であれば自動拡張する"""


# ---------------------------------------------------------------------------
# DocumentSet
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DocumentSet:
    """入力文書束の識別情報。document_set_id の source of truth。"""

    id: str
    """文書束の一意識別子。metadata.document_set_id の正規化元"""

    label: str
    """文書束の表示名"""


# ---------------------------------------------------------------------------
# NodeDef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NodeDef:
    """1 つの業務ノード定義。"""

    id: str
    """node_id。意味構造における一意識別子"""

    type: str
    """'start', 'process', 'decision', 'end' のいずれか"""

    label: str
    """ノードの表示文言"""

    actor_id: str
    """所属する actor の ID"""


# ---------------------------------------------------------------------------
# ConnectionDef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConnectionDef:
    """ノード間またはノード-システム間の接続定義。"""

    id: str
    """接続の一意識別子"""

    from_id: str
    """接続元の node_id"""

    to_id: str
    """接続先の node_id または system_id (system_access の場合)"""

    type: str
    """'business_flow' または 'system_access'"""

    label: str
    """接続ラベル。分岐条件、アクション名など"""

    # --- system_access 固有 (type='system_access' の場合) ---
    system_id: str | None = None
    """対象 system の ID。type='business_flow' の場合は None"""

    action: str | None = None
    """system_access のアクション名。type='business_flow' の場合は None"""


# ---------------------------------------------------------------------------
# LaneDef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaneDef:
    """actor lane または system lane の定義。"""

    id: str
    """actor_id または system_id"""

    type: str
    """'actor_lane' または 'system_lane'"""

    label: str
    """lane の表示名"""

    kind: str
    """actor_kind または system_kind"""


# ---------------------------------------------------------------------------
# ItemMetadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ItemMetadata:
    """ConfirmedInput に付随する管理 metadata。Miro item の aipo namespace に書き込む値の源泉。"""

    stable_item_id_prefix: str
    """flow_group_id。stable_item_id の先頭部分として使用する"""

    managed_by: str
    """管理主体の識別子。標準値は 'miro-flow-maker'"""

    update_mode: str
    """'managed' が標準。create/append で新規に付与する値"""

    project_id: str
    """AIPO project ID。例: 'P0006'"""

    layer_id: str
    """生成元 layer ID。例: 'P0006-SG2'"""

    document_set_id: str
    """入力文書束の ID。正規化時にトップレベルの document_set.id から自動取得する"""

    flow_group_id: str
    """業務フロー単位の ID"""


# ---------------------------------------------------------------------------
# SourceEvidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceEvidence:
    """confirmed 入力の根拠となるソースへの参照。"""

    ref: str
    """ソース文書またはセクションへの参照パス"""

    description: str
    """参照内容の要約"""


# ---------------------------------------------------------------------------
# ConfirmedInput
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfirmedInput:
    """review gate を通過した正規化済み入力。後続の mode handler はこの型だけを受け取る。"""

    # --- flow_group 識別 ---
    flow_group_id: str
    """業務フロー単位の ID。JSON 入力の flow_group.id から取得"""

    flow_group_label: str
    """業務フローの表示名。JSON 入力の flow_group.label から取得。create 時の frame 名等に使用"""

    # --- document_set ---
    document_set: DocumentSet
    """入力文書束の情報。トップレベルの document_set から取得"""

    # --- 構造化データ ---
    nodes: list[NodeDef]
    connections: list[ConnectionDef]
    lanes: list[LaneDef]

    # --- metadata ---
    metadata: ItemMetadata

    # --- 監査参照 ---
    confirmation_packet_ref: str
    source_evidence: list[SourceEvidence]

    # --- ユーザ確認フラグ ---
    confirmed_by_user: bool = True


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReviewResult:
    """review gate の検証結果。"""

    passed: bool
    """True なら Miro 反映へ進んでよい"""

    stop_reasons: list[str]
    """通過しなかった理由の一覧。passed=True の場合は空リスト"""

    normalized_input: ConfirmedInput | None
    """通過した場合、正規化済みの ConfirmedInput を返す。通過しなかった場合は None。"""


# ---------------------------------------------------------------------------
# ItemResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ItemResult:
    """item 単位の実行結果。"""

    stable_item_id: str
    semantic_type: str
    semantic_id: str
    render_role: str
    action: str
    """'create', 'update', 'reconnect', 'skip' のいずれか"""

    result: str
    """'success', 'failed', 'skipped_manual_detached', 'skipped_unmanaged', 'dry_run_skipped' のいずれか"""

    reason: str | None = None
    """失敗理由または未更新理由"""

    miro_item_id: str | None = None
    """SG3 追加: Miro API レスポンスの item id。create 成功時に記録する。

    dry-run / 失敗時 / SG2 以前の run log 形式では None。
    NOTE: SG2 既存 run log には miro_item_id が無い。
    T003 reconciler の backfill_miro_item_ids() で
    board item 一覧から content 照合により補完する。
    """


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

@dataclass  # frozen=True にしない: 実行中に created_count 等を段階的に更新するため mutable とする
class ExecutionResult:
    """mode handler の実行結果。run log の元データとなる。"""

    run_id: str
    """実行単位の一意識別子"""

    mode: str
    """実行モード"""

    success: bool
    """全体として成功したか"""

    board_id: str | None
    """反映先 board ID"""

    frame_id: str | None
    """反映先 frame ID"""

    flow_group_id: str
    """対象 flow_group_id"""

    dry_run: bool
    """dry-run 実行だったか"""

    created_count: int = 0
    """作成した item 数"""

    updated_count: int = 0
    """更新した item 数"""

    skipped_count: int = 0
    """スキップした item 数"""

    failed_count: int = 0
    """失敗した item 数"""

    stop_reasons: list[str] = field(default_factory=list)
    """停止理由。成功時は空リスト"""

    item_results: list[ItemResult] = field(default_factory=list)
    """item 単位の実行結果"""

    partial_success: bool = False
    """SG3 追加: 一部 item の反映は成功したが停止した場合に True。"""

    stopped_stage: str | None = None
    """SG3 追加: 停止した段階の識別子。

    例: 'resolve_board', 'resolve_frame', 'reconcile', 'upsert_shapes',
    'upsert_connectors'。停止しなかった場合は None。
    """

    rerun_eligible: bool = True
    """SG3 追加: 再実行しても安全か。

    connector 未解決で停止した場合は True、データ不整合で停止した場合は False。
    """
