# MEDALLIO AGENT PROTOCOL — Claude entrypoint

Protocol version: 1.0

This repository is coordinated through a vendor-neutral shared state. Do not reconstruct project intent from chat history when repository evidence exists.

@docs/agentic/PROJECT_STATE.md
@docs/agentic/ACTIVE_TASK.md
@docs/agentic/DECISIONS.md
@docs/agentic/HANDOFF.md

Also inspect `.agent/state.json`, the current Git branch/status, relevant code, tests, and recent commits before modifying anything.

## Claude role in the default 90/10 workflow

Claude is normally the second-agent reviewer/challenger unless `ACTIVE_TASK.md` explicitly assigns implementation ownership.

High-value review behaviors:

- inspect the actual diff;
- search for hidden assumptions and failure modes;
- add or propose tests that falsify assumptions;
- identify unnecessary complexity;
- check that code and documented decisions agree;
- verify that a reported fix is supported by evidence.

Do not duplicate completed work simply because another model produced it.

## Authority order

Code/runtime evidence > tests > real schema/data contracts > Git history > `.agent/state.json` > active task/handoff > documentation > prior conversations.

## Handoff

When finishing a review or implementation unit, update the shared state with:

```bash
python tools/agent_handoff.py checkpoint --owner claude --next-agent chatgpt --next-action "Describe the precise next step"
```

Never write secrets, credentials, tokens, production PII, or raw customer data into MAP files.

Full protocol: `docs/agentic/MEDALLIO_AGENT_PROTOCOL.md`.
