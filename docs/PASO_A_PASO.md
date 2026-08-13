# Ejecución

## 1. Extraer overlay

Sobre la raíz del repositorio actual.

## 2. Instalar

```powershell
.\scripts\30_instalar_absorption_phase_c_core.bat
```

## 3. Backfill

```powershell
.\scripts\31_backfill_absorption_phase_c_core.bat
```

## 4. Validar en DBeaver

Ejecutar:

`sql/30_absorption_phase_c/06_validation.sql`

## 5. Discovery de producto

Ejecutar:

`sql/30_absorption_phase_c/09_discover_unit_product_features.sql`

Enviar el resultado antes de construir Fase C v0.2 detallada.

## 6. Power BI

Importar las consultas M de `powerbi/M`.

Modo recomendado inicialmente:
Import.

Power BI solo consume `analytics`, `observability` y, posteriormente,
`decision_intelligence`.
