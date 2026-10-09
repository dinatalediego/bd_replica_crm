from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings

VERSION = "2.9.2.1"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def relation_exists(cur, rel: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (rel,))
    return cur.fetchone()[0] is not None


def install_schema(root: Path, conn):
    sql_path = root / "sql" / "111_project_milestones_deadline_policy" / "01_project_milestones_deadline_policy.sql"
    with conn.cursor() as cur:
        cur.execute(sql_path.read_text(encoding="utf-8"), prepare=False)
    conn.commit()


def band_for(days: int) -> str:
    if days < 0:
        return "PAST_PRELIMINARY_DATE"
    if days <= 30:
        return "CRITICAL"
    if days <= 90:
        return "LATE"
    if days <= 180:
        return "MID"
    return "EARLY"


def sync_milestones(root: Path, conn):
    cfg = load_json(root / "config" / "project_milestones_v2921.json")
    with conn.cursor() as cur:
        for p in cfg["projects"]:
            cur.execute(
                """
                INSERT INTO analytics.project_milestone_v2921(
                    project_key, project_name, preliminary_delivery_date,
                    delivery_status, source_type, source_note, loaded_at
                )
                VALUES(%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT(project_key) DO UPDATE SET
                    project_name=EXCLUDED.project_name,
                    preliminary_delivery_date=EXCLUDED.preliminary_delivery_date,
                    delivery_status=EXCLUDED.delivery_status,
                    source_type=EXCLUDED.source_type,
                    source_note=EXCLUDED.source_note,
                    loaded_at=now()
                """,
                (
                    p["project_key"],
                    p["project_name"],
                    p["preliminary_delivery_date"],
                    p.get("delivery_status") or "PRELIMINARY",
                    cfg["source"]["type"],
                    cfg["source"]["note"],
                )
            )
    conn.commit()


def calculate(root: Path, conn, as_of: date | None = None):
    as_of = as_of or date.today()
    milestones = load_json(root / "config" / "project_milestones_v2921.json")
    policy = load_json(root / "config" / "deadline_policy_v2921.json")
    routes = load_json(root / "config" / "contract_routes_v292.json")
    defaults = load_json(root / "config" / "contract_measurement_defaults_v2921.json")

    bands = {x["band"]: x for x in policy["schedule_bands"]}
    route_map = routes["projects"]

    results = []

    with conn.cursor() as cur:
        for p in milestones["projects"]:
            dd = date.fromisoformat(p["preliminary_delivery_date"])
            days = (dd - as_of).days
            band = band_for(days)
            bc = bands[band]
            key = p["project_key"]

            row = {
                "project_key": key,
                "project_name": p["project_name"],
                "preliminary_delivery_date": dd.isoformat(),
                "days_to_preliminary_delivery": days,
                "schedule_band": band,
                "milestone_status_review_required": days < 0,
                "new_experiment_allowed_by_schedule": bool(bc["new_experiment_allowed"]),
                "default_outcome_window_days": int(bc["default_outcome_window_days"]),
                "route_status": None,
                "recommended_deadline_type": None,
                "recommended_deadline": None,
                "next_deliverable": None,
                "recommendation_reason": bc["reason"],
            }

            if key in route_map:
                route = route_map[key]
                route_status = route["route_status"]
                rule = policy["route_deadline_rules"][route_status]
                sla_days = int(bc[rule["sla_field"]])

                row["route_status"] = route_status
                row["recommended_deadline_type"] = rule["deadline_type"]
                row["recommended_deadline"] = (as_of + timedelta(days=sla_days)).isoformat()
                row["next_deliverable"] = route["next_deliverable"]
                row["recommendation_reason"] = (
                    f"{rule['description']} Schedule band={band}. {bc['reason']}"
                )

                cur.execute(
                    """
                    INSERT INTO decision_intelligence.project_deadline_recommendation_v2921(
                        project_key, calculated_for_date, route_status, schedule_band,
                        days_to_preliminary_delivery, deadline_type, recommended_deadline,
                        default_outcome_window_days,
                        new_experiment_allowed_by_schedule,
                        milestone_status_review_required,
                        recommendation_reason, config_version
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        key, as_of, route_status, band, days,
                        row["recommended_deadline_type"],
                        row["recommended_deadline"],
                        row["default_outcome_window_days"],
                        row["new_experiment_allowed_by_schedule"],
                        row["milestone_status_review_required"],
                        row["recommendation_reason"],
                        VERSION,
                    )
                )

            results.append(row)

    conn.commit()

    out = root / "artifacts" / "contract_activation_v292" / "deadline_policy_v2921"
    out.mkdir(parents=True, exist_ok=True)
    (out / "deadline_recommendations.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "calculated_as_of": as_of.isoformat(),
                "projects": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8"
    )

    return results, defaults


def enrich_approval_templates(root: Path, results: list[dict], defaults: dict):
    by_key = {x["project_key"]: x for x in results}

    for key in ("MD", "MT"):
        template = root / "artifacts" / "contract_activation_v292" / key / "approval_template.json"
        if not template.exists():
            print(f"[V2.9.2.1] {key}: approval_template.json missing; run v2.9.2 install/refresh first.")
            continue

        payload = load_json(template)
        rec = by_key[key]
        measurement = defaults["approval_candidate_defaults"][key]

        # Add recommendations without silently approving/filling human-required fields.
        payload["milestone_context_v2921"] = {
            "preliminary_delivery_date": rec["preliminary_delivery_date"],
            "days_to_preliminary_delivery": rec["days_to_preliminary_delivery"],
            "schedule_band": rec["schedule_band"],
            "milestone_status_review_required": rec["milestone_status_review_required"],
            "new_experiment_allowed_by_schedule": rec["new_experiment_allowed_by_schedule"],
        }

        payload["recommendations_v2921"] = {
            "recommended_deadline": rec["recommended_deadline"],
            "recommended_deadline_type": rec["recommended_deadline_type"],
            "recommended_outcome_window_days": rec["default_outcome_window_days"],
            "primary_metric_recommendation": measurement["primary_metric_recommendation"],
            "secondary_metric_recommendations": measurement["secondary_metric_recommendations"],
            "outcome_capture_method_recommendation": measurement["outcome_capture_method_recommendation"],
            "roi_measurement_plan_recommendation": measurement["roi_measurement_plan_recommendation"],
            "success_criterion_template": measurement["success_criterion_template"],
            "why": rec["recommendation_reason"],
        }

        payload["human_confirmation_v2921"] = {
            "instruction": (
                "Review recommendations_v2921. If accepted, copy the approved values into "
                "deadline / outcome_window_days / outcome_capture_method / roi_measurement_plan. "
                "Define a numeric success_criterion ex ante. Do not copy the success criterion template verbatim."
            ),
            "accepted_recommendations": False
        }

        template.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(
            f"[V2.9.2.1] {key}: template enriched | "
            f"recommended_deadline={rec['recommended_deadline']} | "
            f"outcome_window={rec['default_outcome_window_days']}d"
        )


def print_status(results):
    print(f"[V2.9.2.1] schedule contexts={len(results)}")
    for r in results:
        route = r.get("route_status") or "NO_V292_ROUTE"
        deadline = r.get("recommended_deadline") or "-"
        print(
            f"  {r['project_key']} | delivery={r['preliminary_delivery_date']} | "
            f"days={r['days_to_preliminary_delivery']} | band={r['schedule_band']} | "
            f"route={route} | rec_deadline={deadline} | "
            f"outcome_window={r['default_outcome_window_days']}d"
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", nargs="?", choices=["install", "refresh", "status"], default="status")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to current date")
    args = p.parse_args()

    settings = load_settings()
    root = Path(settings.project_root)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    with connect_postgres(settings) as conn:
        if args.command == "install":
            install_schema(root, conn)
            sync_milestones(root, conn)
            results, defaults = calculate(root, conn, as_of)
            enrich_approval_templates(root, results, defaults)
            print_status(results)
            return

        if args.command == "refresh":
            sync_milestones(root, conn)
            results, defaults = calculate(root, conn, as_of)
            enrich_approval_templates(root, results, defaults)
            print_status(results)
            return

        if args.command == "status":
            results, defaults = calculate(root, conn, as_of)
            print_status(results)


if __name__ == "__main__":
    main()
