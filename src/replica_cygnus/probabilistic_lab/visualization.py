from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def savefig(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    return path


def plot_conversion_rate(rate: float, path: Path) -> Path:
    plt.figure(figsize=(7, 4.2))
    plt.bar(["No venta", "Venta"], [1 - rate, rate])
    plt.ylim(0, 1)
    plt.ylabel("Probabilidad observada")
    plt.title("Bernoulli: desenlace de un ciclo comercial cerrado")
    return savefig(path)


def plot_bayesian_groups(summary: pd.DataFrame, path: Path, top_n: int = 12) -> Path:
    d = summary.sort_values("n", ascending=False).head(top_n).sort_values("posterior_mean")
    plt.figure(figsize=(8, 5))
    plt.errorbar(
        d["posterior_mean"],
        d["group"],
        xerr=[
            d["posterior_mean"] - d["ci_low"],
            d["ci_high"] - d["posterior_mean"],
        ],
        fmt="o",
        capsize=3,
    )
    plt.xlabel("Probabilidad posterior de venta")
    plt.title("Bayes: media posterior e intervalo creíble 95%")
    return savefig(path)


def plot_survival(curve: pd.DataFrame, path: Path) -> Path:
    plt.figure(figsize=(7.5, 4.5))
    plt.step(curve["day"], curve["survival"], where="post")
    plt.ylim(0, 1.02)
    plt.xlabel("Días desde separación")
    plt.ylabel("P(T > t)")
    plt.title("Supervivencia empírica hasta un desenlace")
    return savefig(path)


def plot_calibration(prob_true, prob_pred, path: Path, label: str) -> Path:
    plt.figure(figsize=(6, 5))
    plt.plot([0, 1], [0, 1], linestyle="--", label="Calibración perfecta")
    plt.plot(prob_pred, prob_true, marker="o", label=label)
    plt.xlabel("Probabilidad predicha")
    plt.ylabel("Frecuencia observada")
    plt.title("Curva de calibración")
    plt.legend()
    return savefig(path)


def plot_mixture(df: pd.DataFrame, path: Path) -> Path:
    plt.figure(figsize=(7, 5))
    plt.scatter(
        df["days_stock_to_separation"],
        df["separation_month"],
        c=df["cluster"],
        s=22,
        alpha=0.7,
    )
    plt.xlabel("Días stock → separación")
    plt.ylabel("Mes de separación")
    plt.title("Gaussian Mixture: perfiles latentes")
    return savefig(path)
