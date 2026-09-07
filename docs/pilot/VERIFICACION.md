# Evidencia de implementación — 2026-09-07

## Alcance comprobado

64 pruebas de Python del repositorio pasaron, incluyendo 17 nuevas de reglas del piloto. Se conservaron dos warnings preexistentes de NumPy en `training.py`.

Una prueba adicional de integración pasó ejecutando el SQL y las funciones Python reales mediante psycopg contra PostgreSQL compilado a WASM (PGlite, base vacía y efímera). Se aplicaron las migraciones de Decision Intelligence, lead scoring y piloto; la última se aplicó dos veces para verificar repetibilidad. El fixture revierte toda su transacción. No se conectó a Redshift ni al PostgreSQL de Cygnus.

| Recorrido sintético | Evidencia esperada y comprobada |
|---|---|
| Previsualizar 6 filas | 2 admitidas, 1 cliente repetido, 3 rechazadas; 0 asignaciones persistidas |
| Persistir 6 filas | 2 asignaciones + 1 existente + 3 rechazos = 6 |
| Repetir elegibilidad | 0 nuevas; total en destino sigue en 2 |
| Motivos de exclusión | BACKFILL, evidencia anterior a activación, sin score del modelo congelado |
| Cargar 3 acciones | 2 aceptadas, 1 costo negativo rechazado |
| Repetir 2 acciones | 2 existentes, 0 nuevas |
| Alterar evento con misma clave | Rechazo por conflicto, sin sobreescritura |
| Cargar 2 outcomes maduros | 2 aceptados; al repetir, 2 existentes |
| Cola Power BI | 2 filas, una por cliente asignado |
| Monitor Power BI | 4 filas, dos endpoints por cliente |
| Conciliación de costos | S/ 2.50 en cola, sin multiplicación por unión de acciones/outcomes |
| Resultado separación | 1 positivo sintético en vista analítica |
| Pausar/cerrar | Pausa bloquea nuevas asignaciones; cerrado no reabre |

Las pruebas incluyen semilla reproducible en 10 000 identidades sintéticas, formato de identidad, validación de protocolo pendiente, zonas horarias, límites de 14 días, resultados negativos con cobertura completa, costos inválidos y un intervalo no degenerado cuando ambos grupos tienen cero positivos.

## Notebook

Formato JSON/nbformat validado y todas las celdas de código ejecutadas secuencialmente en modo DEMO; tablas, estimación e instrucciones producidas sin errores. El modo LIVE no fue ejecutado contra Cygnus. La ejecución con kernel Jupyter vía nbclient no pudo arrancar por restricción de interfaces de red del entorno (`Operation not permitted`); queda pendiente abrirlo y ejecutar todas las celdas en VS Code con el kernel del proyecto. No confundir ejecución secuencial de las celdas con verificación del kernel.

## Reproducir

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests\requirements-pilot.txt
.\.venv\Scripts\python.exe -m pytest
```

La integración se omite explícitamente si no existe `PILOT_TEST_DSN`. Para verificar en PostgreSQL nativo, apuntar esa variable a una base **vacía dedicada a pruebas**, nunca a la base operativa. El test rechaza una base donde ya existe el esquema `experiments` y revierte los cambios de su fixture.

```powershell
# Usar los datos reales de conexión de una base de pruebas vacía autorizada.
$env:PILOT_TEST_DSN = "postgresql://USUARIO:CLAVE@localhost:5432/BASE_PRUEBAS_VACIA"
.\.venv\Scripts\python.exe -m pytest tests\test_lead_pilot_postgres.py
Remove-Item Env:PILOT_TEST_DSN
```

PGlite ejecuta PostgreSQL real compilado a WASM, pero su multiplexación no reproduce todas las condiciones de concurrencia de un servidor nativo. Prueba de dos importadores concurrentes y rendimiento con volumen real quedan pendientes; hay unicidad y bloqueo de fila por piloto en el código, sin afirmar haber demostrado ese comportamiento multiusuario en este entorno. Referencia: https://pglite.dev/docs/pglite-socket.

## Gates que siguen abiertos

- Aprobación de protocolo, elegibilidad, definiciones de procesos/proformas, SLA y muestra.
- Instalación en la base local del usuario y conciliación de origen/destino sobre datos reales.
- Integración automática de outcomes desde procesos; v1 usa CSV con revisión y cobertura declarada.
- Pruebas de concurrencia y tiempos en PostgreSQL nativo.
- Verificar partición temporal/calibración del modelo existente antes de usarlo en el piloto.
- Publicación Power BI, permisos de lectores y gateway corporativo. No se entregó ni publicó PBIX.
- Correcciones versionadas de resultados finalizados, costos por horizonte y un mecanismo de auditoría de cambios directos en BD.

No se ha lanzado el piloto, asignado clientes reales, enviado mensajes ni demostrado un incremento de ventas.
