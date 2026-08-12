# Sprint 1 — Medallio Data & Decision Control Tower

## Objetivo
Convertir la réplica Redshift → PostgreSQL en una plataforma observable y lista para Power BI, sin perder el enfoque comercial.

El tablero debe responder, en este orden:

1. **¿Los datos llegaron?**
2. **¿Llegaron a tiempo?**
3. **¿Llegaron bien?**
4. **¿Qué reportes/KPIs de negocio están comprometidos si algo falla?**
5. **¿Los modelos están vigentes?**
6. **¿Las recomendaciones están generando valor?**

Sprint 1 deja operativas las preguntas 1–4 y prepara las 5–6.

## Arquitectura

```text
Redshift Cygnus
      │
      ▼
PostgreSQL medallio_dw
      │
      ├── raw_cygnus
      ├── etl_control
      ├── observability          ← Sprint 1
      │     ├── asset_registry
      │     ├── asset_snapshots
      │     ├── quality_checks
      │     └── vistas Power BI
      ├── model_control          ← preparado
      ├── decision_intelligence  ← preparado
      └── experiments            ← preparado
              │
              ▼
      Power BI Control Tower
      01 Data Platform
      02 Data Quality
      03 Models & MLOps
      04 Decisions & Learning
```

## Dos niveles de observabilidad

### Hourly
Ligero. Se ejecuta después de la réplica horaria y registra:
- último run
- última sincronización exitosa
- filas cargadas en el último run
- watermark origen/destino
- lag de replicación
- SLA de freshness
- estado operacional
- impacto de negocio asociado al activo

No ejecuta conteos exactos completos ni búsqueda de duplicados.

### Deep
Más costoso. Ejecuta:
- COUNT(*) origen y destino
- reconciliación de filas
- llaves NULL
- grupos duplicados por `key_columns`
- schema drift (columnas faltantes)

Debe correr diario o manualmente, no cada hora.

## Principio de negocio
Una tabla no es "crítica" porque sea grande. Es crítica si una falla puede provocar una mala decisión.

Ejemplo:

`procesos` → Separaciones / Minutas / Ventas / Caídas → Reporte Comercial → Gerencia.

Por eso `observability.asset_registry` guarda `business_impact` y `downstream_products`.
