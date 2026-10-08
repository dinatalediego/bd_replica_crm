from __future__ import annotations

import pandas as pd

from replica_cygnus.medallio_os.analytics import (
    build_project_benchmark,
    data_quality_summary,
)


def test_data_quality_summary_counts_missing_and_duplicates() -> None:
    df = pd.DataFrame(
        {
            "proyecto": ["A", "A", "A"],
            "valor": [1.0, 1.0, None],
        }
    )
    metrics, profile = data_quality_summary(df)

    assert metrics["rows"] == 3
    assert metrics["columns"] == 2
    assert metrics["duplicate_rows"] == 1
    assert metrics["missing_cells"] == 1
    valor = profile.loc[profile["columna"] == "valor"].iloc[0]
    assert valor["nulos"] == 1


def test_build_project_benchmark_normalizes_each_project_to_month_zero() -> None:
    df = pd.DataFrame(
        {
            "proyecto": ["A", "A", "B", "B"],
            "fecha": ["2026-01-10", "2026-03-01", "2026-05-01", "2026-06-01"],
            "ventas": [2, 3, 7, 11],
        }
    )

    result = build_project_benchmark(
        df,
        project_col="proyecto",
        date_col="fecha",
        value_col="ventas",
    )

    a = result[result["project"] == "A"]
    b = result[result["project"] == "B"]
    assert a["month_index"].tolist() == [0, 2]
    assert b["month_index"].tolist() == [0, 1]
    assert b["value"].tolist() == [7, 11]


def test_build_project_benchmark_can_return_cumulative_values() -> None:
    df = pd.DataFrame(
        {
            "proyecto": ["A", "A"],
            "fecha": ["2026-01-01", "2026-02-01"],
            "ventas": [2, 5],
        }
    )

    result = build_project_benchmark(
        df,
        project_col="proyecto",
        date_col="fecha",
        value_col="ventas",
        cumulative=True,
    )

    assert result["value"].tolist() == [2, 7]
