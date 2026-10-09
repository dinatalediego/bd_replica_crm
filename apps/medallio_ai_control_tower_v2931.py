from __future__ import annotations

import pandas as pd
import streamlit as st

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


st.set_page_config(page_title="Medallio AI Control Tower", layout="wide")
st.title("Medallio AI Control Tower · v2.9.3.1")
st.caption(
    "PostgreSQL is the source of truth. Contract approval, execution evidence "
    "and outcome evidence are separate states."
)

settings = load_settings()


@st.cache_data(ttl=120)
def query(sql: str) -> pd.DataFrame:
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d.name for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)


kpi = query("SELECT * FROM analytics.v_ai_control_tower_kpis_v2931").iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Scheduled interventions", int(kpi["scheduled_interventions"]))
c2.metric("Active executions", int(kpi["active_executions"]))
c3.metric("Waiting outcomes", int(kpi["waiting_outcomes"]))
c4.metric("Mature outcomes", int(kpi["mature_outcomes"]))

tower = query("""
SELECT *
FROM analytics.v_pbi_ai_control_tower_v293
ORDER BY
    CASE
        WHEN what_needs_me_now='FIX CONTRACT METRIC' THEN 1
        WHEN what_needs_me_now='ESCALATE EXECUTION' THEN 2
        WHEN what_needs_me_now='START ACTION' THEN 3
        WHEN what_needs_me_now='MONITOR EXECUTION' THEN 4
        WHEN what_needs_me_now='FIX DATA' THEN 5
        WHEN what_needs_me_now='DESIGN' THEN 6
        WHEN what_needs_me_now='BUILD EVIDENCE' THEN 7
        ELSE 9
    END,
    priority_score DESC NULLS LAST
""")

st.subheader("What needs attention now")
cols = [
    c for c in [
        "project_key","project_name","what_needs_me_now","priority_score",
        "route_status","workflow_status",
        "execution_status","execution_health",
        "outcome_phase_status","primary_metric","metric_semantics_status"
    ] if c in tower.columns
]
st.dataframe(tower[cols], width="stretch", hide_index=True)

issues = query("""
SELECT *
FROM analytics.v_pbi_contract_semantics_issues_v2931
ORDER BY project_key
""")
if not issues.empty:
    st.warning(
        "At least one active contract has a non-atomic primary metric. "
        "Do not mark it STARTED; cancel/reissue before execution."
    )
    st.dataframe(issues, width="stretch", hide_index=True)

st.subheader("Decision → execution → outcome")
interventions = query("""
SELECT *
FROM decision_intelligence.v_intervention_monitoring_v293
ORDER BY project_key
""")
st.dataframe(interventions, width="stretch", hide_index=True)

st.subheader("Observed outcome & ROI")
roi = query("""
SELECT *
FROM analytics.v_pbi_outcome_roi_v293
ORDER BY project_key
""")
st.dataframe(roi, width="stretch", hide_index=True)

st.subheader("Execution timeline")
events = query("""
SELECT *
FROM decision_intelligence.v_intervention_event_timeline_v293
ORDER BY event_ts DESC
LIMIT 200
""")
st.dataframe(events, width="stretch", hide_index=True)
