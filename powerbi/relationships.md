# Power BI relationships — Forecast Factory v1

Recommended tables:

- Forecast Factory Current
- Forecast Performance
- Forecast Evidence
- Run Contract Compliance

Use existing `Dim Project` as the shared project dimension.

Relationships:
- `Dim Project[project_key]` 1 -> * `Forecast Factory Current[project_key]`
- `Dim Project[project_key]` 1 -> * `Forecast Performance[project_key]`

Do not relate Forecast Evidence directly to Forecast Factory Current unless a dedicated
run/prediction bridge is required for a drill-through page.

Keep model performance and raw predictions as separate facts.
