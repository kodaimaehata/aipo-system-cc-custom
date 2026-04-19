"""miro_flow_maker パッケージのエントリポイント。

Usage:
    python -m miro_flow_maker <mode> [options]

T001 仕様の概念的構造に従う最小実装。
"""

from __future__ import annotations

import sys
import logging

from miro_flow_maker.cli import parse_args, build_request_context
from miro_flow_maker.config import load_config
from miro_flow_maker.core import dispatch
from miro_flow_maker.exceptions import MiroFlowMakerError

logger = logging.getLogger("miro_flow_maker")


def main() -> int:
    """メインエントリポイント。終了コードを返す。"""
    try:
        args = parse_args()

        # Configure logging
        selected_level = args.log_level or ("DEBUG" if args.verbose else "INFO")
        log_level = getattr(logging, selected_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        logger.info("miro_flow_maker starting — mode=%s", args.mode)

        config = load_config(args.env_file)
        context = build_request_context(args, config)
        result = dispatch(args.mode, args.input, config, context)
        return 0 if result.success else 4

    except MiroFlowMakerError as e:
        logger.error("%s: %s", type(e).__name__, e)
        return e.exit_code

    except NotImplementedError as e:
        # Stub functions raise NotImplementedError during bootstrap phase
        logger.error("Not yet implemented: %s", e)
        print(f"[stub] {e}", file=sys.stderr)
        return 4

    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 4


if __name__ == "__main__":
    sys.exit(main())
