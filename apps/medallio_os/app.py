from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT_HINT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT_HINT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from replica_cygnus.medallio_os.analytics import (  # noqa: E402
    build_project_benchmark,
    data_quality_summary,
)
from replica_cygnus.medallio_os.runtime import (  # noqa: E402
    CommandResult,
    discover_kernels,
    discover_notebooks,
    execute_notebook,
    find_repo_root,
    group_notebooks,
    list_recent_runs,
    preflight,
    run_ambassador,
)


st.set_page_config(
    page_title="Medallio OS",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 14px;
        padding: 14px;
      }
      .medallio-kicker {
        letter-spacing: .16em;
        font-size: .75rem;
        opacity: .65;
        font-weight: 700;
      }
      .medallio-card {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 16px;
        padding: 18px 20px;
        margin: 8px 0 14px 0;
      }
      .ok-dot {color: #1f9d55; font-weight: 800;}
      .bad-dot {color: #d64545; font-weight: 800;}
      code {font-size: .86em;}
    </style>
    """,
    unsafe_allow_html=True,
)


def repo_root() -> Path:
    return find_repo_root(Path(__file__))


ROOT = repo_root()


@st.cache_data(ttl=20, show_spinner=False)
def get_kernels(root: str) -> dict[str, str]:
    return discover_kernels(Path(root))


@st.cache_data(ttl=20, show_spinner=False)
def get_notebooks(root: str) -> list[str]:
    return [str(path) for path in discover_notebooks(Path(root))]


@st.cache_data(ttl=20, show_spinner=False)
def get_preflight(root: str) -> list[dict[str, str | bool]]:
    return preflight(Path(root))


def title(name: str, subtitle: str) -> None:
    st.markdown('<div class="medallio-kicker">MEDALLIO LOCAL ANALYTICS</div>', unsafe_allow_html=True)
    st.title(name)
    st.caption(subtitle)


def show_result(result: CommandResult) -> None:
    if result.ok:
        st.success(f"Finalizó correctamente · código {result.returncode}")
    else:
        st.error(f"Finalizó con código {result.returncode}")

    command = " ".join(result.command) if result.command else "(no ejecutado)"
    st.code(command, language="powershell")
    c1, c2 = st.columns(2)
    c1.caption(f"Inicio: {result.started_at}")
    c2.caption(f"Fin: {result.finished_at}")
    if result.output_path:
        st.caption(f"Salida: {result.output_path}")

    if result.stdout.strip():
        with st.expander("stdout", expanded=result.ok):
            st.code(result.stdout[-16000:], language="text")
    if result.stderr.strip():
        with st.expander("stderr / warnings", expanded=not result.ok):
            st.code(result.stderr[-16000:], language="text")


def notebook_runner(
    *,
    key_prefix: str,
    notebook_paths: list[str] | None = None,
    default_kernel: str = "medallio_dw",
) -> None:
    notebooks = notebook_paths if notebook_paths is not None else get_notebooks(str(ROOT))
    kernels = get_kernels(str(ROOT))

    if not notebooks:
        st.warning("No hay notebooks detectados en esta copia del repositorio.")
        return
    if not kernels:
        st.warning("No hay kernels Jupyter detectados desde el Python activo.")
        return

    c1, c2 = st.columns([3, 2])
    selected_nb = c1.selectbox(
        "Notebook",
        notebooks,
        key=f"{key_prefix}_notebook",
    )
    kernel_names = list(kernels)
    default_index = kernel_names.index(default_kernel) if default_kernel in kernel_names else 0
    selected_kernel = c2.selectbox(
        "Kernel",
        kernel_names,
        index=default_index,
        key=f"{key_prefix}_kernel",
    )

    timeout = st.number_input(
        "Timeout por celda (segundos)",
        min_value=60,
        max_value=7200,
        value=1800,
        step=60,
        key=f"{key_prefix}_timeout",
    )
    st.caption(
        "La ejecución crea una copia en `.medallio/runs/`; el notebook fuente no se sobrescribe."
    )
    if st.button("▶ Ejecutar notebook", type="primary", key=f"{key_prefix}_run"):
        with st.spinner("Ejecutando notebook con el kernel seleccionado..."):
            try:
                result = execute_notebook(
                    ROOT,
                    Path(selected_nb),
                    selected_kernel,
                    timeout=int(timeout),
                )
            except Exception as exc:
                st.exception(exc)
            else:
                st.session_state[f"{key_prefix}_result"] = result

    result = st.session_state.get(f"{key_prefix}_result")
    if result:
        show_result(result)


def load_uploaded_table(uploaded) -> pd.DataFrame:
    suffix = Path(uploaded.name).suffix.lower()
    raw = uploaded.getvalue()
    if suffix == ".csv":
        try:
            return pd.read_csv(BytesIO(raw))
        except UnicodeDecodeError:
            return pd.read_csv(BytesIO(raw), encoding="latin-1")
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(BytesIO(raw))
    raise ValueError("Formato no soportado. Usa CSV o XLSX.")


def home() -> None:
    title(
        "Medallio OS",
        "Una capa de producto local sobre tus notebooks, kernels y datasets de bd_replica_crm.",
    )
    kernels = get_kernels(str(ROOT))
    notebooks = get_notebooks(str(ROOT))
    checks = get_preflight(str(ROOT))
    healthy = sum(bool(item["ok"]) for item in checks)

    a, b, c, d = st.columns(4)
    a.metric("Kernels", len(kernels))
    b.metric("Notebooks", len(notebooks))
    c.metric("Preflight", f"{healthy}/{len(checks)}")
    d.metric("Runtime", Path(sys.executable).parent.name)

    st.markdown("### Centro de aplicaciones")
    cards = [
        ("🗼 Control Tower", "Salud del runtime, kernels, notebooks y ejecuciones."),
        ("📑 Executive Briefing", "Dispara Medallio Ambassador y revisa su salida."),
        ("🔮 Forecast Studio", "Entra a los notebooks de forecasting/ML con el kernel correcto."),
        ("🧪 Econometrics Lab", "Ejecuta causalidad, econometría y modelos paramétricos."),
        ("📈 Benchmark Lab", "Compara proyectos por Mes 0, Mes 1, Mes 2…"),
        ("🧹 Data Quality", "Perfila archivos sin tocar el DW ni exponer datos fuera de la PC."),
        ("📚 Notebook Launcher", "Catálogo completo de notebooks ejecutables."),
    ]
    cols = st.columns(2)
    for idx, (name, description) in enumerate(cards):
        with cols[idx % 2]:
            st.markdown(
                f'<div class="medallio-card"><b>{name}</b><br><span style="opacity:.72">{description}</span></div>',
                unsafe_allow_html=True,
            )

    st.info(
        "Medallio OS descubre el estado real de tu copia local. Si un notebook o "
        "`run_ambassador.py` existe solo en tu working tree y aún no está en GitHub, "
        "aparecerá automáticamente cuando ejecutes esta app desde esa carpeta."
    )


def control_tower() -> None:
    title("Control Tower", "Preflight del runtime analítico local de Medallio.")
    checks = get_preflight(str(ROOT))
    for item in checks:
        icon = "●"
        cls = "ok-dot" if item["ok"] else "bad-dot"
        st.markdown(
            f'<div class="medallio-card"><span class="{cls}">{icon}</span> '
            f'<b>{item["check"]}</b><br><code>{item["detail"]}</code></div>',
            unsafe_allow_html=True,
        )

    st.markdown("### Kernels detectados")
    kernels = get_kernels(str(ROOT))
    if kernels:
        st.dataframe(
            pd.DataFrame(
                [{"kernel": name, "ubicación": location} for name, location in kernels.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("Jupyter no devolvió kernels para el Python activo.")

    st.markdown("### Ejecuciones recientes")
    runs = list_recent_runs(ROOT, limit=12)
    if runs:
        st.dataframe(
            pd.DataFrame(
                {
                    "run": [p.name for p in runs],
                    "archivos": [len(list(p.glob("*"))) for p in runs],
                    "ubicación": [str(p.relative_to(ROOT)) for p in runs],
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Todavía no hay ejecuciones creadas por Medallio OS.")

    if st.button("↻ Refrescar diagnóstico"):
        get_kernels.clear()
        get_notebooks.clear()
        get_preflight.clear()
        st.rerun()


def executive_briefing() -> None:
    title(
        "Executive Briefing",
        "Control local de Medallio Ambassador: prueba el slot y luego ejecútalo.",
    )
    script = ROOT / "scripts" / "medallio_ambassador" / "run_ambassador.py"
    if script.exists():
        st.success(f"Ambassador detectado: {script.relative_to(ROOT)}")
    else:
        st.warning(
            "`scripts/medallio_ambassador/run_ambassador.py` no está en esta rama de GitHub. "
            "La captura que compartiste demuestra que sí está en tu working tree local; "
            "Medallio OS lo detectará allí sin que tengas que copiarlo."
        )

    slot = st.selectbox("Slot", ["morning", "afternoon", "evening"], index=0)

    left, right = st.columns(2)
    if left.button("🧪 Ejecutar dry-run", type="primary", use_container_width=True):
        with st.spinner(f"Ejecutando Ambassador · {slot} · dry-run..."):
            st.session_state["ambassador_result"] = run_ambassador(
                ROOT, slot=slot, dry_run=True
            )

    confirm = right.checkbox(
        "Habilitar ejecución real",
        help="Quita --dry-run. Puede generar artefactos/salidas según tu runner.",
    )
    if right.button(
        "▶ Ejecutar real",
        disabled=not confirm,
        use_container_width=True,
    ):
        with st.spinner(f"Ejecutando Ambassador · {slot}..."):
            st.session_state["ambassador_result"] = run_ambassador(
                ROOT, slot=slot, dry_run=False
            )

    if "ambassador_result" in st.session_state:
        show_result(st.session_state["ambassador_result"])


def catalog_candidates(categories: set[str]) -> list[str]:
    paths = [Path(p) for p in get_notebooks(str(ROOT))]
    groups = group_notebooks(paths)
    candidates: list[str] = []
    for category in categories:
        candidates.extend(str(path) for path in groups.get(category, []))
    return sorted(set(candidates), key=str.lower)


def forecast_studio() -> None:
    title(
        "Forecast Studio",
        "Ejecuta la capa de forecasting/ML que ya existe en el repositorio, sin inventar un modelo paralelo.",
    )
    candidates = catalog_candidates({"Forecasting", "Machine Learning"})
    if candidates:
        st.caption(f"{len(candidates)} notebooks candidatos detectados automáticamente.")
        notebook_runner(key_prefix="forecast", notebook_paths=candidates)
    else:
        st.warning(
            "No detecté notebooks cuyo nombre clasifique como forecasting/ML en esta copia."
        )


def econometrics_lab() -> None:
    title(
        "Econometrics Lab",
        "Causalidad, modelos econométricos y experimentación usando tus kernels locales.",
    )
    candidates = catalog_candidates({"Econometría"})
    if not candidates:
        candidates = [
            path
            for path in get_notebooks(str(ROOT))
            if any(token in Path(path).stem.lower() for token in ("causal", "econometric"))
        ]
    notebook_runner(
        key_prefix="econometrics",
        notebook_paths=candidates or None,
        default_kernel="cygnus-estadistica",
    )


def benchmark_lab() -> None:
    title(
        "Project Benchmark Lab",
        "Normaliza cada proyecto a Mes 0 para comparar evolución comercial entre proyectos.",
    )
    uploaded = st.file_uploader(
        "Sube un CSV o XLSX",
        type=["csv", "xlsx", "xlsm"],
        key="benchmark_upload",
    )
    if uploaded is None:
        st.caption(
            "No se envía ningún archivo fuera de tu proceso local de Streamlit. "
            "Aquí puedes usar exportaciones anonimizadas o datasets de Medallio."
        )
        return

    try:
        df = load_uploaded_table(uploaded)
    except Exception as exc:
        st.exception(exc)
        return

    st.write(f"{len(df):,} filas · {len(df.columns):,} columnas")
    st.dataframe(df.head(25), use_container_width=True)

    columns = list(df.columns)
    c1, c2, c3 = st.columns(3)
    project_col = c1.selectbox("Proyecto", columns)
    date_col = c2.selectbox("Fecha / mes", columns, index=min(1, len(columns) - 1))
    value_col = c3.selectbox("Métrica", columns, index=min(2, len(columns) - 1))
    c4, c5 = st.columns(2)
    aggregation = c4.selectbox("Agregación", ["sum", "mean", "count"])
    cumulative = c5.checkbox("Mostrar acumulado")

    try:
        benchmark = build_project_benchmark(
            df,
            project_col=project_col,
            date_col=date_col,
            value_col=value_col,
            aggregation=aggregation,
            cumulative=cumulative,
        )
    except Exception as exc:
        st.exception(exc)
        return

    if benchmark.empty:
        st.warning("No quedaron observaciones válidas después de interpretar las fechas.")
        return

    pivot = benchmark.pivot(index="month_index", columns="project", values="value")
    st.markdown("### Evolución comparable")
    st.line_chart(pivot)
    st.dataframe(
        pivot.reset_index(),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Descargar benchmark CSV",
        data=benchmark.to_csv(index=False).encode("utf-8-sig"),
        file_name="medallio_project_benchmark.csv",
        mime="text/csv",
    )


def data_quality() -> None:
    title(
        "Data Quality Center",
        "Perfil rápido de calidad para CSV/XLSX antes de llevar reglas al pipeline.",
    )
    uploaded = st.file_uploader(
        "Sube un CSV o XLSX",
        type=["csv", "xlsx", "xlsm"],
        key="dq_upload",
    )
    if uploaded is None:
        return

    try:
        df = load_uploaded_table(uploaded)
        metrics, profile = data_quality_summary(df)
    except Exception as exc:
        st.exception(exc)
        return

    a, b, c, d, e = st.columns(5)
    a.metric("Filas", f"{metrics['rows']:,}")
    b.metric("Columnas", metrics["columns"])
    c.metric("Duplicadas", f"{metrics['duplicate_rows']:,}")
    d.metric("Celdas nulas", f"{metrics['missing_cells']:,}")
    e.metric("% nulos", f"{metrics['missing_pct']:.2f}%")

    st.markdown("### Perfil por columna")
    st.dataframe(profile, use_container_width=True, hide_index=True)
    st.download_button(
        "Descargar perfil CSV",
        data=profile.to_csv(index=False).encode("utf-8-sig"),
        file_name="medallio_data_quality_profile.csv",
        mime="text/csv",
    )


def lab_catalog() -> None:
    title(
        "Notebook Launcher",
        "Todos los notebooks del repositorio, agrupados por propósito y ejecutables con cualquier kernel instalado.",
    )
    notebooks = [Path(path) for path in get_notebooks(str(ROOT))]
    groups = group_notebooks(notebooks)
    summary = pd.DataFrame(
        [{"familia": family, "notebooks": len(paths)} for family, paths in groups.items()]
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)

    with st.expander("Ver catálogo completo", expanded=False):
        for family, paths in groups.items():
            st.markdown(f"**{family}**")
            for path in paths:
                st.code(str(path), language="text")

    st.markdown("### Ejecutar")
    notebook_runner(key_prefix="launcher")


PAGES = {
    "🏠 Inicio": home,
    "🗼 Control Tower": control_tower,
    "📑 Executive Briefing": executive_briefing,
    "🔮 Forecast Studio": forecast_studio,
    "🧪 Econometrics Lab": econometrics_lab,
    "📈 Benchmark Lab": benchmark_lab,
    "🧹 Data Quality": data_quality,
    "📚 Notebook Launcher": lab_catalog,
}

with st.sidebar:
    st.markdown("## ◆ MEDALLIO")
    st.caption("LOCAL ANALYTICS OS")
    page_name = st.radio("Aplicación", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption(f"Repo: `{ROOT.name}`")
    st.caption(f"Python: `{Path(sys.executable).name}`")

PAGES[page_name]()
