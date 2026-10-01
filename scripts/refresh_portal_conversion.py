from __future__ import annotations

import argparse
import hashlib
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from portal_conversion.matching import (
    STATUS_RANK,
    MatchResult,
    PersonIdentity,
    best_result,
    canonical_name,
    normalize_dni,
    normalize_source_document,
    score_match,
)
from replica_cygnus.connections import connect_postgres
from replica_cygnus.settings import load_settings


@dataclass
class LeadRow:
    data: dict[str, Any]
    identity: PersonIdentity


@dataclass
class BuyerRow:
    data: dict[str, Any]
    identity: PersonIdentity


def _as_date(value: Any) -> date | None:
    """Normaliza DATE y TIMESTAMP de PostgreSQL para compararlos sin ambigüedad."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresca el mart lead -> Separacion Activo para todos los medio_captacion. "
            "ORIGEN (clientes_proyectos) tiene prioridad sobre MEDIO_ACTUAL (interacciones)."
        )
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=int(os.getenv("PORTAL_CONVERSION_START_YEAR", "2026")),
        help="Primer año a conservar en el mart. Default 2026.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Calcula y valida sin escribir tablas.")
    return parser.parse_args()


def _fetch_dicts(cur, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _client_catalog(
    cur,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    rows = _fetch_dicts(
        cur,
        """
        SELECT
            source_id, documento, numero_documento, nombres, apellidos,
            dq_nombre_cliente, dq_celular_limpio, dq_email_limpio,
            medio_captacion, dq_medio_captacion, dq_score_cliente, dq_contacto_valido_ok
        FROM staging.clientes_calidad
        """,
    )

    def quality_key(row: dict[str, Any]) -> tuple[int, int, str]:
        return (
            int(row.get("dq_score_cliente") or 0),
            1 if row.get("dq_contacto_valido_ok") else 0,
            str(row.get("source_id") or ""),
        )

    by_doc: dict[str, dict[str, Any]] = {}
    by_dni: dict[str, dict[str, Any]] = {}
    by_source_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = normalize_source_document(row.get("source_id"))
        if source_id and (
            source_id not in by_source_id
            or quality_key(row) > quality_key(by_source_id[source_id])
        ):
            by_source_id[source_id] = row
        raw_doc = row.get("documento") or row.get("numero_documento")
        doc_key = normalize_source_document(raw_doc)
        dni = normalize_dni(raw_doc)
        if doc_key and (doc_key not in by_doc or quality_key(row) > quality_key(by_doc[doc_key])):
            by_doc[doc_key] = row
        if dni and (dni not in by_dni or quality_key(row) > quality_key(by_dni[dni])):
            by_dni[dni] = row
    return by_doc, by_dni, by_source_id


def _find_client(
    document: Any,
    client_id: Any,
    by_doc,
    by_dni,
    by_source_id,
) -> dict[str, Any] | None:
    source_id = normalize_source_document(client_id)
    if source_id and source_id in by_source_id:
        return by_source_id[source_id]
    doc_key = normalize_source_document(document)
    if doc_key and doc_key in by_doc:
        return by_doc[doc_key]
    dni = normalize_dni(document)
    return by_dni.get(dni) if dni else None


def _identity_from_client(
    document: Any,
    client: dict[str, Any] | None,
    fallback_name: str = "",
) -> PersonIdentity:
    if client:
        name = client.get("dq_nombre_cliente") or " ".join(
            part for part in [client.get("nombres"), client.get("apellidos")] if part
        )
        client_document = client.get("documento") or client.get("numero_documento")
        return PersonIdentity.build(
            source_document=document or client_document or client.get("source_id"),
            dni=client_document or document,
            name=name,
            phone=client.get("dq_celular_limpio"),
            email=client.get("dq_email_limpio"),
        )
    return PersonIdentity.build(source_document=document, dni=document, name=fallback_name)


def _load_leads(cur, start_year: int, by_doc, by_dni, by_source_id) -> list[LeadRow]:
    start_date = datetime(start_year, 1, 1)
    origin = _fetch_dicts(
        cur,
        """
        SELECT
            cp.id::text AS source_id,
            cp.codigo_proyecto::text AS codigo_proyecto,
            cp.documento_cliente::text AS documento_cliente,
            to_jsonb(cp) ->> 'cliente_id' AS source_cliente_id,
            cp.fecha_creacion, cp.fecha_actualizacion,
            cp.canal_entrada::text AS canal_entrada,
            cp.medio_captacion::text AS medio_captacion,
            cp.nivel_interes::text AS nivel_interes,
            cp.fecha_asignacion,
            cp.vendedor_asignado::text AS vendedor_asignado,
            cp.segmento::text AS segmento,
            cp.utm_source::text AS utm_source,
            cp.utm_medium::text AS utm_medium
        FROM raw_cygnus.clientes_proyectos cp
        WHERE cp.fecha_creacion >= %s
        """,
        (start_date,),
    )
    current = _fetch_dicts(
        cur,
        """
        SELECT
            i.id::text AS source_id,
            i.codigo_proyecto::text AS codigo_proyecto,
            i.documento_cliente::text AS documento_cliente,
            to_jsonb(i) ->> 'cliente_id' AS source_cliente_id,
            i.fecha_creacion, i.fecha_actualizacion,
            i.canal_entrada::text AS canal_entrada,
            i.medio_captacion::text AS medio_captacion,
            i.nivel_interes::text AS nivel_interes,
            i.tipo::text AS tipo_interaccion,
            i.nombre::text AS nombre_interaccion,
            i.segmento::text AS segmento,
            i.utm_source::text AS utm_source,
            i.utm_medium::text AS utm_medium
        FROM raw_cygnus.interacciones i
        WHERE lower(btrim(i.nombre::text)) = 'portal inmobiliario'
          AND i.fecha_creacion >= %s
        """,
        (start_date,),
    )

    leads: list[LeadRow] = []
    for source_name, rows in (("ORIGEN", origin), ("MEDIO_ACTUAL", current)):
        for row in rows:
            document = row.get("documento_cliente")
            client = _find_client(
                document,
                row.get("source_cliente_id"),
                by_doc,
                by_dni,
                by_source_id,
            )
            identity = _identity_from_client(document, client)
            data = {
                **row,
                "lead_uid": f"{source_name}:{row.get('source_id')}",
                "fuente_lead": source_name,
                "cliente_source_id": client.get("source_id") if client else None,
                "nombres": client.get("nombres") if client else None,
                "apellidos": client.get("apellidos") if client else None,
                "nombre_completo": client.get("dq_nombre_cliente") if client else None,
                "dni": identity.dni or None,
                "celular": identity.phone or None,
                "email": identity.email or None,
                "medio_cliente": (
                    client.get("medio_captacion") or client.get("dq_medio_captacion")
                    if client
                    else None
                ),
                "person_key": identity.preferred_person_key() or None,
                "duplicado_en_origen": False,
                "lead_origen_uid": None,
                "incluir_en_kpi": True,
            }
            leads.append(LeadRow(data=data, identity=identity))

    _apply_origin_priority(leads)
    return leads


def _duplicate_keys(lead: LeadRow) -> list[str]:
    project = (lead.data.get("codigo_proyecto") or "").strip().lower()
    suffix = f"|project:{project}" if project else ""
    return [f"{key}{suffix}" for key in lead.identity.strong_keys()]


def _apply_origin_priority(leads: list[LeadRow]) -> None:
    origins = [lead for lead in leads if lead.data["fuente_lead"] == "ORIGEN"]
    origins.sort(key=lambda item: (item.data.get("fecha_creacion") or datetime.max, item.data["lead_uid"]))
    index: dict[str, str] = {}
    for lead in origins:
        for key in _duplicate_keys(lead):
            index.setdefault(key, lead.data["lead_uid"])

    for lead in leads:
        if lead.data["fuente_lead"] != "MEDIO_ACTUAL":
            continue
        matches = [index[key] for key in _duplicate_keys(lead) if key in index]
        if matches:
            lead.data["duplicado_en_origen"] = True
            lead.data["lead_origen_uid"] = sorted(matches)[0]
            lead.data["incluir_en_kpi"] = False


def _conversion_key(identity: PersonIdentity, row: dict[str, Any]) -> str:
    if identity.dni:
        return f"dni:{identity.dni}"
    if identity.email and identity.phone:
        return f"email_phone:{identity.email}|{identity.phone}"
    if identity.email:
        return f"email:{identity.email}"
    if identity.phone:
        return f"phone:{identity.phone}"
    if identity.source_document:
        return f"doc:{identity.source_document}"
    return f"process:{row.get('proceso_id')}|{row.get('codigo_proforma')}"


def _load_buyers(cur, start_year: int, by_doc, by_dni, by_source_id) -> list[BuyerRow]:
    start_date = datetime(start_year, 1, 1)
    rows = _fetch_dicts(
        cur,
        """
        SELECT
            p.id::text AS proceso_id,
            p.codigo_proyecto::text AS codigo_proyecto,
            p.nombre_proyecto::text AS nombre_proyecto,
            p.codigo_unidad::text AS codigo_unidad,
            p.codigo_proforma::text AS codigo_proforma,
            p.documento_cliente::text AS documento_cliente,
            to_jsonb(p) ->> 'cliente_id' AS source_cliente_id,
            p.fecha_inicio AS fecha_separacion,
            p.nombres_cliente::text AS nombres_proceso,
            p.apellidos_cliente::text AS apellidos_proceso
        FROM raw_cygnus.procesos p
        WHERE lower(btrim(p.nombre::text)) = 'separacion'
          AND lower(btrim(p.estado::text)) = 'activo'
          AND p.fecha_inicio >= %s
        """,
        (start_date,),
    )

    grouped: dict[str, list[tuple[dict[str, Any], PersonIdentity, dict[str, Any] | None]]] = defaultdict(list)
    for row in rows:
        document = row.get("documento_cliente")
        client = _find_client(
            document,
            row.get("source_cliente_id"),
            by_doc,
            by_dni,
            by_source_id,
        )
        fallback_name = " ".join(
            part for part in [row.get("nombres_proceso"), row.get("apellidos_proceso")] if part
        )
        identity = _identity_from_client(document, client, fallback_name=fallback_name)
        grouped[_conversion_key(identity, row)].append((row, identity, client))

    buyers: list[BuyerRow] = []
    for conversion_key, members in grouped.items():
        members.sort(key=lambda item: (
            item[0].get("fecha_separacion") or datetime.max,
            item[0].get("proceso_id") or "",
        ))
        row, identity, client = members[0]
        names = client.get("nombres") if client else row.get("nombres_proceso")
        surnames = client.get("apellidos") if client else row.get("apellidos_proceso")
        full_name = (
            client.get("dq_nombre_cliente")
            if client
            else " ".join(part for part in [names, surnames] if part)
        )
        data = {
            "conversion_uid": hashlib.sha1(conversion_key.encode("utf-8")).hexdigest()[:24],
            "conversion_key": conversion_key,
            "proceso_id": row.get("proceso_id"),
            "codigo_proyecto": row.get("codigo_proyecto"),
            "nombre_proyecto": row.get("nombre_proyecto"),
            "codigo_unidad": row.get("codigo_unidad"),
            "codigo_proforma": row.get("codigo_proforma"),
            "documento_cliente": row.get("documento_cliente"),
            "fecha_separacion": row.get("fecha_separacion"),
            "nombres": names,
            "apellidos": surnames,
            "nombre_completo": full_name or None,
            "dni": identity.dni or None,
            "celular": identity.phone or None,
            "email": identity.email or None,
            "medio_cliente": (
                    client.get("medio_captacion") or client.get("dq_medio_captacion")
                    if client
                    else None
                ),
            "person_key": identity.preferred_person_key() or None,
            "filas_proceso_deduplicadas": len(members),
        }
        buyers.append(BuyerRow(data=data, identity=identity))
    return buyers


class BuyerIndex:
    def __init__(self, buyers: list[BuyerRow]):
        self.buyers = buyers
        self.by_dni: dict[str, set[int]] = defaultdict(set)
        self.by_doc: dict[str, set[int]] = defaultdict(set)
        self.by_email: dict[str, set[int]] = defaultdict(set)
        self.by_email_block: dict[str, set[int]] = defaultdict(set)
        self.by_phone: dict[str, set[int]] = defaultdict(set)
        self.by_phone_suffix: dict[str, set[int]] = defaultdict(set)
        self.by_name_token: dict[str, set[int]] = defaultdict(set)
        for idx, buyer in enumerate(buyers):
            ident = buyer.identity
            if ident.dni:
                self.by_dni[ident.dni].add(idx)
            if ident.source_document:
                self.by_doc[ident.source_document].add(idx)
            if ident.email:
                self.by_email[ident.email].add(idx)
                self.by_email_block[self._email_block(ident.email)].add(idx)
            if ident.phone:
                self.by_phone[ident.phone].add(idx)
                if len(ident.phone) >= 6:
                    self.by_phone_suffix[ident.phone[-6:]].add(idx)
            for token in self._name_tokens(ident.name):
                self.by_name_token[token].add(idx)

    @staticmethod
    def _email_block(email: str) -> str:
        local, _, domain = email.partition("@")
        return f"{local[:3]}@{domain}"

    @staticmethod
    def _name_tokens(name: str) -> tuple[str, ...]:
        tokens = sorted(
            (token for token in canonical_name(name).split() if len(token) >= 4),
            key=len,
            reverse=True,
        )
        return tuple(tokens[:3])

    def candidates(self, lead: PersonIdentity) -> set[int]:
        candidates: set[int] = set()
        if lead.dni:
            candidates |= self.by_dni.get(lead.dni, set())
        if lead.source_document:
            candidates |= self.by_doc.get(lead.source_document, set())
        if lead.email:
            candidates |= self.by_email.get(lead.email, set())
            candidates |= self.by_email_block.get(self._email_block(lead.email), set())
        if lead.phone:
            candidates |= self.by_phone.get(lead.phone, set())
            if len(lead.phone) >= 6:
                candidates |= self.by_phone_suffix.get(lead.phone[-6:], set())
        for token in self._name_tokens(lead.name):
            candidates |= self.by_name_token.get(token, set())
        return candidates


def _empty_match(lead_uid: str) -> dict[str, Any]:
    return {
        "lead_uid": lead_uid,
        "conversion_uid": None,
        "conversion_key": None,
        "estado_match": "NO MATCH",
        "criterio_match": "Sin candidato suficiente",
        "score_global": 0.0,
        "score_dni": 0.0,
        "score_nombre": 0.0,
        "score_celular": 0.0,
        "score_email": 0.0,
        "fecha_separacion": None,
        "dias_a_separacion": None,
        "conversion_elegible": False,
        "conversion_atribuida": False,
        "motivo_atribucion": "Sin conversión atribuible",
    }


def _match_leads(leads: list[LeadRow], buyers: list[BuyerRow]) -> list[dict[str, Any]]:
    index = BuyerIndex(buyers)
    matches: list[dict[str, Any]] = []
    for lead in leads:
        lead_date = lead.data.get("fecha_creacion")
        lead_day = _as_date(lead_date)
        scored: list[tuple[str, MatchResult]] = []
        buyer_by_uid: dict[str, BuyerRow] = {}
        for buyer_idx in index.candidates(lead.identity):
            buyer = buyers[buyer_idx]
            sep_date = buyer.data.get("fecha_separacion")
            sep_day = _as_date(sep_date)
            if lead_day and sep_day and sep_day < lead_day:
                continue
            result = score_match(lead.identity, buyer.identity)
            if result.status != "NO MATCH":
                uid = buyer.data["conversion_uid"]
                scored.append((uid, result))
                buyer_by_uid[uid] = buyer

        best = best_result(scored)
        if best is None:
            matches.append(_empty_match(lead.data["lead_uid"]))
            continue

        conversion_uid, result = best
        buyer = buyer_by_uid[conversion_uid]
        sep_date = buyer.data.get("fecha_separacion")
        sep_day = _as_date(sep_date)
        days = (sep_day - lead_day).days if lead_day and sep_day else None
        eligible = bool(
            result.automatic_conversion
            and lead.data.get("incluir_en_kpi")
            and days is not None
            and days >= 0
        )
        matches.append({
            "lead_uid": lead.data["lead_uid"],
            "conversion_uid": conversion_uid,
            "conversion_key": buyer.data["conversion_key"],
            "estado_match": result.status,
            "criterio_match": result.criteria,
            "score_global": result.global_score,
            "score_dni": result.dni_score,
            "score_nombre": result.name_score,
            "score_celular": result.phone_score,
            "score_email": result.email_score,
            "fecha_separacion": sep_date,
            "dias_a_separacion": days,
            "conversion_elegible": eligible,
            "conversion_atribuida": False,
            "motivo_atribucion": (
                "Pendiente de deduplicación"
                if eligible
                else ("Duplicado de ORIGEN" if lead.data.get("duplicado_en_origen") else "Match no automático")
            ),
        })

    _assign_unique_conversions(leads, matches)
    return matches


def _assign_unique_conversions(leads: list[LeadRow], matches: list[dict[str, Any]]) -> None:
    lead_map = {lead.data["lead_uid"]: lead for lead in leads}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in matches:
        if match.get("conversion_elegible") and match.get("conversion_key"):
            grouped[match["conversion_key"]].append(match)

    for candidates in grouped.values():
        def winner_key(match: dict[str, Any]):
            lead = lead_map[match["lead_uid"]]
            source_priority = 1 if lead.data.get("fuente_lead") == "ORIGEN" else 0
            lead_date = lead.data.get("fecha_creacion") or datetime.max
            return (
                STATUS_RANK.get(match["estado_match"], 0),
                float(match.get("score_global") or 0),
                -lead_date.timestamp(),
                source_priority,
                match["lead_uid"],
            )

        winner = max(candidates, key=winner_key)
        winner["conversion_atribuida"] = True
        winner["motivo_atribucion"] = "Conversión única atribuida"
        for match in candidates:
            if match is winner:
                continue
            match["conversion_atribuida"] = False
            match["motivo_atribucion"] = (
                f"Conversión deduplicada por persona; atribuida a {winner['lead_uid']}"
            )


def _insert_many(cur, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    cur.executemany(sql, rows)


def _write(conn, leads: list[LeadRow], buyers: list[BuyerRow], matches: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE analytics.portal_lead_match, "
            "staging.portal_leads_base, staging.portal_compradores_base"
        )
        _insert_many(
            cur,
            """
            INSERT INTO staging.portal_leads_base (
                lead_uid, fuente_lead, source_id, codigo_proyecto, documento_cliente,
                fecha_creacion, fecha_actualizacion, canal_entrada, medio_captacion, nivel_interes,
                fecha_asignacion, vendedor_asignado, tipo_interaccion, nombre_interaccion, segmento,
                utm_source, utm_medium, cliente_source_id, nombres, apellidos, nombre_completo,
                dni, celular, email, medio_cliente, person_key, duplicado_en_origen,
                lead_origen_uid, incluir_en_kpi, refreshed_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,now()
            )
            """,
            (
                (
                    d["lead_uid"], d["fuente_lead"], d.get("source_id"), d.get("codigo_proyecto"), d.get("documento_cliente"),
                    d.get("fecha_creacion"), d.get("fecha_actualizacion"), d.get("canal_entrada"), d.get("medio_captacion"), d.get("nivel_interes"),
                    d.get("fecha_asignacion"), d.get("vendedor_asignado"), d.get("tipo_interaccion"), d.get("nombre_interaccion"), d.get("segmento"),
                    d.get("utm_source"), d.get("utm_medium"), d.get("cliente_source_id"), d.get("nombres"), d.get("apellidos"), d.get("nombre_completo"),
                    d.get("dni"), d.get("celular"), d.get("email"), d.get("medio_cliente"), d.get("person_key"), d.get("duplicado_en_origen"),
                    d.get("lead_origen_uid"), d.get("incluir_en_kpi"),
                )
                for d in (lead.data for lead in leads)
            ),
        )
        _insert_many(
            cur,
            """
            INSERT INTO staging.portal_compradores_base (
                conversion_uid, conversion_key, proceso_id, codigo_proyecto, nombre_proyecto,
                codigo_unidad, codigo_proforma, documento_cliente, fecha_separacion,
                nombres, apellidos, nombre_completo, dni, celular, email, medio_cliente,
                person_key, filas_proceso_deduplicadas, refreshed_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
            )
            """,
            (
                (
                    d["conversion_uid"], d["conversion_key"], d.get("proceso_id"), d.get("codigo_proyecto"), d.get("nombre_proyecto"),
                    d.get("codigo_unidad"), d.get("codigo_proforma"), d.get("documento_cliente"), d.get("fecha_separacion"),
                    d.get("nombres"), d.get("apellidos"), d.get("nombre_completo"), d.get("dni"), d.get("celular"), d.get("email"), d.get("medio_cliente"),
                    d.get("person_key"), d.get("filas_proceso_deduplicadas"),
                )
                for d in (buyer.data for buyer in buyers)
            ),
        )
        _insert_many(
            cur,
            """
            INSERT INTO analytics.portal_lead_match (
                lead_uid, conversion_uid, conversion_key, estado_match, criterio_match,
                score_global, score_dni, score_nombre, score_celular, score_email,
                fecha_separacion, dias_a_separacion, conversion_elegible, conversion_atribuida,
                motivo_atribucion, refreshed_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            """,
            (
                (
                    m["lead_uid"], m.get("conversion_uid"), m.get("conversion_key"), m["estado_match"], m.get("criterio_match"),
                    m.get("score_global"), m.get("score_dni"), m.get("score_nombre"), m.get("score_celular"), m.get("score_email"),
                    m.get("fecha_separacion"), m.get("dias_a_separacion"), m.get("conversion_elegible"), m.get("conversion_atribuida"),
                    m.get("motivo_atribucion"),
                )
                for m in matches
            ),
        )
        cur.execute("SELECT conversiones_duplicadas_error FROM analytics.v_portal_conversion_health")
        duplicate_errors = int(cur.fetchone()[0])
        if duplicate_errors:
            raise RuntimeError(
                f"Health gate: {duplicate_errors} conversion(es) quedaron atribuidas más de una vez"
            )
    conn.commit()


def _summary(leads: list[LeadRow], buyers: list[BuyerRow], matches: list[dict[str, Any]]) -> str:
    status = Counter(match["estado_match"] for match in matches)
    return (
        f"leads={len(leads)} "
        f"(origen={sum(l.data['fuente_lead']=='ORIGEN' for l in leads)}, "
        f"medio_actual={sum(l.data['fuente_lead']=='MEDIO_ACTUAL' for l in leads)}, "
        f"duplicados_origen={sum(bool(l.data['duplicado_en_origen']) for l in leads)}); "
        f"compradores_dedup={len(buyers)}; "
        f"conversiones_atribuidas={sum(bool(m['conversion_atribuida']) for m in matches)}; "
        f"matches={dict(status)}"
    )


def main() -> int:
    args = parse_args()
    settings = load_settings()
    with connect_postgres(settings) as conn:
        with conn.cursor() as cur:
            for relation in (
                "raw_cygnus.clientes_proyectos",
                "raw_cygnus.interacciones",
                "raw_cygnus.procesos",
                "staging.clientes_calidad",
                "staging.portal_leads_base",
                "staging.portal_compradores_base",
                "analytics.portal_lead_match",
            ):
                cur.execute("SELECT to_regclass(%s)", (relation,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError(
                        f"Falta {relation}; ejecutar RAW/schema/clientes_calidad antes del mart de portales"
                    )
            by_doc, by_dni, by_source_id = _client_catalog(cur)
            leads = _load_leads(cur, args.start_year, by_doc, by_dni, by_source_id)
            buyers = _load_buyers(cur, args.start_year, by_doc, by_dni, by_source_id)

        matches = _match_leads(leads, buyers)
        print("[PORTAL_CONVERSION] " + _summary(leads, buyers, matches))
        if args.dry_run:
            conn.rollback()
            print("[PORTAL_CONVERSION] dry-run: no se escribieron tablas.")
            return 0
        _write(conn, leads, buyers, matches)
        print("[PORTAL_CONVERSION] refresh OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
