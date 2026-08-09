# Migración v0.1.0 → v0.2.0

## Opción recomendada: patch

Si ya configuraste `.env` y `config/tables.yml`, usa el ZIP patch sobre tu carpeta actual.

Ruta esperada:

```text
C:\AI\replica_redshift_local_v0.1.0\replica_redshift_local
```

1. Haz una copia de seguridad de `.env` y `config/tables.yml`.
2. Extrae el contenido del patch directamente dentro de `replica_redshift_local`, permitiendo reemplazar archivos.
3. Abre VS Code en esa misma carpeta.
4. Ejecuta:

```powershell
.\scripts\01_instalar.bat
```

Esto actualizará dependencias sin borrar tu `.env` ni `tables.yml`.

5. Inicializa los nuevos esquemas:

```powershell
.\scripts\03_inicializar_postgres.bat
```

El comando `init` ahora crea también:

```text
features
decision_intelligence
model_control
experiments
```

6. Valida los contratos:

```powershell
.\scripts\10_validar_contratos_decision.bat
```

7. Ejecuta la demo:

```powershell
.\scripts\11_demo_decisiones.bat
```

8. Abre `reports\decision_demo.csv` para revisar el flujo completo sin datos reales.

## Opción full

Usa el ZIP completo si todavía no has personalizado significativamente la v0.1.0 o quieres comenzar en una carpeta nueva.

Ejemplo:

```text
C:\AI\replica_redshift_local_v0.2.0\replica_redshift_local
```

Luego copia manualmente tus credenciales desde el `.env` anterior; nunca copies un `.env` a repositorios públicos.

## Qué NO cambia

- La lógica de extracción incremental sigue intacta.
- `raw_cygnus`, `staging`, `analytics` y `etl_control` siguen existiendo.
- La tarea horaria de réplica puede seguir utilizándose.
- `config/tables.yml` conserva el mismo formato.

## Qué se agrega

- librerías analíticas (`pandas`, `numpy`, `scikit-learn`, `statsmodels`);
- contratos de decisión;
- causalidad baseline;
- modelos predictivos baseline;
- forecast baseline;
- economía y valor incremental;
- registro de recomendaciones, acciones y outcomes;
- experiment registry.
