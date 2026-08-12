# Orden recomendado en DBeaver

1. Conectarse a `medallio_dw` y verificar `SELECT current_database(), current_user;`.
2. Ejecutar `00_preflight_control_and_schemas.sql`.
3. Ejecutar `01_inventory_metadata.sql`.
4. Resolver `datos_extras` con `02_find_datos_extras.sql`.
5. Inspeccionar dominio de eventos con `03_process_event_domain.sql`.
6. Validar business key con `04_business_key_cardinality.sql`.
7. Comprobar composición de proformas con `05_proforma_unidad_relationships.sql`.
8. Investigar dependencia de fecha de venta con `06_sale_date_dependency_probe.sql`.
9. Investigar entrada a stock con `07_stock_entry_candidate_probe.sql`.
10. Revisar secuencias con `08_temporal_sequences_probe.sql`.
11. Revisar planes con `09_performance_probe.sql`.
12. Ejecutar QA inicial con `10_data_quality_probe.sql`.

No crear todavía índices ni marts definitivos antes de revisar estos resultados.
