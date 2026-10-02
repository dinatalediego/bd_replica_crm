# Active Task

Task ID: ABS-2024-VENTAS
Title: Stock pendiente de venta y absorción mensual por proyecto
Status: VALIDATION_REQUIRED
Owner: chatgpt
Next agent: human
Branch: feat/absorcion-mensual-ventas-2024
Base branch: main

## Objective

Cuadro mensual desde enero 2024 de departamentos y ventas vigentes retrospectivas,
con detalle por unidad y casos comentados. Publicación autorizada en PR #36.

## Decisions and scope

ADR-012 sustituye elegibilidad e inicio de ADR-011 por instrucciones explícitas del
usuario. Inicio efectivo = mes más antiguo entre adjunto y evidencia de venta.
Pago CI anterior a separación se acepta con observación. Proformas anuladas se
excluyen retrospectivamente. Venta Activo solo respalda separaciones originales Y
analíticas anteriores a 2026. No cambiar Phase B, controles CI ni ledger global.
Reutilizar CORE, ciclos y RAW locales; sin nueva carga Redshift.
Seguimiento por eventos y versiones temporales queda como ampliación posterior.

## Evidence

48 pruebas aprobadas: integración PostgreSQL sintética y regresión de contratos.
Migración desde contrato publicado probada en PostgreSQL desechable, conservando
una vista consumidora dependiente. git diff --check y compilación Python limpios.
CSV locales anteriores permitieron detectar ventas omitidas por separación legacy;
los nuevos totales reales aún deben consultarse en Medallio después de instalar.
No almacenar CSV ni datos personales en el repositorio.

## Next action

Descargar rama, ejecutar schema_sync.py --only absorcion_ventas_mensual y consultar
sql/96_absorcion_ventas/02_validation.sql. Exportar mensual, inicios y observaciones.
No hay conexión directa a Medallio local desde esta sesión. No fusionar main.

## Other work

NIGHT-002 permanece independiente; no se cambia cola ni políticas nocturnas.
