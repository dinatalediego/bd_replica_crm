"""Strict versioned JSON contracts, cross references and numerical invariants."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from importlib.resources import files
from jsonschema import Draft202012Validator, FormatChecker

MAX_JSON_BYTES = 4_000_000


class PackError(ValueError):
    """Safe error for users; never embeds source records or credential values."""


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict_load(raw: bytes):
    if len(raw) > MAX_JSON_BYTES:
        raise PackError('JSON exceeds size budget')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PackError('Duplicate JSON key')
            result[key] = value
        return result
    def reject(_):
        raise PackError('Non-finite JSON number')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
        # Also detects 1e999 which the standard decoder converts to infinity.
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PackError('Invalid JSON encoding or structure') from exc


def validate(kind, value):
    schema = json.loads(files(__package__).joinpath(f'schemas/{kind}.schema.json').read_text())
    try:
        canonical(value)
    except (ValueError, TypeError, RecursionError) as exc:
        raise PackError('Non-JSON value') from exc
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        path = '/'.join(map(str, errors[0].absolute_path))
        raise PackError(f'{kind}: invalid field at {path or "root"}')


def validate_snapshot(snapshot):
    validate('snapshot', snapshot)
    seen = set()
    as_of = date.fromisoformat(snapshot['as_of'])
    for row in snapshot['rows']:
        key = row['project'], row['period']
        period = date.fromisoformat(row['period'])
        if key in seen or period.day != 1 or (period.year, period.month) >= (as_of.year, as_of.month):
            raise PackError('Duplicate or incomplete monthly period')
        seen.add(key)
        if row['review_units'] or row['sales'] > row['stock_open']:
            raise PackError('Unresolved review units or invalid sales population')
        if not math.isclose(row['stock_open'] - row['sales'], row['stock_close'], abs_tol=1e-8):
            raise PackError('Stock reconciliation failed')
    for project in {r['project'] for r in snapshot['rows']}:
        rows = sorted((r for r in snapshot['rows'] if r['project'] == project), key=lambda r:r['period'])
        if len(rows) < 7:
            raise PackError('At least seven complete months per project required')
        for before, after in zip(rows, rows[1:]):
            a, b = date.fromisoformat(before['period']), date.fromisoformat(after['period'])
            if (b.year*12+b.month)-(a.year*12+a.month) != 1:
                raise PackError('Missing month in project series')
            if not math.isclose(before['stock_close'], after['stock_open'], abs_tol=1e-8):
                raise PackError('This v1 product requires a fixed inventory cohort')


def scenario_value(prediction, stock, multiplier):
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
           for x in (prediction, stock, multiplier)):
        raise PackError('Scenario inputs must be finite numbers')
    if not 0.5 <= multiplier <= 1.5 or not 0 <= prediction <= stock:
        raise PackError('Scenario outside model support')
    return min(stock, prediction * multiplier)


def validate_bundle(packs):
    if set(packs) != {'data','model','story','scenario'}:
        raise PackError('Incomplete bundle')
    for kind, pack in packs.items():
        validate(f'{kind}-pack', pack)
    data, model, story, scenarios = (packs[k] for k in ('data','model','story','scenario'))
    if model['data_pack_id'] != data['id'] or story['data_pack_id'] != data['id']:
        raise PackError('Broken data reference')
    if story['model_pack_id'] != model['id'] or scenarios['model_pack_id'] != model['id']:
        raise PackError('Broken model reference')
    for pack in packs.values():
        if pack['classification'] != data['classification'] or pack['provenance'] != data['provenance']:
            raise PackError('Mixed provenance or classification')
    snapshot = dict(schema_version='1.0.0',source=data['provenance']['source'],
                    semantics=data['provenance']['semantics'],as_of=data['provenance']['as_of'],rows=data['rows'])
    validate_snapshot(snapshot)
    from .factory import demo_snapshot
    synthetic = snapshot == demo_snapshot()
    expected_class = 'SYNTHETIC' if synthetic else 'PRIVATE'
    expected_label = 'DEMO / SYNTHETIC DATA' if synthetic else 'PRIVATE / HISTÓRICO RECONSTRUIDO'
    if data['classification'] != expected_class or any(p['label'] != expected_label for p in packs.values()):
        raise PackError('Classification or visible label mismatch')
    if snapshot['semantics'] == 'SYNTHETIC_DEMO' and not synthetic:
        raise PackError('Unrecognized synthetic provenance')
    if digest(snapshot) != data['provenance']['dataset_sha256']:
        raise PackError('Dataset fingerprint mismatch')
    def index(items):
        ids = [x['id'] for x in items]
        if len(ids) != len(set(ids)):
            raise PackError('Duplicate object identity')
        return set(ids)
    indicators = index(data['indicators'])
    findings = index(story['findings'])
    index(story['decisions']); index(story['wisdom_cards'])
    scenario_ids = index(scenarios['scenarios'])
    results = {r['project']:r for r in model['results']}
    if len(results) != len(model['results']):
        raise PackError('Duplicate model result')
    for row in model['results']:
        if row['prediction'] > row['stock']:
            raise PackError('Prediction exceeds inventory')
    from statistics import mean
    projects = {r['project'] for r in data['rows']}
    if set(results) != projects:
        raise PackError('Model population mismatch')
    errors = []
    expected_indicators = {}
    for project in projects:
        rows = sorted((r for r in data['rows'] if r['project'] == project), key=lambda r:r['period'])
        velocity = mean(r['sales'] for r in rows[-3:])
        last = rows[-1]
        result = results[project]
        if (result['origin'] != last['period'] or result['stock'] != last['stock_close']
                or not math.isclose(result['prediction'], min(last['stock_close'],velocity), abs_tol=1e-8)):
            raise PackError('Model result does not match source')
        expected_indicators.update({f'{project}-stock':last['stock_close'],
                                    f'{project}-velocity':velocity,f'{project}-sales':last['sales']})
        for i in range(len(rows)-3,len(rows)):
            estimate = min(rows[i]['stock_open'],mean(r['sales'] for r in rows[i-3:i]))
            errors.append(abs(estimate-rows[i]['sales']))
    if indicators != set(expected_indicators):
        raise PackError('Indicator population mismatch')
    for item in data['indicators']:
        if not math.isclose(item['value'],expected_indicators[item['id']],abs_tol=1e-8):
            raise PackError('Indicator calculation mismatch')
    if len(model['metrics']) != 1 or model['metrics'][0]['name'] != 'MAE' or model['metrics'][0]['n'] != len(errors) or not math.isclose(model['metrics'][0]['value'],mean(errors),abs_tol=1e-8):
        raise PackError('Evaluation metric does not match temporal holdout')
    if model['training_period'] != {'start':min(r['period'] for r in data['rows']), 'end':max(r['period'] for r in data['rows'])}:
        raise PackError('Model fitting period mismatch')
    for item in scenarios['scenarios']:
        if item['model_pack_id'] != model['id'] or item['project'] not in results:
            raise PackError('Scenario reference missing')
        result = results[item['project']]
        expected = scenario_value(result['prediction'],result['stock'],item['multiplier'])
        if not math.isclose(expected,item['prediction'],abs_tol=1e-8):
            raise PackError('Scenario calculation mismatch')
    for item in story['steps'] + story['findings']:
        if not set(item['indicator_ids']) <= indicators:
            raise PackError('Missing indicator reference')
    for item in story['decisions']:
        if item['finding_id'] not in findings or item['model_pack_id'] != model['id'] or not set(item['scenario_ids']) <= scenario_ids:
            raise PackError('Broken decision evidence chain')
    for item in story['wisdom_cards']:
        if item['finding_id'] not in findings:
            raise PackError('Broken wisdom evidence chain')
