# Medallio Ambassador v2.5 — Client Narrative Layer

## Propósito

La v2.5 convierte el deck automático en un **producto de consultoría ejecutiva**:
no sólo muestra qué ocurrió, sino que estructura lo que explicarías a Dirección
o a un cliente inmobiliario y separa esa narrativa de lo que debe ejecutar el equipo interno.

## Slides por slot

### 1. Executive Brief
- headline
- Coverage / WAPE / Trust / Alerts / Open Actions
- Evidence Grade A/B/C
- lectura ejecutiva

### 2. Qué cambió y por qué importa
- cambios materiales
- decisiones sugeridas
- conclusión proporcional a severidad

### 3. Portafolio de proyectos
Ambassador busca artifacts CSV/XLSX de la corrida y detecta columnas como:
- proyecto
- ventas
- minutas / separaciones
- stock
- absorción / ritmo
- forecast / WAPE
- precio / descuento
- monto / revenue
- conversión / leads
- gap / cobertura / aging

Sólo muestra señales si están realmente presentes.
Si no encuentra evidencia tabular, lo declara y recomienda el dataset faltante.

### 4. Recomendaciones por frente
- Comercial
- Pricing
- Operaciones
- Marketing

### 5. Narrativa doble
**Qué le diría al cliente / Dirección**
vs
**Qué debe hacer el equipo interno**

### 6. Rigor económico
- Evidence Grade
- impacto esperado × confianza × urgencia
- owner + outcome
- baseline / challenger
- escalar sólo valor repetible

## Principio anti-hallucination

La v2.5 no fabrica métricas por proyecto.

Si no existe un artifact de la corrida con proyecto + métricas comparables,
la slide lo dice explícitamente.

## Instalación

Reemplaza:

```text
scripts\medallio_ambassador_v2.py
```

Prueba:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Qué debería venir después

Antes de Fase 2 corporativa, la v2.6 ideal sería **Economic Decision Layer**:
- Value at Risk por proyecto
- Value to Capture
- uplift esperado
- costo de acción
- ROI esperado
- confidence-adjusted value
- ranking ejecutivo de decisiones
- decision/outcome ledger
