from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from replica_cygnus.lead_scoring.pilot import (
    assigned_arm, subject_key, timestamp, validate_event, validate_protocol, itt_comparison,
)

UTC=timezone.utc


def protocol():
    return dict(pilot_id="test",model_run_id=str(uuid4()),seed="fixed-test-seed-0123456789",
                projects=["P1"],min_priority_score=5,max_age_hours=24,max_score_age_hours=2,
                sla_minutes=60,treatment_fraction=.5,target_per_arm=100,
                enrollment_end=(datetime.now(UTC)+timedelta(days=30)).isoformat(),primary_outcome="separacion_14d",
                treatment_description="Call after assignment",control_description="Usual service",
                business_rules_approved=True,eligibility_definition="Reviewed roster",outcome_definition="Reviewed process",
                analysis_plan="Pre-specified test, fixed horizon")


def test_subject_persistence_across_reassignment_and_input_order():
    p=protocol()
    docs=[str(i).zfill(8) for i in range(10000)]
    arms={d:assigned_arm(p,subject_key(d)) for d in docs}
    assert arms=={d:assigned_arm(p,subject_key(d)) for d in reversed(docs)}
    assert subject_key(" 001 ")==subject_key("001")
    assert subject_key("001")!=subject_key("1")
    assert 4700<sum(a=="TREATMENT" for a in arms.values())<5300


@pytest.mark.parametrize("field,value",[("business_rules_approved",False),("model_run_id",None),
    ("min_priority_score",float('nan')),("target_per_arm",None),("sla_minutes",1.5),("projects",[]),
    ("analysis_plan","PENDIENTE"),("seed","short")])
def test_incomplete_protocol_fails_closed(field,value):
    p=protocol(); p[field]=value
    with pytest.raises(ValueError): validate_protocol(p)


def test_timestamp_must_have_timezone():
    with pytest.raises(ValueError): timestamp("2026-09-07T09:00:00")
    assert timestamp("2026-09-07T09:00:00-05:00").hour==14


def outcome_row(start,**changes):
    row=dict(assignment_id=str(uuid4()),source_ref="crm/export/1",outcome_name="separacion_14d",value="1",
        event_at=(start+timedelta(days=2)).isoformat(),observed_through=(start+timedelta(days=14)).isoformat(),verified_by="reviewer")
    row.update(changes)
    return row


def test_outcome_requires_entire_horizon_even_for_positives():
    now=datetime.now(UTC); start=now-timedelta(days=15)
    assert validate_event(outcome_row(start),start,now,"outcomes")["value"]==1
    with pytest.raises(ValueError,match="HORIZON"):
        validate_event(outcome_row(start,observed_through=(start+timedelta(days=13)).isoformat()),start,now,"outcomes")
    with pytest.raises(ValueError,match="EVENT"):
        validate_event(outcome_row(start,event_at=(start-timedelta(seconds=1)).isoformat()),start,now,"outcomes")
    with pytest.raises(ValueError,match="EVENT"):
        validate_event(outcome_row(start,event_at=(start+timedelta(days=14)).isoformat()),start,now,"outcomes")
    assert validate_event(outcome_row(start,value="0",event_at=""),start,now,"outcomes")["event_at"] is None


@pytest.mark.parametrize("cost",["NaN","Infinity","-1","0.00001","100000000000000"])
def test_action_rejects_invalid_costs(cost):
    now=datetime.now(UTC); start=now-timedelta(hours=1)
    row=dict(assignment_id=str(uuid4()),event_id=str(uuid4()),source_ref="crm/1",action_at=now.isoformat(),
             action_type="CALL",result="NO_ANSWER",owner="advisor",cost_pen=cost)
    with pytest.raises(ValueError,match="COST"): validate_event(row,start,now,"actions")


def test_rare_zero_outcomes_have_nonzero_interval():
    r=itt_comparison(0,100,0,100)
    assert r["difference_pp"]==0 and r["ci95_low_pp"]<0<r["ci95_high_pp"]
    assert r["relative_lift"] is None
    assert itt_comparison(1,10,0,0)["status"]=="INSUFFICIENT_MATURE_DATA"
