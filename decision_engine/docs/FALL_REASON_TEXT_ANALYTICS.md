# Fall Reason Text Analytics

## Objetivo

Incorporar `datos_extras.motivo_caida_segun_asesor` como evidencia histórica para entender **por qué** caen oportunidades y descubrir patrones que puedan mejorar el diseño futuro de features, reglas comerciales e intervenciones.

La lógica reproduce el alcance del Power Query de negocio para `entidad = proforma` y los atributos:

- `motivo_caida_segun_asesor`;
- `cambio_de_departamento`;
- `depa_del_cambio`.

La relación es:

`datos_extras.codigo -> codigo_proforma`

En PostgreSQL se selecciona el valor no vacío más reciente por `codigo_proforma + nombre` y luego se pivotea mediante agregaciones `FILTER`.

---

## Regla crítica: motivo de caída NO es feature live

Normalmente el motivo se registra después de conocer la caída. Por tanto:

`motivo_caida_segun_asesor = POST_OUTCOME_ONLY`

No puede entrar directamente a `features.separation_fall_risk_current`, porque introduciría **target leakage**: el modelo estaría utilizando información producida como consecuencia del evento que intenta predecir.

Sí puede utilizarse para:

1. describir y clasificar caídas históricas;
2. descubrir tópicos recurrentes;
3. medir diferencias por proyecto, asesor o cohorte;
4. proponer nuevas variables que sí existan antes de la caída;
5. auditar falsos positivos/falsos negativos;
6. diseñar intervenciones específicas por familia de causa;
7. eventualmente entrenar un segundo modelo de `fall_reason_given_fall`, separado del modelo de riesgo.

Solo podría convertirse en feature predictiva si en el futuro se demuestra, con timestamp point-in-time, que una señal equivalente estaba disponible antes de `decision_observed_at`.

---

## Dos conceptos que no debemos mezclar

### 1. Target temporal: caída antes de conversión

Fase B / CORE ya compara los eventos fechados:

- si `fecha_venta <= primera_fecha_caida` el ciclo es `VENTA`;
- si la caída ocurre primero el ciclo es `CAIDA`;
- si ninguno ha terminado, queda `ABIERTA`.

Por eso el target temporal gobernado es:

- `1 = FELL` cuando `resultado_ciclo = CAIDA`;
- `0 = CONVERTED` cuando `resultado_ciclo = VENTA`;
- `NULL` cuando `resultado_ciclo = ABIERTA` y aún no existe outcome temporal suficiente.

Esto preserva correctamente un caso que **cayó primero y eventualmente volvió/pagó después**: históricamente sigue siendo una caída-before-conversion para el problema de riesgo, aunque hoy ya no sea candidato.

### 2. Muestra de interés/conversión actual

Además se expone:

`conversion_interest_sample`

que vale verdadero cuando existe `VENTA` o cualquier evidencia consolidada de pago inicial:

- `fecha_pago_ci`;
- `pago_ci_marker_confirmado`;
- `monto_pago_ci_positivo`.

Esta señal responde a otra pregunta: **¿esta oportunidad ya mostró el interés fuerte que nos importa?**

En el sistema CURRENT, cualquiera de esas evidencias la saca de `risk_to_fall`: ya no debemos recomendar seguimiento preventivo de caída como si continuara siendo una separación abierta sin conversión.

Cuando solo existe marcador/monto positivo pero no una fecha confiable, la fila puede servir como muestra descriptiva de interés, pero **no se inventa una fecha de conversión ni se usa como label temporal limpio**.

Esta separación entre `target_fall_before_conversion` y `conversion_interest_sample` evita contaminar el backtest.

---

## Contratos creados

SQL:

`decision_engine/sql/06_historical_fall_outcomes.sql`

Vista principal:

`decision_intelligence.v_separation_fall_outcome_history`

Incluye:

- outcome temporal certificado;
- `conversion_interest_sample`;
- evidencia de pago;
- fechas de caída/venta;
- motivo de caída;
- cambio de departamento;
- departamento del cambio;
- flags de precisión temporal y leakage.

Corpus de texto sin duplicar una proforma por cada unidad asociada:

`decision_intelligence.v_fall_reason_proforma_history`

Health check:

`decision_intelligence.v_separation_fall_outcome_health`

Entre otros, monitorea:

- caídas etiquetadas;
- conversiones etiquetadas;
- muestras de interés/conversión;
- evidencia de conversión sin label temporal;
- cobertura de motivo de caída;
- caídas históricas que hoy tienen evidencia de pago y requieren interpretación temporal.

---

## Por qué hay dos granularidades

El modelo operacional trabaja en el grain:

`codigo_proforma + codigo_unidad + observed_at`

Pero `motivo_caida_segun_asesor` pertenece a la proforma.

Una misma proforma puede contener departamento, estacionamiento y depósito. Repetir el mismo texto por cada unidad sesgaría el análisis NLP, por lo que el corpus textual se reduce a **una fila por `codigo_proforma`**, priorizando la unidad residencial cuando existe.

---

## Primera capa NLP implementada

Ejecutar:

```powershell
python .\scripts\analyze_fall_reason_text.py
```

El script usa herramientas locales y reproducibles de `scikit-learn`:

- normalización de texto;
- taxonomía inicial transparente por palabras/expresiones;
- `TF-IDF` con unigramas y bigramas;
- `NMF` para descubrimiento no supervisado de tópicos.

No descarga modelos ni depende de APIs externas.

Genera en `reports/fall_reason_text/`:

- `summary.json`;
- `fall_reason_records.csv`;
- `taxonomy_counts.csv`;
- `taxonomy_by_project.csv`;
- `taxonomy_by_advisor.csv`;
- `nmf_topics.csv` cuando existe volumen suficiente.

---

## Cómo convertir los hallazgos en mejores features

El texto no debe copiarse al modelo live. El flujo correcto es:

`texto histórico -> patrón -> hipótesis -> señal previa observable -> feature point-in-time -> backtest`

Ejemplos:

- si aparece frecuentemente **crédito no aprobado**, buscar antes de la caída señales certificadas de pre-calificación/financiamiento;
- si aparece **precio**, construir relación precio/presupuesto o magnitud de descuento conocida antes de la decisión;
- si aparece **cambio de departamento**, medir número de cambios de unidad previos y distancia entre preferencias;
- si aparece **falta de contacto**, mejorar el contrato de interacciones reales;
- si aparece **competencia**, buscar señales previas de proyectos alternativos si el CRM las captura.

De esta forma el NLP funciona como un **motor de descubrimiento de features**, no como una fuga de información.

---

## Evolución recomendada

Cuando existan suficientes motivos limpios:

1. revisar manualmente una muestra estratificada;
2. consolidar una taxonomía de negocio de 6–12 causas;
3. medir cobertura y acuerdo entre revisores;
4. etiquetar histórico;
5. comparar taxonomía rule-based vs embeddings/clustering;
6. utilizar la causa como outcome secundario;
7. medir qué causas son prevenibles mediante una acción comercial concreta.

La meta final no es solo saber **quién caerá**, sino aproximarnos a:

`P(caída | información actual)` + `causa probable` + `acción que puede evitarla` + `valor esperado de intervenir`.
