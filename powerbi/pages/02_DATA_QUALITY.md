# Página 02 — Data Quality

## Pregunta ejecutiva
**¿La data que llegó es suficientemente confiable para análisis, C-level y modelos?**

## Fila 1 — KPIs
1. `Estado Calidad Datos`
2. `Data Quality Score`
3. `Checks Críticos FAIL 24h`
4. `Activos con Duplicados`
5. `Activos con Keys NULL`
6. `Activos con Schema Drift`

## Fila 2 — Dimensiones de calidad
- Barras: cantidad de FAIL por `quality_dimension`.
- Matriz: asset × dimensión con PASS/WARN/FAIL.
- Tendencia: `Pass Rate 24h` / por día.

Dimensiones mínimas:
- freshness
- reconciliation
- completeness
- uniqueness
- schema

## Fila 3 — Excepciones accionables
Columnas:
- asset_key
- criticality
- check_name
- status
- metric_value
- threshold_value
- details
- business_impact
- downstream_products

## Uso recomendado
El control profundo incluye `COUNT(*)`, duplicados y schema drift. No se ejecuta cada hora; se ejecuta diario/manual para no convertir observabilidad en carga innecesaria sobre Redshift.
