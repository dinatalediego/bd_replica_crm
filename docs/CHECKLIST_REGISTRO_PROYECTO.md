# Checklist de registro del proyecto en Medallio

Este checklist sirve para registrar una iniciativa analítica y, cuando aplique,
dar de alta cada proyecto inmobiliario que participará en sus indicadores,
modelos y decisiones. Una casilla solo se marca cuando existe evidencia.

## 0. Ficha de control

- [ ] Nombre de la iniciativa: `________________________________`
- [ ] Cliente/empresa: `________________________________`
- [ ] Project owner: `________________________________`
- [ ] Sponsor gerencial: `________________________________`
- [ ] Data owner: `________________________________`
- [ ] Decision owner: `________________________________`
- [ ] Repositorio: `________________________________`
- [ ] Rama/release inicial: `________________________________`
- [ ] Fecha de alta: `____ / ____ / ______`
- [ ] Estado: `DESCUBRIMIENTO / PILOTO / OPERATIVO / PAUSADO / RETIRADO`
- [ ] Responsable de aprobación: `________________________________`

**Evidencia:** enlace al repositorio, issue/PR de alta y decisión de aprobación.

## 1. Problema económico y decisión

- [ ] El problema está expresado como una decisión, no solo como un dashboard.
- [ ] Se definió quién decide.
- [ ] Se definió cuándo decide.
- [ ] Se listaron las acciones realmente disponibles.
- [ ] Se definió el outcome que se busca cambiar.
- [ ] Se definió el horizonte: `____ días`.
- [ ] Se definió el costo de actuar.
- [ ] Se definió el costo de equivocarse.
- [ ] Se definió la métrica primaria de valor: `________________________`.
- [ ] Se documentó qué acciones necesitan aprobación humana.

**Gate:** no iniciar ML si no existe una acción posible y un outcome observable.

## 2. Alta del proyecto inmobiliario

- [ ] `codigo_proyecto` oficial: `________________________________`
- [ ] `nombre_proyecto` oficial: `________________________________`
- [ ] Empresa/promotor: `________________________________`
- [ ] Moneda principal: `PEN / USD / OTRA`
- [ ] Tipo de cambio o política aplicable documentada.
- [ ] Fecha de lanzamiento registrada.
- [ ] Fecha de entrega estimada registrada.
- [ ] Meta comercial y periodo de meta documentados.
- [ ] Tipos de unidad incluidos: departamento, estacionamiento, depósito, local.
- [ ] Torres/etapas/bloques homologados.
- [ ] Tipologías y `tipologia_ubicacion` homologadas.
- [ ] Estados comerciales mapeados a catálogo.
- [ ] Fuente mandante de precio definida.
- [ ] Fuente mandante de stock definida.
- [ ] Regla de `fecha_entrada_stock` definida.
- [ ] Unidades duplicadas, nulas o sin código enviadas a cuarentena.

**Gate:** una fila única por `codigo_proyecto + codigo_unidad` en el mart vigente.

## 3. Fuentes y permisos

- [ ] Fuente operacional identificada: Redshift/Sperant/otra.
- [ ] Tablas fuente inventariadas.
- [ ] Responsable y permiso de lectura confirmados.
- [ ] Frecuencia y latencia esperadas documentadas.
- [ ] Zona horaria confirmada.
- [ ] Campos personales identificados y minimizados.
- [ ] Secretos almacenados fuera de Git.
- [ ] `.env.example` contiene nombres, nunca valores reales.
- [ ] Restricciones contractuales de uso de datos revisadas.
- [ ] Ruta de recuperación ante indisponibilidad documentada.

**Evidencia:** inventario de tablas, prueba de conexión y matriz de acceso.

## 4. Contrato de datos

- [ ] Grano de cada dataset declarado.
- [ ] Clave primaria declarada y probada.
- [ ] Relaciones y cardinalidades declaradas.
- [ ] Campos obligatorios definidos.
- [ ] Catálogos de valores válidos definidos.
- [ ] Timestamps de evento, carga y actualización diferenciados.
- [ ] Regla de deduplicación definida.
- [ ] Regla de datos tardíos definida.
- [ ] Política ante cambio de esquema definida.
- [ ] Reglas del funnel versionadas.
- [ ] Definición de separación validada.
- [ ] Definición de pago de inicial ≥5% validada.
- [ ] Definición de minuta/venta validada.
- [ ] Definición de caída y cambio de departamento validada.

**Gate:** ninguna regla ambigua se transforma silenciosamente en código.

## 5. Pipeline Redshift → PostgreSQL

- [ ] Carga inicial ejecutada.
- [ ] Incremental/watermark ejecutado.
- [ ] Idempotencia demostrada repitiendo la misma ejecución.
- [ ] Conteos origen/destino reconciliados.
- [ ] Nulos y duplicados reportados.
- [ ] Filas rechazadas guardadas con motivo.
- [ ] `run_id`, inicio, fin, duración y estado registrados.
- [ ] Schema drift probado.
- [ ] Reintento y recuperación probados.
- [ ] Tarea programada confirmada.
- [ ] Freshness visible en observabilidad.
- [ ] `raw_cygnus` permanece sin transformaciones destructivas.

**Evidencia:** último `run_id`, conciliación y resultado de QA.

## 6. CORE, analytics y Power BI

- [ ] Dimensión proyecto creada/actualizada.
- [ ] Dimensión unidad creada/actualizada.
- [ ] Ciclo comercial por proforma/unidad reconstruible.
- [ ] Marts tienen grano y owner documentados.
- [ ] KPIs cuadran con una muestra conocida del negocio.
- [ ] Power BI consume `analytics`/vistas gobernadas, no lógica duplicada en M.
- [ ] Relaciones uno-a-muchos no contienen claves nulas.
- [ ] Refresh probado desde Power BI Desktop.
- [ ] Gateway/refresh de Power BI Service validado.
- [ ] Fecha de corte visible para el usuario.

**Gate:** un KPI puede rastrearse desde Power BI hasta su evento fuente.

## 7. Preparación para modelos

- [ ] Unidad de predicción definida.
- [ ] Momento exacto de scoring definido.
- [ ] Target y horizonte definidos.
- [ ] Snapshot point-in-time disponible.
- [ ] Features usan solo información disponible al decidir.
- [ ] Revisión de leakage aprobada.
- [ ] Ventanas train/validation/test respetan el tiempo.
- [ ] Baseline de regla simple registrado.
- [ ] Modelo explicable registrado como challenger.
- [ ] AUC/PR, Brier y top-k reportados según corresponda.
- [ ] Performance revisada por proyecto, canal y cohorte.
- [ ] Dataset y Git SHA registrados.

**Gate:** el challenger debe superar o complementar una decisión existente.

## 8. Recomendación, acción y outcome

- [ ] Cada score genera una recomendación identificable.
- [ ] La recomendación declara que es propensión o causalidad.
- [ ] El responsable puede aceptar, cambiar o no ejecutar la recomendación.
- [ ] La acción real registra owner, fecha, costo y notas.
- [ ] Separación 14d se enlaza al mismo `evidence_key`.
- [ ] Minuta/venta 60d se enlaza al mismo `evidence_key`.
- [ ] Se distingue outcome pendiente de outcome negativo maduro.
- [ ] La cobertura de acciones es medible.
- [ ] La performance por banda es visible en Power BI.
- [ ] No se interpreta correlación como impacto causal.

**Evidencia:** `decision_intelligence.v_lead_action_outcome` y su vista de performance.

## 9. MLOps y operación

- [ ] Tracking backend definido.
- [ ] Artifact store definido fuera de Git.
- [ ] Experimento y run reproducibles.
- [ ] Registry tiene candidate/champion/serving.
- [ ] Promoción exige gate y aprobador.
- [ ] Rollback probado.
- [ ] Drift de features monitoreado.
- [ ] Calibración y performance monitoreadas al madurar outcomes.
- [ ] Criterios de reentrenamiento definidos.
- [ ] Alertas tienen owner y runbook.
- [ ] Producción no depende de una PC personal.

**Gate:** ningún modelo se promueve únicamente porque tiene mejor métrica técnica.

## 10. Experimentos, promociones y descuentos

- [ ] Promoción y descuento tienen identificador único.
- [ ] Elegibilidad registrada antes de asignar tratamiento.
- [ ] Tratamiento/control definidos.
- [ ] Oferta y aceptación se registran por separado.
- [ ] Costo del regalo/descuento disponible.
- [ ] Venta, margen y tiempo de conversión disponibles.
- [ ] Contaminación e incumplimiento medibles.
- [ ] Hipótesis y estimando causal aprobados.
- [ ] Resultado incremental registrado con incertidumbre.
- [ ] Decisión posterior al experimento documentada.

## 11. RAG y conocimiento gerencial

- [ ] Fuentes documentales autorizadas e inventariadas.
- [ ] Documento, versión, vigencia, proyecto y owner etiquetados.
- [ ] Reglas antiguas no se presentan como vigentes.
- [ ] Fragmentos recuperados conservan procedencia.
- [ ] Cifras provienen de PostgreSQL, no del texto generado.
- [ ] Respuestas incluyen fuentes y fecha de corte.
- [ ] Preguntas sin evidencia producen abstención explícita.
- [ ] Evaluación de recuperación y respuesta preparada.
- [ ] Feedback editorial registrado.

## 12. Cierre del alta

- [ ] Pruebas locales aprobadas.
- [ ] CI remoto aprobado.
- [ ] Revisión de seguridad aprobada.
- [ ] Documentación operativa aprobada.
- [ ] Riesgos y deuda técnica registrados.
- [ ] Dashboard o salida operativa accesible al usuario objetivo.
- [ ] Responsable de monitoreo asignado.
- [ ] Fecha de primera revisión definida.
- [ ] Decision Memory actualizada.
- [ ] Project owner aprobó el alta.

## Acta final

```text
Proyecto:
Versión:
Fecha:
Estado aprobado:
Último run_id:
Dataset/modelo vigente:
Dashboard:
Decision owner:
Próxima revisión:
Pendientes aceptados:
Aprobado por:
```
