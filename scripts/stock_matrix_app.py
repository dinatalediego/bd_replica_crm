from __future__ import annotations

import html
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from replica_cygnus.stock_export import export_stock_excel
from replica_cygnus.stock_export.matrix_service import (
    fetch_apartment_units,
    fetch_stock_status_data,
)


STATE_COLORS = {
    "Disponible": "#F4C542",
    "No disponible": "#D9D9D9",
    "Separado": "#F26B38",
    "Vendido": "#2ECC71",
    "Entregado": "#8E63D9",
    "Sin clasificar": "#ECEFF1",
}
STATE_ICONS = {
    "Disponible": "🟨",
    "No disponible": "⬜",
    "Separado": "🟧",
    "Vendido": "🟩",
    "Entregado": "🟪",
    "Sin clasificar": "▫️",
}
STATE_ORDER = ["Disponible", "No disponible", "Separado", "Vendido", "Entregado", "Sin clasificar"]
STOCK_BUTTON_STATES = ["Disponible", "No disponible", "Separado", "Vendido", "Entregado"]
DEFAULT_STOCK_STATES = ["Disponible", "No disponible"]


def _norm(value: object) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return " ".join(text.split())


def state_group(value: object) -> str:
    state = _norm(value)
    if not state:
        return "Sin clasificar"
    if "no disponible" in state or "bloque" in state:
        return "No disponible"
    if "entrega" in state or "entregado" in state:
        return "Entregado"
    if "separ" in state:
        return "Separado"
    if "venta" in state or "vendido" in state or "aprobacion" in state:
        return "Vendido"
    if "disponible" in state:
        return "Disponible"
    return "Sin clasificar"


def default_exchange_rate(project: str) -> float:
    p = _norm(project)
    if "torre marsano" in p or p == "marsano":
        return 3.4
    if "matera" in p or "napoles" in p:
        return 3.7
    return 3.8


def natural_key(value: object):
    text = str(value or "")
    parts = re.split(r"(\d+(?:\.\d+)?)", text)
    key: list[object] = []
    for part in parts:
        try:
            key.append(float(part))
        except ValueError:
            key.append(part.lower())
    return key


def floor_key(value: object):
    text = str(value or "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if match:
        return (0, -float(match.group()))
    return (1, text.lower())


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def prepare_units(df: pd.DataFrame, exchange_rate: float) -> pd.DataFrame:
    out = _to_numeric(
        df,
        [
            "area_total",
            "precio_lista",
            "precio_venta",
            "precio_m2_origen",
            "discount_pct",
            "precio_con_descuento",
        ],
    )
    out["estado_matriz"] = out["estado_comercial"].map(state_group)

    currency = out["moneda"].fillna("PEN").astype(str).str.upper().str.strip()
    is_usd = currency.isin({"USD", "US$", "$", "DOLAR", "DÓLAR", "DOLARES", "DÓLARES"})

    out["precio_lista_soles"] = np.where(is_usd, out["precio_lista"] * exchange_rate, out["precio_lista"])
    out["precio_lista_usd"] = np.where(is_usd, out["precio_lista"], out["precio_lista"] / exchange_rate)
    out["precio_desc_soles"] = np.where(
        is_usd,
        out["precio_con_descuento"] * exchange_rate,
        out["precio_con_descuento"],
    )
    out["precio_desc_usd"] = np.where(
        is_usd,
        out["precio_con_descuento"],
        out["precio_con_descuento"] / exchange_rate,
    )

    area = out["area_total"].where(out["area_total"] > 0)
    out["precio_m2_soles"] = out["precio_lista_soles"] / area
    out["precio_m2_usd"] = out["precio_lista_usd"] / area

    raw_m2_soles = np.where(is_usd, out["precio_m2_origen"] * exchange_rate, out["precio_m2_origen"])
    raw_m2_usd = np.where(is_usd, out["precio_m2_origen"], out["precio_m2_origen"] / exchange_rate)
    out["precio_m2_soles"] = out["precio_m2_soles"].fillna(pd.Series(raw_m2_soles, index=out.index))
    out["precio_m2_usd"] = out["precio_m2_usd"].fillna(pd.Series(raw_m2_usd, index=out.index))
    return out


def metric_formatter(metric: str, value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return ""
    if metric in {"precio_m2_usd", "precio_lista_usd", "precio_desc_usd"}:
        return f"US$ {value:,.0f}"
    return f"S/ {value:,.0f}"


def matrix_html(
    df: pd.DataFrame,
    *,
    metric: str,
    row_dim: str,
    col_dim: str,
    title: str,
    subtitle: str,
) -> str:
    work = df.dropna(subset=[row_dim, col_dim]).copy()
    work[row_dim] = work[row_dim].astype(str).str.strip()
    work[col_dim] = work[col_dim].astype(str).str.strip()
    work = work[(work[row_dim] != "") & (work[col_dim] != "")]

    if work.empty:
        return "<div class='empty-matrix'>No hay datos para construir la matriz con estos filtros.</div>"

    rows = sorted(work[row_dim].unique(), key=floor_key if row_dim == "piso" else natural_key)
    cols = sorted(work[col_dim].unique(), key=floor_key if col_dim == "piso" else natural_key)
    grouped = {
        (str(r), str(c)): g
        for (r, c), g in work.groupby([row_dim, col_dim], dropna=False)
    }

    header_name = "PISO" if row_dim == "piso" else "TIPO"
    pieces = [
        "<div class='matrix-card'>",
        f"<div class='matrix-title'>{html.escape(title)}</div>",
        f"<div class='matrix-subtitle'>{html.escape(subtitle)}</div>",
        "<div class='matrix-scroll'><table class='matrix-table'>",
        "<thead><tr>",
        f"<th class='matrix-axis'>{html.escape(header_name)}</th>",
    ]
    for col in cols:
        pieces.append(f"<th>{html.escape(str(col))}</th>")
    pieces.append("<th>Prom.</th></tr></thead><tbody>")

    for row in rows:
        row_df = work[work[row_dim] == row]
        row_avg = pd.to_numeric(row_df[metric], errors="coerce").mean()
        pieces.append(f"<tr><th class='matrix-row'>{html.escape(str(row))}</th>")
        for col in cols:
            cell = grouped.get((str(row), str(col)))
            if cell is None or cell.empty:
                pieces.append("<td class='matrix-empty'></td>")
                continue
            value = pd.to_numeric(cell[metric], errors="coerce").mean()
            states = cell["estado_matriz"].value_counts()
            state = states.index[0] if not states.empty else "Sin clasificar"
            color = STATE_COLORS.get(state, STATE_COLORS["Sin clasificar"])
            units = ", ".join(cell["unidad"].astype(str).head(4).tolist())
            if len(cell) > 4:
                units += f" +{len(cell) - 4}"
            tooltip = f"{state} · Unidad: {units}"
            pieces.append(
                f"<td style='background:{color}' title='{html.escape(tooltip)}'>"
                f"{html.escape(metric_formatter(metric, value))}</td>"
            )
        pieces.append(f"<td class='matrix-total-value'>{html.escape(metric_formatter(metric, row_avg))}</td></tr>")

    pieces.append("<tr><th class='matrix-bottom'>Prom.</th>")
    for col in cols:
        col_avg = pd.to_numeric(work.loc[work[col_dim] == col, metric], errors="coerce").mean()
        pieces.append(f"<td class='matrix-bottom-value'>{html.escape(metric_formatter(metric, col_avg))}</td>")
    grand_avg = pd.to_numeric(work[metric], errors="coerce").mean()
    pieces.append(f"<td class='matrix-grand'>{html.escape(metric_formatter(metric, grand_avg))}</td></tr>")
    pieces.append("</tbody></table></div></div>")
    return "".join(pieces)


def legend_html(states: list[str]) -> str:
    chips = []
    for state in states:
        chips.append(
            f"<span class='legend-item'><span class='legend-dot' style='background:{STATE_COLORS[state]}'></span>"
            f"{html.escape(state)}</span>"
        )
    return "<div class='legend'>" + "".join(chips) + "</div>"


def render_cards(cards: list[tuple[object, str, str]]) -> None:
    for col, label, value in cards:
        with col:
            st.markdown(
                f"<div class='metric-card'><div class='metric-label'>{html.escape(label)}</div>"
                f"<div class='metric-value'>{html.escape(value)}</div></div>",
                unsafe_allow_html=True,
            )


@st.cache_data(ttl=60, show_spinner=False)
def cached_stock_status() -> pd.DataFrame:
    return fetch_stock_status_data()


@st.cache_data(ttl=60, show_spinner=False)
def cached_units() -> pd.DataFrame:
    return fetch_apartment_units()


st.set_page_config(page_title="Medallio · Matrices Stock & Unidades", page_icon="▦", layout="wide")
st.markdown(
    """
    <style>
    :root { --navy:#062C43; --soft:#F5F7F8; --border:#D9E0E4; }
    .block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1500px; }
    .hero { background:linear-gradient(115deg,#062C43,#174D5A); padding:22px 26px; border-radius:18px; color:white; margin-bottom:18px; }
    .hero h1 { margin:0; font-size:28px; letter-spacing:-0.4px; }
    .hero p { margin:6px 0 0; opacity:.85; font-size:14px; }
    .metric-card { background:white; border:1px solid var(--border); border-radius:14px; padding:14px 16px; min-height:88px; }
    .metric-label { color:#65727A; font-size:12px; text-transform:uppercase; letter-spacing:.6px; font-weight:700; }
    .metric-value { color:#062C43; font-size:25px; font-weight:800; margin-top:4px; }
    .matrix-card { background:white; border:1px solid #CDD6DB; border-radius:14px; padding:18px; margin-top:10px; box-shadow:0 2px 12px rgba(6,44,67,.05); }
    .matrix-title { font-size:20px; color:#062C43; font-weight:800; }
    .matrix-subtitle { color:#61717A; font-size:13px; margin:3px 0 14px; }
    .matrix-scroll { overflow-x:auto; }
    .matrix-table { border-collapse:separate; border-spacing:0; width:100%; min-width:720px; font-size:14px; }
    .matrix-table th { background:#062C43; color:white; padding:9px 11px; border-right:1px solid white; text-align:center; white-space:nowrap; }
    .matrix-table td { padding:8px 10px; text-align:center; border-right:1px solid white; border-bottom:1px solid white; white-space:nowrap; font-weight:650; color:#17242A; }
    .matrix-table .matrix-row { background:#F0F2F3; color:#17242A; text-align:left; font-weight:800; position:sticky; left:0; z-index:2; }
    .matrix-table .matrix-axis { text-align:left; position:sticky; left:0; z-index:3; }
    .matrix-table .matrix-empty { background:#FAFBFB; }
    .matrix-table .matrix-total-value, .matrix-table .matrix-bottom-value, .matrix-table .matrix-grand { background:white; color:#243239; font-weight:900; }
    .matrix-table .matrix-bottom { background:white; color:#243239; text-align:left; font-weight:900; }
    .legend { display:flex; flex-wrap:wrap; gap:18px; align-items:center; padding:13px 4px 4px; font-weight:750; color:#062C43; }
    .legend-item { display:inline-flex; align-items:center; gap:7px; }
    .legend-dot { width:18px; height:18px; border-radius:5px; border:1px solid rgba(0,0,0,.08); display:inline-block; }
    .empty-matrix { padding:30px; border:1px dashed #B9C5CA; border-radius:12px; color:#66757D; text-align:center; }
    div[data-testid='stTabs'] button { font-weight:750; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class='hero'>
      <h1>Medallio · Matrices de Stock & Unidades</h1>
      <p>Stock operativo (disponible + bloqueado), inventario por estado comercial y matrices de departamentos.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

refresh_col, status_col = st.columns([1, 5])
with refresh_col:
    if st.button("↻ Actualizar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with status_col:
    st.caption("Fuente: PostgreSQL local · medallio_dw · caché de 60 segundos")

try:
    stock_df = cached_stock_status()
    units_df = cached_units()
except Exception as exc:
    st.error("No se pudo leer Medallio DW. Ejecuta scripts\\50_exportar_stock_disponible.bat y vuelve a abrir la interfaz.")
    st.exception(exc)
    st.stop()

stock_tab, units_tab = st.tabs(["Stock", "Unidades · departamentos"])

with stock_tab:
    st.subheader("Stock · disponible + no disponible / bloqueado")
    st.caption(
        "Por defecto se muestran Disponible + No disponible/Bloqueado. Puedes sumar o quitar estados con los botones. El Excel continúa exportando sólo Disponibles."
    )

    stock_projects = sorted(stock_df["proyecto"].dropna().astype(str).unique(), key=natural_key)
    selected_projects = st.multiselect(
        "Proyectos",
        stock_projects,
        default=stock_projects,
        key="stock_projects",
    )
    project_view = (
        stock_df[stock_df["proyecto"].isin(selected_projects)].copy()
        if selected_projects
        else stock_df.iloc[0:0].copy()
    )

    if "stock_selected_states" not in st.session_state:
        st.session_state["stock_selected_states"] = DEFAULT_STOCK_STATES.copy()

    counts = project_view["estado_grupo"].value_counts()
    selected_states = list(st.session_state["stock_selected_states"])

    quick1, quick2, quick3 = st.columns([1.2, 1.2, 4])
    with quick1:
        if st.button("Stock operativo", use_container_width=True, help="Disponible + No disponible/Bloqueado"):
            st.session_state["stock_selected_states"] = DEFAULT_STOCK_STATES.copy()
            st.rerun()
    with quick2:
        if st.button("Todos los estados", use_container_width=True):
            st.session_state["stock_selected_states"] = [
                s for s in STOCK_BUTTON_STATES if int(counts.get(s, 0)) > 0
            ]
            st.rerun()

    button_cols = st.columns(len(STOCK_BUTTON_STATES))
    for col, state in zip(button_cols, STOCK_BUTTON_STATES):
        count = int(counts.get(state, 0))
        active = state in selected_states
        with col:
            if st.button(
                f"{STATE_ICONS[state]} {state} · {count}",
                key=f"stock_toggle_{state}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                current = list(st.session_state["stock_selected_states"])
                if state in current:
                    current.remove(state)
                else:
                    current.append(state)
                st.session_state["stock_selected_states"] = current
                st.rerun()

    selected_states = list(st.session_state["stock_selected_states"])
    stock_view = (
        project_view[project_view["estado_grupo"].isin(selected_states)].copy()
        if selected_states
        else project_view.iloc[0:0].copy()
    )
    stock_view = _to_numeric(stock_view, ["precio_lista", "precio_con_descuento", "discount_pct"])

    c1, c2, c3, c4, c5 = st.columns(5)
    render_cards([
        (c1, "Unidades visibles", f"{len(stock_view):,}"),
        (c2, "Disponibles", f"{(stock_view['estado_grupo'] == 'Disponible').sum():,}"),
        (c3, "No disp./bloq.", f"{(stock_view['estado_grupo'] == 'No disponible').sum():,}"),
        (c4, "Valor lista", f"S/ {stock_view['precio_lista'].sum(skipna=True):,.0f}"),
        (c5, "Valor c/ descuento", f"S/ {stock_view['precio_con_descuento'].sum(skipna=True):,.0f}"),
    ])

    st.dataframe(
        stock_view[[
            "proyecto", "estado_grupo", "estado_comercial", "tipo_unidad", "unidad",
            "nombre_tipologia", "piso", "area_total", "precio_lista", "discount_pct",
            "precio_con_descuento", "fecha_actualizacion_dato"
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "proyecto": "Proyecto",
            "estado_grupo": "Estado",
            "estado_comercial": "Estado origen",
            "tipo_unidad": "Tipo",
            "unidad": "Unidad",
            "nombre_tipologia": "Tipología",
            "piso": "Piso",
            "area_total": st.column_config.NumberColumn("Área m²", format="%.2f"),
            "precio_lista": st.column_config.NumberColumn("Precio lista", format="S/ %.0f"),
            "discount_pct": st.column_config.NumberColumn("Dscto.", format="percent"),
            "precio_con_descuento": st.column_config.NumberColumn("Precio con descuento", format="S/ %.0f"),
            "fecha_actualizacion_dato": "Actualización dato",
        },
    )

    st.caption("La tabla puede combinar estados. El botón de Excel mantiene el contrato original de unidades Disponibles.")
    if st.button("Generar Excel de DISPONIBLES para estos proyectos", type="primary"):
        with st.spinner("Generando Excel de stock disponible..."):
            output = export_stock_excel(projects=selected_projects or None)
            st.session_state["excel_path"] = str(output)

    excel_path = st.session_state.get("excel_path")
    if excel_path and Path(excel_path).exists():
        path = Path(excel_path)
        st.download_button(
            "Descargar Excel de disponibles",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with units_tab:
    st.subheader("Unidades · matriz de departamentos")
    st.caption("Solo flag_departamento = true. Esta rama es visual y no se exporta a Excel por ahora.")

    projects = sorted(units_df["proyecto"].dropna().astype(str).unique(), key=natural_key)
    if not projects:
        st.warning("No se encontraron departamentos en core.v_unidades_fuentes.")
        st.stop()

    top1, top2, top3 = st.columns([2.1, 1, 1.5])
    with top1:
        project = st.selectbox("Proyecto", projects)
    with top2:
        tc = st.number_input(
            "Tipo de cambio",
            min_value=1.0,
            max_value=10.0,
            value=float(default_exchange_rate(project)),
            step=0.05,
            format="%.2f",
        )
    with top3:
        total_currency = st.radio("Precios totales", ["Soles (S/)", "Dólares (US$)"], horizontal=True)

    project_df = prepare_units(units_df[units_df["proyecto"] == project].copy(), tc)
    state_counts = project_df["estado_matriz"].value_counts()
    available_states = [s for s in STATE_ORDER if s in state_counts.index]
    selected_unit_states = st.multiselect(
        "Estados comerciales visibles",
        available_states,
        default=available_states,
    )
    view = (
        project_df[project_df["estado_matriz"].isin(selected_unit_states)].copy()
        if selected_unit_states
        else project_df.iloc[0:0].copy()
    )

    if total_currency.startswith("Soles"):
        total_list_metric = "precio_lista_soles"
        total_discount_metric = "precio_desc_soles"
        list_label = "Precio de lista · S/"
        discount_label = "Precio con descuento · S/"
    else:
        total_list_metric = "precio_lista_usd"
        total_discount_metric = "precio_desc_usd"
        list_label = "Precio de lista · US$"
        discount_label = "Precio con descuento · US$"

    metric_options = {
        "Precio por m² · US$": "precio_m2_usd",
        "Precio por m² · S/": "precio_m2_soles",
        list_label: total_list_metric,
        discount_label: total_discount_metric,
    }

    f1, f2, f3 = st.columns([2, 1.4, 1.4])
    with f1:
        metric_label = st.selectbox("Métrica de la matriz", list(metric_options.keys()))
        metric = metric_options[metric_label]
    with f2:
        orientation = st.radio("Orientación", ["Piso en filas", "Piso en columnas"])
    with f3:
        show_raw = st.checkbox("Mostrar detalle debajo", value=False)

    row_dim, col_dim = (
        ("piso", "tipologia_ubicacion")
        if orientation == "Piso en filas"
        else ("tipologia_ubicacion", "piso")
    )

    k1, k2, k3, k4 = st.columns(4)
    render_cards([
        (k1, "Departamentos", f"{len(view):,}"),
        (k2, "Disponible", f"{(view['estado_matriz'] == 'Disponible').sum():,}"),
        (k3, "Precio m² prom.", metric_formatter("precio_m2_usd", view["precio_m2_usd"].mean())),
        (k4, "Descuento", f"{view['discount_pct'].max(skipna=True) * 100:.0f}%" if not view.empty else "—"),
    ])

    subtitle = f"{metric_label} · TC: {tc:.2f} · color = estado comercial · flag_departamento = true"
    st.markdown(
        matrix_html(
            view,
            metric=metric,
            row_dim=row_dim,
            col_dim=col_dim,
            title=f"{project} · {metric_label}",
            subtitle=subtitle,
        ),
        unsafe_allow_html=True,
    )

    legend_states = [
        s for s in ["Disponible", "No disponible", "Separado", "Vendido", "Entregado"]
        if s in available_states
    ]
    st.markdown(legend_html(legend_states), unsafe_allow_html=True)
    st.caption("Disponible = amarillo · No disponible/Bloqueado = gris · Separado = naranja · Vendido = verde · Entregado = morado.")

    duplicates = (
        view.groupby(["piso", "tipologia_ubicacion"], dropna=False)
        .size()
        .reset_index(name="n")
        .query("n > 1")
    )
    if not duplicates.empty:
        st.info(
            f"Hay {len(duplicates)} celdas piso × tipología con más de una unidad. "
            "La matriz muestra el promedio de la métrica y el estado más frecuente."
        )

    if show_raw:
        detail_cols = [
            "unidad", "piso", "tipologia_ubicacion", "nombre_tipologia", "estado_comercial", "estado_matriz",
            "area_total", "precio_m2_usd", "precio_m2_soles", "precio_lista_soles", "precio_desc_soles",
            "discount_pct", "esquema_fuente", "fecha_actualizacion_dato",
        ]
        st.dataframe(view[detail_cols], use_container_width=True, hide_index=True)
