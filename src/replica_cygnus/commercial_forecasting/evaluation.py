"""Validation-only policy selection on identical populations and complete paths.

Raw candidate metrics and deployable policy metrics have different denominators.
This module makes both explicit and never uses test outcomes for model choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

KEYS = ['project', 'origin', 'horizon']


def nonoverlapping_origins(origins, horizon):
    accepted = []
    for origin in sorted(pd.Series(list(origins), dtype='datetime64[ns]').drop_duplicates()):
        if not accepted or origin >= accepted[-1] + pd.DateOffset(months=int(horizon)):
            accepted.append(origin)
    return len(accepted)


def complete_paths(rows, horizon):
    if rows.empty:
        return rows.copy()
    if rows.duplicated(KEYS).any():
        raise ValueError('Duplicate forecast key in model evaluation')
    required = set(range(1, horizon + 1))
    keys = [k for k, g in rows.groupby(['project', 'origin']) if set(g.horizon) == required]
    index = pd.MultiIndex.from_frame(rows[['project', 'origin']])
    return rows[index.isin(keys)].copy()


def score(rows):
    error = rows.prediction - rows.actual
    total = float(rows.actual.sum())
    return dict(rows=len(rows), projects=int(rows.project.nunique()), origins=int(rows.origin.nunique()),
                mae=float(error.abs().mean()) if len(rows) else None,
                bias=float(error.mean()) if len(rows) else None,
                wape=float(error.abs().sum() / total) if total > 0 else None)


def paired_rows(reference, candidate):
    paired = reference.merge(candidate[KEYS + ['prediction', 'actual']], on=KEYS,
                             suffixes=('_baseline', ''), validate='one_to_one')
    if not np.allclose(paired.actual, paired.actual_baseline):
        raise ValueError('Candidates do not share the same outcomes')
    return paired


def paired_comparisons(backtest):
    records = []
    for partition, rows in backtest.groupby('partition'):
        ref = rows[rows.model.eq('mean3')]
        for model in sorted(set(rows.model) - {'mean3'}):
            pair = paired_rows(ref, rows[rows.model.eq(model)])
            for h in [0, *sorted(pair.horizon.unique())]:
                group = pair if h == 0 else pair[pair.horizon.eq(h)]
                if group.empty:
                    continue
                baseline = (group.prediction_baseline - group.actual).abs().mean()
                denominator = len(ref if h == 0 else ref[ref.horizon.eq(h)])
                records.append(dict(partition=partition, model=model, horizon=int(h),
                    scope='PAIRED_CANDIDATE', **score(group), baseline_mae=float(baseline),
                    relative_improvement=float(1 - score(group)['mae'] / baseline) if baseline else None,
                    reference_rows=denominator, paired_fraction=len(group) / denominator,
                    nonoverlap_origins=nonoverlapping_origins(group.origin, h or group.horizon.max())))
    return pd.DataFrame(records)


def select_policy(backtest, cfg):
    """One candidate family, with project guards and transparent baseline fallbacks.

    Use complete validation paths only: recent short horizons cannot dominate
    a six-month model choice. Rank all policies on the exact same reference rows.
    """
    validation = backtest[backtest.partition.eq('validation')]
    ref = complete_paths(validation[validation.model.eq('mean3')], cfg.horizon)
    decisions, rankings, project_maps = [], [], {}
    baseline_mae = score(ref)['mae']
    for model in sorted(set(validation.model) - {'mean3'}):
        cand = complete_paths(validation[validation.model.eq(model)], cfg.horizon)
        pair = paired_rows(ref, cand)
        allowed = set()
        for project, baseline in ref.groupby('project'):
            group = pair[pair.project.eq(project)]
            n_origins = int(group.origin.nunique())
            n_separate = nonoverlapping_origins(group.origin, cfg.horizon)
            base = float((group.prediction_baseline - group.actual).abs().mean()) if len(group) else None
            error = score(group)['mae']
            share = len(group) / len(baseline)
            reason = 'VALIDATION_PROJECT_GATE'
            if n_origins < cfg.min_gate_origins:
                reason = 'INSUFFICIENT_ORIGINS'
            elif n_separate < cfg.min_gate_nonoverlap_origins:
                reason = 'INSUFFICIENT_NONOVERLAPPING_ORIGINS'
            elif share < cfg.min_candidate_coverage:
                reason = 'INSUFFICIENT_CANDIDATE_COVERAGE'
            elif base == 0:
                reason = 'BASELINE_ALREADY_EXACT'
            elif error > base * (1 - cfg.min_gate_improvement):
                reason = 'NO_VALIDATION_IMPROVEMENT'
            else:
                allowed.add(project)
            decisions.append(dict(project=project, candidate=model, decision=reason,
                use_candidate=project in allowed, paired_rows=len(group), origins=n_origins,
                nonoverlap_origins=n_separate, candidate_fraction=share, candidate_mae=error,
                baseline_mae=base))
        policy = _policy_rows(ref, cand, allowed)
        error = score(policy)['mae']
        improvement = 1 - error / baseline_mae if baseline_mae else None
        rankings.append(dict(model=model, **score(policy), baseline_mae=baseline_mae,
            relative_improvement=improvement, candidate_projects=len(allowed),
            candidate_rows=int(policy.used_candidate.sum()), reference_rows=len(ref)))
        project_maps[model] = sorted(allowed)
    eligible = [r for r in rankings if r['candidate_projects'] and r['relative_improvement'] is not None
                and r['relative_improvement'] >= cfg.min_gate_improvement]
    selected = min(eligible, key=lambda r: (r['mae'], r['model']))['model'] if eligible else 'mean3'
    return dict(version='guarded_project_policy_v2', selected_model=selected,
        candidate_projects=project_maps.get(selected, []),
        selection_partition='validation', full_validation_rows=len(ref),
        validation_outcome_max=str(ref.outcome_month.max().date()) if len(ref) else None,
        validation_origins=int(ref.origin.nunique()),
        validation_nonoverlap_origins=nonoverlapping_origins(ref.origin, cfg.horizon),
        project_decisions=decisions, rankings=rankings,
        test_used_for_selection=False, deployment_status='SHADOW_NO_AUTOMATIC_PROMOTION')


def _policy_rows(reference, candidate, allowed):
    columns = [c for c in ['prediction', 'model', 'state_probabilities', 'lower80', 'upper80',
        'lower95', 'upper95', 'interval_errors', 'interval_origins', 'interval_nonoverlap_origins',
        'interval_status'] if c in candidate.columns]
    right = candidate[KEYS + columns].rename(columns={c: f'candidate_{c}' for c in columns})
    out = reference.merge(right, on=KEYS, how='left', validate='one_to_one')
    use = out.project.isin(allowed) & out.candidate_prediction.notna()
    out['used_candidate'] = use
    for column in columns:
        out.loc[use, column] = out.loc[use, f'candidate_{column}']
    if 'stock_remaining' in out:
        out['stock_remaining'] = out.stock - out.prediction
    return out.drop(columns=[f'candidate_{c}' for c in columns])


def apply_policy(future, policy, horizon):
    out = future.copy()
    out['is_selected'] = False
    out['selection_reason'] = 'SHADOW_CANDIDATE'
    for project, group in out.groupby('project'):
        model = policy['selected_model'] if project in policy['candidate_projects'] else 'mean3'
        chosen = group[group.model.eq(model)]
        reason = 'VALIDATION_PROJECT_GATE' if model != 'mean3' else 'BASELINE_POLICY'
        if set(chosen.horizon) != set(range(1, horizon + 1)):
            chosen = group[group.model.eq('mean3')]
            reason = 'CURRENT_MODEL_UNAVAILABLE'
        if set(chosen.horizon) != set(range(1, horizon + 1)):
            raise ValueError(f'Incomplete fallback forecast path: {project}')
        out.loc[chosen.index, 'is_selected'] = True
        out.loc[chosen.index, 'selection_reason'] = reason
    if not out.groupby(['project', 'horizon']).is_selected.sum().eq(1).all():
        raise ValueError('Forecast selection is not unique')
    return out


def policy_backtest(backtest, policy, cfg):
    output = []
    for partition in ('validation', 'test'):
        rows = backtest[backtest.partition.eq(partition)]
        ref = complete_paths(rows[rows.model.eq('mean3')], cfg.horizon)
        candidate = complete_paths(rows[rows.model.eq(policy['selected_model'])], cfg.horizon)
        result = _policy_rows(ref, candidate, set(policy['candidate_projects']))
        result['baseline_prediction'] = ref.set_index(KEYS).prediction.reindex(
            pd.MultiIndex.from_frame(result[KEYS])).to_numpy()
        output.append(result)
    return pd.concat(output, ignore_index=True)


def policy_uncertainty(rows, cfg):
    """Descriptive moving-block bootstrap; rows/projects are not IID trials."""
    if rows.empty:
        return dict(status='NO_EVIDENCE', independent_origins=0)
    separate = nonoverlapping_origins(rows.origin, cfg.horizon)
    result = dict(status='INSUFFICIENT_NONOVERLAPPING_ORIGINS', independent_origins=separate,
                  origins=int(rows.origin.nunique()), block_months=cfg.horizon,
                  improvement_low95=None, improvement_high95=None)
    if separate < 3:
        return result
    work = rows.assign(candidate_error=(rows.prediction - rows.actual).abs(),
                       baseline_error=(rows.baseline_prediction - rows.actual).abs())
    by_origin = work.groupby('origin')[['candidate_error', 'baseline_error']].sum().sort_index()
    calendar = pd.date_range(by_origin.index.min(), by_origin.index.max(), freq='MS')
    if not by_origin.index.equals(calendar):
        result['status'] = 'IRREGULAR_ORIGIN_GRID'
        return result
    arr = by_origin.to_numpy(); n = len(arr); length = cfg.horizon
    rng = np.random.default_rng(cfg.seed)
    improvements = []
    for _ in range(500):
        starts = rng.integers(0, n - length + 1, size=int(np.ceil(n / length)))
        indices = np.concatenate([np.arange(s, s + length) for s in starts])[:n]
        candidate, baseline = arr[indices].sum(axis=0)
        if baseline:
            improvements.append(float(1 - candidate / baseline))
    if improvements:
        result.update(status='DESCRIPTIVE_BLOCK_BOOTSTRAP',
            improvement_low95=float(np.quantile(improvements, .025)),
            improvement_high95=float(np.quantile(improvements, .975)))
    else:
        result['status'] = 'ZERO_BASELINE_ERROR'
    return result
