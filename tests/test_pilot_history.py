from datetime import date

import pytest

from replica_cygnus.lead_scoring.history_diagnostic import COUNTS, summarize, parameters, wilson


def test_calendar_zero_days_missing_labels_and_reconciliation():
    row=dict.fromkeys(COUNTS,0)
    row.update(project='P1',day='2026-01-01',assignments=4,first_client_project=2,first_client_global=1,
               first_inferred=2,sep_mature=2,sep_observed=1,sep_positive=1)
    payload=dict(daily=[row],quality=dict(window_source_rows=5,invalid_identity_or_project=1),excluded_at_or_after_cutoff=0)
    result=summarize(payload,date(2026,1,1),date(2026,1,11))
    p=result['projects'][0]
    assert p['first_clients_per_calendar_day']==.2 and p['days_without_first_clients']==9
    assert p['repeat_assignments']==2 and p['sep_missing']==1
    assert p['sep_complete_cohort_rate'] is None
    assert p['sep_missing_bounds']==[.5,1]
    assert len(result['daily'])==10 and result['quality']['reconciled']
    payload['quality']['window_source_rows']=6
    with pytest.raises(ValueError,match='concilian'): summarize(payload,date(2026,1,1),date(2026,1,11))


def test_empty_history_and_calendar_bounds():
    result=summarize(dict(daily=[],quality=dict(window_source_rows=0,invalid_identity_or_project=0),excluded_at_or_after_cutoff=0),date(2026,1,1),date(2026,1,2))
    assert result['projects']==[] and result['quality']['reconciled']
    with pytest.raises(ValueError): parameters(date(2026,1,1),date(2026,1,1))
    assert parameters(date(2026,1,1),date(2026,1,2))['start_at'].utcoffset().total_seconds()==-18000
    assert wilson(0,100)[1]>0 and wilson(0,0) is None
