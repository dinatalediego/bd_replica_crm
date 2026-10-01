# Decisions

## MAP-ADR-001 — Git repository is the shared agent memory

Date: 2026-09-30  
Status: ACCEPTED

### Decision

Durable cross-agent context lives in versioned repository files and Git history, not in any model's private conversation history.

### Rationale

ChatGPT, Claude, humans, and future tools do not share identical memory. Git is inspectable, portable, diffable, and model-independent.

### Consequence

A handoff is complete only when enough state exists in the repository for another competent agent to continue.

---

## MAP-ADR-002 — Human-readable Markdown plus machine-readable JSON

Date: 2026-09-30  
Status: ACCEPTED

### Decision

MAP uses Markdown for reasoning/context and `.agent/state.json` for structured state.

### Rationale

Humans and models benefit from prose; scripts and future automation need deterministic fields.

---

## MAP-ADR-003 — Repository evidence outranks agent memory

Date: 2026-09-30  
Status: ACCEPTED

### Decision

Observed code/runtime/tests/schema/Git evidence outranks MAP prose and prior conversations.

### Rationale

Agent summaries can become stale. Executable evidence should correct documentation, not the reverse.

---

## MAP-ADR-004 — One active writer per task

Date: 2026-09-30  
Status: ACCEPTED

### Decision

A task has one active writer/owner at a time. Another agent may review from a checkpoint, or parallel work must use separate task IDs/branches.

### Rationale

This reduces conflicting edits and ambiguous ownership during ChatGPT ↔ Claude handoffs.

---

## MAP-ADR-005 — Handoffs contain no secrets or raw PII

Date: 2026-09-30  
Status: ACCEPTED

### Decision

MAP documents may name environment variables and data contracts but must never store secret values, tokens, credentials, or raw customer PII.

### Rationale

Agentic state is versioned and may be broadly visible to repository collaborators.

---

## MAP-ADR-006 — Protocol is vendor-neutral

Date: 2026-09-30  
Status: ACCEPTED

### Decision

The core protocol is named MEDALLIO AGENT PROTOCOL rather than after ChatGPT or Claude.

### Rationale

The coordination layer should survive model/provider changes. Provider-specific files are entrypoints into the same shared state.
