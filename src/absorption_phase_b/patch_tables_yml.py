from pathlib import Path
import re
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "config" / "tables.yml"

if not path.exists():
    raise SystemExit(f"No existe: {path}")

text = path.read_text(encoding="utf-8")
lines = text.splitlines()

starts = []
for i, line in enumerate(lines):
    if re.search(r"^\s*-\s+source_schema\s*:", line):
        starts.append(i)
starts.append(len(lines))

target = None
for a, b in zip(starts[:-1], starts[1:]):
    block = "\n".join(lines[a:b])
    if re.search(r"^\s*source_table\s*:\s*procesos\s*(?:#.*)?$", block, re.M):
        target = (a, b)
        break

if target is None:
    raise SystemExit("No encontré una entrada source_table: procesos en config/tables.yml")

a, b = target
changed = False
for i in range(a, b):
    if re.match(r"^(\s*)key_columns\s*:", lines[i]):
        indent = re.match(r"^(\s*)", lines[i]).group(1)
        old = lines[i]
        lines[i] = f"{indent}key_columns: [nombre, id]   # composite source key validado en Redshift"
        changed = old != lines[i]
        break
else:
    # insertar después de source_table
    for i in range(a, b):
        if re.match(r"^\s*source_table\s*:", lines[i]):
            indent = re.match(r"^(\s*)", lines[i]).group(1)
            lines.insert(i + 1, f"{indent}key_columns: [nombre, id]   # composite source key validado en Redshift")
            changed = True
            break

if not changed:
    print("tables.yml ya usa key_columns: [nombre, id]. No se hicieron cambios.")
    raise SystemExit(0)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = path.with_name(f"tables.yml.backup_before_procesos_keyfix_{stamp}")
shutil.copy2(path, backup)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"OK: actualizado {path}")
print(f"Backup: {backup}")
