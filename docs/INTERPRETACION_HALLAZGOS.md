# Interpretación de resultados reales

## 1. Las 74 Ventas no efectivas

Estados anteriores:

- SOLD: 50
- AVAILABLE: 24

Interpretación:

### SOLD → Venta

No es una nueva salida de inventario.
La unidad ya había alcanzado SOLD por una operación/evento anterior.
Puede ser:

- regularización;
- workflow administrativo posterior;
- otra proforma documental sobre unidad ya vendida;
- reproceso histórico.

Debe conservarse para auditoría, pero:

`delta_ventas_inventario = 0`

### AVAILABLE → Venta

Existe una venta documental sin una transición efectiva previa a SEPARATED.
No debe inventarse la separación.

Se conserva como:

`VENTA_DOCUMENTAL_SIN_SEPARACION_EFECTIVA`

y requiere análisis de calidad/proceso.

## 2. Las 126 Separaciones no efectivas

- SOLD: 73
- SEPARATED: 53

### SOLD

Workflow comercial sobre unidad que el ledger ya considera vendida.

### SEPARATED

Evento redundante o workflow adicional mientras la unidad ya estaba separada.

En ambos casos:

`delta_stock = 0`

## 3. Las 111 Caídas no efectivas

- SOLD: 102
- AVAILABLE: 9

La Anulación se conserva como evento RAW/documental.

Solo:

`SEPARATED → AVAILABLE`

puede generar reingreso.

## 4. Reconciliación

1833 de 1962 ciclos coinciden directamente.

Los 129 restantes NO deben interpretarse automáticamente como bugs.

La divergencia es una señal de que:

`workflow documental ≠ transición física de inventario`

Por eso los marts futuros deben elegir la semántica correcta según la métrica:

- Stock / absorción física → ledger efectivo.
- Auditoría de workflow → ciclo documental.
- Ventas canónicas → venta documental + transición física + reglas de calidad.
