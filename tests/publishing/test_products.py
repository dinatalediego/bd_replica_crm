import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest
from replica_cygnus.publishing.archive import build_archive, read_archive, install_archive
from replica_cygnus.publishing.contracts import PackError, strict_load, validate_snapshot, validate_bundle, scenario_value, canonical
from replica_cygnus.publishing.factory import demo_snapshot, build_products
from replica_cygnus.publishing.preview import render

STAMP='2026-10-09T18:00:00Z'


def products(): return build_products(demo_snapshot(),generated_at=STAMP)
def archive(p=None): return build_archive(p or products(),git_commit='a'*40,builder_sha256='b'*64)


def test_factory_manual_values_and_temporal_mae():
    p=products()
    # A errors: 19/3-4, 5-3, 4-3 = 7/3, 2, 1.
    # B errors: 7-19/3, 8-20/3, 8-22/3 = 2/3, 4/3, 2/3.
    assert p['model']['metrics'][0]['value']==pytest.approx(4/3)
    assert p['model']['metrics'][0]['n']==6
    a=p['model']['results'][0]
    assert a['prediction']==pytest.approx(10/3)
    assert a['stock']==67
    assert p['story']['decisions'][0]['outcome']['value'] is None


def test_round_trip_determinism():
    raw=archive()
    assert raw==archive()
    m,p=read_archive(raw)
    assert p==products()
    assert m['classification']=='SYNTHETIC'


@pytest.mark.parametrize('multiplier,expected',[(0.5,2),(1,4),(1.5,5)])
def test_scenario_cap(multiplier,expected):
    assert scenario_value(4,5,multiplier)==expected


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,2,True])
def test_invalid_scenario(value):
    with pytest.raises(PackError): scenario_value(4,5,value)


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":1e999}',b'not json',b'\xff'])
def test_strict_json(raw):
    with pytest.raises(PackError): strict_load(raw)


@pytest.mark.parametrize('mutation',[
    lambda s:s['rows'].append(copy.deepcopy(s['rows'][0])),
    lambda s:s['rows'][0].update(stock_close=999),
    lambda s:s['rows'][0].update(review_units=1),
    lambda s:s['rows'][0].update(period='2026-10-01'),
    lambda s:s['rows'].pop(1),
    lambda s:s.update(schema_version='2.0.0'),
    lambda s:s['rows'][0].update(email='private@example.invalid'),
])
def test_bad_snapshot(mutation):
    s=demo_snapshot();mutation(s)
    with pytest.raises(PackError):validate_snapshot(s)


def test_private_classification_and_no_synthetic_self_certification():
    s=demo_snapshot();s['source']='local aggregate';s['semantics']='RECONSTRUCTED_REVISED_HISTORY'
    assert build_products(s,generated_at=STAMP)['data']['classification']=='PRIVATE'
    s['semantics']='SYNTHETIC_DEMO'
    with pytest.raises(ValueError):build_products(s,generated_at=STAMP)


@pytest.mark.parametrize('mutation',[
    lambda p:p['model'].update(data_pack_id='missing'),
    lambda p:p['story']['steps'][0].update(indicator_ids=['missing']),
    lambda p:p['story']['decisions'][0].update(scenario_ids=['missing']),
    lambda p:p['scenario']['scenarios'][0].update(prediction=999),
    lambda p:p['model']['results'][0].update(prediction=999),
    lambda p:p['model'].update(schema_version='2.0.0'),
])
def test_references_and_semantics(mutation):
    p=products();mutation(p)
    with pytest.raises(PackError):validate_bundle(p)


def rewrite(raw,name,value):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as old,zipfile.ZipFile(out,'w') as new:
        for item in old.infolist():new.writestr(item.filename,value if item.filename==name else old.read(item.filename))
    return out.getvalue()


def test_tampered_archive_rejected_and_previous_install_preserved(tmp_path):
    raw=archive();target=tmp_path/'installed.zip';install_archive(raw,target)
    broken=rewrite(raw,'model.json',b'{}')
    with pytest.raises(PackError):install_archive(broken,target)
    assert target.read_bytes()==raw


@pytest.mark.parametrize('name',['../escape.json','extra.json','data.json'])
def test_archive_entry_policy(name):
    out=io.BytesIO(archive())
    with zipfile.ZipFile(out,'a') as z:z.writestr(name,b'{}')
    with pytest.raises(PackError):read_archive(out.getvalue())


def test_preview_offline_and_escaped():
    p=products();html=render(p)
    assert '<script src=' not in html and '<link ' not in html
    assert 'DEMO / SYNTHETIC DATA' in html
    p['story']['question']='</script><img src=x onerror=alert(1)>'
    html=render(p)
    assert '<img src=x' not in html


def test_no_future_leakage_in_earlier_holdout():
    s=demo_snapshot()
    # Add one sale in last month, adjusting stock; only that target's error changes.
    s['semantics']='RECONSTRUCTED_REVISED_HISTORY';s['source']='private test fixture'
    s['rows'][8]['sales']+=1;s['rows'][8]['stock_close']-=1
    p=build_products(s,generated_at=STAMP)
    assert p['model']['metrics'][0]['value']==pytest.approx(products()['model']['metrics'][0]['value']-1/6)

@pytest.mark.parametrize('mutation',[
    lambda p:p['model']['metrics'][0].update(value=0),
    lambda p:p['data']['indicators'][0].update(value=999),
    lambda p:p['model']['results'][0].update(prediction=1),
    lambda p:p['data'].update(classification='PRIVATE'),
    lambda p:p['story'].update(label='Real production data'),
])
def test_forged_metrics_and_provenance(mutation):
    p=products();mutation(p)
    with pytest.raises(PackError):validate_bundle(p)


def test_feedback_requires_outcome_value_and_unit():
    from replica_cygnus.publishing.contracts import validate
    event=dict(schema_version='1.0.0',archive_sha256='a'*64,decision_id='test',
               event_type='OUTCOME_OBSERVED',occurred_at=STAMP,note='Observed after action; not causal.',value=5,unit='units')
    validate('decision-event',event)
    event['value']=None
    with pytest.raises(PackError):validate('decision-event',event)
