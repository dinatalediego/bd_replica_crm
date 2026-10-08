from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


IGNORED_PARTS = {
    ".git",
    ".venv",
    ".ipynb_checkpoints",
    ".pytest_cache",
    "__pycache__",
    ".medallio",
}


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str
    output_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root without assuming a fixed Windows drive."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (
            (candidate / "pyproject.toml").exists()
            and (candidate / "src").exists()
        ):
            return candidate
    raise FileNotFoundError(
        f"No se encontró la raíz de bd_replica_crm desde {current}"
    )


def ensure_inside_repo(repo_root: Path, path: Path) -> Path:
    """Resolve a path and reject paths outside the repository."""
    root = repo_root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Ruta fuera del repositorio: {resolved}") from exc
    return resolved


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 7200,
    output_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    started = datetime.now().astimezone()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env or os.environ.copy(),
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTimeout luego de {timeout} segundos."
    except OSError as exc:
        returncode = 127
        stdout = ""
        stderr = str(exc)

    finished = datetime.now().astimezone()
    return CommandResult(
        command=tuple(command),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        started_at=started.isoformat(timespec="seconds"),
        finished_at=finished.isoformat(timespec="seconds"),
        output_path=str(output_path) if output_path else None,
    )


def discover_kernels(repo_root: Path) -> dict[str, str]:
    """Return Jupyter kernel names and their resource directories."""
    command = [sys.executable, "-m", "jupyter", "kernelspec", "list", "--json"]
    result = _run(command, cwd=repo_root, timeout=30)
    if not result.ok:
        return {}

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    kernels: dict[str, str] = {}
    for name, meta in payload.get("kernelspecs", {}).items():
        kernels[name] = str(meta.get("resource_dir", ""))
    return dict(sorted(kernels.items(), key=lambda item: item[0].lower()))


def discover_notebooks(repo_root: Path) -> list[Path]:
    """Discover repository notebooks while ignoring virtualenv/runtime folders."""
    root = repo_root.resolve()
    notebooks: list[Path] = []
    for path in root.rglob("*.ipynb"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        notebooks.append(relative)
    return sorted(notebooks, key=lambda p: str(p).lower())


def classify_notebook(path: Path) -> str:
    name = path.stem.lower()
    groups = (
        ("Forecasting", ("forecast", "predic", "serie", "time_series")),
        ("Econometría", ("econometric", "causal", "elastic", "season", "estacion")),
        ("Machine Learning", ("model", "scoring", "ml_", "uplift", "explain")),
        ("Decision Intelligence", ("decision", "control_tower", "command_center")),
        ("Data / ETL", ("etl", "replica", "quality", "dq_", "postgres", "redshift")),
        ("Pricing / Stock", ("pricing", "price", "stock", "absorcion", "absorption")),
        ("Executive", ("ceo", "brief", "executive", "gerencia")),
    )
    for label, keywords in groups:
        if any(keyword in name for keyword in keywords):
            return label
    return "Otros"


def group_notebooks(paths: Iterable[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(classify_notebook(path), []).append(path)
    return dict(sorted(groups.items(), key=lambda item: item[0]))


def preflight(repo_root: Path) -> list[dict[str, str | bool]]:
    kernels = discover_kernels(repo_root)
    notebooks = discover_notebooks(repo_root)
    ambassador = repo_root / "scripts" / "medallio_ambassador" / "run_ambassador.py"

    checks: list[dict[str, str | bool]] = [
        {
            "check": "Python del entorno",
            "ok": bool(sys.executable),
            "detail": sys.executable,
        },
        {
            "check": "Jupyter kernels",
            "ok": bool(kernels),
            "detail": f"{len(kernels)} kernels detectados" if kernels else "No detectados",
        },
        {
            "check": "Kernel medallio_dw",
            "ok": "medallio_dw" in kernels,
            "detail": kernels.get("medallio_dw", "No instalado"),
        },
        {
            "check": "Notebooks",
            "ok": bool(notebooks),
            "detail": f"{len(notebooks)} notebooks detectados",
        },
        {
            "check": "Medallio Ambassador",
            "ok": ambassador.exists(),
            "detail": (
                str(ambassador.relative_to(repo_root))
                if ambassador.exists()
                else "No está en esta copia/rama del repositorio"
            ),
        },
    ]
    return checks


def execute_notebook(
    repo_root: Path,
    notebook_relative: Path,
    kernel_name: str,
    *,
    timeout: int = 1800,
) -> CommandResult:
    """Execute a notebook to a runtime copy; never overwrite the source notebook."""
    root = repo_root.resolve()
    source = ensure_inside_repo(root, root / notebook_relative)
    if source.suffix.lower() != ".ipynb" or not source.exists():
        raise FileNotFoundError(f"Notebook no encontrado: {source}")

    kernels = discover_kernels(root)
    if kernel_name not in kernels:
        raise ValueError(f"Kernel no disponible: {kernel_name}")

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = root / ".medallio" / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{source.stem}.executed.ipynb"
    output_path = run_dir / output_name

    command = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(source),
        "--output",
        output_name,
        "--output-dir",
        str(run_dir),
        f"--ExecutePreprocessor.kernel_name={kernel_name}",
        f"--ExecutePreprocessor.timeout={timeout}",
    ]
    return _run(
        command,
        cwd=root,
        timeout=max(timeout + 120, 300),
        output_path=output_path,
    )


def run_ambassador(
    repo_root: Path,
    slot: str = "morning",
    *,
    dry_run: bool = True,
    timeout: int = 7200,
) -> CommandResult:
    root = repo_root.resolve()
    script = root / "scripts" / "medallio_ambassador" / "run_ambassador.py"
    if not script.exists():
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        return CommandResult(
            command=(),
            returncode=127,
            stdout="",
            stderr=(
                "No se encontró scripts/medallio_ambassador/run_ambassador.py. "
                "Si existe solo en tu working tree local, conserva esos cambios y "
                "ejecuta Medallio OS desde esa copia."
            ),
            started_at=now,
            finished_at=now,
        )

    command = [sys.executable, str(script), "--slot", slot]
    if dry_run:
        command.append("--dry-run")
    return _run(command, cwd=root, timeout=timeout)


def list_recent_runs(repo_root: Path, limit: int = 10) -> list[Path]:
    runs_root = repo_root / ".medallio" / "runs"
    if not runs_root.exists():
        return []
    runs = [path for path in runs_root.iterdir() if path.is_dir()]
    return sorted(runs, key=lambda p: p.name, reverse=True)[:limit]
