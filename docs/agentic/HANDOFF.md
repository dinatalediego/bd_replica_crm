# Latest Handoff

Task: FORECAST-EVIDENCE-001 — Forecasting comercial con entrenamiento y evidencia
Owner: chatgpt
Next agent: human
Branch: feat/forecasting-evidence-pilot
Status: REVIEW_READY
Published PR: https://github.com/dinatalediego/bd_replica_crm/pull/39

## Evidence
- CI 37150045806: 156 platform + 106 decision engine tests passed, including PostgreSQL.
- Final unit tests passed after embargo and ETS serialization.
- Demo and notebook executed; final synthetic selection Random Forest.
- Final CI includes one additional PostgreSQL source-adapter test.

## Next action
Execute scripts/64_forecasting_medallio.bat on the user's PC after updating Medallio.
Open report.html; register targets/actions and connect Power BI views.
Actual Cygnus model metrics are not known; local DB is not available in this session.
Historical revised absorption remains diagnostic, predictions remain shadow.
No merge to main, no source load to Redshift and no changes to canonical sales rules.

## Contracts
ADR-013. Immutable snapshots, predictions and first mature outcomes.
Validation outcome windows overlapping final test origins are embargoed.
Forecasts are cumulative over existing inventory; no causal pricing or cash forecast.
