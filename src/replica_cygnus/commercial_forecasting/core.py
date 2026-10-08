from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import RobustScaler
from statsmodels.tsa.holtwinters import ExponentialSmoothing

FEATURES = ['sales', 'mean3', 'trend', 'absorption', 'log_stock', 'age', 'month_sin', 'month_cos']
MODELS = ('mean3', 'ets', 'gmm_analog', 'random_forest')
REQUIRED = ['month', 'project', 'sales', 'stock_open', 'stock_close', 'inflows', 'review_units']


@dataclass(frozen=True)
class Config:
    horizon: int = 6
    min_train_rows: int = 24
    max_clusters: int = 3
    backtest_origins: int = 24
    test_origins: int = 6
    seed: int = 42
    min_interval_errors: int = 20
    min_gate_origins: int = 3
    min_gate_improvement: float = .05
    min_gate_nonoverlap_origins: int = 2
    min_candidate_coverage: float = .8
    min_project_history: int = 6
    min_cluster_rows: int = 10
    min_interval_origins: int = 3

    def validate(self):
        if not 1 <= self.horizon <= 6:
            raise ValueError('horizon must be between 1 and 6')
        if self.min_train_rows < 8 or not 1 <= self.max_clusters <= 4:
            raise ValueError('Invalid training size or cluster count')
        if not 1 <= self.test_origins < self.backtest_origins:
            raise ValueError('Need validation origins before final test origins')
        if self.min_interval_errors < 5 or self.min_gate_origins < 1:
            raise ValueError('Insufficient evidence thresholds')
        if not 0 <= self.min_gate_improvement < 1:
            raise ValueError('Invalid improvement threshold')
        if self.min_gate_nonoverlap_origins < 2 or self.min_interval_origins < 2:
            raise ValueError('Need multiple temporal evidence origins')
        if not 0 < self.min_candidate_coverage <= 1 or self.min_project_history < 3 or self.min_cluster_rows < 2:
            raise ValueError('Invalid model support thresholds')


def validate_panel(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing columns: {sorted(missing)}')
    d = frame[REQUIRED].copy()
    if d.isna().any().any():
        raise ValueError('Unknown observations cannot be imputed as zero')
    d['month'] = pd.to_datetime(d.month, errors='raise')
    if not d.month.eq(d.month.dt.to_period('M').dt.to_timestamp()).all():
        raise ValueError('month must be the first day of the month')
    d['project'] = d.project.astype(str)
    if d.project.str.strip().eq('').any():
        raise ValueError('Empty project identifier')
    if d.duplicated(['project', 'month']).any():
        raise ValueError('Duplicate project-month')
    for c in REQUIRED[2:]:
        d[c] = pd.to_numeric(d[c], errors='raise')
        if not np.isfinite(d[c]).all() or (d[c] < 0).any() or not d[c].eq(np.floor(d[c])).all():
            raise ValueError(f'{c} must contain nonnegative integer counts')
    if not d.stock_open.add(d.inflows).sub(d.sales).eq(d.stock_close).all():
        raise ValueError('Stock balance failed: open + inflows - sales != close')
    report = {'input_rows': len(d), 'excluded_cam': int(d.project.eq('CAM').sum()),
              'review_rows': int(d.review_units.gt(0).sum()), 'gaps': []}
    d = d[d.project.ne('CAM')].sort_values(['project', 'month'])
    active = []
    for project, g in d.groupby('project', sort=True):
        # Months before commercial entry are not zero-demand observations.
        entered = g.stock_open.add(g.inflows).gt(0)
        if not entered.any():
            continue
        g = g.loc[entered.idxmax():].copy()
        expected = pd.date_range(g.month.min(), g.month.max(), freq='MS')
        if len(expected) != len(g):
            raise ValueError(f'Missing monthly observations: {project}')
        if not g.stock_open.iloc[1:].reset_index(drop=True).eq(
            g.stock_close.iloc[:-1].reset_index(drop=True)).all():
            raise ValueError(f'Stock continuity failed for {project}')
        active.append(g)
    if report['gaps']:
        raise ValueError(f'Missing monthly observations: {report["gaps"]}')
    if not active:
        raise ValueError('No eligible department inventory')
    d = pd.concat(active, ignore_index=True)
    stale = d.groupby('project').month.max()
    stale = stale[stale.lt(d.month.max())].index.tolist()
    if stale:
        raise ValueError(f'Projects missing latest monthly observation: {stale}')
    report.update(active_rows=len(d), projects=d.project.nunique(),
                  reviewed_projects=sorted(d.loc[d.review_units.gt(0), 'project'].unique().tolist()))
    canonical = d.to_csv(index=False, date_format='%Y-%m-%d', float_format='%.10g')
    report['sha256'] = hashlib.sha256(canonical.encode()).hexdigest()
    return d, report


def design(panel: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    rows = []
    for project, g in panel.groupby('project', sort=True):
        g = g.sort_values('month').reset_index(drop=True)
        # Quarantine entire projects with unresolved sales/inventory evidence.
        if g.review_units.gt(0).any():
            continue
        for i in range(len(g)):
            r = g.iloc[i]
            stock = float(r.stock_close)
            if stock <= 0:
                continue
            recent = g.sales.iloc[max(0, i-2):i+1].to_numpy(float)
            x = dict(project=project, month=r.month, stock=stock, sales=float(r.sales),
                     mean3=float(recent.mean()), trend=float(recent[-1]-recent[0]),
                     absorption=float(r.sales / max(r.stock_open+r.inflows, 1)),
                     log_stock=float(np.log1p(stock)), age=float(i),
                     month_sin=float(np.sin(2*np.pi*r.month.month/12)),
                     month_cos=float(np.cos(2*np.pi*r.month.month/12)))
            for h in range(1, cfg.horizon+1):
                x[f'y{h}'] = np.nan
            if i+cfg.horizon < len(g):
                future = g.iloc[i+1:i+cfg.horizon+1]
                # Forecast scope: existing stock only, without announced additions.
                if future.inflows.sum() == 0 and future.sales.sum() <= stock:
                    cumulative = future.sales.cumsum().to_numpy(float)
                    for h, value in enumerate(cumulative, 1):
                        x[f'y{h}'] = value / stock
            rows.append(x)
    return pd.DataFrame(rows, columns=['project', 'month', 'stock', *FEATURES,
                                       *[f'y{h}' for h in range(1, cfg.horizon+1)]])


def fit_predict(panel: pd.DataFrame, origin: pd.Timestamp, cfg: Config):
    """All fitting, feature transforms and outcomes are restricted to origin."""
    observed = panel[panel.month.le(origin)]
    matrix = design(observed, cfg)
    current = matrix[matrix.month.eq(origin)].copy()
    target_cols = [f'y{h}' for h in range(1, cfg.horizon+1)]
    train = matrix.dropna(subset=target_cols)
    train = train[train.age.ge(2)]
    # Even without ML, projects with zero stock have exact zero forecasts.
    quarantined = set(observed.loc[observed.review_units.gt(0), 'project'])
    zero = observed[observed.month.eq(origin) & observed.stock_close.eq(0)
                    & ~observed.project.isin(quarantined)]
    meta = {'origin': str(origin.date()), 'train_rows': len(train), 'features': FEATURES,
            'config': asdict(cfg), 'train_feature_max': None, 'train_outcome_max': None,
            'unavailable': {}, 'clusters': [], 'feature_importance': {}}
    if len(train):
        meta['train_feature_max'] = str(train.month.max().date())
        meta['train_outcome_max'] = str((train.month.max()+pd.DateOffset(months=cfg.horizon)).date())
    models = {}
    gmm_prob = None
    if len(train) >= cfg.min_train_rows and len(current):
        x, y = train[FEATURES].to_numpy(float), train[target_cols].to_numpy(float)
        scaler = RobustScaler().fit(x)
        z = scaler.transform(x)
        choices, bic_audit = [], []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            for k in range(1, min(cfg.max_clusters, max(1, len(train)//cfg.min_train_rows))+1):
                gm = GaussianMixture(k, covariance_type='diag', reg_covar=1e-3,
                                     n_init=3, random_state=cfg.seed).fit(z)
                component_support = gm.predict_proba(z).sum(axis=0)
                supported = bool(gm.converged_ and component_support.min() >= cfg.min_cluster_rows)
                bic_audit.append(dict(k=k, bic=float(gm.bic(z)), eligible=supported,
                                      minimum_support=float(component_support.min())))
                if supported:
                    choices.append((float(gm.bic(z)), gm))
        meta['bic'] = bic_audit
        if choices:
            _, gm = min(choices, key=lambda pair: pair[0])
            prob = gm.predict_proba(z)
            support = prob.sum(axis=0)
            # Shrink poorly supported components towards the pooled outcome mean.
            rates = (prob.T @ y + 5*y.mean(axis=0)) / (support[:, None]+5)
            gmm_prob = gm.predict_proba(scaler.transform(current[FEATURES].to_numpy(float)))
            models['gmm_analog'] = (gmm_prob @ rates) * current.stock.to_numpy()[:, None]
            for k in range(gm.n_components):
                meta['clusters'].append({'state': k, 'effective_rows': float(support[k]),
                    'profile': dict(zip(FEATURES, (prob[:, k] @ x / support[k]).tolist())),
                    'cumulative_rates': rates[k].tolist()})
            models['_gmm_bundle'] = (scaler, gm, rates)
            meta['cluster_diagnostics'] = dict(chosen_k=gm.n_components,
                tested_max_k=max(r['k'] for r in bic_audit), at_search_boundary=gm.n_components==max(r['k'] for r in bic_audit),
                minimum_support=float(support.min()), converged=bool(gm.converged_))
        else:
            meta['unavailable']['gmm_analog'] = 'No converged fit'
        rf = RandomForestRegressor(n_estimators=80, max_depth=5, min_samples_leaf=5,
                                   random_state=cfg.seed, n_jobs=1).fit(x, y)
        pred = np.asarray(rf.predict(current[FEATURES].to_numpy(float))).reshape(len(current), cfg.horizon)
        models['random_forest'] = pred * current.stock.to_numpy()[:, None]
        models['_rf_bundle'] = rf
        meta['feature_importance'] = dict(zip(FEATURES, rf.feature_importances_.tolist()))
        meta['feature_importance_semantics'] = 'TRAINING_IMPURITY_ON_FRACTION_TARGET_NOT_CAUSAL'
        meta['training_feature_ranges'] = {f: dict(min=float(train[f].min()), max=float(train[f].max())) for f in FEATURES}
        meta['extrapolation'] = [dict(project=r.project, feature=f, value=float(r[f]),
            training_min=meta['training_feature_ranges'][f]['min'], training_max=meta['training_feature_ranges'][f]['max'])
            for _, r in current.iterrows() for f in FEATURES
            if r[f] < train[f].min() or r[f] > train[f].max()]
    else:
        for name in ('gmm_analog', 'random_forest'):
            meta['unavailable'][name] = 'Insufficient mature training rows or current features'
    forecasts = []
    for i, (_, r) in enumerate(current.iterrows()):
        paths = {'mean3': np.arange(1, cfg.horizon+1)*r.mean3}
        g = observed[observed.project.eq(r.project)].sort_values('month')
        if len(g) >= 8:
            with warnings.catch_warnings(record=True) as fit_warnings:
                warnings.simplefilter('always', UserWarning)
                # SSE=0 can make unused ETS information criteria log(0).
                warnings.filterwarnings('ignore', message='divide by zero encountered in log',
                                        category=RuntimeWarning, module=r'statsmodels\.tsa\.holtwinters\.model')
                try:
                    series = pd.Series(g.sales.to_numpy(float), index=pd.DatetimeIndex(g.month, freq='MS'))
                    ets = ExponentialSmoothing(series, trend='add', seasonal=None,
                                               initialization_method='estimated').fit(optimized=True)
                    optimizer = getattr(ets, 'mle_retvals', None)
                    if optimizer is not None and not optimizer.get('success', True):
                        raise ValueError('ETS optimizer did not converge')
                    models.setdefault('_ets_bundles', {})[r.project] = ets
                    paths['ets'] = np.maximum(ets.forecast(cfg.horizon).to_numpy(), 0).cumsum()
                except (ValueError, FloatingPointError) as exc:
                    meta['unavailable'][f'ets:{r.project}'] = f'{type(exc).__name__}: {exc}'
                if fit_warnings:
                    meta.setdefault('fit_warnings', {})[f'ets:{r.project}'] = sorted(set(str(w.message) for w in fit_warnings))
        for name in ('gmm_analog', 'random_forest'):
            if name in models and len(g) >= cfg.min_project_history:
                paths[name] = models[name][i]
            elif name in models:
                meta['unavailable'][f'{name}:{r.project}'] = 'Insufficient project history; baseline fallback'
        for name, path in paths.items():
            if not np.isfinite(path).all():
                meta['unavailable'][f'{name}:{r.project}'] = 'Nonfinite forecast rejected'
                continue
            path = np.maximum.accumulate(np.clip(path, 0, r.stock))
            for h, value in enumerate(path, 1):
                forecasts.append(dict(project=r.project, origin=origin, horizon=h, model=name,
                    prediction=float(value), stock=float(r.stock), stock_remaining=float(r.stock-value),
                    state_probabilities=json.dumps(gmm_prob[i].tolist()) if name=='gmm_analog' else None))
    for _, r in zero.iterrows():
        for h in range(1, cfg.horizon+1):
            forecasts.append(dict(project=r.project, origin=origin, horizon=h, model='mean3',
                prediction=0., stock=0., stock_remaining=0., state_probabilities=None))
    return pd.DataFrame(forecasts), meta, {k: v for k, v in models.items() if k.startswith('_')}


def metrics(rows: pd.DataFrame) -> dict:
    error = rows.prediction - rows.actual
    total = float(rows.actual.sum())
    return {'rows': len(rows), 'origins': int(rows.origin.nunique()),
            'mae': float(error.abs().mean()), 'bias': float(error.mean()),
            'wape': float(error.abs().sum()/total) if total > 0 else None}


def attach_intervals(predictions: pd.DataFrame, errors: pd.DataFrame, cfg: Config):
    from .evaluation import nonoverlapping_origins
    out = predictions.copy()
    for coverage in (80, 95):
        out[f'lower{coverage}'] = np.nan
        out[f'upper{coverage}'] = np.nan
    out['interval_errors'] = 0
    out['interval_origins'] = 0
    out['interval_nonoverlap_origins'] = 0
    out['interval_status'] = 'INSUFFICIENT_TEMPORAL_SUPPORT'
    for idx, r in out.iterrows():
        pool = errors[errors.model.eq(r.model) & errors.horizon.eq(r.horizon)
                      & errors.outcome_month.le(r.origin) & errors.origin.lt(r.origin)]
        out.loc[idx, 'interval_errors'] = len(pool)
        origins = int(pool.origin.nunique())
        separate = nonoverlapping_origins(pool.origin, int(r.horizon))
        out.loc[idx, 'interval_origins'] = origins
        out.loc[idx, 'interval_nonoverlap_origins'] = separate
        if len(pool) < cfg.min_interval_errors or origins < cfg.min_interval_origins or separate < 2:
            continue
        out.loc[idx, 'interval_status'] = 'EMPIRICAL_POOLED_NOT_GUARANTEED'
        absolute = (pool.actual-pool.prediction).abs().to_numpy()
        for coverage in (80, 95):
            # Empirical out-of-sample error bands; not an exchangeability guarantee.
            margin = float(np.quantile(absolute, min(1, (len(pool)+1)*coverage/100/len(pool)), method='higher'))
            out.loc[idx, f'lower{coverage}'] = max(0., r.prediction-margin)
            out.loc[idx, f'upper{coverage}'] = min(r.stock, r.prediction+margin)
    return out


def evaluate(panel: pd.DataFrame, cfg: Config):
    cfg.validate()
    latest = panel.month.max()
    eligible = sorted(m for m in panel.month.unique()
                      if pd.Timestamp(m)+pd.DateOffset(months=cfg.horizon) <= latest)
    origins = eligible[-cfg.backtest_origins:]
    test_set = set(origins[-cfg.test_origins:])
    test_start = pd.Timestamp(min(test_set)) if test_set else latest
    rows, evidence = [], []
    for month in origins:
        origin = pd.Timestamp(month)
        predictions, meta, _ = fit_predict(panel, origin, cfg)
        evidence.append(meta)
        for _, r in predictions.iterrows():
            future = panel[panel.project.eq(r.project) & panel.month.gt(origin)
                           & panel.month.le(origin+pd.DateOffset(months=int(r.horizon)))]
            if len(future) != r.horizon:
                continue
            # No score for horizons whose inventory scope does not match the scenario.
            if future.inflows.sum() > 0 or future.review_units.gt(0).any() or future.sales.sum() > r.stock:
                continue
            record = r.to_dict()
            record.update(actual=float(future.sales.sum()), outcome_month=future.month.max(),
                          partition=('test' if month in test_set else
                                     'validation' if future.month.max() <= test_start else 'embargo'))
            rows.append(record)
    bt = pd.DataFrame(rows)
    if bt.empty:
        raise ValueError('No mature temporal evaluation rows; need more monthly history')
    bt = attach_intervals(bt, bt, cfg)
    summaries = []
    for (partition, model, h), g in bt.groupby(['partition', 'model', 'horizon']):
        result = dict(partition=partition, model=model, horizon=int(h), **metrics(g))
        for coverage in (80, 95):
            available = g.dropna(subset=[f'lower{coverage}', f'upper{coverage}'])
            result[f'coverage{coverage}'] = float((available.actual.ge(available[f'lower{coverage}'])
                & available.actual.le(available[f'upper{coverage}'])).mean()) if len(available) else None
            result[f'interval_rows{coverage}'] = len(available)
        summaries.append(result)
    from .evaluation import select_policy
    selected = select_policy(bt, cfg)['selected_model']
    return bt, pd.DataFrame(summaries), evidence, selected
