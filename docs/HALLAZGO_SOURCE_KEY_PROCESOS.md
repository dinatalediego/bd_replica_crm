# Hallazgo crítico — source key de procesos

## Evidencia

Redshift tiene:

- 5,031 filas
- 4,921 IDs distintos

El archivo de duplicados contiene 110 IDs.

Para cada uno de esos 110 IDs:

- `veces = 2`
- `proformas = 2`
- `unidades = 2`
- `nombres = 2`
- `fechas_inicio = 2`

Además, al agrupar Redshift por `nombre`, no existe duplicación de `id`
dentro de cada tipo de proceso.

## Conclusión

La suposición anterior:

`procesos.id = identificador global del evento`

queda **refutada por los datos reales**.

Contrato actualizado:

- `source_id = id`
- `source_event_type = nombre`
- `source key = (nombre, id)`
- `source_event_key = lower(nombre) || ':' || id`

Esto explica exactamente la diferencia:

5,031 filas origen - 4,921 filas local = **110 filas perdidas por colisión de `id`**.

## Consecuencia

No construir Fase B sobre `raw_cygnus.procesos` hasta reparar la réplica.
