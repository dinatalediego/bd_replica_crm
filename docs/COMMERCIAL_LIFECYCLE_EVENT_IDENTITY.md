# Commercial Lifecycle Event Identity Contract v1

## Hallazgo

`raw_cygnus.procesos.id` no es una llave global.

La validación local del 2026-08-18 encontró 121 grupos de `id` repetido. Los 242 registros afectados no son copias exactas: corresponden a procesos distintos que reutilizan el mismo valor numérico de `id`.

El patrón observado fue una colisión de namespace asociada a `Entrega`: cada `id` repetido aparecía una vez en `Entrega` y una vez en otro proceso (`Separacion`, `Venta`, `Anulacion` o `Aprobacion`). Por ello, `procesos.id` debe conservarse como identificador RAW de origen, pero no debe utilizarse solo como llave de evento corporativa.

## Contrato de identidad

Para el ciclo comercial certificado se utilizan únicamente estos eventos de `procesos`:

- `Separacion`
- `Venta`
- `Anulacion`

La identidad mínima observable del evento es:

```text
(nombre, id)
```

y la identidad persistida/recomendada en ledgers es `source_event_key`, por ejemplo:

```text
separacion:<id>
venta:<id>
anulacion:<id>
```

El gate automático exige que `(nombre, id)` sea único dentro del conjunto de eventos del ciclo. También comprueba una firma más fuerte con `codigo_proforma`, `codigo_unidad`, `fecha_inicio` y `fecha_actualizacion`.

## Granularidad del ciclo

La unidad de negocio certificada es:

```text
(codigo_proforma, codigo_unidad)
```

El gate exige:

- máximo una `Separacion` por par;
- máximo una `Separacion` activa por par;
- cero pares duplicados en `analytics.int_ciclo_comercial_unidad`;
- reconciliación exacta entre separaciones RAW esperadas y `analytics.int_ciclo_comercial_unidad`, después de aplicar `etl_control.business_exclusions`;
- `movement_id` y `source_event_key` únicos en `analytics.fact_movimientos_stock`.

## Regla de fecha de entrada a stock

Se mantiene la regla vigente del proyecto: `fecha_entrada_stock` se basa en la primera `fecha_creacion` observable de `raw_cygnus.proforma_unidad`. Si una separación RAW es anterior a esa fecha, la fecha RAW se preserva y la fecha analítica se ajusta a la entrada a stock, dejando trazabilidad del ajuste.

## Consecuencia de arquitectura

No se debe corregir ni renumerar `raw_cygnus.procesos.id`.

La capa gobernada debe separar:

```text
RAW id de origen
    !=
identidad corporativa del evento
```

Esto permite mantener evidencia fiel del CRM y, al mismo tiempo, construir un ledger determinístico y auditable para absorción, ventas, caídas y modelos posteriores.

## Gate operativo

Ejecutar:

```powershell
python scripts/validate_commercial_lifecycle_grain.py
```

El ciclo solo puede promoverse a CORE cuando no exista ninguna métrica `FAIL`.
