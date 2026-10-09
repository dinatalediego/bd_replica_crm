# Medallio Ambassador v1.3 — Safe Profiling Fix

## Error corregido

La corrida ya superó el problema del kernel y del timeout. El nuevo fallo era:

```text
TypeError: unhashable type: 'dict'
```

La causa estaba en:

```python
df.duplicated()
```

Algunas vistas de Medallio contienen columnas `object` con estructuras Python/JSON
como `dict` o `list`. Pandas necesita valores hashables para calcular duplicados y
por eso la celda fallaba.

## Fix

`Medallio_CEO_AI_Control_Tower_Lite.ipynb` ahora:

- detecta `dict`, `list`, `tuple`, `set` y `ndarray`;
- los serializa de forma estable sólo para el cálculo de calidad;
- calcula duplicados sobre máximo 5,000 filas;
- si todavía encuentra un objeto no hashable, usa sólo columnas seguras;
- si no existe ninguna columna segura, devuelve `NaN` en vez de romper la torre.

Esto mantiene el profiling como diagnóstico y evita que un campo JSON tumbe todo
el briefing ejecutivo.

## Kernel

v1.3 también cambia la prioridad:

1. `kernel_name` del config;
2. `medallio_dw`;
3. metadata del notebook;
4. `python3`.

Así una metadata genérica `python3` no desplaza al kernel corporativo.

## Instalación mínima

Reemplaza:

```text
notebooks\Medallio_CEO_AI_Control_Tower_Lite.ipynb
scripts\medallio_ambassador\run_ambassador.py
```

Y conserva tu `config\medallio_ambassador.json` actual, verificando que tenga:

```json
"kernel_name": "medallio_dw"
```

## Prueba

```powershell
python scripts\medallio_ambassador\run_ambassador.py --slot morning --dry-run
```

## Sobre el mensaje de VS Code

Si ves:

```text
Failed to save 'preview_morning.html': The content of the file is newer...
```

no es un fallo del Ambassador. El script reescribió el preview mientras VS Code
tenía una versión antigua abierta. Cierra esa pestaña y abre el HTML en el navegador:

```powershell
Start-Process .\artifacts\medallio_ambassador\preview_morning.html
```

No edites manualmente ese archivo: es un artifact generado.
