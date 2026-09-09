from __future__ import annotations

import argparse
import json

from replica_cygnus.settings import load_settings
from replica_cygnus.supervisory_agent import run_once


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cygnus supervisory agent: health -> online heartbeat -> supervised commands."
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Ask the online control plane to notify the supervisor after the heartbeat.",
    )
    args = parser.parse_args()

    result = run_once(load_settings(), notify=args.notify)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
