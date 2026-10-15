# MEDALLIO Data Partner — revisión OpenAI opt-in

## Estado en `main`

Este componente queda integrado como **piloto manual y deshabilitado por defecto**. No forma parte del refresh horario, no realiza llamadas OpenAI automáticamente y no publica datos empresariales sin una acción explícita del operador.

Su propósito es detectar brechas de evidencia en paquetes agregados que luego revisa una persona. No modifica CRM, no ejecuta decisiones, no afirma causalidad y no promueve texto del modelo a tablas operativas.

## Límite de datos

El flujo usa una allowlist estricta de agregados. No debe enviarse `context.json` completo porque puede contener muestras o datos personales.

El paquete permitido puede incluir:

- métricas agregadas de portafolio/proyecto;
- readiness por capa;
- conteos de cobertura;
- estados de madurez predictiva;
- referencias de evidencia locales.

Se excluyen nombres, teléfonos, emails, unidades, clientes, muestras de filas, texto fuente, precios individuales y cualquier campo no enumerado.

## Flujo

```text
contexto local
    ↓
prepare: allowlist agregada
    ↓
inspección humana del paquete
    ↓
review manual con --send --data-approved
    ↓
JSON estructurado
    ↓
validación local de referencias
    ↓
DRAFT_REVIEW_REQUIRED
    ↓
feedback humano ACCEPT / REJECT / REVISE
```

La llamada usa `store: false`, salida estructurada y sin tools. Esto no sustituye la revisión de retención, residencia, permisos y presupuesto del proyecto OpenAI.

## Prueba offline

```powershell
$env:PYTHONPATH="src"
python tests\test_ai_review.py
```

El test sintético comprueba allowlist, rechazo de referencias inexistentes, abstención, ejecución offline y feedback humano.

## Preparar un paquete

```powershell
$env:PYTHONPATH="src"
python scripts\medallio_ai_review.py prepare `
  --context artifacts\project_intelligence_v290\MD\context.json `
  --output private\md_packet.json
```

Inspeccionar el archivo generado antes de cualquier envío.

## Revisión manual

Solo en un entorno autorizado:

```powershell
python scripts\medallio_ai_review.py review `
  --packet private\md_packet.json `
  --output private\md_review.json `
  --model gpt-4.1-mini `
  --send `
  --data-approved
```

La salida no se considera decisión; queda como borrador sujeto a revisión humana.

## Instalar las tablas opt-in

En la integración a `main` no se modificó el `schema_sync` desatendido. Para instalar únicamente las tablas de revisión:

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python .\scripts\install_ai_review_schema.py
```

Esto aplica `sql/115_ai_review/01_ai_review.sql` sobre PostgreSQL local. No toca CRM ni tablas de ejecución comercial.

Luego `review --persist-db` puede guardar borradores validados en `decision_intelligence.ai_review_*`.

## Feedback humano

```powershell
python scripts\medallio_ai_review.py feedback `
  --record private\md_review.json `
  --finding-index 0 `
  --verdict REVISE `
  --reviewer analyst `
  --note "Comprobar contra outcomes maduros" `
  --output private\md_feedback.jsonl
```

## Gate antes de ampliar

1. Mantener el paquete dentro de la allowlist.
2. Revisar autorización organizacional, región, retención y presupuesto.
3. Construir un set de evaluación con casos conocidos.
4. Medir falsos hallazgos, utilidad y tiempo de revisión humana.
5. Expandir solo si la revisión aporta valor frente al analista determinístico y no introduce afirmaciones no sustentadas.

## Principio de operación

Integrar el código en `main` no habilita llamadas ni exportaciones. Todas las acciones externas siguen requiriendo flags explícitos, credenciales locales y aprobación humana.
