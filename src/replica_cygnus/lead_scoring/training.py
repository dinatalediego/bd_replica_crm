from __future__ import annotations

import json
import pickle
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from ..decision_intelligence.prediction import train_binary_logistic_model
from .config import LeadScoringConfig
from .metrics import baseline_bundle_metrics, binary_metrics, priority_metrics

NUMERIC_FEATURES = [
    "hour_of_day","day_of_week","is_weekend","client_prior_assignments_90d",
    "days_since_previous_assignment","project_leads_90d","project_sep_rate_90d",
    "project_minuta_rate_180d","advisor_leads_90d","advisor_sep_rate_90d",
    "advisor_minuta_rate_180d","global_sep_rate_90d","global_minuta_rate_180d",
]
CATEGORICAL_FEATURES = ["codigo_proyecto","asesor","canal","medio"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def _read_frame(conn, query: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
    with conn.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [item.name for item in cursor.description or []]
    return pd.DataFrame(rows, columns=columns)


def _load_target_frame(conn, target: str) -> pd.DataFrame:
    if target not in {"separacion_14d","minuta_60d"}:
        raise ValueError(f"Target no soportado: {target}")
    columns = ", ".join(["evidence_key","decision_at",*MODEL_FEATURES,target])
    return _read_frame(conn, f"""SELECT {columns} FROM features.lead_evidence
        WHERE {target} IS NOT NULL AND features_refreshed_at IS NOT NULL
        ORDER BY decision_at,evidence_key""")


def _load_common_frame(conn) -> pd.DataFrame:
    columns = ", ".join(["evidence_key","decision_at",*MODEL_FEATURES,"separacion_14d","minuta_60d"])
    return _read_frame(conn, f"""SELECT {columns} FROM features.lead_evidence
        WHERE separacion_14d IS NOT NULL AND minuta_60d IS NOT NULL
          AND features_refreshed_at IS NOT NULL ORDER BY decision_at,evidence_key""")


def temporal_split(frame: pd.DataFrame, validation_days: int, test_days: int) -> TemporalSplit:
    if frame.empty:
        raise ValueError("No hay evidencia para dividir temporalmente.")
    data = frame.copy()
    data["decision_at"] = pd.to_datetime(data["decision_at"], utc=True)
    data = data.sort_values(["decision_at","evidence_key"]).reset_index(drop=True)
    max_ts = data["decision_at"].max()
    test_start = max_ts - pd.Timedelta(days=test_days)
    validation_start = test_start - pd.Timedelta(days=validation_days)
    train = data[data["decision_at"] < validation_start].copy()
    validation = data[(data["decision_at"] >= validation_start) & (data["decision_at"] < test_start)].copy()
    test = data[data["decision_at"] >= test_start].copy()
    min_split = max(20, int(len(data) * 0.08))
    if min(len(train),len(validation),len(test)) < min_split:
        n = len(data)
        train_end = max(1, int(n * 0.65))
        validation_end = max(train_end + 1, int(n * 0.82))
        train, validation, test = data.iloc[:train_end].copy(), data.iloc[train_end:validation_end].copy(), data.iloc[validation_end:].copy()
    if min(len(train),len(validation),len(test)) == 0:
        raise ValueError("No fue posible construir train/validation/test temporal con evidencia suficiente.")
    return TemporalSplit(train, validation, test)


def _git_sha(project_root: Path) -> str | None:
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"], cwd=project_root, text=True,
                                       stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return None


def _artifact_path(project_root: Path, cfg: LeadScoringConfig, model_version: str) -> Path:
    base = Path(cfg.artifact_dir)
    if not base.is_absolute():
        base = project_root / base
    path = base / model_version / "lead_priority_bundle.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_uri(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def train_challenger(conn, cfg: LeadScoringConfig, project_root: Path) -> tuple[str, dict[str, Any]]:
    sep_frame, minuta_frame, common_frame = _load_target_frame(conn,"separacion_14d"), _load_target_frame(conn,"minuta_60d"), _load_common_frame(conn)
    for name, frame in (("separacion_14d",sep_frame),("minuta_60d",minuta_frame),("common_eval",common_frame)):
        if len(frame) < cfg.training_min_rows:
            raise RuntimeError(f"Evidencia insuficiente para {name}: {len(frame)} < {cfg.training_min_rows}.")
    sep_split = temporal_split(sep_frame,cfg.validation_days,cfg.test_days)
    minuta_split = temporal_split(minuta_frame,cfg.validation_days,cfg.test_days)
    common_split = temporal_split(common_frame,cfg.validation_days,cfg.test_days)
    sep_train = pd.concat([sep_split.train,sep_split.validation], ignore_index=True)
    minuta_train = pd.concat([minuta_split.train,minuta_split.validation], ignore_index=True)
    if sep_train["separacion_14d"].nunique() < 2 or minuta_train["minuta_60d"].nunique() < 2:
        raise RuntimeError("El train contiene una sola clase en al menos uno de los targets.")

    sep_model = train_binary_logistic_model(sep_train,"separacion_14d",NUMERIC_FEATURES,CATEGORICAL_FEATURES)
    minuta_model = train_binary_logistic_model(minuta_train,"minuta_60d",NUMERIC_FEATURES,CATEGORICAL_FEATURES)
    evaluation = common_split.test.copy()
    p_sep, p_minuta = sep_model.predict_probability(evaluation), minuta_model.predict_probability(evaluation)
    candidate = {"type":"CHALLENGER",
        "sep":binary_metrics(evaluation["separacion_14d"],p_sep,cfg.promotion.top_fraction),
        "minuta":binary_metrics(evaluation["minuta_60d"],p_minuta,cfg.promotion.top_fraction),
        "priority":priority_metrics(evaluation["separacion_14d"],evaluation["minuta_60d"],p_sep,p_minuta,
                                    cfg.weight_sep,cfg.weight_minuta,cfg.promotion.top_fraction)}
    sep_prev, minuta_prev = float(sep_train["separacion_14d"].mean()), float(minuta_train["minuta_60d"].mean())
    baseline = baseline_bundle_metrics(evaluation["separacion_14d"],evaluation["minuta_60d"],sep_prev,minuta_prev,
                                       cfg.weight_sep,cfg.weight_minuta,cfg.promotion.top_fraction)
    now = datetime.now(timezone.utc)
    model_run_id, model_version = str(uuid.uuid4()), now.strftime("leadscore-%Y%m%dT%H%M%SZ")
    path = _artifact_path(project_root,cfg,model_version)
    test_from, test_to = pd.to_datetime(evaluation["decision_at"],utc=True).min(), pd.to_datetime(evaluation["decision_at"],utc=True).max()
    metrics = {"candidate":candidate,"baseline":baseline,
               "common_test":{"from":test_from.isoformat(),"to":test_to.isoformat(),"rows":int(len(evaluation))}}
    parameters = {"algorithm":"logistic_regression_bundle","sep_horizon_days":cfg.sep_horizon_days,
                  "minuta_horizon_days":cfg.minuta_horizon_days,"weight_sep":cfg.weight_sep,"weight_minuta":cfg.weight_minuta,
                  "validation_days":cfg.validation_days,"test_days":cfg.test_days,"top_fraction":cfg.promotion.top_fraction,
                  "git_sha":_git_sha(project_root),"sep_training_prevalence":sep_prev,"minuta_training_prevalence":minuta_prev}
    artifact = {"format_version":1,"decision_system":"priorizacion_leads","model_name":"lead_priority_bundle",
                "model_run_id":model_run_id,"model_version":model_version,"trained_at":now.isoformat(),
                "numeric_features":NUMERIC_FEATURES,"categorical_features":CATEGORICAL_FEATURES,
                "weight_sep":cfg.weight_sep,"weight_minuta":cfg.weight_minuta,"sep_model":sep_model,"minuta_model":minuta_model,
                "metrics":metrics,"parameters":parameters}
    with path.open("wb") as fh:
        pickle.dump(artifact,fh,protocol=pickle.HIGHEST_PROTOCOL)
    with conn.cursor() as cursor:
        cursor.execute("""INSERT INTO model_control.model_runs
          (model_run_id,decision_system,model_name,model_version,trained_at,training_window_from,training_window_to,target,
           feature_list,metrics,parameters,artifact_uri,status)
          VALUES (%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,'CHALLENGER')""",
          (model_run_id,"priorizacion_leads","lead_priority_bundle",model_version,now,
           min(pd.to_datetime(sep_train["decision_at"],utc=True).min(),pd.to_datetime(minuta_train["decision_at"],utc=True).min()).to_pydatetime(),
           max(pd.to_datetime(sep_train["decision_at"],utc=True).max(),pd.to_datetime(minuta_train["decision_at"],utc=True).max()).to_pydatetime(),
           "separacion_14d+minuta_60d",json.dumps(MODEL_FEATURES),json.dumps(metrics),json.dumps(parameters),_artifact_uri(project_root,path)))
    conn.commit()
    return model_run_id, metrics


def load_artifact(project_root: Path, artifact_uri: str) -> dict[str, Any]:
    path = Path(artifact_uri)
    if not path.is_absolute():
        path = project_root / path
    with path.open("rb") as fh:
        artifact = pickle.load(fh)
    if artifact.get("format_version") != 1:
        raise RuntimeError("Versión de artifact no soportada.")
    return artifact


def load_evaluation_frame(conn, test_from: str, test_to: str) -> pd.DataFrame:
    columns = ", ".join(["evidence_key","decision_at",*MODEL_FEATURES,"separacion_14d","minuta_60d"])
    return _read_frame(conn, f"""SELECT {columns} FROM features.lead_evidence
      WHERE separacion_14d IS NOT NULL AND minuta_60d IS NOT NULL AND features_refreshed_at IS NOT NULL
        AND decision_at >= %s::timestamptz AND decision_at <= %s::timestamptz
      ORDER BY decision_at,evidence_key""", (test_from,test_to))
