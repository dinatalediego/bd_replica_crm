# Ambassador v2.4 — Slide Quality & Executive Storytelling

## Objetivo

Elevar la Fase 1 para que el deck de Google Slides ya se parezca más a un
**reporte ejecutivo que tú mismo presentarías a clientes o a Dirección en Cygnus**.

## Qué mejora

### 1. El deck ya no es “un bloque de texto”
Ahora genera 3 slides por slot:

1. **Executive Board**
   - headline ejecutivo;
   - KPI cards (Coverage, WAPE, Trust, Alerts, Open Actions);
   - mensaje ejecutivo para Dirección/Cliente.

2. **Recomendaciones y conclusiones**
   - cambios materiales;
   - recomendaciones accionables;
   - conclusión analítica.

3. **Próximos pasos y evidencia**
   - siguientes pasos sugeridos;
   - activos / evidencia en Drive, Sheets, Slides y Docs.

### 2. Storytelling ejecutivo
La narrativa ya no se limita a copiar links o decisiones crudas.
Construye un mini guion:
- lectura ejecutiva;
- salud analítica;
- disciplina de ejecución;
- mensaje para Cygnus;
- conclusión según severidad.

### 3. Mejor visual
- barra superior corporativa;
- tarjetas KPI;
- cajas por sección;
- colores por severidad;
- mejor jerarquía tipográfica.

### 4. Mejor formato de métricas
Valores como `None` ahora se renderizan como `N/A` y no como `None%`.

## Instalación

Reemplaza:

```text
scripts\medallio_ambassador_v2.py
```

Luego prueba:

```powershell
python .\scripts\medallio_ambassador_v2.py --slot morning --dry-run
python .\scripts\medallio_ambassador_v2.py --slot morning
```

## Siguiente iteración sugerida

La siguiente mejora natural sería una **v2.5 Client Narrative Layer**:
- secciones por proyecto (Matera, Napoles, Urbanzen, etc.);
- riesgos / oportunidades comerciales;
- recomendaciones por área (Comercial, Pricing, Operaciones, Marketing);
- “qué le diría al cliente” vs “qué debe hacer el equipo interno”.
