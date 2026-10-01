# MEDALLIO AGENT PROTOCOL — OpenAI entrypoint

Protocol version: 1.0

This repository uses the MEDALLIO AGENT PROTOCOL (MAP) as the shared handoff contract between ChatGPT/Codex, Claude Code, humans, and future agents.

## Read before changing code

Read in this order:

1. `docs/agentic/PROJECT_STATE.md`
2. `docs/agentic/ACTIVE_TASK.md`
3. `docs/agentic/DECISIONS.md`
4. `docs/agentic/HANDOFF.md`
5. `.agent/state.json`
6. the real code, tests, database/schema evidence, and Git history relevant to the task

## Authority order

When sources disagree, prefer:

1. executable code and observed runtime evidence
2. automated tests
3. real schema/data contracts
4. Git history
5. `.agent/state.json`
6. `ACTIVE_TASK.md` and `HANDOFF.md`
7. other documentation
8. prior conversations or agent memory

Never preserve stale documentation over verified repository truth.

## Operating rules

- Work on one explicit task at a time.
- Verify the current branch and Git status before edits.
- Do not silently change accepted decisions in `DECISIONS.md`; add a new decision that supersedes the old one.
- Do not store secrets, credentials, tokens, production PII, or raw customer data in agentic documents.
- Prefer evidence: tests, commands, affected files, commit/PR references.
- Do not claim a test passed unless it was executed.
- Keep handoffs concise enough for another agent to load quickly.
- One agent is the writer at a time. A reviewing agent should work from a clean checkpoint or explicit review branch.

## Local commands

```bash
python tools/agent_handoff.py status
python tools/agent_handoff.py validate
python tools/agent_handoff.py checkpoint --owner chatgpt --next-agent claude --next-action "Review the current implementation"
```

To seed MAP in another repository:

```bash
python tools/agent_handoff.py bootstrap --target ../another-repo --project-name "another-repo"
```

## Completion contract

Before handing work to another agent:

1. inspect the real diff;
2. run the relevant tests when possible;
3. update the active task;
4. record decisions that materially changed;
5. run `checkpoint`;
6. commit the code and agentic state together when practical;
7. hand off by task ID, branch, and next action—not by copying an entire chat.

The full specification lives in `docs/agentic/MEDALLIO_AGENT_PROTOCOL.md`.
