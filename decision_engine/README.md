# CYGNUS Decision Engine

Sistema para convertir el warehouse comercial en decisiones accionables.

## Propósito

Este módulo NO reemplaza `bd_replica_crm`. Lo consume como **data foundation** y agrega una capa de inteligencia orientada a decisiones:

`raw_cygnus -> staging -> analytics -> semantic/features -> models -> decision_engine -> actions -> feedback`

El objetivo no es crear otro dashboard, sino responder de forma trazable:

1. ¿Qué cambió?
2. ¿Por qué importa?
3. ¿Qué debería hacer el equipo comercial?
4. ¿Cuál es el impacto económico esperado?
5. ¿Qué ocurrió después de ejecutar o ignorar la recomendación?

## Alcance v0.1

- catálogo de decisiones comerciales;
- priorización por impacto, factibilidad y madurez de datos;
- contratos de decisión y recomendación;
- motor de reglas baseline;
- registro de decisiones;
- API-ready domain layer;
- esquema SQL para recomendaciones y feedback;
- tests unitarios;
- roadmap de 90 días.

## Primeras decisiones priorizadas

1. Riesgo de caída de separaciones.
2. Leads que deben ser trabajados hoy.
3. Unidades con riesgo de envejecimiento de stock.
4. Proyecto con desviación de absorción.
5. Probabilidad de cumplimiento de meta mensual.
6. Lead x asesor recomendado.
7. Lead x proyecto/unidad recomendado.
8. Descuento recomendado sujeto a margen y velocidad.
9. Presupuesto de marketing por canal/proyecto.
10. Alertas de calidad/reconciliación que invalidan decisiones.

## Principios

- **Baseline antes de ML**: toda decisión debe tener una regla simple de comparación.
- **Tiempo correcto**: validación temporal; nunca random split para decisiones comerciales dependientes del tiempo.
- **No leakage**: ninguna feature puede usar información posterior al instante de decisión.
- **Human-in-the-loop**: v0.x recomienda; no ejecuta acciones comerciales irreversibles.
- **Feedback obligatorio**: toda recomendación debe poder asociarse a acción y resultado.
- **Valor económico**: AUC/F1 no son el objetivo final; se mide uplift, margen, conversión, tiempo y stock.
- **Trazabilidad**: guardar versión de datos, modelo, regla y evidencia.

## Estructura

```text
decision_engine/
├── README.md
├── pyproject.toml
├── config/
│   └── decisions.yml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DECISION_MAP.md
│   └── ROADMAP_90_DAYS.md
├── sql/
│   └── 00_decision_control.sql
├── src/cygnus_decision_engine/
│   ├── __init__.py
│   ├── contracts.py
│   ├── registry.py
│   └── rules.py
└── tests/
    └── test_rules.py
```

## Relación con MEDALLIO

MEDALLIO mantiene la verdad analítica y la reconciliación. Este módulo asume que métricas críticas como venta canónica, stock físico y absorción provienen de tablas analíticas validadas. El Decision Engine no debe reconstruir esas reglas desde Power BI ni desde notebooks.

## Próximo hito

Conectar el primer caso real: **riesgo de caída de separaciones activas**, empezando por baseline explicable y luego modelo survival/classification con validación temporal.
