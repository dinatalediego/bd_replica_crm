from __future__ import annotations

import numpy as np
import pandas as pd

from replica_cygnus.lead_scoring.config import LeadScoringConfig, PromotionConfig
from replica_cygnus.lead_scoring.metrics import baseline_bundle_metrics, binary_metrics, priority_metrics, promotion_gate
from replica_cygnus.lead_scoring.scoring import _priority_bands
from replica_cygnus.lead_scoring.training import temporal_split
from replica_cygnus.lead_scoring.feedback import (
    outcome_id_for_evidence,
    recommendation_id_for_score,
    recommended_action_for_band,
)


def test_temporal_split_preserves_order():
    n=300
    frame=pd.DataFrame({"evidence_key":[f"k{i:04d}" for i in range(n)],
                        "decision_at":pd.date_range("2025-01-01",periods=n,freq="D",tz="UTC"),"x":range(n)})
    split=temporal_split(frame,30,30)
    assert split.train["decision_at"].max()<split.validation["decision_at"].min()
    assert split.validation["decision_at"].max()<split.test["decision_at"].min()


def test_priority_bands_make_top_twenty_percent_a():
    rank,band=_priority_bands(pd.Series(np.arange(100,dtype=float)))
    assert (band=="A").sum()==20
    assert rank.min()==1
    assert band.iloc[-1]=="A"


def test_priority_metrics_reward_high_conversion_top():
    y_sep=pd.Series([1]*20+[0]*80); y_min=pd.Series([1]*10+[0]*90)
    p=pd.Series(np.linspace(1.0,0.0,100))
    m=priority_metrics(y_sep,y_min,p,p,0.55,0.45,0.20)
    assert m["sep_rate_top"]==1.0
    assert m["minuta_rate_top"]==0.5


def test_promotion_gate_can_pass_against_naive_baseline():
    rng=np.random.default_rng(42); n=1000; latent=rng.normal(size=n)
    p_sep=1/(1+np.exp(-(latent-0.5))); p_min=1/(1+np.exp(-(latent-1.5)))
    y_sep=rng.binomial(1,p_sep); y_min=rng.binomial(1,p_min)
    candidate={"type":"CHALLENGER","sep":binary_metrics(y_sep,p_sep,0.20),"minuta":binary_metrics(y_min,p_min,0.20),
               "priority":priority_metrics(y_sep,y_min,p_sep,p_min,0.55,0.45,0.20)}
    baseline=baseline_bundle_metrics(y_sep,y_min,float(np.mean(y_sep)),float(np.mean(y_min)),0.55,0.45,0.20)
    passed,reasons,_=promotion_gate(candidate,baseline,PromotionConfig(min_eval_rows=100,min_positive_sep=10,min_positive_minuta=5))
    assert passed,reasons


def test_weights_must_sum_one():
    cfg=LeadScoringConfig(weight_sep=0.7,weight_minuta=0.4)
    try:
        cfg.validate()
    except ValueError as exc:
        assert "sumar 1" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError")


def test_priority_band_maps_to_operational_action():
    assert recommended_action_for_band("A") == "CONTACTAR_PRIORIDAD_ALTA"
    assert recommended_action_for_band("B") == "CONTACTAR"
    assert recommended_action_for_band("C") == "NURTURE"
    assert recommended_action_for_band("D") == "NURTURE"


def test_feedback_identifiers_are_deterministic_and_distinct():
    assert recommendation_id_for_score("score-1") == recommendation_id_for_score("score-1")
    assert outcome_id_for_evidence("evidence-1", "separacion_14d") == outcome_id_for_evidence(
        "evidence-1", "separacion_14d"
    )
    assert outcome_id_for_evidence("evidence-1", "separacion_14d") != outcome_id_for_evidence(
        "evidence-1", "minuta_60d"
    )
