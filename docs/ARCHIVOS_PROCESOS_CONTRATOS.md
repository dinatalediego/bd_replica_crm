# Clasificación de archivos de contrato

La vista `analytics.archivos_procesos` clasifica únicamente filas con `montaje = 'Contrato'`.

## Campos de salida

- `nombre_normalizado`: nombre en minúsculas, sin tildes y con separadores convertidos a espacios.
- `es_convenio_separacion`: booleano.
- `es_carta_aprobacion`: booleano.
- `es_contrato_minuta`: booleano.
- `tipo_contrato_archivo`: categoría final; si no existe exactamente una coincidencia queda `incierto`.

Las filas cuyo `montaje` no es `Contrato` dejan `tipo_contrato_archivo` en NULL.

## Patrones configurables

Los patrones viven en:

```sql
analytics.archivos_contrato_patrones
```

Columnas:

- `tipo_contrato`
- `patron`
- `activo`
- `prioridad`
- `descripcion`

Los patrones deben guardarse normalizados: minúsculas, sin tildes y sin extensión.

### Agregar un patrón

```sql
INSERT INTO analytics.archivos_contrato_patrones (
    tipo_contrato, patron, prioridad, descripcion
)
VALUES (
    'carta de aprobacion',
    'carta aprobada',
    40,
    'Nueva variante observada'
)
ON CONFLICT (tipo_contrato, patron)
DO UPDATE SET activo = true;
```

### Desactivar un patrón demasiado amplio

```sql
UPDATE analytics.archivos_contrato_patrones
SET activo = false
WHERE tipo_contrato = 'carta de aprobacion'
  AND patron = 'carta';
```

## Casos observados inicialmente

| Nombre observado | Clasificación esperada |
|---|---|
| CONVENIO DE SEPARACION - VERA ROJAS KAREN_.pdf | Convenio de Separacion |
| CONVENIO_DE_SEPARACION_-_VILLENA_ALVAREZ.pdf | Convenio de Separacion |
| CONVENIO_-_PARIONA_DINA_-_1205_-_ESTAC_12.pdf | Convenio de Separacion |
| Pendiente_de_Carta.pdf | carta de aprobacion |
| MINUTA_-_VILLENA_ALVAREZ_ROMULO_-_A2502.pdf | contrato o minuta |
| MINUTA_MATERA_-_SAAVEDRA_VELASQUEZ_MONICA_-A702.pdf | contrato o minuta |
| MINUTA_FINAL_-_MUÑOZ_ROSAS_LIDIA_-_1104.pdf | contrato o minuta |
| Regularizar.pdf | incierto |
| Captura_de_pantalla_2026-07-18_125034.pdf | incierto |

## Regla conservadora

Si un nombre coincide con cero categorías o con más de una categoría, la categoría final es `incierto`.
Esto evita resolver automáticamente una ambigüedad con una prioridad arbitraria.
