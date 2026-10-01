from __future__ import annotations

from pathlib import Path
from textwrap import wrap

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .types import FamilyResult


class PresentationBuilder:
    """PDF multipágina generado desde los resultados estructurados."""

    def __init__(self, title: str):
        self.title = title

    @staticmethod
    def _text_page(pdf: PdfPages, heading: str, lines: list[str]) -> None:
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.text(0.07, 0.92, heading, fontsize=22, weight="bold", va="top")
        y = 0.84
        for raw in lines:
            wrapped = wrap(str(raw), width=105) or [""]
            for idx, line in enumerate(wrapped):
                prefix = "• " if idx == 0 else "  "
                fig.text(0.09, y, prefix + line, fontsize=12, va="top")
                y -= 0.045
                if y < 0.08:
                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)
                    fig = plt.figure(figsize=(11.69, 8.27))
                    y = 0.9
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    def build(self, results: list[FamilyResult], output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        with PdfPages(output) as pdf:
            self._text_page(
                pdf,
                self.title,
                [
                    "Medallio como laboratorio: datos del ciclo comercial transformados en preguntas probabilísticas.",
                    "Ruta narrativa: variable aleatoria → incertidumbre → tiempo → predicción → estructura latente.",
                    "Fuente: PostgreSQL local medallio_dw. El laboratorio no consulta Redshift.",
                ],
            )
            for i, result in enumerate(results, start=1):
                lines = [f"Pregunta: {result.question}"]
                lines += [f"Teoría: {x}" for x in result.theory]
                lines += [f"Métrica · {k}: {v}" for k, v in result.metrics.items()]
                lines += [f"Lectura: {x}" for x in result.insights]
                lines += [f"Limitación: {x}" for x in result.limitations]
                self._text_page(pdf, f"{i}. {result.title}", lines)

                for fig_path in result.figures:
                    if not fig_path.exists():
                        continue
                    img = plt.imread(fig_path)
                    fig = plt.figure(figsize=(11.69, 8.27))
                    ax = fig.add_axes([0.06, 0.08, 0.88, 0.84])
                    ax.imshow(img)
                    ax.axis("off")
                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)
        return output
