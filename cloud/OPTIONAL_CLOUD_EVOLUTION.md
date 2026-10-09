# Evolución cloud opcional

## Secret Manager
Úsalo para secretos cloud cuando tengas ADC/identidad de servicio definida.
No migres el token OAuth Desktop todavía: primero estabiliza el sistema local.

## Pub/Sub
Ambassador puede publicar un `ExecutiveEvent` por corrida.
Útil para desacoplar futuros consumidores: Cloud Functions, web apps, auditoría.

## BigQuery
Puede guardar una fila ejecutiva por corrida.
Recomendación: empezar sólo con resúmenes; no migrar `medallio_dw` completo por ahora.

## Cloud Scheduler
Mientras la fuente sea PostgreSQL local, no debe ser el scheduler principal.
Úsalo después como watchdog cloud: por ejemplo, alertar si no llega un heartbeat/ExecutiveEvent.
