# Instalación Sprint 1 sobre tu proyecto existente

Supuesto de ruta actual:

```text
C:\AI\replica_redshift_local\replica_redshift_local
```

## 1. Respaldo mínimo
Antes de copiar el patch, guarda:

```text
.env
config\tables.yml
config\decision_systems.yml   (si ya existe)
```

El patch no debería reemplazar `.env` ni `tables.yml`.

## 2. Copia el patch sobre la raíz del proyecto
Extrae el ZIP patch directamente dentro de:

```text
C:\AI\replica_redshift_local\replica_redshift_local
```

Acepta reemplazar los archivos incluidos.

## 3. Actualiza el entorno
En VS Code / PowerShell:

```powershell
cd C:\AI\replica_redshift_local\replica_redshift_local
.\.venv\Scripts\Activate.ps1
.\scripts\01_instalar.bat
```

Si no existe `config\observability.yml`, el instalador lo creará desde el ejemplo.

## 4. Inicializa PostgreSQL

```powershell
.\scripts\03_inicializar_postgres.bat
```

Ahora debe existir:

```text
observability.asset_registry
observability.asset_snapshots
observability.quality_checks
```

además de las vistas `observability.v_*`.

## 5. Registra tus activos

```powershell
.\scripts\12_inicializar_observabilidad.bat
```

Edita después:

```text
config\observability.yml
```

para adaptar criticidad, SLA e impacto real de cada tabla.

## 6. Toma el primer snapshot liviano

```powershell
.\scripts\13_observar_ahora.bat
```

## 7. Primer control profundo
Cuando no estés en un momento de alta carga:

```powershell
.\scripts\14_calidad_profunda.bat
```

## 8. Tu tarea horaria existente
Si ya tienes en Windows:

```text
Medallio - Replica Redshift Local
```

no necesitas crearla de nuevo si apunta a la misma carpeta. El nuevo `scripts\run_hourly.bat` hará:

```text
sync
  ↓
observe --mode hourly
```

Así cada ejecución horaria deja telemetría lista para Power BI.

## 9. Calidad profunda diaria (opcional)
El paquete incluye:

```text
scripts\15_crear_tarea_calidad_diaria.bat
```

La configuración propuesta es diaria a las 06:30. Revísala antes de activarla según disponibilidad de Redshift y carga de trabajo.

## 10. Validación DBeaver

```sql
SELECT *
FROM observability.v_asset_health_current
ORDER BY criticality, asset_key;
```

```sql
SELECT *
FROM observability.v_quality_checks
ORDER BY checked_at DESC
LIMIT 100;
```

```sql
SELECT *
FROM observability.asset_snapshots
ORDER BY snapshot_at DESC
LIMIT 100;
```

El Sprint 1 está operativo cuando ves snapshots nuevos después de cada ciclo horario.
