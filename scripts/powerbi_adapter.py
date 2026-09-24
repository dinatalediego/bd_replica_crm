from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.powerbi_adapter import AdapterConfig, scan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detecta progreso Power BI y genera un plan de traducción hacia Medallio."
    )
    parser.add_argument("command", nargs="?", default="scan", choices=("scan",))
    parser.add_argument("--config", default="config/powerbi_adapter.yml")
    parser.add_argument(
        "--input",
        dest="input_path",
        help="PBIX/PBIT/PBIP o carpeta PBIP específica. Si se omite, toma la versión más reciente.",
    )
    args = parser.parse_args()

    config_path = (ROOT / args.config).resolve()
    config = AdapterConfig.from_yaml(config_path)
    if not config.state_dir.is_absolute():
        config = AdapterConfig(
            source_dir=config.source_dir,
            state_dir=(ROOT / config.state_dir).resolve(),
            pbi_tools_executable=config.pbi_tools_executable,
            keep_extracted=config.keep_extracted,
        )

    explicit_input = Path(args.input_path) if args.input_path else None
    if explicit_input and not explicit_input.is_absolute():
        explicit_input = (Path.cwd() / explicit_input).resolve()

    try:
        result = scan(config, explicit_input)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
