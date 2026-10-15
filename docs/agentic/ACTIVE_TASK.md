# Active Task

Task ID: MARKETING-AUDIENCES-001
Title: Audiencias locales LAL/RMKT mantenidas por el refresh canónico
Status: REVIEW_READY
Owner: chatgpt
Next agent: human
Branch: feat/medallio-refresh-hardening-review
Base branch: main

## Result

Se añadieron un mart local y vistas separadas para base positiva, negativa sin
avance y exclusiones. La base positiva incluye proforma, separación y
minuta/venta; la negativa usa 180 días sin avance. Consentimientos y supresiones
son explícitos y nunca se infieren. El paso corre después de clientes_calidad en
el refresh canónico y no añade llamadas a Redshift.

## Validation

La prueba SQL aislada PGlite pasa con proforma, separación, venta, antigüedad,
contacto, consentimiento y supresión. Quince pruebas Python relevantes pasan;
py_compile y diff-check pasan. El PostgreSQL y el Programador de tareas del PC
requieren smoke test local.

## Next action

Actualizar la rama en el PC, instalar `marketing_audiences`, ejecutar una vez el
refresh local y verificar `02c_marketing_audiences_refresh` en el log. Luego
conectar las vistas `analytics.v_marketing_*` desde Power BI. Ver
`docs/MARKETING_AUDIENCIAS.md`.
