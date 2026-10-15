# MEDALLIO Data Partner: pilot of independent evidence review

This pilot adds a second review of the existing v2.9.0 context. It proposes missing checks for an economist/data scientist to investigate. It does **not** revise the CRM, issue a recommendation for execution, validate causal effects, or promote model text into the decision ledger.

The separate, aggregate Supabase modeling source is documented in `docs/SUPABASE_MINIMAL_MART.md`. It supplies a private project-month training panel; the OpenAI reviewer continues to consume only its own inspected evidence packet.

## Boundary and ownership

| Step | Owner | Contract |
|---|---|---|
| Compile context | Existing `project_intelligence_context_v290.py` | Local `context.json` can contain source samples and personal data. Never send it to an API. |
| Prepare | Data analyst | Strict allowlist of numeric project aggregates, readiness flags, coverage counts and evidence ceiling; project key becomes a short hash. Inspect the resulting packet. |
| Send | Authorized operator | One manual Responses API call with `store: false`, structured output, bounded output tokens and no tools. Organizational data approval and an API project budget are prerequisites. |
| Validate | Program | Check JSON shape, evidence IDs, permitted values and absence of literal figures/identifiers in free text. These checks cannot prove a hypothesis true. |
| Review | Economist/data scientist | Accept, reject or revise each draft with a written reason. Only a human can initiate a separate existing decision workflow. |

The allowlist deliberately omits `sources.*.sample`, `profile`, raw execution/outcome rows, project name, free-form hypotheses, customer or unit identifiers, prices at row level and all source text. Aggregate counts for small projects may still reveal business-sensitive information. An organizational data owner must inspect the packet and approve its export; the `--data-approved` flag records the operator's assertion, not a technical privacy certification. Configure a dedicated OpenAI API project with scoped key and spend limit. The code does not set a monetary limit or schedule outbound jobs.

## Local exercise with synthetic data

Install the repository package as usual, or set `PYTHONPATH=src`. Run `PYTHONPATH=src python tests/test_ai_review.py` without database credentials or network access. The test constructs a context with fake customer fields, verifies that these fields cannot enter the request, exercises a synthetic Responses payload, blocks unsupported evidence and records a feedback verdict.

Prepare one project packet from an existing local context:

```bash
PYTHONPATH=src python scripts/medallio_ai_review.py prepare \
  --context artifacts/project_intelligence_v290/MD/context.json \
  --output /tmp/medallio_MD_packet.json
```

Inspect the packet and approve the precise data export internally. For a live pilot, configure a scoped `OPENAI_API_KEY` in the operator environment and a hard spend limit in the API project, then run one project manually:

```bash
PYTHONPATH=src python scripts/medallio_ai_review.py review \
  --packet /tmp/medallio_MD_packet.json \
  --output /tmp/medallio_MD_review.json \
  --model gpt-4.1-mini --send --data-approved
```

The output file must not exist, preventing accidental repeated requests on rerun. The adapter makes no retry after an ambiguous network failure. It stores a draft record locally with the packet/context hashes, model, response ID, token usage and findings. API failure or invalid output does not become an accepted finding. API data retention and residency settings must be checked under the organization's agreement before using any business data; `store: false` is not a zero-retention guarantee.

To persist validated drafts in PostgreSQL, install the separate opt-in component with `PYTHONPATH=src python scripts/schema_sync.py --only ai_review` in an approved environment. Add `--persist-db` to `review`. The SQL creates only isolated `decision_intelligence.ai_review_*` tables and is excluded from unattended schema sync. No trigger or foreign key reaches a production CRM or executable decision table.

For a human verdict (zero-based finding index):

```bash
PYTHONPATH=src python scripts/medallio_ai_review.py feedback \
  --record /tmp/medallio_MD_review.json --finding-index 0 \
  --verdict REVISE --reviewer analyst --note "Comprobar contra outcomes maduros" \
  --output /tmp/medallio_MD_feedback.jsonl
```

Use `--persist-db` if the opt-in tables are installed and the draft was also persisted. Keep the packet, review and feedback files in approved local storage with normal access control and retention. Never commit them.

## Evaluation gate before expanding

1. Run the included synthetic privacy and contract tests.
2. Assemble a labeled set of at least twenty historical or synthetic project snapshots: missing source, contradictory metric, immature forecast, missing benchmark, empty outcome status, and a genuinely mature outcome. Keep live snapshots inside the authorized environment.
3. Two domain reviewers rate each finding on evidence support, materiality, novelty and actionability; also record false claims and unnecessary escalations. Compare against the deterministic v2.9.1 analyst without counting model text as ground truth.
4. Expand only if no restricted fields leave the allowlist, reference validation passes, false factual claims are caught by human review, and the measured benefit justifies tokens and review time. Review the API project usage and cost after each run.

The first deployment requires actual access to the authorized local context, PostgreSQL and API key. None of these are exercised by the repository's offline test. The human feedback table is a review trail, not an automatic retraining pipeline; any future prompt revision should use curated feedback through versioned code and a repeatable evaluation set.
