# Laboratorio económico de audiencias de marketing

## Objetivo

`notebooks/12_marketing_audiences_economics_lab.ipynb` convierte el mart local de
audiencias en un laboratorio explicable para negocio. El cuaderno trabaja con
estadística descriptiva, intervalos de confianza, contrastes de hipótesis,
cohortes y matrices proyecto-canal-etapa.

El notebook no consulta Redshift y no carga nombres, documentos, teléfonos ni
correos. Todo el análisis usa atributos agregables de
`analytics.marketing_audiencias` en PostgreSQL local.

## Instalación en VS Code

Desde la raíz del repositorio, en PowerShell:

```powershell
$python = ".\.venv\Scripts\python.exe"
& $python -m pip install -e .
& $python -m pip install ipykernel matplotlib scipy statsmodels
& $python -m ipykernel install --user --name medallio-dw --display-name "Python (Medallio DW)"
code .\notebooks\12_marketing_audiences_economics_lab.ipynb
```

En la esquina superior derecha del notebook seleccionar el kernel
`Python (Medallio DW)` y ejecutar **Run All**.

## Preguntas que responde

1. ¿Qué tamaño y composición tienen las audiencias?
2. ¿Qué proyectos y canales concentran la oportunidad de remarketing?
3. ¿La tasa de avance difiere estadísticamente entre canales?
4. ¿Cómo cambia la conversión proxy por cohorte?
5. ¿Qué diferencias son materialmente importantes y cuáles pueden ser ruido?
6. ¿Qué experimento permitiría medir lift incremental sin confundir asociación
   con causalidad?

## Lectura correcta

- `positiva` significa que existe proforma, separación o minuta/venta. Es una
  proxy de avance histórico, no el efecto causal de un canal.
- `negativa_sin_avance` identifica antigüedad sin avance y sirve para dimensionar
  RMKT; no implica que la persona deba ser contactada.
- `apto_entrega_externa` exige contacto válido, consentimiento vigente y ausencia
  de supresión. Si es cero, el notebook debe utilizarse solo para análisis.
- Las pruebas de hipótesis detectan asociación. Para estimar incrementalidad se
  propone un experimento aleatorio con grupo control.

