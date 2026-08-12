MEDALLIO UNIVERSAL UPGRADE -> v0.3.0

Compatible como overlay para una carpeta basada en v0.1.0 o v0.2.0.
No incluye .env ni config/tables.yml, por lo que no debe reemplazar tus credenciales ni configuración real de tablas.

1) Extraer TODO dentro de la raiz actual del proyecto.
2) Ejecutar scripts\00_actualizar_a_v0.3.0.bat
3) Ejecutar scripts\03_inicializar_postgres.bat
4) Ejecutar scripts\12_inicializar_observabilidad.bat
5) Ejecutar scripts\13_observar_ahora.bat
6) Luego construir Power BI siguiendo powerbi\POWER_BI_BUILD_STEP_BY_STEP.md
