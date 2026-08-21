from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

from .config import PromotionConfig


def precision_at_fraction(y_true, scores, fraction: float) -> float | None:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(scores, dtype=float)
    if len(y) == 0:
        return None
    n = max(1, int(math.ceil(len(y) * fraction)))
    order = np.argsort(-p, kind="mergesort")
    return float(np.mean(y[order[:n]]))


def binary_metrics(y_true, probabilities, top_fraction: float) -> dict[str, Any]:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    if len(y) != len(p):
        raise ValueError("y_true y probabilities deben tener la misma longitud.")
    if len(y) == 0:
        return {"n": 0, "positives": 0, "base_rate": None, "auc": None,
                "brier": None, "precision_top": None, "lift_top": None}
    base_rate = float(np.mean(y))
    auc = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else None
    brier = float(brier_score_loss(y, p))
    precision_top = precision_at_fraction(y, p, top_fraction)
    lift = float(precision_top / base_rate) if precision_top is not None and base_rate > 0 else None
    return {"n": int(len(y)), "positives": int(np.sum(y)), "base_rate": base_rate,
            "auc": auc, "brier": brier, "precision_top": precision_top, "lift_top": lift}


def priority_metrics(y_sep, y_minuta, p_sep, p_minuta, weight_sep: float,
                     weight_minuta: float, top_fraction: float) -> dict[str, Any]:
    sep = np.asarray(y_sep, dtype=int)
    minuta = np.asarray(y_minuta, dtype=int)
    ps = np.asarray(p_sep, dtype=float)
    pm = np.asarray(p_minuta, dtype=float)
    if not (len(sep) == len(minuta) == len(ps) == len(pm)):
        raise ValueError("Todas las series deben tener igual longitud.")
    if len(sep) == 0:
        return {"n": 0, "sep_rate_top": None, "minuta_rate_top": None,
                "priority_score_mean": None, "priority_score_p90": None}
    score = weight_sep * ps + weight_minuta * pm
    n_top = max(1, int(math.ceil(len(score) * top_fraction)))
    top_idx = np.argsort(-score, kind="mergesort")[:n_top]
    return {"n": int(len(score)), "sep_rate_top": float(np.mean(sep[top_idx])),
            "minuta_rate_top": float(np.mean(minuta[top_idx])),
            "priority_score_mean": float(np.mean(score)),
            "priority_score_p90": float(np.quantile(score, 0.90))}


def baseline_bundle_metrics(y_sep, y_minuta, sep_prevalence: float,
                            minuta_prevalence: float, weight_sep: float,
                            weight_minuta: float, top_fraction: float) -> dict[str, Any]:
    sep = np.asarray(y_sep, dtype=int)
    minuta = np.asarray(y_minuta, dtype=int)
    p_sep = np.repeat(float(sep_prevalence), len(sep))
    p_minuta = np.repeat(float(minuta_prevalence), len(minuta))
    result = {
        "type": "NAIVE_PREVALENCE",
        "sep": binary_metrics(sep, p_sep, top_fraction),
        "minuta": binary_metrics(minuta, p_minuta, top_fraction),
        "priority": priority_metrics(sep, minuta, p_sep, p_minuta,
                                     weight_sep, weight_minuta, top_fraction),
    }
    result["priority"]["sep_rate_top"] = float(np.mean(sep)) if len(sep) else None
    result["priority"]["minuta_rate_top"] = float(np.mean(minuta)) if len(minuta) else None
    return result


def _delta(candidate, comparator):
    if candidate is None or comparator is None:
        return None
    return float(candidate - comparator)


def promotion_gate(candidate: dict[str, Any], comparator: dict[str, Any],
                   cfg: PromotionConfig) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    sep, minuta, priority = candidate["sep"], candidate["minuta"], candidate["priority"]
    comp_sep, comp_minuta, comp_priority = comparator["sep"], comparator["minuta"], comparator["priority"]

    if int(priority.get("n") or 0) < cfg.min_eval_rows:
        reasons.append(f"muestra común insuficiente: {priority.get('n')} < {cfg.min_eval_rows}")
    if int(sep.get("positives") or 0) < cfg.min_positive_sep:
        reasons.append(f"positivos separación insuficientes: {sep.get('positives')} < {cfg.min_positive_sep}")
    if int(minuta.get("positives") or 0) < cfg.min_positive_minuta:
        reasons.append(f"positivos minuta insuficientes: {minuta.get('positives')} < {cfg.min_positive_minuta}")

    for name, cand, comp in (("AUC separación", sep.get("auc"), comp_sep.get("auc")),
                             ("AUC minuta", minuta.get("auc"), comp_minuta.get("auc"))):
        if cand is not None and comp is not None and cand < comp - cfg.max_auc_drop:
            reasons.append(f"{name} cae más de tolerancia: {cand:.4f} vs {comp:.4f}")
    for name, cand, comp in (("Brier separación", sep.get("brier"), comp_sep.get("brier")),
                             ("Brier minuta", minuta.get("brier"), comp_minuta.get("brier"))):
        if cand is not None and comp is not None and cand > comp + cfg.max_brier_increase:
            reasons.append(f"{name} empeora más de tolerancia: {cand:.4f} vs {comp:.4f}")
    for name, cand, comp in (("Top-rate separación", priority.get("sep_rate_top"), comp_priority.get("sep_rate_top")),
                             ("Top-rate minuta", priority.get("minuta_rate_top"), comp_priority.get("minuta_rate_top"))):
        if cand is not None and comp is not None and cand < comp - cfg.max_top_rate_drop:
            reasons.append(f"{name} cae más de tolerancia: {cand:.4f} vs {comp:.4f}")

    improvements = [
        _delta(priority.get("sep_rate_top"), comp_priority.get("sep_rate_top")),
        _delta(priority.get("minuta_rate_top"), comp_priority.get("minuta_rate_top")),
        _delta(comp_sep.get("brier"), sep.get("brier")),
        _delta(comp_minuta.get("brier"), minuta.get("brier")),
    ]
    if not any(v is not None and v >= cfg.min_material_improvement for v in improvements):
        reasons.append("el challenger no muestra una mejora material en top-rate o calibración")
    details = {"candidate": candidate, "comparator": comparator,
               "improvements": {"sep_rate_top_delta": improvements[0],
                                "minuta_rate_top_delta": improvements[1],
                                "sep_brier_improvement": improvements[2],
                                "minuta_brier_improvement": improvements[3]}}
    return len(reasons) == 0, reasons, details
