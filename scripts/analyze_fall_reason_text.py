from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from psycopg.rows import dict_row
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


FALL_CORPUS_SQL = """
select
    codigo_proforma,
    codigo_proyecto,
    asesor,
    fecha_separacion,
    fecha_caida,
    days_to_fall,
    motivo_caida_segun_asesor,
    cambio_de_departamento,
    depa_del_cambio,
    motivo_caida_updated_at
from decision_intelligence.v_fall_reason_proforma_history
where has_fall_reason_text
order by fecha_caida, codigo_proforma
"""

HEALTH_SQL = "select * from decision_intelligence.v_separation_fall_outcome_health"

# Deliberately local/self-contained: no runtime language-model dependency and no
# network downloads. The unsupervised topics are exploratory, not canonical labels.
SPANISH_STOP_WORDS = {
    "a", "al", "algo", "algun", "alguna", "algunas", "alguno", "algunos",
    "ante", "antes", "como", "con", "contra", "cual", "cuando", "de", "del",
    "desde", "donde", "dos", "el", "ella", "ellas", "ellos", "en", "entre",
    "era", "es", "esa", "ese", "eso", "esta", "estaba", "este", "esto",
    "fue", "ha", "hacia", "hasta", "hay", "la", "las", "le", "les", "lo",
    "los", "mas", "me", "mi", "mis", "muy", "no", "nos", "o", "para",
    "pero", "por", "porque", "que", "se", "sin", "sobre", "su", "sus",
    "tambien", "te", "tiene", "un", "una", "uno", "unos", "unas", "y", "ya",
    "cliente", "clientes", "asesor", "asesora", "proforma",
}

# Transparent first-pass taxonomy. Keep it auditable; discovered topics can later
# be used to revise this dictionary with business-owner approval.
TAXONOMY: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "FINANCIAMIENTO_CREDITO",
        (
            "credito", "banco", "bancario", "financiamiento", "financiar",
            "aprobacion", "calificacion", "califica", "score", "deuda",
        ),
    ),
    (
        "CAPACIDAD_PAGO",
        (
            "cuota", "inicial", "ingreso", "presupuesto", "liquidez", "dinero",
            "pago", "capacidad", "economico", "economica", "fondos",
        ),
    ),
    (
        "PRECIO_CONDICIONES",
        (
            "precio", "descuento", "caro", "costo", "costoso", "cotizacion",
            "promocion", "bono", "tasa", "condiciones",
        ),
    ),
    (
        "CAMBIO_UNIDAD",
        (
            "cambio de departamento", "cambio departamento", "cambiar depa",
            "cambio depa", "otra unidad", "otro departamento", "otra tipologia",
        ),
    ),
    (
        "PRODUCTO_UNIDAD",
        (
            "metraje", "distribucion", "piso", "vista", "dormitorio", "habitacion",
            "balcon", "terraza", "estacionamiento", "deposito", "departamento",
            "depa", "unidad", "acabado",
        ),
    ),
    (
        "UBICACION",
        ("ubicacion", "distrito", "zona", "distancia", "lejos", "avenida"),
    ),
    (
        "COMPETENCIA_OTRA_OPCION",
        (
            "competencia", "otra inmobiliaria", "otro proyecto", "compro otro",
            "compro en", "otra opcion", "otra alternativa",
        ),
    ),
    (
        "PERSONAL_FAMILIAR",
        (
            "familia", "familiar", "personal", "salud", "trabajo", "laboral",
            "viaje", "separacion", "divorcio", "mudanza",
        ),
    ),
    (
        "POSTERGACION_TIEMPO",
        (
            "posterga", "postergar", "mas adelante", "despues", "esperar",
            "tiempo", "aun no", "todavia no", "proximo ano",
        ),
    ),
    (
        "DESISTIMIENTO_SIN_DETALLE",
        ("desiste", "desistio", "ya no desea", "ya no quiere", "no interesado"),
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analiza motivo_caida_segun_asesor como evidencia post-outcome. "
            "Nunca lo incorpora al scoring live."
        )
    )
    parser.add_argument("--topics", type=int, default=6, help="Máximo de tópicos NMF.")
    parser.add_argument(
        "--min-docs",
        type=int,
        default=12,
        help="Mínimo de textos no vacíos para intentar topic modelling.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/fall_reason_text",
        help="Directorio relativo al project root.",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ñ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def taxonomy_label(normalized_text: str, cambio_departamento: Any) -> str:
    # Structured CRM evidence beats keyword inference for this specific reason.
    cambio = normalize_text(cambio_departamento)
    if cambio and cambio not in {"no", "0", "false", "falso", "ninguno", "ninguna"}:
        return "CAMBIO_UNIDAD"

    for label, terms in TAXONOMY:
        if any(normalize_text(term) in normalized_text for term in terms):
            return label
    return "OTRO_NO_CLASIFICADO"


def fetch_rows(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def build_topics(df: pd.DataFrame, *, max_topics: int, min_docs: int) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if len(df) < min_docs:
        return df, []

    vectorizer = TfidfVectorizer(
        stop_words=sorted(SPANISH_STOP_WORDS),
        ngram_range=(1, 2),
        min_df=2 if len(df) >= 20 else 1,
        max_df=0.95 if len(df) >= 20 else 1.0,
        max_features=3000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(df["motivo_caida_text_normalized"])
    if matrix.shape[0] < 3 or matrix.shape[1] < 3:
        return df, []

    n_topics = min(max_topics, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if n_topics < 2:
        return df, []

    model = NMF(
        n_components=n_topics,
        init="nndsvda",
        random_state=42,
        max_iter=700,
    )
    weights = model.fit_transform(matrix)
    terms = vectorizer.get_feature_names_out()

    topic_rows: list[dict[str, Any]] = []
    for topic_id, component in enumerate(model.components_, start=1):
        top_indices = component.argsort()[::-1][:12]
        top_terms = [str(terms[index]) for index in top_indices]
        topic_rows.append(
            {
                "topic_id": topic_id,
                "top_terms": top_terms,
                "top_terms_text": " | ".join(top_terms),
            }
        )

    best_zero_based = weights.argmax(axis=1)
    df = df.copy()
    df["topic_id"] = best_zero_based + 1
    df["topic_weight"] = weights.max(axis=1)
    return df, topic_rows


def main() -> int:
    args = _parse_args()
    settings = load_settings()
    output_dir = settings.project_root / Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        corpus_rows = fetch_rows(conn, FALL_CORPUS_SQL)
        health_rows = fetch_rows(conn, HEALTH_SQL)

    df = pd.DataFrame(corpus_rows)
    health = health_rows[0] if health_rows else {}

    if df.empty:
        summary = {
            "status": "NO_TEXT_ROWS",
            "message": "No hay motivos de caída no vacíos en el corpus histórico instalado.",
            "health": health,
            "leakage_rule": "motivo_caida_segun_asesor is POST_OUTCOME_ONLY",
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    df["motivo_caida_text_normalized"] = df["motivo_caida_segun_asesor"].map(normalize_text)
    df = df[df["motivo_caida_text_normalized"].str.len() > 0].copy()
    df["reason_taxonomy"] = [
        taxonomy_label(text, cambio)
        for text, cambio in zip(
            df["motivo_caida_text_normalized"],
            df["cambio_de_departamento"],
            strict=False,
        )
    ]

    df, topic_rows = build_topics(df, max_topics=args.topics, min_docs=args.min_docs)

    taxonomy_counts = (
        df.groupby("reason_taxonomy", dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "reason_taxonomy"], ascending=[False, True])
    )
    project_counts = (
        df.groupby(["codigo_proyecto", "reason_taxonomy"], dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "codigo_proyecto"], ascending=[False, True])
    )
    advisor_counts = (
        df.groupby(["asesor", "reason_taxonomy"], dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "asesor"], ascending=[False, True])
    )

    df.to_csv(output_dir / "fall_reason_records.csv", index=False, encoding="utf-8-sig")
    taxonomy_counts.to_csv(output_dir / "taxonomy_counts.csv", index=False, encoding="utf-8-sig")
    project_counts.to_csv(output_dir / "taxonomy_by_project.csv", index=False, encoding="utf-8-sig")
    advisor_counts.to_csv(output_dir / "taxonomy_by_advisor.csv", index=False, encoding="utf-8-sig")
    if topic_rows:
        pd.DataFrame(topic_rows).to_csv(output_dir / "nmf_topics.csv", index=False, encoding="utf-8-sig")

    summary = {
        "status": "OK",
        "documents_analyzed": int(len(df)),
        "taxonomy_distribution": dict(Counter(df["reason_taxonomy"])),
        "nmf_topics_built": len(topic_rows),
        "health": health,
        "outputs": [
            "fall_reason_records.csv",
            "taxonomy_counts.csv",
            "taxonomy_by_project.csv",
            "taxonomy_by_advisor.csv",
            *( ["nmf_topics.csv"] if topic_rows else [] ),
        ],
        "interpretation": (
            "Taxonomy and NMF topics are exploratory post-outcome analytics. "
            "They may explain historical falls but are not eligible live features."
        ),
        "leakage_rule": "motivo_caida_segun_asesor is POST_OUTCOME_ONLY",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
