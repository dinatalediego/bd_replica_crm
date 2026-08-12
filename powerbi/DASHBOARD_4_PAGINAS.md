# Medallio Data & Decision Control Tower — propuesta de 4 páginas

## Navegación
`01 Data Platform` → `02 Data Quality` → `03 Models & MLOps` → `04 Decisions & Learning`

El flujo visual replica el sistema de decisión:

```text
DATOS → CALIDAD → MODELOS → DECISIONES → RESULTADOS → APRENDIZAJE
```

Las páginas 1 y 2 son el Sprint 1 operativo. Las páginas 3 y 4 ya tienen SQL/M/DAX y se poblarán progresivamente.

## Diseño común
- Encabezado pequeño: nombre de página + última observación.
- Fila superior: 4–6 KPI cards como máximo.
- Centro: 2–3 visuales para tendencia y distribución.
- Parte inferior: **tabla de excepciones accionables**.
- Slicers laterales o superiores: criticidad, proceso, activo y rango temporal.

## Convención semáforo
- `OK`: verde / estable
- `WARN`: ámbar / requiere seguimiento
- `FAIL`: rojo / riesgo directo
- `UNKNOWN`: gris / observabilidad insuficiente

No usar colores únicamente: mantener siempre etiquetas de estado.

## Jerarquía de atención
1. activo crítico con FAIL
2. activo crítico fuera de SLA
3. schema drift / duplicados / key NULL
4. modelos con scoring fallido o drift
5. baja adopción / bajo feedback
6. valor realizado por debajo del esperado

## Norte del tablero
La plataforma debe evolucionar de:

`¿el job corrió?`

a:

`¿qué decisión comercial podría estar equivocada y qué debemos hacer ahora?`
