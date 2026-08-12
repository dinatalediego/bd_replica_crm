# Construcción del PBIX — Medallio Control Tower

## Recomendación de conectividad
Para estas tablas de monitoreo recomiendo **Import** en la primera versión: el volumen es pequeño, las medidas responden rápido y el ETL ya mantiene PostgreSQL actualizado. El conector PostgreSQL de Power BI también soporta DirectQuery, pero no aporta mucho en este Sprint.

## 1. Crear un PBIX nuevo
Nombre sugerido:

```text
Medallio - Data & Decision Control Tower.pbix
```

## 2. Crear parámetros Power Query
En Power Query crea consultas en blanco y pega, en este orden:

1. `M/pPostgresServer.m`
2. `M/pPostgresDatabase.m`
3. `M/pDaysHistory.m`

Valores por defecto:

```text
localhost:5432
medallio_dw
90
```

## 3. Crear consultas
Para cada archivo `.m`, crea una consulta en blanco → Editor avanzado → pega el contenido.

Carga:
- qDimAsset
- qDimDate
- qAssetHealthCurrent
- qAssetQualityCurrent
- qAssetSnapshots
- qPipelineRuns
- qQualityChecks
- qModelHealthCurrent
- qDecisionHealthDaily

Renómbralas según `model/RELATIONSHIPS.md`.

## 4. Credenciales
Cuando Power BI pregunte:

```text
Authentication: Database
Server: localhost:5432
Database: medallio_dw
User: tu usuario PostgreSQL
Password: ********
```

## 5. Modelo
Crea las relaciones indicadas en:

```text
powerbi/model/RELATIONSHIPS.md
```

Dirección de filtro: Single.

Marca `Dim Date` como tabla de fechas usando `Dim Date[Date]`.

## 6. Medidas DAX
Crea una tabla vacía de medidas, por ejemplo:

```DAX
_Medidas = { BLANK() }
```

Oculta su única columna y crea allí las medidas de:

```text
DAX/01_Data_Platform.dax
DAX/02_Data_Quality.dax
DAX/03_Models_MLOps.dax
DAX/04_Decisions_Learning.dax
```

Crea cada medida individualmente; los archivos están organizados para copiar por bloques.

## 7. Tema
En Power BI Desktop:

```text
View → Themes → Browse for themes
```

carga:

```text
powerbi/theme/medallio_control_tower_theme.json
```

## 8. Páginas
Crea exactamente cuatro páginas:

```text
01 | Data Platform
02 | Data Quality
03 | Models & MLOps
04 | Decisions & Learning
```

Los layouts están en `powerbi/pages/`.

## 9. Refresh
En Desktop, `Refresh` volverá a consultar PostgreSQL local.

Si posteriormente publicas un modelo Import que depende de PostgreSQL en tu PC/red local, Power BI Service necesita poder alcanzar esa fuente mediante una conexión/gateway configurada. No mezcles todavía esa etapa cloud con el Sprint 1 local.

## 10. Validación funcional
Antes de considerar terminado el PBIX:

- cambia intencionalmente el SLA de un activo a un valor muy bajo y verifica WARN/FAIL;
- comprueba que `business_impact` aparezca en la tabla de excepciones;
- verifica que una ejecución fallida aparezca en `Pipeline Runs`;
- ejecuta `14_calidad_profunda.bat` y confirma que página 02 recibe checks;
- página 03 debe mostrar "sin modelos" si aún no hay registros;
- página 04 debe mostrar "sin decisiones" si aún no hay recomendaciones/outcomes.

Eso es correcto: no se deben inventar métricas inexistentes.
