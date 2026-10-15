"""Auditable coverage, calibration, snapshot compatibility and artifact integrity."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .evaluation import paired_comparisons, policy_backtest, policy_uncertainty, score, select_policy


def project_coverage(panel, predictions, horizon):
    records = []
    origin = panel.month.max()
    for project, rows in panel.groupby('project'):
        latest = rows.sort_values('month').iloc[-1]
        chosen = predictions[predictions.project.eq(project) & predictions.is_selected]
        reviewed = bool(rows.review_units.gt(0).any())
        complete = set(chosen.horizon) == set(range(1, horizon + 1)) and len(chosen) == horizon
        if reviewed:
            status = 'QUARANTINED_REVIEW_UNITS'
        elif latest.month != origin:
            status = 'STALE_PROJECT'
        elif not complete:
            status = 'MISSING_FORECAST'
        else:
            status = 'ZERO_INVENTORY' if latest.stock_close == 0 else 'FORECAST_AVAILABLE'
        records.append(dict(project=project, status=status, stock=float(latest.stock_close),
            history_months=len(rows), review_months=int(rows.review_units.gt(0).sum()),
            has_forecast=complete, selected_model=chosen.model.iloc[0] if complete else None,
            horizon=horizon, forecast_cumulative=float(chosen.sort_values('horizon').prediction.iloc[-1]) if complete else None))
    return pd.DataFrame(records)


def snapshot_revisions(previous, current):
    """New observations are not historical revisions. Compare the overlapping keys."""
    columns = ['sales', 'stock_open', 'stock_close', 'inflows', 'review_units']
    left, right = previous.copy(), current.copy()
    for frame in (left, right):
        frame['month'] = pd.to_datetime(frame.month)
        frame['project'] = frame.project.astype(str)
    joined = left.merge(right, on=['project', 'month'], how='outer', suffixes=('_old', '_new'),
                        indicator=True, validate='one_to_one')
    common = joined[joined._merge.eq('both')].copy()
    changed = pd.Series(False, index=common.index)
    field_counts = {}
    for field in columns:
        difference = common[f'{field}_old'].ne(common[f'{field}_new'])
        field_counts[field] = int(difference.sum())
        changed |= difference
    return dict(compared_rows=len(common), revised_rows=int(changed.sum()),
        removed_rows=int(joined._merge.eq('left_only').sum()), new_rows=int(joined._merge.eq('right_only').sum()),
        revised_projects=sorted(common.loc[changed, 'project'].unique().tolist()), fields=field_counts)


def outcome_scope(window, origin, horizon, issued_stock):
    expected = pd.date_range(pd.Timestamp(origin) + pd.DateOffset(months=1), periods=horizon, freq='MS')
    observed = pd.DatetimeIndex(pd.to_datetime(window.month)).sort_values()
    if not observed.equals(expected):
        return dict(complete=False, eligible_scope=False, reason='INCOMPLETE_PROJECT_WINDOW', actual=None)
    rows = window.sort_values('month')
    actual = float(rows.sales.sum())
    reasons = []
    if rows.stock_open.iloc[0] != float(issued_stock):
        reasons.append('ISSUANCE_STOCK_REVISED')
    if rows.inflows.gt(0).any():
        reasons.append('NEW_INVENTORY')
    if rows.review_units.gt(0).any():
        reasons.append('UNRESOLVED_REVIEW')
    if actual > float(issued_stock):
        reasons.append('SALES_EXCEED_ISSUED_STOCK')
    if not rows.stock_open.add(rows.inflows).sub(rows.sales).eq(rows.stock_close).all():
        reasons.append('INVENTORY_BALANCE_FAILED')
    if len(rows) > 1 and not np.array_equal(rows.stock_open.to_numpy()[1:], rows.stock_close.to_numpy()[:-1]):
        reasons.append('INVENTORY_CONTINUITY_FAILED')
    return dict(complete=True, eligible_scope=not reasons, reason=';'.join(reasons) or 'COMPATIBLE_SCOPE', actual=actual)


def interval_calibration(backtest):
    rows = backtest.copy()
    rows['stock_band'] = pd.cut(rows.stock, [-1, 9, 49, np.inf], labels=['0-9', '10-49', '50+'])
    records = []
    for (part, model, h, band), group in rows.groupby(['partition', 'model', 'horizon', 'stock_band'], observed=True):
        for coverage in (80, 95):
            available = group.dropna(subset=[f'lower{coverage}', f'upper{coverage}'])
            if available.empty:
                observed, width, interval_score = None, None, None
            else:
                lo, hi, actual = available[f'lower{coverage}'], available[f'upper{coverage}'], available.actual
                observed = float((actual.ge(lo) & actual.le(hi)).mean())
                width = float((hi - lo).mean())
                alpha = 1 - coverage / 100
                interval_score = float((hi-lo + 2/alpha*((lo-actual).clip(lower=0)+(actual-hi).clip(lower=0))).mean())
            records.append(dict(partition=part, model=model, horizon=int(h), stock_band=str(band),
                nominal=coverage, rows=len(group), interval_rows=len(available),
                origins=int(available.origin.nunique()), observed_coverage=observed,
                mean_width=width, interval_score=interval_score))
    return pd.DataFrame(records)


def diagnostics(panel, future, backtest, cfg, policy=None):
    policy = policy or select_policy(backtest, cfg)
    coverage = project_coverage(panel, future, cfg.horizon)
    deployed = policy_backtest(backtest, policy, cfg)
    tests = deployed[deployed.partition.eq('test')]
    stock = float(coverage.stock.sum())
    summary = dict(architecture_version='2.0', selected_model=policy['selected_model'],
        source_evidence='RECONSTRUCTED_HISTORY_NOT_POINT_IN_TIME', automatic_promotion=False,
        evaluation_status='RETROSPECTIVE_DEVELOPMENT_DIAGNOSTIC',
        projects_total=len(coverage), projects_forecast=int(coverage.has_forecast.sum()),
        stock_total=stock, stock_forecast=float(coverage.loc[coverage.has_forecast, 'stock'].sum()),
        stock_coverage=float(coverage.loc[coverage.has_forecast, 'stock'].sum()/stock) if stock else None,
        quarantine=coverage.loc[coverage.status.eq('QUARANTINED_REVIEW_UNITS'), 'project'].tolist(),
        test_policy_score=score(tests), test_temporal_uncertainty=policy_uncertainty(tests, cfg),
        policy_evaluation='Frozen validation choices; fallback included on the same population',
        interval_method='Pooled empirical absolute errors with temporal support checks; not guaranteed coverage')
    return summary, coverage, paired_comparisons(backtest), deployed, interval_calibration(backtest)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_integrity(directory):
    files = {p.relative_to(directory).as_posix(): sha256(p) for p in sorted(directory.rglob('*'))
             if p.is_file() and p.name != 'checksums.json'}
    (directory/'checksums.json').write_text(json.dumps(dict(algorithm='sha256', files=files), indent=2), encoding='utf-8')


def verify_integrity(directory):
    index = directory/'checksums.json'
    if not index.is_file():
        return dict(status='UNAVAILABLE_LEGACY_ARTIFACTS', missing=[], changed=[], unexpected=[])
    expected = json.loads(index.read_text(encoding='utf-8'))['files']
    missing, changed = [], []
    for name, value in expected.items():
        path = directory/name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Artifact index contains unsafe paths')
        if not path.is_file():
            missing.append(name)
        elif sha256(path) != value:
            changed.append(name)
    present = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() and p.name != 'checksums.json'}
    unexpected = sorted(present-set(expected))
    return dict(status='VERIFIED' if not missing and not changed and not unexpected else 'FAILED',
                missing=missing, changed=changed, unexpected=unexpected)
