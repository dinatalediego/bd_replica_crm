# Dashboard Power BI — Absorción

Power BI solo consume PostgreSQL.

## 01 | Absorción Ejecutiva

Pregunta:
**¿Qué tan rápido estamos convirtiendo inventario disponible en operaciones?**

KPIs:
- Stock Disponible
- Separadas Activas
- Ventas 30d
- Absorción Neta 30d
- Meses Stock 30d
- Tasa Caída 30d

Visual central:
tendencia de `stock_fin`, `ventas_30d` y `absorcion_neta_30d`.

Tabla de acción:
Proyecto | Stock | Ventas 30d | Absorción 30d | Meses Stock | Caída 30d

## 02 | Inventario & Rotación

Pregunta:
**¿Dónde se está acumulando inventario y dónde está rotando?**

v0.1:
- proyecto;
- available/separated/sold;
- stock inicio/fin;
- altas/separaciones/caídas.

v0.2 añadirá:
tipología, subdivisión, dormitorios, piso y tipo_unidad después del discovery.

## 03 | Conversión & Ciclos

Pregunta:
**¿Qué está ocurriendo entre separación, caída y venta?**

KPIs:
- Separaciones brutas
- Caídas
- Separaciones netas
- Ventas canónicas
- Conversión
- días promedio separación → venta

Agregar un bloque pequeño de confiabilidad:
`qReconciliationHealth`.

No esconder excepciones.

## 04 | Forecast & Decisión

Inicialmente:
estado "modelo aún no publicado".

Después consumirá únicamente PostgreSQL:
- `decision_intelligence.forecast_absorcion`
- riesgo de stock
- recomendaciones de pricing
- escenarios
- valor económico esperado

Power BI NO ejecutará modelos.
