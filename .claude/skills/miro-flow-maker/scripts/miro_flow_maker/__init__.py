"""miro_flow_maker — Miro board flow maker for AIPO system.

Generates and updates Miro boards from confirmed workflow definitions.
"""

from __future__ import annotations

__version__ = "0.1.0"

from miro_flow_maker._constants import (
    ItemAction,
    ItemResultStatus,
    SkipReason,
    StoppedStage,
    UpdateMode,
)
from miro_flow_maker._frame_helpers import extract_frame_id_from_link
from miro_flow_maker.models import (
    ConfirmedInput,
    RequestContext,
    ReviewResult,
    AppConfig,
    ExecutionResult,
    NodeDef,
    ConnectionDef,
    LaneDef,
    ItemMetadata,
    SourceEvidence,
    DocumentSet,
)
from miro_flow_maker.gate import validate, build_stable_item_id
from miro_flow_maker.config import Config, load_config
from miro_flow_maker.core import dispatch
from miro_flow_maker.append_handler import AppendHandler
from miro_flow_maker.create_handler import CreateHandler
from miro_flow_maker.update_handler import UpdateHandler
from miro_flow_maker.cli import build_request_context
from miro_flow_maker.miro_client import MiroClient
from miro_flow_maker.layout import (
    FramePlan,
    LanePlan,
    NodePlan,
    EndpointPlan,
    SystemLabelPlan,
    ConnectorPlan,
    DrawingPlan,
    build_drawing_plan,
)
from miro_flow_maker.metadata_helper import (
    build_item_metadata,
    build_plan_metadata_map,
)
from miro_flow_maker.run_log import (
    RunLog,
    build_run_log,
    write_run_log,
    load_run_log,
    build_id_mapping_from_run_log,
    find_latest_run_log,
)
from miro_flow_maker.reconciler import (
    ReconcileAction,
    ReconcileResult,
    reconcile,
    backfill_miro_item_ids,
)

__all__ = [
    "__version__",
    # models
    "ConfirmedInput",
    "RequestContext",
    "ReviewResult",
    "AppConfig",
    "ExecutionResult",
    "NodeDef",
    "ConnectionDef",
    "LaneDef",
    "ItemMetadata",
    "SourceEvidence",
    "DocumentSet",
    "Config",
    # constants
    "ItemAction",
    "ItemResultStatus",
    "SkipReason",
    "StoppedStage",
    "UpdateMode",
    # frame helpers
    "extract_frame_id_from_link",
    # gate
    "validate",
    "build_stable_item_id",
    # config
    "load_config",
    # core
    "dispatch",
    # create_handler
    "CreateHandler",
    # update_handler
    "UpdateHandler",
    # append_handler
    "AppendHandler",
    # cli
    "build_request_context",
    # miro_client
    "MiroClient",
    # layout
    "FramePlan",
    "LanePlan",
    "NodePlan",
    "EndpointPlan",
    "SystemLabelPlan",
    "ConnectorPlan",
    "DrawingPlan",
    "build_drawing_plan",
    # metadata_helper
    "build_item_metadata",
    "build_plan_metadata_map",
    # run_log
    "RunLog",
    "build_run_log",
    "write_run_log",
    "load_run_log",
    "build_id_mapping_from_run_log",
    "find_latest_run_log",
    # reconciler
    "ReconcileAction",
    "ReconcileResult",
    "reconcile",
    "backfill_miro_item_ids",
]
