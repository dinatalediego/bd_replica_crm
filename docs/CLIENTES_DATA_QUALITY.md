# staging.clientes_calidad

## Objetivo

Mover al DW la lógica de calidad de clientes que hoy vive en Power Query M, con paridad funcional aproximada y ejecución horaria después de raw_cygnus.clientes.

La fuente de verdad operacional sigue siendo raw_cygnus.clientes. Esta capa no modifica RAW: normaliza, clasifica y agrega campos dq_* para consumo de Power BI, notebooks, Streamlit y modelos.

## Reglas trasladadas

- Construcción de nombre desde nombre o nombres + apellidos.
- Limpieza de documento dejando solo dígitos.
- Prioridad telefónica estricta: celulares; celular solo cuando la columna plural no existe; telefono solo si el valor celular elegido es NULL.
- Retiro de 51 / 0051 cuando el número es compatible con Perú.
- Clasificación de celular Perú, teléfono Perú, celular extranjero, vacío o formato a revisar.
- Email en minúsculas con fallback email -> correo.
- Fallbacks de asesor, proyecto, medio de captación y estado.
- Flags dq_*_ok, flags de identidad/contacto, score 0–100 y nivel de calidad.
- dq_documento_ok_estado = revisar dni cuando no existe documento limpio.

## Aproximaciones conscientes

Las funciones privadas de Power Query (fx_EsNombreCompleto, fx_EsDocumentoValido, fx_EsEmailValido, fx_NormalizarTexto) no están versionadas en este repositorio. Por eso Medallio usa contratos explícitos y auditables:

- nombre completo: al menos dos tokens no vacíos;
- documento: solo dígitos y longitud entre 8 y 12;
- email: patrón básico usuario@dominio.extensión;
- texto: trim, colapso de espacios y vacío -> NULL.

Estas reglas deben ajustarse si después se versionan las funciones M originales o se detectan diferencias materiales en una prueba de paridad.

## Refresco

El schema se instala por scripts/schema_sync.py. El refresh de datos se ejecuta con:

    .\.venv\Scripts\python.exe .\scripts\refresh_clientes_calidad.py

El refresh maestro llama este paso automáticamente después de 02_schema_sync y antes de CORE/analytics dependientes.

## Health gate

staging.v_clientes_calidad_health expone:

- filas RAW vs staging;
- uso de celulares, compatibilidad celular y fallback telefono;
- celulares extranjeros y formatos a revisar;
- documentos con revisar dni;
- clientes sin contacto;
- timestamps de refresh.

El script falla si la cantidad de filas de staging.clientes_calidad no coincide con raw_cygnus.clientes.
