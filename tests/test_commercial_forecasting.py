from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from replica_cygnus.commercial_forecasting.core import (
    Config, FEATURES, attach_intervals, design, evaluate, fit_predict, metrics, validate_panel,
)
from replica_cygnus.commercial_forecasting.service import execute, json_safe, synthetic_panel


@pytest.fixture(scope='module')
def panel():
    return validate_panel(synthetic_panel())[0]


def test_quality_rejects_unknown_duplicate_gap_and_inventory():
    raw=synthetic_panel()
    with pytest.raises(ValueError,match='Duplicate'):
        validate_panel(pd.concat([raw,raw.iloc[:1]]))
    bad=raw.copy(); bad.loc[0,'sales']=np.nan
    with pytest.raises(ValueError,match='Unknown'):
        validate_panel(bad)
    with pytest.raises(ValueError,match='Missing monthly'):
        validate_panel(raw.drop(index=5))
    bad=raw.copy(); bad.loc[0,'stock_close']+=1
    with pytest.raises(ValueError,match='Stock balance'):
        validate_panel(bad)


def test_cam_is_excluded_and_reviews_are_quarantined():
    raw=synthetic_panel(); raw.loc[raw.project.eq('DEMO_1'),'project']='CAM'
    panel,quality=validate_panel(raw)
    assert 'CAM' not in panel.project.unique()
    assert quality['excluded_cam']==42
    panel.loc[panel.project.eq('DEMO_2'),'review_units']=1
    assert 'DEMO_2' not in design(panel,Config()).project.unique()


def test_outcomes_must_be_mature_and_no_future_enters_training(panel):
    origin=pd.Timestamp('2025-03-01')
    a,meta,bundles=fit_predict(panel,origin,Config())
    assert len(bundles['_ets_bundles'])==panel.project.nunique()
    changed=panel.copy()
    changed.loc[changed.month.gt(origin),'sales']=9999
    changed.loc[changed.month.gt(origin),'stock_close']=99999
    b,other,_=fit_predict(changed,origin,Config())
    pd.testing.assert_frame_equal(a,b)
    assert pd.Timestamp(meta['train_outcome_max'])<=origin
    assert meta['train_rows']==other['train_rows']
    assert set(a.model)=={'mean3','ets','gmm_analog','random_forest'}


def test_counts_are_bounded_and_cumulative_monotone(panel):
    out,_,_=fit_predict(panel,panel.month.max(),Config())
    assert out.prediction.ge(0).all() and out.prediction.le(out.stock).all()
    for _,g in out.groupby(['project','model']):
        assert g.sort_values('horizon').prediction.diff().dropna().ge(0).all()


def test_launch_gets_baseline_without_fake_ml_training():
    panel=synthetic_panel().iloc[:2]
    out,meta,bundles=fit_predict(panel,panel.month.max(),Config())
    assert set(out.model)=={'mean3'}
    assert not bundles and meta['train_rows']==0


def test_future_additions_exclude_training_analogs():
    p=synthetic_panel().iloc[:12].copy()
    p.loc[5,'inflows']=50
    p.loc[5:,'stock_close']+=50
    p.loc[6:,'stock_open']+=50
    p,_=validate_panel(p)
    matrix=design(p,Config())
    assert matrix.loc[matrix.month.eq(pd.Timestamp('2023-03-01')),'y6'].isna().all()


def test_intervals_use_only_previously_mature_out_of_sample_errors():
    origin=pd.Timestamp('2025-01-01')
    prediction=pd.DataFrame([dict(model='mean3',horizon=1,origin=origin,prediction=10.,stock=100.)])
    errors=pd.DataFrame([dict(model='mean3',horizon=1,origin=m,
        outcome_month=m+pd.DateOffset(months=1),actual=12.,prediction=10.)
        for m in pd.date_range('2023-01-01',periods=20,freq='MS')])
    a=attach_intervals(prediction,errors,Config())
    poison=pd.DataFrame([dict(model='mean3',horizon=1,origin=origin,
        outcome_month=pd.Timestamp('2025-02-01'),actual=1000.,prediction=0.)]*100)
    b=attach_intervals(prediction,pd.concat([errors,poison]),Config())
    pd.testing.assert_frame_equal(a,b)
    assert a.lower80.iloc[0]==8 and a.upper95.iloc[0]==12
    c=attach_intervals(prediction,errors.iloc[:1],Config())
    assert c.lower80.isna().all()


def test_backtest_partitions_and_all_fits_have_purged_targets(panel):
    bt,summary,evidence,selected=evaluate(panel,Config(backtest_origins=7,test_origins=2))
    assert bt[bt.partition.eq('validation')].origin.max()<bt[bt.partition.eq('test')].origin.min()
    assert bt[bt.partition.eq('validation')].outcome_month.max()<=bt[bt.partition.eq('test')].origin.min()
    for fit in evidence:
        if fit['train_outcome_max']:
            assert pd.Timestamp(fit['train_outcome_max'])<=pd.Timestamp(fit['origin'])
    assert summary.mae.notna().all()
    assert selected in set(bt.model)


def test_zero_actual_wape_is_undefined():
    frame=pd.DataFrame(dict(actual=[0.],prediction=[1.],origin=[pd.Timestamp('2024-01-01')]))
    assert metrics(frame)['wape'] is None
    assert json_safe({'a':np.nan})=={'a':None}


def test_executable_artifacts_are_explicitly_synthetic(tmp_path,panel):
    root=Path(__file__).resolve().parents[1]
    directory,manifest,future,bt=execute(panel,root,tmp_path,Config(backtest_origins=5,test_origins=2),synthetic=True)
    assert manifest['evidence_level']=='SYNTHETIC_ONLY'
    assert (directory/'trained_models.joblib').is_file()
    assert (directory/'report.html').is_file()
    assert (directory/'training_cuts.json').is_file()
    from replica_cygnus.commercial_forecasting.robustness import verify_integrity
    assert verify_integrity(directory)['status']=='VERIFIED'
    assert (directory/'source_code/src/replica_cygnus/commercial_forecasting/core.py').is_file()
    assert (directory/'project_coverage.csv').is_file()
    assert manifest['architecture_version']=='2.0'
    assert future.groupby(['project','horizon']).is_selected.sum().eq(1).all()
    # A second run receives a separate identity and never overwrites evidence.
    assert manifest['run_id']==directory.name
