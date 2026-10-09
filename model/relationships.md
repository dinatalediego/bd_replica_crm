# Power BI model — relationships

Load the tables as separate semantic entities. Do not relate facts directly to other facts.

## Dimension

### Dim Project
Primary key:
- `project_key`

## Relationships

Create these single-direction relationships from `Dim Project`:

- `Dim Project[project_key]` 1 → * `AI Control Tower[project_key]`
- `Dim Project[project_key]` 1 → * `Intervention Monitoring[project_key]`
- `Dim Project[project_key]` 1 → * `Intervention Events[project_key]`
- `Dim Project[project_key]` 1 → * `Outcome ROI[project_key]`
- `Dim Project[project_key]` 1 → * `Predictive Evidence[project_key]`
- `Dim Project[project_key]` 1 → * `Project Deep Dive[project_key]`
- `Dim Project[project_key]` 1 → * `Contract Semantics Issues[project_key]`

Do NOT create a relationship from `Control Tower KPIs` to any table. It is a one-row KPI table.

## Suggested table names in Power BI

- Dim Project
- AI Control Tower
- Control Tower KPIs
- Intervention Monitoring
- Intervention Events
- Outcome ROI
- Predictive Evidence
- Project Deep Dive
- Contract Semantics Issues

## Storage mode

Start with **Import** for all tables.

Reason:
- small executive model;
- stable refresh;
- fast interactions;
- PostgreSQL remains source of truth;
- avoids premature DirectQuery complexity.

Move selected tables to DirectQuery only if operational latency later becomes a real requirement.
