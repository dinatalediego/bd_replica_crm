from __future__ import annotations

from typing import Literal

import pandas as pd


def data_quality_summary(df: pd.DataFrame) -> tuple[dict[str, int], pd.DataFrame]:
    """Return dataset-level metrics and a column-level quality profile."""
    rows, columns = df.shape
    duplicate_rows = int(df.duplicated().sum())
    total_cells = max(rows * columns, 1)
    missing_cells = int(df.isna().sum().sum())

    metrics = {
        "rows": int(rows),
        "columns": int(columns),
        "duplicate_rows": duplicate_rows,
        "missing_cells": missing_cells,
        "missing_pct": round(100 * missing_cells / total_cells, 2),
    }

    profile = pd.DataFrame(
        {
            "columna": df.columns.astype(str),
            "tipo": [str(dtype) for dtype in df.dtypes],
            "nulos": [int(df[col].isna().sum()) for col in df.columns],
            "nulos_pct": [
                round(float(df[col].isna().mean() * 100), 2) if rows else 0.0
                for col in df.columns
            ],
            "unicos": [int(df[col].nunique(dropna=True)) for col in df.columns],
        }
    )
    return metrics, profile.sort_values(
        ["nulos_pct", "columna"], ascending=[False, True]
    ).reset_index(drop=True)


def build_project_benchmark(
    df: pd.DataFrame,
    *,
    project_col: str,
    date_col: str,
    value_col: str,
    aggregation: Literal["sum", "mean", "count"] = "sum",
    cumulative: bool = False,
) -> pd.DataFrame:
    """
    Normalize each project to month 0 based on its first valid observation.

    Output columns: project, month_index, value.
    """
    required = {project_col, date_col, value_col}
    missing = required.difference(df.columns)
    if missing:
        raise KeyError(f"Faltan columnas: {', '.join(sorted(missing))}")

    data = df[[project_col, date_col, value_col]].copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    data = data.dropna(subset=[project_col, date_col])
    if data.empty:
        return pd.DataFrame(columns=["project", "month_index", "value"])

    data["_month"] = data[date_col].dt.to_period("M").dt.to_timestamp()
    first_month = data.groupby(project_col)["_month"].transform("min")
    data["month_index"] = (
        (data["_month"].dt.year - first_month.dt.year) * 12
        + data["_month"].dt.month
        - first_month.dt.month
    ).astype(int)

    if aggregation == "count":
        grouped = (
            data.groupby([project_col, "month_index"], dropna=False)
            .size()
            .rename("value")
            .reset_index()
        )
    else:
        data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
        data = data.dropna(subset=[value_col])
        grouped_obj = data.groupby([project_col, "month_index"], dropna=False)[value_col]
        if aggregation == "mean":
            grouped = grouped_obj.mean().rename("value").reset_index()
        else:
            grouped = grouped_obj.sum().rename("value").reset_index()

    grouped = grouped.rename(columns={project_col: "project"})
    grouped = grouped.sort_values(["project", "month_index"]).reset_index(drop=True)
    if cumulative and not grouped.empty:
        grouped["value"] = grouped.groupby("project")["value"].cumsum()
    return grouped
