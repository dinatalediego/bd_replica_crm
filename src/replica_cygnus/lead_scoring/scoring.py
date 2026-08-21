from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import LeadScoringConfig
from .registry import DECISION_SYSTEM, MODEL_NAME, serving_model
from .training import MODEL_FEATURES, load_artifact


def _read_scoring_frame(conn, score_window_days: int) -> pd.DataFrame:
    columns = ", ".join(["evidence_key","lead_id","decision_at","documento_cliente","codigo_proyecto","asesor","canal","medio",
                         *[f for f in MODEL_FEATURES if f not in {"codigo_proyecto","asesor","canal","medio"}]])
    with conn.cursor() as cursor:
        cursor.execute(f"""SELECT {columns} FROM features.lead_evidence
          WHERE decision_at >= current_date - (%s * interval '1 day') AND features_refreshed_at IS NOT NULL
          ORDER BY decision_at,evidence_key""",(score_window_days,))
        rows=cursor.fetchall(); names=[item.name for item in cursor.description or []]
    return pd.DataFrame(rows,columns=names)


def _priority_bands(scores: pd.Series) -> tuple[pd.Series,pd.Series]:
    n=len(scores)
    if n == 0:
        return pd.Series(dtype="int64"),pd.Series(dtype="object")
    rank=scores.rank(method="first",ascending=False).astype(int)
    pct=rank/float(n)
    band=np.select([pct<=0.20,pct<=0.50,pct<=0.80],["A","B","C"],default="D")
    return rank,pd.Series(band,index=scores.index,dtype="object")


def score_current_leads(conn, cfg: LeadScoringConfig, project_root: Path) -> dict[str,Any]:
    serving=serving_model(conn)
    artifact=load_artifact(project_root,serving["artifact_uri"])
    frame=_read_scoring_frame(conn,cfg.score_window_days)
    if frame.empty:
        return {"rows_scored":0,"model_run_id":serving["model_run_id"],"model_version":serving["model_version"],"status":"NO_ROWS"}
    p_sep=artifact["sep_model"].predict_probability(frame)
    p_minuta=artifact["minuta_model"].predict_probability(frame)
    priority_score=(100.0*(artifact["weight_sep"]*p_sep+artifact["weight_minuta"]*p_minuta)).clip(0.0,100.0)
    frame=frame.copy(); frame["p_sep_14d"]=p_sep; frame["p_minuta_60d"]=p_minuta; frame["priority_score"]=priority_score
    frame["decision_date"]=pd.to_datetime(frame["decision_at"],utc=True).dt.date
    frame["priority_rank"]=0; frame["priority_band"]=""
    for _,idx in frame.groupby("decision_date").groups.items():
        day_rank,day_band=_priority_bands(frame.loc[idx,"priority_score"])
        frame.loc[idx,"priority_rank"]=day_rank; frame.loc[idx,"priority_band"]=day_band
    frame["priority_rank"]=frame["priority_rank"].astype(int)
    batch_id=str(uuid.uuid4()); scored_at=datetime.now(timezone.utc); provisional=serving["status"] != "CHAMPION"
    records=[]
    for row in frame.to_dict(orient="records"):
        records.append((str(uuid.uuid4()),row["evidence_key"],row["lead_id"],row["decision_at"],scored_at,serving["model_run_id"],
                        float(row["p_sep_14d"]),float(row["p_minuta_60d"]),float(row["priority_score"]),int(row["priority_rank"]),
                        str(row["priority_band"]),bool(provisional),json.dumps({"semantics":"PROPENSITY_NOT_UPLIFT",
                        "codigo_proyecto":row.get("codigo_proyecto"),"asesor":row.get("asesor"),"canal":row.get("canal"),"medio":row.get("medio"),
                        "weights":{"sep":artifact["weight_sep"],"minuta":artifact["weight_minuta"]}},ensure_ascii=False)))
    with conn.cursor() as cursor:
        cursor.executemany("""INSERT INTO decision_intelligence.lead_scores
          (score_id,evidence_key,lead_id,decision_at,scored_at,model_run_id,p_separacion_14d,p_minuta_60d,priority_score,
           priority_rank,priority_band,is_provisional,context_json)
          VALUES (%s::uuid,%s,%s,%s,%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb)
          ON CONFLICT (evidence_key,model_run_id) DO UPDATE SET scored_at=EXCLUDED.scored_at,
           p_separacion_14d=EXCLUDED.p_separacion_14d,p_minuta_60d=EXCLUDED.p_minuta_60d,
           priority_score=EXCLUDED.priority_score,priority_rank=EXCLUDED.priority_rank,priority_band=EXCLUDED.priority_band,
           is_provisional=EXCLUDED.is_provisional,context_json=EXCLUDED.context_json""",records)
        cursor.execute("""INSERT INTO model_control.scoring_batches
          (scoring_batch_id,model_run_id,decision_system,model_name,model_version,scored_at,data_as_of,rows_scored,status,
           drift_score,drift_status,metrics,notes)
          VALUES (%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,'SUCCESS',NULL,'NOT_EVALUATED_V0',%s::jsonb,%s)""",
          (batch_id,serving["model_run_id"],DECISION_SYSTEM,MODEL_NAME,serving["model_version"],scored_at,
           pd.to_datetime(frame["decision_at"],utc=True).max().to_pydatetime(),len(frame),json.dumps({
             "priority_score_mean":float(frame["priority_score"].mean()),"priority_score_p50":float(frame["priority_score"].median()),
             "priority_score_p90":float(frame["priority_score"].quantile(0.90)),"band_A_rows":int((frame["priority_band"]=="A").sum()),
             "p_sep_mean":float(frame["p_sep_14d"].mean()),"p_minuta_mean":float(frame["p_minuta_60d"].mean())}),
           "Score de propensión para priorización; no estima uplift causal."))
    conn.commit()
    latest=frame["decision_date"].max()
    top=frame.loc[frame["decision_date"]==latest,["lead_id","decision_at","codigo_proyecto","asesor","p_sep_14d","p_minuta_60d",
                                                    "priority_score","priority_rank","priority_band"]].sort_values("priority_rank").head(20)
    return {"rows_scored":int(len(frame)),"model_run_id":serving["model_run_id"],"model_version":serving["model_version"],
            "status":"PROVISIONAL" if provisional else "CHAMPION","batch_id":batch_id,"top_leads":top.to_dict(orient="records")}
