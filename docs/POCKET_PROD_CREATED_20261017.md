# Medallio Pocket PROD — creado 2026-10-17

Proyecto Supabase aislado para el APK Medallio Pocket.

- Project ref: `kecsobzifeireuerjkte`
- Región: `sa-east-1`
- API URL: `https://kecsobzifeireuerjkte.supabase.co`
- Costo cotizado al crear: US$0/mes adicional

## Security baseline aplicado

- 10 tablas `pocket_*` con RLS.
- `anon`: 0 privilegios sobre tablas Pocket.
- `authenticated`: solo `SELECT`, condicionado por `pocket_access`.
- Política adicional restrictiva MFA: JWT debe tener `aal = aal2`.
- Esquema `private` sin acceso para `anon`/`authenticated`.
- Default privileges revocados para futuras tablas/secuencias/funciones en `public`.
- Auditoría de nombres de columnas sensibles: 0 coincidencias.
- Security Advisor después del hardening: 0 hallazgos.

## Qué NO debe existir en este proyecto

- clientes
- leads
- teléfonos / emails / DNI
- conversaciones o notas CRM
- raw/staging/core de Medallio
- credenciales Redshift
- `service_role` en el APK

## Flujo previsto

`medallio_dw -> analytics.v_pocket_commercial_project_month -> allowlist + HMAC -> Pocket PROD -> Android`

El primer snapshot comercial real debe ejecutarse desde la máquina que tiene acceso a `medallio_dw`, usando `scripts/sync_pocket_prod.py` y un secreto HMAC local de al menos 32 bytes.

## Pendientes operativos

1. Crear/invitar el primer usuario Auth de Pocket.
2. Insertar su UUID en `public.pocket_access`.
3. Enrolar MFA TOTP y actualizar el login Android para challenge/verify AAL2.
4. Configurar localmente `MEDALLIO_DSN`, `POCKET_SUPABASE_DB_URL` y `POCKET_PROJECT_HMAC_KEY`.
5. Ejecutar `python scripts/install_pocket_commercial.py`.
6. Ejecutar `python scripts/sync_pocket_prod.py --dry-run` y luego sin `--dry-run`.
7. Verificar privacy audit y Security Advisor después del primer snapshot.
