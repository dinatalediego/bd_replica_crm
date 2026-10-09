"""A complete, small analytical factory over fixed-cohort monthly sales."""
from __future__ import annotations

from statistics import mean
from .contracts import digest, validate_snapshot, validate_bundle, scenario_value

QUESTION = '¿Tener menos stock significa que estamos vendiendo mejor?'


def demo_snapshot():
    """Authored synthetic fixture; never derived from a CRM record."""
    rows = []
    for project, sales in [('DEMO-A',[8,9,7,8,6,5,4,3,3]),
                           ('DEMO-B',[4,5,5,6,6,7,7,8,8])]:
        stock = 120
        for month, sold in enumerate(sales, 1):
            rows.append(dict(project=project,period=f'2026-{month:02d}-01',
                             stock_open=stock,sales=sold,stock_close=stock-sold,review_units=0))
            stock -= sold
    return dict(schema_version='1.0.0',source='Authored deterministic fixture housing-v1',
                semantics='SYNTHETIC_DEMO',as_of='2026-10-01',rows=rows)


def build_products(snapshot, *, generated_at, version='1.0.0'):
    validate_snapshot(snapshot)
    # Only the exact fixture is eligible for the public demo path. User-provided
    # classification or anonymized names cannot grant publication eligibility.
    synthetic = snapshot == demo_snapshot()
    if snapshot['semantics'] == 'SYNTHETIC_DEMO' and not synthetic:
        raise ValueError('Unrecognized synthetic fixture; public provenance cannot be self-certified')
    classification = 'SYNTHETIC' if synthetic else 'PRIVATE'
    label = 'DEMO / SYNTHETIC DATA' if synthetic else 'PRIVATE / HISTÓRICO RECONSTRUIDO'
    provenance = dict(source=snapshot['source'],semantics=snapshot['semantics'],
        as_of=snapshot['as_of'],generated_at=generated_at,dataset_sha256=digest(snapshot),
        transformation='Meses completos; cohorte fija; media móvil de tres meses limitada por stock.',
        limitations=['Datos inventados exclusivamente para demostración.' if synthetic else
                    'Historia revisada retrospectivamente; no representa lo conocido en cada corte.',
                    'Sin reposiciones, anulaciones intermedias ni cambios de universo.'])
    def base(kind):
        return dict(schema_version='1.0.0',kind=kind,id=f'housing-{kind}',version=version,
                    classification=classification,label=label,provenance=provenance.copy())
    indicators, results, errors = [], [], []
    for project in sorted({r['project'] for r in snapshot['rows']}):
        rows = sorted((r for r in snapshot['rows'] if r['project']==project),key=lambda r:r['period'])
        # Last three months held out. Fixed, declared algorithm; no tuning on holdout.
        for i in range(len(rows)-3,len(rows)):
            estimate=min(rows[i]['stock_open'],mean(r['sales'] for r in rows[i-3:i]))
            errors.append(abs(estimate-rows[i]['sales']))
        last=rows[-1]
        velocity=mean(r['sales'] for r in rows[-3:])
        results.append(dict(project=project,origin=last['period'],horizon=1,
                            prediction=min(last['stock_close'],velocity),stock=last['stock_close']))
        for suffix,name,value,unit,method in [
            ('stock','Stock al cierre',last['stock_close'],'unidades','Saldo de cohorte al final del mes.'),
            ('velocity','Ritmo reciente',velocity,'unidades/mes','Media aritmética de tres meses completos.'),
            ('sales','Ventas del último mes',last['sales'],'unidades','Ventas del último mes completo.')]:
            indicators.append(dict(id=f'{project}-{suffix}',name=name,value=value,unit=unit,
                                   period=last['period'],methodology=method))
    data={**base('data'),'question':QUESTION,'grain':'project_month','dimensions':['project','period'],
          'metrics':['stock_open','sales','stock_close'],'rows':snapshot['rows'],'indicators':indicators,
          'quality':dict(status='PASS',checks=['Grano único','Meses consecutivos completos','Stock conciliado','Sin unidades pendientes de revisión'],
                         freshness=f"Corte {snapshot['as_of']}; no implica actualización en tiempo real.")}
    model={**base('model'),'data_pack_id':data['id'],'question':'¿Qué ritmo sugiere el trimestre reciente para el siguiente mes?',
        'family':'moving_average_3','target':'Ventas del siguiente mes; unidades de la cohorte disponible.',
        'features':['sales_lag_1','sales_lag_2','sales_lag_3','stock_close'],
        'execution':'external_python','training_period':dict(start=min(r['period'] for r in snapshot['rows']),end=max(r['period'] for r in snapshot['rows'])),
        'parameters':dict(window=3,stock_cap=True),
        'metrics':[dict(name='MAE',value=mean(errors),unit='unidades/mes',partition='temporal_holdout',n=len(errors),
                        interpretation='Error absoluto medio: distancia típica en unidades sobre los últimos tres meses de cada proyecto; algoritmo fijo, actualización secuencial.')],
        'results':results,'uncertainty':dict(status='NOT_ESTIMATED',explanation='Muestra pequeña: no se publican intervalos calibrados. Los escenarios no son intervalos de confianza.'),
        'evidence_type':'predictive','validation':'Últimos tres meses por proyecto; cada origen usa solo tres meses anteriores. Baseline simple sin selección de hiperparámetros. Historia sintética o revisada: no certifica calidad prospectiva.',
        'assumptions':['El ritmo reciente es una referencia útil.','No entran nuevas unidades.','Ventas acotadas al stock disponible.'],
        'limitations':['No estima elasticidad ni causalidad.','No aprende cambios de régimen o estacionalidad.','No constituye recomendación de pricing.'],
        'explanation':'Promedia las ventas de los tres meses anteriores y aplica el límite del stock. Es un baseline auditable, no ML entrenado.',
        'allowed_controls':[dict(id='velocity_multiplier',min=0.5,max=1.5,default=1.0,
                                 meaning='Supuesto del usuario sobre ritmo: no es un coeficiente estimado ni efecto causal.') ]}
    scenarios=[]
    for result in results:
        for name,multiplier in [('slow',0.75),('base',1.0),('fast',1.25)]:
            scenarios.append(dict(id=f"{result['project']}-{name}",model_pack_id=model['id'],project=result['project'],
                multiplier=multiplier,prediction=scenario_value(result['prediction'],result['stock'],multiplier),
                explanation=f'Ritmo multiplicado por {multiplier}; acotado por inventario. Supuesto, no probabilidad.'))
    scenario={**base('scenario'),'model_pack_id':model['id'],'scenarios':scenarios}
    findings=[]
    for result in results:
        project=result['project']
        rows=sorted((r for r in snapshot['rows'] if r['project']==project),key=lambda r:r['period'])
        recent=mean(r['sales'] for r in rows[-3:]); previous=mean(r['sales'] for r in rows[-6:-3])
        findings.append(dict(id=f'{project}-finding',statement=f'{project}: ritmo reciente {recent:.2f} unidades/mes frente a {previous:.2f} en el trimestre anterior; stock final {result["stock"]:g}.',
            indicator_ids=[f'{project}-stock',f'{project}-velocity'],evidence_type='descriptive',
            confidence=dict(status='NOT_ASSESSED',reason='Comparación aritmética; no prueba significancia ni causalidad.'),
            possible_explanations=['Composición del stock disponible','Estacionalidad','Cambios de demanda'],
            cannot_conclude=['Que precio sea la causa.','Que stock pequeño implique demanda fuerte.']))
    story={**base('story'),'data_pack_id':data['id'],'model_pack_id':model['id'],'question':QUESTION,
        'steps':[dict(title='La pregunta',body='El stock es un saldo. El ritmo mide un flujo. Para entender la evolución necesitamos ambos.',indicator_ids=[]),
                 dict(title='La evidencia',body='Compara el inventario final con las ventas mensuales y su ritmo reciente. Todos los períodos son meses completos.',indicator_ids=[i['id'] for i in indicators]),
                 dict(title='El modelo',body=model['explanation'],indicator_ids=[]),
                 dict(title='El experimento',body='Cambia el supuesto de ritmo y compara con el escenario original. No estás midiendo un efecto causal.',indicator_ids=[])],
        'findings':findings,
        'decisions':[dict(id=f"{f['id']}-decision",question='¿Qué investigar antes de cambiar precios?',finding_id=f['id'],model_pack_id=model['id'],
            scenario_ids=[s['id'] for s in scenarios if s['project']==results[i]['project']],
            options=['Mantener y medir','Revisar composición','Diseñar experimento de precio'],status='REVIEW_REQUIRED',
            recommended_action='Revisar composición y reunir evidencia antes de decidir pricing.',
            objective='Comprender el cambio de ritmo sin atribuir causas no identificadas.',
            constraints=['No ejecutar cambios comerciales automáticamente.','No confundir simulación con evidencia causal.'],owner=None,
            outcome=dict(status='NOT_OBSERVED',value=None)) for i,f in enumerate(findings)],
        'wisdom_cards':[dict(id='stock-is-not-demand',title='Stock no es demanda',finding_id=findings[0]['id'],
            observation='Un saldo menor puede coexistir con un ritmo menor.',caution='No inferir preferencia solo de ventas absolutas.',
            why='La oferta disponible limita lo que puede venderse.',application='Comparar ritmo, composición y exposición antes de recomendar.',
            validation_status='EDUCATIONAL_NOT_VALIDATED_POLICY')],
        'what_we_learned':'Separar saldo, flujo y supuesto evita conclusiones apresuradas.',
        'what_we_do_not_know':'No conocemos el efecto causal del precio ni la demanda no observada.',
        'next_test':'Congelar pronósticos antes del próximo mes y medir sus errores con el mismo universo.'}
    packs=dict(data=data,model=model,story=story,scenario=scenario)
    validate_bundle(packs)
    return packs
