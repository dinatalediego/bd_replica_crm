from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.economic_intelligence import install_feature_mart, load_monthly_panel


def main() -> int:
    print("[1/2] Instalando feature mart de Economic Intelligence...")
    install_feature_mart()
    print("[2/2] Validando panel mensual...")
    panel = load_monthly_panel()
    if panel.empty:
        raise RuntimeError("analytics.v_econ_project_monthly_features quedó sin filas.")
    print(f"OK: {len(panel):,} project-months | {panel['proyecto'].nunique()} proyectos | {panel['periodo_mes'].min():%Y-%m} -> {panel['periodo_mes'].max():%Y-%m}")
    print("Siguiente: notebooks/economic_intelligence/00_contrato_y_auditoria.ipynb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
