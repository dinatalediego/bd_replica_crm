# Medallio v2.7.4.1 — `date` import hotfix

El validador llegó correctamente hasta:

- DB bridge: OK
- Governed project state: 17 proyectos / 10 acciones

y falló en Google JSON coercion por:

```text
NameError: name 'date' is not defined
```

La causa era un import incompleto en:

```text
scripts/medallio_ambassador_v2.py
```

Antes:

```python
from datetime import datetime, timedelta
```

Ahora:

```python
from datetime import date, datetime, timedelta
```

Esto permite que `google_json_scalar()` procese correctamente:

- `datetime`
- `date`
- `Decimal`
- pandas/numpy scalars
- diccionarios/listas
- NaN/NaT

## Instalación

Reemplaza:

```text
scripts\medallio_ambassador_v2.py
```

y vuelve a ejecutar:

```powershell
python .\scripts\validate_v274_runtime_reliability.py
```

Si pasa el punto `[3] Google JSON coercion`, continúa con:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```
