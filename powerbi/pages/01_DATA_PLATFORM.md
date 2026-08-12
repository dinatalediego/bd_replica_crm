# Página 01 — Data Platform

## Pregunta ejecutiva
**¿Puedo confiar ahora mismo en los tableros que consumen esta data?**

## Fila 1 — KPIs
1. `Estado Global Datos`
2. `Freshness Crítica %`
3. `Reliability 24h`
4. `Lag Replicación Máx (min)`
5. `Ejecuciones Fallidas 24h`
6. `Filas Cargadas 24h`

## Fila 2 — Monitoreo
- Línea: `run_date / hora` vs `Ejecuciones Exitosas` y fallidas.
- Barras horizontales: `asset_key` vs `minutes_since_success`, con línea de referencia del SLA.
- Donut o barra 100%: activos por `health_status`.

## Fila 3 — Tabla de excepciones (visual principal)
Columnas:
- criticality
- asset_key
- health_status
- last_success_at
- minutes_since_success
- replication_lag_minutes
- rows_last_run
- business_impact
- downstream_products

Orden: critical > high > medium; FAIL > WARN > OK.

### Regla de negocio
Nunca mostrar una falla técnica sin indicar **qué reporte, KPI o decisión podría estar comprometido**.

## Slicers
- criticality
- business_process
- asset_key
- últimos 7/30/90 días (para tendencias)
