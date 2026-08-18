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
    motivo_caida_updated_at,
    has_motivo_text,
    has_confirmed_department_change,
    has_any_reason_evidence,
    reason_evidence_mode
from decision_intelligence.v_fall_reason_analysis_corpus
where has_any_reason_evidence
order by fecha_caida, codigo_proforma
"""

HEALTH_SQL = "select * from decision_intelligence.v_fall_reason_analysis_health"
OUTCOME_HEALTH_SQL = "select * from decision_intelligence.v_separation_fall_outcome_health"

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

# Transparent business taxonomy. A row can receive multiple tags; the first tag
# is retained as primary only for compact reporting. Structured department change
# evidence has precedence because it is a direct CRM field rather than inference.
TAXONOMY: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "FINANCIAMIENTO_CREDITO",
        (
            "credito", "banco", "bancario", "financiamiento", "financiar",
            "aprobacion", "calificacion", "califica", "score", "tasa",
            "financiero", "financiera", "financieros", "financieras",
        ),
    ),
    (
        "CAPACIDAD_PAGO",
        (
            "cuota inicial", "cuotas futuras", "cuota", "inicial", "ingreso",
            "presupuesto", "liquidez", "dinero", "capacidad", "fondos",
            "economico", "economica", "no podre cumplir", "no puede asumir",
        ),
    ),
    (
        "CONTACTABILIDAD",
        (
            "no responde", "sin respuesta", "llamadas", "llamada", "correo",
            "correos", "inubicable", "no contesta", "sin contacto",
        ),
    ),
    (
        "DOCUMENTACION_LEGAL",
        (
            "documento", "documentacion", "terreno", "legal", "contrato",
            "partida", "titulo", "notaria",
        ),
    ),
    (
        "PRECIO_CONDICIONES",
        (
            "precio", "descuento", "caro", "costo", "costoso", "cotizacion",
            "promocion", "bono", "condiciones comerciales",
        ),
    ),
    (
        "PROYECTO_EJECUCION",
        (
            "retraso", "retrasos", "construccion", "estado del proyecto",
            "avance de obra", "obra", "entrega del proyecto",
        ),
    ),
    (
        "PRODUCTO_UNIDAD",
        (
            "metraje", "distribucion", "piso", "vista", "dormitorio", "habitacion",
            "balcon", "terraza", "estacionamiento", "deposito", "departamento",
            "depa", "unidad", "acabado", "no le agrado",
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
        "PERSONAL_FAMILIAR_SALUD_LABORAL",
        (
            "familia", "familiar", "personales", "personal", "salud", "operacion",
            "trabajo", "laboral", "viaje", "divorcio", "mudanza", "pareja",
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
            "Analiza motivo_caida_segun_asesor y evidencia estructurada de cambio "
            "como POST_OUTCOME_ONLY. Nunca la incorpora al scoring live."
        )
    )
    parser.add_argument("--topics", type=int, default=6, help="Máximo de tópicos NMF.")
    parser.add_argument(
        "--min-docs",
        type=int,
        default=12,
        help="Mínimo de textos libres no vacíos para intentar topic modelling.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/fall_reason_text",
        help="Directorio relativo al project root.",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9ñ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_confirmed_department_change(cambio_departamento: Any, depa_del_cambio: Any) -> bool:
    # Do not treat generic values such as "Se cayó" as department changes.
    target = normalize_text(depa_del_cambio)
    if target:
        return True
    cambio = normalize_text(cambio_departamento)
    return bool(cambio and ("cambi" in cambio or "otro departamento" in cambio))


def taxonomy_tags(
    normalized_text: str,
    cambio_departamento: Any,
    depa_del_cambio: Any,
) -> list[str]:
    tags: list[str] = []
    if is_confirmed_department_change(cambio_departamento, depa_del_cambio):
        tags.append("CAMBIO_UNIDAD")

    for label, terms in TAXONOMY:
        if any(normalize_text(term) in normalized_text for term in terms):
            tags.append(label)

    if not tags:
        cambio = normalize_text(cambio_departamento)
        if cambio in {"se cayo", "cayo", "caida"}:
            tags.append("DESISTIMIENTO_SIN_DETALLE")
        else:
            tags.append("OTRO_NO_CLASIFICADO")

    # Stable de-duplication while preserving precedence/order.
    return list(dict.fromkeys(tags))


def fetch_rows(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def build_topics(
    free_text_df: pd.DataFrame,
    *,
    max_topics: int,
    min_docs: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if len(free_text_df) < min_docs:
        return free_text_df, []

    vectorizer = TfidfVectorizer(
        stop_words=sorted(SPANISH_STOP_WORDS),
        ngram_range=(1, 2),
        min_df=2 if len(free_text_df) >= 20 else 1,
        max_df=0.95 if len(free_text_df) >= 20 else 1.0,
        max_features=3000,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(free_text_df["motivo_caida_text_normalized"])
    if matrix.shape[0] < 3 or matrix.shape[1] < 3:
        return free_text_df, []

    n_topics = min(max_topics, matrix.shape[0] - 1, matrix.shape[1] - 1)
    if n_topics < 2:
        return free_text_df, []

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

    result = free_text_df.copy()
    best_zero_based = weights.argmax(axis=1)
    result["topic_id"] = best_zero_based + 1
    result["topic_weight"] = weights.max(axis=1)
    return result, topic_rows


def main() -> int:
    args = _parse_args()
    settings = load_settings()
    output_dir = settings.project_root / Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect_postgres(settings) as conn:
        corpus_rows = fetch_rows(conn, FALL_CORPUS_SQL)
        health_rows = fetch_rows(conn, HEALTH_SQL)
        outcome_health_rows = fetch_rows(conn, OUTCOME_HEALTH_SQL)

    df = pd.DataFrame(corpus_rows)
    health = health_rows[0] if health_rows else {}
    outcome_health = outcome_health_rows[0] if outcome_health_rows else {}

    if df.empty:
        summary = {
            "status": "NO_REASON_EVIDENCE_ROWS",
            "message": "No hay evidencia histórica de motivo de caída para analizar.",
            "health": health,
            "outcome_health": outcome_health,
            "leakage_rule": "fall reason evidence is POST_OUTCOME_ONLY",
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    df["motivo_caida_text_normalized"] = df["motivo_caida_segun_asesor"].map(normalize_text)
    all_tags: list[list[str]] = [
        taxonomy_tags(text, cambio, depa)
        for text, cambio, depa in zip(
            df["motivo_caida_text_normalized"],
            df["cambio_de_departamento"],
            df["depa_del_cambio"],
            strict=False,
        )
    ]
    df["reason_tags"] = ["|".join(tags) for tags in all_tags]
    df["primary_reason_taxonomy"] = [tags[0] for tags in all_tags]
    df["reason_tag_count"] = [len(tags) for tags in all_tags]

    free_text_df = df[df["motivo_caida_text_normalized"].str.len() > 0].copy()
    free_text_topics, topic_rows = build_topics(
        free_text_df,
        max_topics=args.topics,
        min_docs=args.min_docs,
    )
    if "topic_id" in free_text_topics.columns:
        topic_lookup = free_text_topics.set_index("codigo_proforma")[["topic_id", "topic_weight"]]
        df = df.join(topic_lookup, on="codigo_proforma")

    taxonomy_counts = (
        df.groupby("primary_reason_taxonomy", dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "primary_reason_taxonomy"], ascending=[False, True])
    )

    tag_counter: Counter[str] = Counter(tag for tags in all_tags for tag in tags)
    tag_counts = pd.DataFrame(
        [{"reason_tag": key, "falls": value} for key, value in tag_counter.items()]
    ).sort_values(["falls", "reason_tag"], ascending=[False, True])

    project_counts = (
        df.groupby(["codigo_proyecto", "primary_reason_taxonomy"], dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "codigo_proyecto"], ascending=[False, True])
    )
    advisor_counts = (
        df.groupby(["asesor", "primary_reason_taxonomy"], dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "asesor"], ascending=[False, True])
    )
    evidence_mode_counts = (
        df.groupby("reason_evidence_mode", dropna=False)
        .size()
        .reset_index(name="falls")
        .sort_values(["falls", "reason_evidence_mode"], ascending=[False, True])
    )

    df.to_csv(output_dir / "fall_reason_records.csv", index=False, encoding="utf-8-sig")
    taxonomy_counts.to_csv(output_dir / "taxonomy_counts.csv", index=False, encoding="utf-8-sig")
    tag_counts.to_csv(output_dir / "reason_tag_counts.csv", index=False, encoding="utf-8-sig")
    project_counts.to_csv(output_dir / "taxonomy_by_project.csv", index=False, encoding="utf-8-sig")
    advisor_counts.to_csv(output_dir / "taxonomy_by_advisor.csv", index=False, encoding="utf-8-sig")
    evidence_mode_counts.to_csv(output_dir / "evidence_mode_counts.csv", index=False, encoding="utf-8-sig")
    if topic_rows:
        pd.DataFrame(topic_rows).to_csv(output_dir / "nmf_topics.csv", index=False, encoding="utf-8-sig")

    summary = {
        "status": "OK",
        "reason_evidence_records_analyzed": int(len(df)),
        "free_text_documents_analyzed": int(len(free_text_df)),
        "primary_taxonomy_distribution": dict(Counter(df["primary_reason_taxonomy"])),
        "multi_label_tag_distribution": dict(tag_counter),
        "evidence_mode_distribution": dict(Counter(df["reason_evidence_mode"])),
        "nmf_topics_built": len(topic_rows),
        "health": health,
        "outcome_health": outcome_health,
        "outputs": [
            "fall_reason_records.csv",
            "taxonomy_counts.csv",
            "reason_tag_counts.csv",
            "taxonomy_by_project.csv",
            "taxonomy_by_advisor.csv",
            "evidence_mode_counts.csv",
            *(["nmf_topics.csv"] if topic_rows else []),
        ],
        "interpretation": (
            "Taxonomy uses free text plus structured department-change evidence. "
            "NMF uses free text only. All reason evidence remains post-outcome and "
            "is not eligible as a live risk feature."
        ),
        "leakage_rule": "fall reason evidence is POST_OUTCOME_ONLY",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
