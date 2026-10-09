# Arquitectura y decisiones

Baseline inspeccionado: `3863a03` (main, Medallio OS integrado). Se conservaron
`commercial_forecasting`, `econometric_datasets`, `decision_intelligence`, las
reglas comerciales, los refreshes y todos los contratos actuales de Power BI.

## ADR-PUBLISH-001 — Capa aditiva

No renombrar ni redistribuir todo `src`. La fábrica portable vive en
`replica_cygnus.publishing`; el adaptador local usa el contrato existente
`analytics.comercial_proyecto_mes`. La nueva migración se instala de forma optativa
con `schema_sync --only publishing`. El pipeline horario no cambia.

## ADR-PUBLISH-002 — Snapshot privado, publicación pública sintética

Una agregación todavía puede revelar resultados empresariales. El origen
PostgreSQL es privado; no se publica por defecto. La demo pública tiene datos
inventados desde cero y una identificación visible constante. No se usa CRM,
PII, credenciales, VPN ni acceso a Medallio para abrir la demo.

## ADR-PUBLISH-003 — Registro de artefactos inmutables

Un registro JSONB conserva cada release completo y su SHA; vistas exponen
productos sin duplicar tablas de modelos existentes. La inserción es transaccional
con clave SHA, idempotente para idénticos bytes; update/delete/truncate se rechazan.
La BD es memoria privada, no un endpoint público. El propietario de la BD sigue
pudiendo cambiar sus permisos/DDL; los triggers no sustituyen administración.

## ADR-PUBLISH-004 — Evidencia multidimensional

No implementar L0–L6 como puntuación universal. Separar tipo de evidencia,
semántica temporal, evaluación, incertidumbre, limitaciones y estado de decisión.
La sabiduría requiere aprendizaje contrastado con outcomes; una tarjeta educativa
se etiqueta como tal. Este criterio precisa la propuesta aprobada sin rebajar rigor.

## ADR-PUBLISH-005 — Una familia completa antes de muchas superficiales

`moving_average_3` conecta todos los objetos y tiene prueba temporal determinista.
No inventar elasticidades ni exportar estimadores Python al dispositivo. El trabajo
ML existente permanece disponible localmente; futuras familias requieren un
adaptador específico que preserve evidencia del productor, sin reinterpretarla.

## Flujo por archivos

- `contracts.py` + `schemas/`: validación estructural, temporal, numérica y relaciones.
- `local.py`: lectura de agregado local y registro transaccional de un pack.
- `factory.py`: datos sintéticos reproducibles y producción de los cuatro objetos.
- `archive.py`: JSON canónico, checksums, límites y sustitución atómica.
- `preview.py`: consumidor local explicativo con un control y gráficos accesibles.
- `cli.py` / `scripts/publish_atlas.py`: demo, capture, build, validate, register, preview.
- `sql/101_publishing/01_registry.sql`: memoria privada de releases y vistas.

## Próximos incrementos

1. Importador Android nativo con el mismo corpus de packs válidos/corruptos.
2. Adaptador del forecasting existente: run ID, población, horizontes, métricas
   comparables, cobertura e intervalos emitidos; nunca ejecución de pickle.
3. Comparación de eventos de decisión y outcomes ya registrados, con cobertura y
   controles de elegibilidad antes de convertir experiencia en políticas.
4. Nuevas historias y familias después de validar cada contrato.

No se incluyen sincronización remota, API pública, newsletters, publicación
comercial automática ni entrenamiento en el teléfono.
