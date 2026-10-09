# Validación — ATLAS-PUBLISH-001

Verificado en entorno aislado sobre el código de esta entrega:

- `python -m pytest tests/publishing tests/test_economics.py tests/test_decision_contracts.py`: **45 aprobadas**.
- `node tests/publishing/check_registry.cjs` con PGlite: instalación dos veces,
  idempotencia, diez vistas, inmutabilidad de releases, referencia de decisiones,
  feedback inmutable y vista de aprendizaje: **PASS**.
- `python -m compileall -q src/replica_cygnus/publishing scripts/publish_atlas.py`: **PASS**.
- Demo CLI → ZIP → importador → HTML offline: **PASS**.
- Exportación determinista y preservación del pack anterior ante corrupción:
  cubiertas por pruebas ejecutadas.
- `python tools/agent_handoff.py validate`: **PASS**.
- `git diff --check`: **PASS**.

La advertencia de ZIP duplicado en pytest es deliberada: se construye un pack
malicioso para confirmar que el importador lo rechaza.

Límites: no se ejecutó toda la suite del repositorio ni el PostgreSQL real del
usuario. PGlite valida SQL aislado, no las credenciales ni el rendimiento local.
La prueba de interfaz con Playwright quedó bloqueada: Chromium no estaba instalado
y su descarga devolvió un archivo inválido. No se afirma verificación visual ni
prueba manual del slider en un navegador. El importador Android no forma parte de
este cambio; requiere implementación en `dntl_economia`.

Para repetir SQL:

```bash
npm install --prefix /tmp/atlas-sql-test @electric-sql/pglite
NODE_PATH=/tmp/atlas-sql-test/node_modules node tests/publishing/check_registry.cjs
```

El código SQL usado no necesita la réplica ni datos reales. El caso de regresión
comercial se mantiene separado; esta capa no modifica sus consultas ni reglas.
