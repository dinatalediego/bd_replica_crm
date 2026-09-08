from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.lead_scoring.config import load_lead_scoring_config
from replica_cygnus.lead_scoring.evidence import capture_evidence, refresh_historical_features, refresh_labels
from replica_cygnus.lead_scoring.feedback import (
    measurement_summary,
    refresh_outcomes,
    register_action,
    sync_recommendations,
)
from replica_cygnus.lead_scoring.registry import approve_promotion, evaluate_challenger, model_status
from replica_cygnus.lead_scoring.schema import ensure_lead_scoring
from replica_cygnus.lead_scoring.scoring import score_current_leads
from replica_cygnus.lead_scoring.training import train_challenger
from replica_cygnus.settings import load_settings


def _parser():
    p=argparse.ArgumentParser(description="Medallio Lead Scoring: evidence -> challenger -> gate -> serving -> score")
    p.add_argument("--config",default="config/lead_scoring.yml")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("init")
    cap=sub.add_parser("capture"); cap.add_argument("--mode",choices=["live","backfill"],default="live")
    sub.add_parser("live")
    train=sub.add_parser("train"); train.add_argument("--evaluate",action="store_true")
    ev=sub.add_parser("evaluate"); ev.add_argument("--model-run-id",required=True)
    pr=sub.add_parser("promote"); pr.add_argument("--model-run-id",required=True); pr.add_argument("--approved-by",required=True)
    sub.add_parser("score")
    sub.add_parser("recommend")
    action=sub.add_parser("action")
    action.add_argument("--recommendation-id",required=True)
    action.add_argument("--taken",required=True)
    action.add_argument("--owner",required=True)
    action.add_argument("--cost",type=float,default=0.0)
    action.add_argument("--notes")
    sub.add_parser("outcomes")
    sub.add_parser("measure")
    cyc=sub.add_parser("cycle"); cyc.add_argument("--capture-mode",choices=["live","backfill"],default="live")
    sub.add_parser("status")
    return p


def _config_path(root: Path,value: str)->Path:
    path=Path(value); path=path if path.is_absolute() else root/path
    if path.exists(): return path
    example=root/"config"/"lead_scoring.example.yml"
    path.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(example,path)
    print(f"Configuración local creada: {path}"); return path


def _refresh(conn,cfg,mode):
    return {"captured_or_refreshed":capture_evidence(conn,cfg,mode),
            "labels_refreshed":refresh_labels(conn,cfg),
            "features_refreshed":refresh_historical_features(conn,cfg)}


def _print_eval(r):
    print(f"Gate: {'PASS' if r['passed'] else 'FAIL'} | decision={r['decision']} | candidate={r['candidate_model_run_id']}")
    for reason in r["reasons"]: print(f"  - {reason}")
    c=r["details"]["candidate"]
    print(f"  AUC sep={c['sep'].get('auc')} | Brier sep={c['sep'].get('brier')} | AUC minuta={c['minuta'].get('auc')} | Brier minuta={c['minuta'].get('brier')}")
    print(f"  Top20%: sep={c['priority'].get('sep_rate_top')} | minuta={c['priority'].get('minuta_rate_top')}")


def _score(conn,cfg,root):
    r=score_current_leads(conn,cfg,root)
    print(f"Scoring: {r['rows_scored']} leads | modelo={r['model_version']} | estado={r['status']}")
    for row in r.get("top_leads",[])[:10]:
        print(f"  #{row['priority_rank']:>2} lead={row['lead_id']} score={row['priority_score']:.1f} Psep={row['p_sep_14d']:.3f} Pminuta={row['p_minuta_60d']:.3f} band={row['priority_band']}")
    return r


def _close_feedback_loop(conn,cfg):
    recommendations=sync_recommendations(conn)
    outcomes=refresh_outcomes(conn,cfg)
    print(f"Feedback: recomendaciones={recommendations} | outcomes_maduros={outcomes}")


def main(argv=None):
    args=_parser().parse_args(argv); settings=load_settings(); root=settings.project_root
    cfg=load_lead_scoring_config(_config_path(root,args.config))
    with connect_postgres(settings) as conn:
        ensure_lead_scoring(conn,root)
        if args.command=="init": print("Lead Scoring inicializado."); return 0
        if args.command=="capture": print(json.dumps(_refresh(conn,cfg,args.mode),ensure_ascii=False)); return 0
        if args.command=="live":
            print(json.dumps(_refresh(conn,cfg,"live"),ensure_ascii=False)); _score(conn,cfg,root); _close_feedback_loop(conn,cfg); return 0
        if args.command=="train":
            run_id,metrics=train_challenger(conn,cfg,root); print(f"Challenger registrado: {run_id} | test={metrics['common_test']['rows']}")
            if args.evaluate: _print_eval(evaluate_challenger(conn,cfg,root,run_id))
            return 0
        if args.command=="evaluate":
            r=evaluate_challenger(conn,cfg,root,args.model_run_id); _print_eval(r); return 0 if r["passed"] else 1
        if args.command=="promote":
            r=approve_promotion(conn,args.model_run_id,args.approved_by); print(f"Promovido a CHAMPION: {r['model_version']} | aprobado_por={r['approved_by']}"); return 0
        if args.command=="score": _score(conn,cfg,root); return 0
        if args.command=="recommend": print(f"Recomendaciones sincronizadas: {sync_recommendations(conn)}"); return 0
        if args.command=="action":
            action_id=register_action(conn,args.recommendation_id,args.taken,args.owner,args.cost,args.notes)
            print(f"Acción registrada: {action_id}"); return 0
        if args.command=="outcomes": print(f"Outcomes sincronizados: {refresh_outcomes(conn,cfg)}"); return 0
        if args.command=="measure":
            rows=measurement_summary(conn)
            print(json.dumps(rows,ensure_ascii=False,default=str,indent=2)); return 0
        if args.command=="cycle":
            print("Evidencia:",json.dumps(_refresh(conn,cfg,args.capture_mode),ensure_ascii=False))
            run_id,metrics=train_challenger(conn,cfg,root); print(f"Challenger: {run_id} | common_test_rows={metrics['common_test']['rows']}")
            r=evaluate_challenger(conn,cfg,root,run_id); _print_eval(r)
            try: _score(conn,cfg,root); _close_feedback_loop(conn,cfg)
            except RuntimeError as exc: print(f"Scoring omitido: {exc}")
            return 0 if r["passed"] else 1
        if args.command=="status":
            with conn.cursor() as cur:
                cur.execute("""SELECT COUNT(*),COUNT(*) FILTER (WHERE evidence_source='LIVE'),
                  COUNT(*) FILTER (WHERE separacion_14d IS NOT NULL),COUNT(*) FILTER (WHERE minuta_60d IS NOT NULL),
                  MAX(decision_at),MAX(features_refreshed_at) FROM features.lead_evidence"""); row=cur.fetchone()
            print(f"Evidencia | total={row[0]} live={row[1]} sep_matured={row[2]} minuta_matured={row[3]} latest={row[4]} features={row[5]}")
            for run_id,version,trained,status,aliases in model_status(conn): print(f"  {version} | {status} | aliases={aliases or '-'} | run={run_id} | trained={trained}")
            return 0
    return 0


if __name__=="__main__": raise SystemExit(main())
