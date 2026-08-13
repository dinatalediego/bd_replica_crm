# Instalación Fase B v0.2

Prerequisito:
Fase B v0.1 ya ejecutada y con tablas:

- analytics.int_ciclo_comercial_unidad
- analytics.fact_movimientos_stock
- observability.absorption_quality_results

## 1. Extraer overlay

Copiar el contenido a la raíz del repositorio actual.

## 2. Instalar

```powershell
.\scripts\26_instalar_absorption_reconciliation_v02.bat
```

## 3. Ejecutar QA/reconciliación

```powershell
.\scripts\27_qa_absorption_reconciliation_v02.bat
```

## 4. Consultar

```sql
SELECT *
FROM analytics.v_ciclo_comercial_reconciliado
ORDER BY requiere_revision DESC, codigo_proforma
LIMIT 100;
```

```sql
SELECT *
FROM observability.v_absorption_reconciliation_current;
```

```sql
SELECT *
FROM analytics.v_inventory_state_current
ORDER BY codigo_proyecto, codigo_unidad
LIMIT 100;
```

## 5. Condición para avanzar a Fase C

No se exige que workflow documental y ledger físico coincidan 100%.

Sí se exige:

- ninguna fecha_venta_validada < fecha_separacion;
- source key de procesos reconciliada;
- conservation check del inventario;
- divergencias clasificadas;
- casos ambiguos visibles y cuantificados.

Fase C usará explícitamente la capa reconciliada.
