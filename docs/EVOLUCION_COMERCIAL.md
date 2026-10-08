# Evolución comercial comparable

Producto local sobre `v_absorcion_ventas_unidad` y `core.dim_unidad`.
No añade consultas Redshift ni activa GitHub Actions.

## Instalar y actualizar (PowerShell, carpeta bd_replica_crm)

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts\schema_sync.py --only absorcion_ventas_mensual --only evolucion_comercial
.\.venv\Scripts\python.exe scripts\refresh_evolucion_comercial.py
```

Actualizar CORE y absorción con el flujo local habitual antes del refresh.
Ejecutar este refresh una vez al día después de ese flujo. No se instala una tarea
programada automáticamente. Es transaccional y serializado; repetirlo el mismo día
recalcula los paneles pero conserva la primera observación de precios de ese día.
`schema_sync` instala contratos, el segundo script llena las tablas.

## Tablas para Power BI

| Objeto analytics | Una fila por | Uso |
|---|---|---|
| comercial_proyecto_mes | proyecto × mes | Stock al lanzamiento, stock inicial mensual, ventas, acumulado, stock final, absorción y exposición |
| comercial_unidad_mes | departamento × mes del proyecto | Modelar venta/no venta, edad comercial, calendario, tipología, dormitorios, área y precio relativos |
| v_comercial_composicion_mes | proyecto × mes × tipología × dormitorios | Comparar mezcla inicial, vendida y remanente |
| comercial_precio_observado | departamento × día observado | Historia prospectiva de precios de lista y atributos |
| v_comercial_indice_precios | proyecto × moneda × mes observado | Índice nominal de precio/m² base 100, cesta fija y cobertura |
| v_comercial_calendario | proyecto × mes calendario | Tasa descriptiva sobre meses completos |

Usar dimensiones de proyecto y fecha relacionadas 1:* con cada tabla, sin relaciones
hecho-a-hecho. Mes_vida es entero: 1,2,3…; periodo_mes conserva el calendario real.

## Reglas de interpretación

- Empieza en el mes de ingreso efectivo canónico, incluso antes de 2024. Termina en
  el mes de agotamiento o en el presente si quedan unidades. Conserva meses con cero ventas.
- Stock inicial del primer mes = stock de lanzamiento. Es el saldo disponible antes
  de las ventas de ese primer mes, distinto del saldo anterior al alta del mart antiguo.
- Supone todas las altas al comienzo del proyecto, siguiendo la regla aprobada.
  No representa liberaciones escalonadas observadas. NP solo NP-A; proyectos sin
  inicio definido continúan en `v_absorcion_proyectos_sin_inicio`, no se inventan fechas.
- Histórico reconstruido con ventas vigentes: las anulaciones modifican meses pasados.
  No es información conocida en aquel momento. No usarlo como backtest point-in-time.
- `requiere_revision` y `unidades_revision` conservan las alertas heredadas. Un stock
  pendiente puede contener ventas sin fecha confirmada. No afirmar agotamiento real
  sin resolverlas. No se modifican reglas de fecha de minuta ni veto legacy 2026.
- Mes 1 representa un mes calendario de alta, no 30 días exactos desde lanzamiento.
  El alta se normalizó al primer día; exposición inicial también es reconstruida.
- Exposición: días de unidad pendiente hasta la venta (inclusive) o el corte. Las
  unidades vendidas anteriormente tienen exposición cero. Tasa = ventas/exposición×30.
- Composición histórica usa atributos actuales de CORE: dormitorio/tipología/área
  pueden haber sido corregidos después. Los snapshots conservan atributos desde hoy.
- Área relativa = área / media del universo inicial del mismo proyecto y dormitorios.
  0.85 representa un departamento 15% menor que esa referencia. No mezclar esa
  comparación interna con diferencias de área absoluta entre proyectos.
- Precio relativo = precio/m² / media del stock inicial del mismo proyecto, mes,
  dormitorios y moneda. Solo observaciones anteriores al primer día del mes;
  no se rellena el pasado con el precio actual. Moneda desconocida no genera ratio.
  Ver fecha_precio_observado para antigüedad; histórico anterior a captura estará NULL.
- Monedas separadas, sin asumir PEN, sin tipo de cambio inventado. El precio es de
  lista nominal; no es precio de cierre, descuento, precio real deflactado ni elasticidad.

## Serie de precios normalizados

Cada proyecto/moneda inicia en su primer mes con observaciones válidas. La cesta fija
contiene las unidades observadas en ese mes, incluidas las vendidas para evitar que
el índice cambie solo por retirar unidades. Para cada unidad se calcula el cociente
precio/m² actual / precio/m² base. El índice es 100 por su media geométrica.
Usa la última observación real de cada mes. Un mes sin observaciones no se inventa.
Si falta alguna unidad de la cesta, índice NULL y cobertura <100%; no se sustituye por
un índice de composición variable. Revisar bajas y monedas modificadas. El índice
puede reflejar correcciones de área, no solo precio; los snapshots permiten auditarlas.
Mes actual es provisional; primer mes base se completa con observaciones de ese mes
hasta su cierre. Fechas de actualización y carga no prueban precios históricos.
Una serie histórica de cierre requiere importación futura de evidencia fechada,
moneda y precio de departamento sin estacionamientos/depósitos incluidos.

## Estacionalidad y estacionariedad

Estacionalidad es el patrón por mes del año; estacionariedad es la estabilidad de
propiedades estadísticas de una serie. Estos paneles permiten estudiar ambas, pero
no declaran automáticamente un efecto estacional ni una relación causal de precios.

Para estimar estacionalidad, usar panel de meses completos con stock/exposición >0,
controlar proyecto, mes_vida (flexible), año/tendencia, dormitorios, tipología y área.
Una regresión de conteos con log(exposición) como offset o supervivencia discreta a
nivel unidad evita confundir pocas ventas con poco inventario. Empezar sin precios
si aún no hay historia; incorporarlos solo cuando exista cobertura suficiente.
Revisar solapamiento entre proyectos/edades y meses del año: con pocos ciclos la
estacionalidad puede no identificarse. Validación temporal y errores agrupados por
proyecto; incluir campañas/etapa cuando haya historia documentada. No interpretar
el coeficiente del precio como elasticidad causal: ajustes de precio responden a demanda.

Para estacionariedad, estudiar tendencia y log-variaciones del índice cuando haya
historia suficiente y continua; no ejecutar pruebas sobre una única observación ni
sobre meses rellenados artificialmente. Un índice base 100 no vuelve estacionaria la serie.

## Visuales recomendados

1. Curvas por mes_vida: absorción acumulada, con líneas por proyecto.
2. Matriz proyecto × mes_vida: ventas/stock inicial y tooltip con denominador.
3. Composición: dormitorios/tipología del lanzamiento frente al stock remanente.
4. Dispersión de área/precio relativos frente a absorción o tiempo hasta venta,
   mostrando unidades no vendidas como censuradas y filtrando calidad/cobertura.
5. Calendario enero-diciembre de tasas descriptivas, luego efectos ajustados del modelo.
6. Línea de índice base 100 por proyecto y moneda, con cobertura y fecha observada.

Nunca sumar porcentajes ni índices en Power BI; recalcular absorción como
SUM(ventas_mes)/SUM(stock_inicial). Evitar sumar stock de distintos meses.
