# Production Readiness — `separation_fall_risk`

## Objetivo

Promover el primer producto de Decision Intelligence sin confundir tres hitos distintos:

1. **técnicamente correcto**;
2. **operativamente útil**;
3. **causalmente valioso**.

El baseline puede pasar el primero sin haber demostrado todavía el tercero.

---

## Stage 0 — Data repair

### Requisito crítico

`raw_cygnus.datos_extras` debe reconciliar con Redshift usando el grain certificado `(id, nombre)`.

Hallazgo que originó este gate:

- `id` duplicado en origen: existen múltiples atributos bajo un mismo id;
- `(id,nombre)` duplicado: 0 en el perfil certificado;
- la configuración histórica `[id]` colapsaba atributos y podía borrar evidencia de pago.

### Go / no-go

GO solo cuando:

- source duplicate `(id,nombre)` = 0;
- target duplicate `(id,nombre)` = 0;
- source row count = target row count;
- source `(id,nombre)` key count = target key count;
- full refresh de reparación terminado;
- Scheduled Task vuelve a incremental normal.

Ejecutar:

```powershell
python scripts/production_readiness_decision_engine.py
```

---

## Stage 1 — Contract certification

Debe aprobar:

```powershell
python -m pytest
python scripts/core_commercial_lifecycle.py status
python -m cygnus_decision_engine --env-file .env validate-separation-risk
python scripts/audit_risk_candidates_payment_evidence.py
```

Hard gates:

- 0 duplicados;
- 0 candidatos con Entrega Activa;
- 0 candidatos con evidencia de pago;
- 0 candidatos fuera de ventana temporal;
- 0 leakage;
- 0 montos no parseables dentro de scoring;
- universo reconciliado;
- CORE resoluble;
- auditor RAW vs CORE = 0 mismatches.

---

## Stage 2 — Dry run

Comando seguro por defecto:

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --top 20
```

Sin `--shadow` o `--live`, el modo es `DRY_RUN`.

Validación humana del top-N:

- caso realmente vigente;
- no convertido;
- no Entrega Activa;
- asesor/proyecto correctos;
- señales entendibles;
- prioridad razonable frente a otros casos con el mismo score.

Registrar ejemplos de falsos positivos y falsos negativos conocidos. No ajustar reglas usando solo anécdotas; cada hallazgo debe convertirse en test o feature candidate.

---

## Stage 3 — Shadow mode

Instalar PolicyOps:

```powershell
python -m cygnus_decision_engine --env-file .env install-separation-risk
python -m cygnus_decision_engine --env-file .env policy-status
```

La policy baseline debe quedar:

```text
policy_status = SHADOW
live_allowed = false
shadow_allowed = true
```

Ejecutar:

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --shadow --top 20
```

Shadow mode:

- persiste evidencia y ranking;
- registra `decision_run`;
- status de recomendaciones = `SHADOW`;
- no aparecen en la worklist `ACTIVE`;
- no debe gatillar acciones automáticas.

### Duración mínima sugerida

14 días, siempre que exista volumen suficiente.

### Evidencia mínima sugerida

- >= 30 recomendaciones revisadas;
- >= 80% de coverage de outcome para recomendaciones cuyo horizonte ya venció;
- revisión de concentración por proyecto/asesor;
- revisión de falsos positivos conocidos;
- estabilidad diaria del candidate universe.

---

## Stage 4 — Human-in-the-loop pilot

Antes de activar LIVE a escala, hacer un piloto visible a un grupo controlado.

La unidad de decisión no es “score”. Es:

`separación -> recomendación -> asesor/supervisor -> acción -> resultado`

Capturar en `recommendation_feedback`:

- SHOWN;
- ACCEPTED;
- MODIFIED;
- REJECTED;
- reason;
- chosen_action.

Capturar en `recommendation_outcome`:

- venta/pago confirmado;
- caída;
- permanece abierta;
- fecha del outcome;
- valor económico cuando pueda estimarse.

---

## Stage 5 — Evaluation

### Baseline mínimo

Comparar la policy contra políticas ingenuas:

1. ordenar solo por `days_since_separation`;
2. ordenar solo por `days_since_last_interaction`;
3. selección aleatoria dentro del universo elegible;
4. operación actual sin recomendación, si puede reconstruirse.

### Métricas operativas

- precision@K de caídas futuras;
- conversion@K;
- recall de caídas;
- action acceptance rate;
- time-to-action;
- outcome coverage.

### Métricas económicas

- ventas protegidas estimadas;
- margen protegido;
- costo de contacto incremental;
- valor económico por recomendación;
- valor económico por hora del equipo comercial.

### Métricas de seguridad

- falso riesgo de un caso ya convertido = 0;
- falso riesgo de una Entrega Activa = 0;
- recomendaciones basadas en evidencia futura = 0.

---

## Stage 6 — Live promotion

LIVE no debe habilitarse modificando código. Debe ser una transición gobernada de policy.

Requisitos:

- data parity verde;
- tests verdes;
- shadow window cumplida;
- outcome coverage suficiente;
- owner de negocio aprueba;
- owner técnico aprueba;
- rollback definido;
- policy registry cambia de `SHADOW` a `ACTIVE`;
- monitor diario activo.

Solo entonces:

```powershell
python -m cygnus_decision_engine --env-file .env run-separation-risk --live
```

El CLI debe bloquearlo mientras la policy siga `SHADOW`.

---

## Rollback

Ante cualquiera de estos eventos:

- pérdida de paridad origen-destino;
- evidencia de pago dentro de scoring;
- Entrega Activa dentro de scoring;
- drift brusco no explicado;
- incidentes severos de datos;
- degradación operativa;

la policy se cambia a `PAUSED` y se detienen ejecuciones LIVE. Los datos históricos no se eliminan.

---

## Executive readout

Para gerencia, el reporte debe reducirse a:

- oportunidades revisables hoy;
- principales causas de riesgo;
- distribución por proyecto y asesor;
- acciones recomendadas;
- adopción;
- conversiones/caídas posteriores;
- valor económico estimado/realizado;
- confiabilidad del sistema.

La explicación técnica queda disponible para auditoría, no como interfaz principal.
