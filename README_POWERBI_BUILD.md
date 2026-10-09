# Medallio AI Control Tower v1 — Power BI Build Kit

This kit is designed for the current Medallio PostgreSQL semantic layer after v2.9.3.1.

## Architecture

```text
Medallio PostgreSQL
        ↓
stable semantic views
        ↓
Power BI Import model
        ↓
CEO / management dashboard
```

Use Streamlit for analyst/AI-operator exploration.
Use Power BI for corporate consumption.
Add MLOps later for model lifecycle monitoring.

## First prerequisite

Resolve any row in:

```text
analytics.v_pbi_contract_semantics_issues_v2931
```

before a contract is marked STARTED.

At the current state, Modena can be READY_TO_START while Matera may remain blocked until its primary metric is atomic.

## Import order

1. `Dim Project`
2. `AI Control Tower`
3. `Control Tower KPIs`
4. `Intervention Monitoring`
5. `Intervention Events`
6. `Outcome ROI`
7. `Predictive Evidence`
8. `Project Deep Dive`
9. `Contract Semantics Issues`

SQL files are in `/queries`.

## PostgreSQL connection

In Power BI Desktop:

```text
Get data
→ PostgreSQL database
→ server: your local PostgreSQL server
→ database: medallio_dw
→ Advanced options
→ SQL statement
```

Paste each query from the corresponding SQL file.

Start with Import mode.

## Model

Follow:

```text
model/relationships.md
```

Core rule:

```text
Dim Project
   ↓
all business tables
```

Avoid fact-to-fact joins.

## DAX

Paste measures from:

```text
dax/measures_v1.dax
```

Create the measures in a dedicated Measures table if desired.

## Pages

Build in this order:

```text
01 CEO Control Tower
02 Decision & Execution
03 Outcome & ROI
04 Predictive Evidence
05 Project Deep Dive
```

Detailed field specs are in:

```text
pages/page_specs.json
```

## Executive design principle

The CEO page should not begin with model metrics.

It should begin with:

```text
What needs my attention now?
```

The causal chain should be visually legible:

```text
DATA
→ DECISION
→ EXECUTION
→ OUTCOME
→ VALUE
→ LEARNING
```

## What Power BI should NOT recreate

Do not reimplement these in DAX:

```text
BLOCKED_RECONCILIATION
READY_TO_START
BLOCKED_METRIC_SEMANTICS
NOT_STARTED
WAITING_OUTCOME
OUTCOME_MATURE
FIX DATA
DESIGN
BUILD EVIDENCE
START ACTION
```

They belong in PostgreSQL.

DAX should aggregate, rank, format, calculate presentation ratios and support interaction.

## Recommended first release boundary

Ship v1 when these three pages are solid:

```text
01 CEO Control Tower
02 Decision & Execution
05 Project Deep Dive
```

Then add Outcome & ROI as outcomes mature, and Predictive Evidence as the prospective registry matures.

This keeps Power BI useful immediately without pretending that outcome evidence already exists.
