from __future__ import annotations

import pandas as pd
import streamlit as st

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


st.set_page_config(page_title="Medallio AI Control Tower", layout="wide")
st.title("Medallio AI Control Tower · v2.9.3")
st.caption("PostgreSQL is the source of truth. This app is an analyst/operations surface, not the evidence store.")

settings = load_settings()


@st.cache_data(ttl=120)
def query(sql: str) -> pd.DataFrame:
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d.name for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)


tower = query("""
SELECT *
FROM analytics.v_pbi_ai_control_tower_v293
ORDER BY
    CASE
        WHEN what_needs_me_now='ESCALATE EXECUTION' THEN 1
        WHEN what_needs_me_now='START ACTION' THEN 2
        WHEN what_needs_me_now='MONITOR EXECUTION' THEN 3
        WHEN what_needs_me_now='FIX DATA' THEN 4
        WHEN what_needs_me_now='DESIGN' THEN 5
        WHEN what_needs_me_now='BUILD EVIDENCE' THEN 6
        ELSE 9
    END,
    priority_score DESC NULLS LAST
""")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Projects in tower", len(tower))
c2.metric("Active interventions", int(tower["intervention_code"].notna().sum()) if "intervention_code" in tower else 0)
c3.metric("Execution at risk", int((tower["execution_health"] == "EXECUTION_AT_RISK").sum()) if "execution_health" in tower else 0)
c4.metric("Mature outcomes", int(tower["mature_outcome_count"].fillna(0).sum()) if "mature_outcome_count" in tower else 0)

st.subheader("What needs attention now")
cols = [
    c for c in [
        "project_key","project_name","what_needs_me_now","priority_score",
        "route_status","workflow_status","execution_status","execution_health",
        "outcome_sla_status","outcome_due_date","evidence_level"
    ] if c in tower.columns
]
st.dataframe(tower[cols], use_container_width=True, hide_index=True)

st.subheader("Decision → execution → outcome")
interventions = query("""
SELECT *
FROM decision_intelligence.v_intervention_monitoring_v293
ORDER BY project_key
""")
st.dataframe(interventions, use_container_width=True, hide_index=True)

st.subheader("Observed outcome & ROI")
roi = query("""
SELECT *
FROM analytics.v_pbi_outcome_roi_v293
ORDER BY project_key
""")
st.dataframe(roi, use_container_width=True, hide_index=True)

st.subheader("Execution timeline")
events = query("""
SELECT *
FROM decision_intelligence.v_intervention_event_timeline_v293
ORDER BY event_ts DESC
LIMIT 200
""")
st.dataframe(events, use_container_width=True, hide_index=True)
