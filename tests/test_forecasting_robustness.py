import json

import numpy as np
import pandas as pd
import pytest

from replica_cygnus.commercial_forecasting.core import Config, attach_intervals, fit_predict, validate_panel
from replica_cygnus.commercial_forecasting.evaluation import (
    apply_policy, complete_paths, paired_comparisons, policy_backtest, policy_uncertainty, select_policy,
)
from replica_cygnus.commercial_forecasting.robustness import (
    outcome_scope, project_coverage, snapshot_revisions, verify_integrity, write_integrity,
)
from replica_cygnus.commercial_forecasting.service import synthetic_panel


def evidence():
    rows = []
    for part, start, periods in [('validation', '2022-01-01', 18), ('test', '2024-01-01', 6)]:
        for origin in pd.date_range(start, periods=periods, freq='MS'):
            for project in ['ACTIVE', 'QUIET']:
                for h in range(1, 7):
                    actual = float(h * 2) if project == 'ACTIVE' else 0.
                    for model in ['mean3', 'random_forest', 'gmm_analog']:
                        prediction = actual
                        if model == 'mean3' and project == 'ACTIVE':
                            prediction += h
                        elif project == 'QUIET' and model != 'mean3':
                            prediction = 1.
                        if model == 'gmm_analog':
                            prediction += 2.
                        rows.append(dict(partition=part, origin=origin, project=project, horizon=h,
                            model=model, prediction=prediction, actual=actual, stock=100.,
                            outcome_month=origin+pd.DateOffset(months=h)))
    return pd.DataFrame(rows)


def test_validation_policy_ignores_test_outcomes_and_guards_exact_baseline():
    bt = evidence(); cfg = Config()
    a = select_policy(bt, cfg)
    assert a['selected_model'] == 'random_forest'
    assert a['candidate_projects'] == ['ACTIVE']
    poisoned = bt.copy()
    poisoned.loc[poisoned.partition.eq('test'), ['actual', 'prediction']] = 999999.
    assert select_policy(poisoned, cfg) == a
    rows = policy_backtest(bt, a, cfg)
    assert rows[rows.project.eq('QUIET')].model.eq('mean3').all()
    assert rows[rows.partition.eq('test')].prediction.eq(rows[rows.partition.eq('test')].actual).all()
    assert all(r['rows'] == a['full_validation_rows'] for r in a['rankings'])


def test_monthly_overlap_and_incomplete_paths_cannot_pass_as_independent_evidence():
    bt = evidence()
    recent = bt[(bt.origin.lt(pd.Timestamp('2022-05-01'))) | bt.partition.eq('test')]
    policy = select_policy(recent, Config())
    assert policy['selected_model'] == 'mean3'
    assert any(r['decision'] == 'INSUFFICIENT_NONOVERLAPPING_ORIGINS' for r in policy['project_decisions'])
    ref = bt[bt.model.eq('mean3')].copy()
    cut = ref.drop(ref.index[0])
    complete = complete_paths(cut, 6)
    assert not ((complete.project == 'ACTIVE') & (complete.origin == pd.Timestamp('2022-01-01'))).any()
    with pytest.raises(ValueError, match='Duplicate'):
        complete_paths(pd.concat([ref, ref.iloc[:1]]), 6)


def test_pairing_reports_denominator_and_rejects_disagreeing_actuals():
    bt = evidence()
    bt = bt[~(bt.project.eq('QUIET') & bt.model.eq('random_forest'))]
    report = paired_comparisons(bt)
    row = report[(report.model == 'random_forest') & (report.partition == 'test') & (report.horizon == 0)].iloc[0]
    assert row.paired_fraction == .5 and row.baseline_mae == 3.5 and row.mae == 0
    bt.loc[bt.model.eq('random_forest'), 'actual'] += 1
    with pytest.raises(ValueError, match='same outcomes'):
        paired_comparisons(bt)


def test_policy_falls_back_for_whole_path_if_current_candidate_incomplete():
    bt = evidence(); policy = select_policy(bt, Config())
    future = bt[bt.origin.eq(pd.Timestamp('2024-01-01'))].copy()
    future = future[~(future.project.eq('ACTIVE') & future.model.eq('random_forest') & future.horizon.eq(3))]
    chosen = apply_policy(future, policy, 6)
    assert chosen[chosen.is_selected].model.eq('mean3').all()
    assert chosen.groupby(['project', 'horizon']).is_selected.sum().eq(1).all()


def test_policy_keeps_the_selected_models_own_intervals():
    bt = evidence()
    bt['lower80'] = np.where(bt.model.eq('mean3'), 0., 1.)
    bt['upper80'] = np.where(bt.model.eq('mean3'), 99., 20.)
    bt['stock_remaining'] = bt.stock-bt.prediction
    rows = policy_backtest(bt, select_policy(bt, Config()), Config())
    assert rows[rows.model.eq('random_forest')].lower80.eq(1.).all()
    assert rows[rows.model.eq('mean3')].upper80.eq(99.).all()
    assert rows.stock_remaining.eq(rows.stock-rows.prediction).all()


def test_interval_row_count_does_not_substitute_temporal_support():
    origin = pd.Timestamp('2025-01-01')
    pred = pd.DataFrame([dict(model='mean3', horizon=6, origin=origin, prediction=5., stock=50.)])
    errors = pd.DataFrame([dict(model='mean3', horizon=6, origin=pd.Timestamp('2024-01-01'),
        outcome_month=pd.Timestamp('2024-07-01'), prediction=4., actual=5.)] * 500)
    result = attach_intervals(pred, errors, Config())
    assert result.interval_errors.iloc[0] == 500
    assert result.interval_origins.iloc[0] == 1
    assert result.lower80.isna().all()


def test_temporal_bootstrap_declines_small_correlated_test():
    bt = evidence(); cfg = Config()
    rows = policy_backtest(bt, select_policy(bt, cfg), cfg)
    assert policy_uncertainty(rows[rows.partition.eq('test')], cfg)['status'] == 'INSUFFICIENT_NONOVERLAPPING_ORIGINS'
    result = policy_uncertainty(rows[rows.partition.eq('validation')], cfg)
    assert result['status'] == 'DESCRIPTIVE_BLOCK_BOOTSTRAP'
    assert result['improvement_low95'] == 1.


def test_cold_start_is_not_given_a_pooled_ml_forecast_and_tiny_gmm_components_are_rejected():
    raw = synthetic_panel()
    new = raw[raw.project.eq('DEMO_1')].iloc[-2:].copy(); new['project'] = 'NEW'
    panel, _ = validate_panel(pd.concat([raw, new], ignore_index=True))
    forecasts, meta, _ = fit_predict(panel, panel.month.max(), Config())
    assert set(forecasts[forecasts.project.eq('NEW')].model) == {'mean3'}
    assert all(c['effective_rows'] >= 10 for c in meta['clusters'])
    assert meta['feature_importance_semantics'].startswith('TRAINING_IMPURITY')


def test_quarantine_includes_zero_stock_and_coverage_accounts_for_every_project():
    panel, _ = validate_panel(synthetic_panel())
    group = panel[panel.project.eq('DEMO_1')]
    panel.loc[group.index[0], 'review_units'] = 1
    last = group.index[-1]
    panel.loc[last, 'sales'] = panel.loc[last, 'stock_open']
    panel.loc[last, 'stock_close'] = 0
    future, _, _ = fit_predict(panel, panel.month.max(), Config())
    assert 'DEMO_1' not in set(future.project)
    future['is_selected'] = future.model.eq('mean3')
    coverage = project_coverage(panel, future, 6)
    assert len(coverage) == panel.project.nunique()
    assert coverage.set_index('project').loc['DEMO_1', 'status'] == 'QUARANTINED_REVIEW_UNITS'


def test_snapshot_revisions_are_distinct_from_new_months():
    previous = synthetic_panel().iloc[:3].copy()
    current = synthetic_panel().iloc[:4].copy()
    current.loc[1, 'sales'] += 1
    result = snapshot_revisions(previous, current)
    assert result['new_rows'] == 1 and result['revised_rows'] == 1
    assert result['fields']['sales'] == 1 and result['removed_rows'] == 0


def test_outcome_rejects_revised_issuance_stock_even_when_future_balances():
    row = pd.DataFrame([dict(month=pd.Timestamp('2026-10-01'), sales=3, stock_open=9,
                            stock_close=6, inflows=0, review_units=0)])
    result = outcome_scope(row, pd.Timestamp('2026-09-01'), 1, 8)
    assert result['complete'] and not result['eligible_scope']
    assert result['reason'] == 'ISSUANCE_STOCK_REVISED'
    assert outcome_scope(row, pd.Timestamp('2026-09-01'), 2, 8)['complete'] is False


def test_integrity_detects_changed_missing_untracked_and_unsafe_files(tmp_path):
    (tmp_path/'model.bin').write_bytes(b'opaque-model-not-loaded')
    write_integrity(tmp_path)
    assert verify_integrity(tmp_path)['status'] == 'VERIFIED'
    (tmp_path/'model.bin').write_bytes(b'changed')
    assert verify_integrity(tmp_path)['changed'] == ['model.bin']
    (tmp_path/'model.bin').unlink()
    (tmp_path/'extra.txt').write_text('extra')
    result = verify_integrity(tmp_path)
    assert result['missing'] == ['model.bin'] and result['unexpected'] == ['extra.txt']
    (tmp_path/'checksums.json').write_text(json.dumps({'files': {'../outside': 'hash'}}))
    with pytest.raises(ValueError, match='unsafe'):
        verify_integrity(tmp_path)
