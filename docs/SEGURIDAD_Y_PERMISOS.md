# Seguridad y permisos

Antes de copiar datos del cliente a una laptop, confirma autorización explícita de Cygnus y las reglas aplicables de Sperant. La viabilidad técnica no reemplaza la autorización para almacenar datos personales fuera de la infraestructura administrada.

## Controles mínimos

1. Usa un usuario Redshift **solo lectura** y restringido a los esquemas necesarios.
2. No compartas `.env`; está excluido por `.gitignore`.
3. Activa BitLocker o el cifrado de dispositivo de Windows.
4. Protege la sesión de Windows con contraseña y bloqueo automático.
5. No sincronices columnas personales que no sean necesarias para BI o ML.
6. No subas la base local, archivos de logs ni exports a repositorios públicos.
7. Evita conectarte desde redes públicas; usa la VPN corporativa cuando corresponda.
8. Define una política de retención y borrado cuando termine la relación con el cliente.
9. Cambia las credenciales si sospechas que fueron expuestas.
10. Verifica que Power BI y notebooks no exporten DNI, teléfonos o correos sin necesidad.

## Usuario Redshift recomendado

El sistema necesita como máximo:

- permiso de conexión a la base;
- `USAGE` sobre el esquema fuente;
- `SELECT` sobre las tablas autorizadas;
- visibilidad del catálogo de columnas.

No necesita `INSERT`, `UPDATE`, `DELETE`, `CREATE` ni `DROP` en Redshift.
