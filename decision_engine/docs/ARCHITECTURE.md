# Architecture — CYGNUS Decision Engine

## 1. System boundary

`bd_replica_crm` owns ingestion, raw replication, reconciliation and trusted analytical marts. `decision_engine` owns decision contracts, features-at-decision-time, models/rules, recommendation generation and feedback.

```text
Sperant / Redshift / Meta / Pricing
              |
              v
        raw_cygnus
              |
              v
     staging / reconciliation
              |
              v
          analytics
              |
      +-------+-------+
      |               |
      v               v
 semantic         feature views
      |               |
      +-------+-------+
              v
        model/rule layer
              |
              v
        Decision Engine
        /      |       \
       v       v        v
   Power BI   API     Alerts/Copilot
       \       |        /
        +------+-------+
               v
        action + outcome
               |
               v
          feedback loop
```

## 2. Decision object

Every decision must declare:

- `decision_id`
- business question
- decision owner
- entity/grain
- observation timestamp
- action space
- target/outcome
- baseline
- feature set
- constraints
- model/rule version
- expected economic value
- confidence
- explanation/evidence
- expiry

## 3. Layer responsibilities

### Data foundation
Trusted history. No recommendation logic.

### Semantic layer
Stable business concepts: lead, client, project, unit, advisor, commercial cycle, separation, sale, fall, stock position, channel and campaign.

### Feature layer
Point-in-time correct features only. Examples:

- lead recency and interaction velocity;
- days since separation;
- historical conversion by advisor/project/channel;
- unit age in stock;
- relative price/m2;
- project absorption momentum;
- funnel congestion;
- recent commercial activity.

### Modeling layer
Each use case starts with a baseline. ML is accepted only if it beats baseline out-of-time and improves an economic metric.

### Decision layer
Combines predictions with constraints and business utility. A probability alone is not a decision.

Example:

`expected_value = p(conversion) * expected_margin - contact_cost - discount_cost`

### Delivery layer
Power BI, API, daily queue, email/Teams/agent surfaces. Delivery must preserve evidence and recommendation IDs.

### Feedback layer
Record whether a recommendation was shown, accepted, modified, rejected or expired and the eventual outcome.

## 4. Guardrails

1. No use of future data in training or inference.
2. No automatic discount publication in v0.x.
3. No advisor performance ranking without minimum sample/reliability treatment.
4. No marketing budget reallocation from observational attribution alone; causal or experimental evidence required for strong claims.
5. Any unresolved reconciliation error that changes stock or sale status can block affected decisions.
6. Personally identifiable information should not be copied into model artifacts unless strictly necessary.

## 5. Multi-client readiness

Business rules and mappings must be configuration-driven. Client-specific source names belong in adapters/config; domain objects remain generic.

Target abstraction:

```text
SourceAdapter -> CanonicalCommercialModel -> FeatureProvider -> DecisionPolicy
```

This permits Cygnus first and a second Sperant client later without rewriting the decision domain.
