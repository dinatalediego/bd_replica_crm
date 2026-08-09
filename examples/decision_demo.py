from pathlib import Path

from replica_cygnus.decision_intelligence.demo import run_demo

if __name__ == "__main__":
    path = run_demo(Path("reports/decision_demo.csv"))
    print(f"Demo creada en: {path}")
