# MEDALLIO AGENT PROTOCOL (MAP)

Version: 1.0  
Status: Initial standard

## Purpose

MAP is a small, repository-native protocol that lets different AI agents and humans continue the same engineering work without requiring access to each other's full conversation history.

The core idea is:

**Agents are replaceable. The project state belongs to the repository.**

MAP optimizes for a workflow in which ChatGPT/Work performs most architecture and implementation work, while Claude Code or another agent can enter late as a reviewer, challenger, debugger, or continuation agent.

## Goals

- Preserve the minimum context required to continue work safely.
- Make handoffs auditable through Git.
- Separate durable decisions from transient conversations.
- Give humans and agents the same compact project map.
- Keep the protocol vendor-neutral and reusable across repositories.
- Avoid repeatedly loading large chat histories.

## Non-goals

MAP is not:

- a replacement for source code or tests;
- a transcript archive;
- a place for secrets or production data;
- an autonomous permission system;
- a substitute for issue/PR history.

## Required files

| File | Purpose |
|---|---|
| `AGENTS.md` | OpenAI/Codex entrypoint and behavioral contract |
| `CLAUDE.md` | Claude entrypoint |
| `PROJECT_STATE.md` | Durable project snapshot |
| `ACTIVE_TASK.md` | Exactly what is being worked on now |
| `DECISIONS.md` | Architecture/operational decisions and rationale |
| `HANDOFF.md` | Latest compact relay between agents |
| `.agent/state.json` | Machine-readable state |
| `tools/agent_handoff.py` | Validate/status/checkpoint/bootstrap CLI |

## Source-of-truth hierarchy

If two sources conflict, use this order:

1. executable code and observed runtime evidence;
2. automated tests;
3. real data/schema/API contracts;
4. Git commit/PR history;
5. machine-readable MAP state;
6. active task and latest handoff;
7. durable documentation;
8. chat history or model memory.

Documentation must be corrected when reality disproves it.

## Task state machine

Recommended states:

- `PLANNED`
- `IMPLEMENTING`
- `BLOCKED`
- `REVIEW_READY`
- `REVIEWING`
- `VALIDATION_REQUIRED`
- `DONE`
- `CANCELLED`

A task should have one current owner and one explicit next action.

Recommended owners:

- `chatgpt`
- `claude`
- `human`
- `automation`
- `none`

## Handoff contract

A useful handoff answers only what the next agent needs:

1. What task is active?
2. What changed?
3. What evidence exists?
4. What remains?
5. What must not be changed casually?
6. What is the exact next action?
7. Which branch/commit contains the work?

Avoid long narrative summaries when Git already contains the detail.

## Default 90/10 orchestration

### ChatGPT / Work — primary agent

Typical responsibilities:

- problem decomposition;
- architecture;
- implementation;
- repository changes;
- migrations and integration design;
- primary debugging;
- updating MAP state before relay.

### Claude Code — secondary agent

Typical responsibilities:

- adversarial review;
- failure-mode search;
- test expansion;
- simplification review;
- independent code reading;
- continuation when ChatGPT capacity is exhausted.

Claude may become the implementation owner when `ACTIVE_TASK.md` explicitly says so.

## One-writer principle

Only one agent should be considered the active writer for a task at a time.

For parallel work, split the work into independent task IDs/branches. Do not have two agents edit the same working tree without an explicit merge strategy.

## Decisions

Use `DECISIONS.md` for choices that another competent engineer might otherwise reverse because they cannot see the reasoning.

A decision should include:

- ID;
- date;
- status;
- decision;
- rationale;
- consequences;
- supersedes/superseded-by when relevant.

Do not rewrite history. Add a new decision that supersedes the old one.

## Evidence standard

Agents should distinguish:

- **observed:** command/test/query actually executed;
- **inferred:** conclusion from code or docs;
- **planned:** not yet executed.

Never mark inferred or planned work as tested.

## Security and privacy

Never place the following in MAP files:

- passwords;
- API keys;
- auth tokens;
- connection strings containing credentials;
- private customer records;
- raw PII;
- secrets copied from `.env`.

It is acceptable to refer to secret names, e.g. `REDSHIFT_PASSWORD`, without storing their values.

## GitHub integration

Recommended mapping:

- GitHub Issue = durable unit of work.
- Branch = implementation isolation.
- Commits = evidence of actual changes.
- Pull Request = review/integration boundary.
- MAP files = current compact state.

Task IDs may use issue numbers when available, e.g. `GH-142`.

## Checkpoint lifecycle

Before handoff:

```text
work
  -> inspect diff
  -> run relevant tests
  -> update ACTIVE_TASK / DECISIONS if needed
  -> agent_handoff.py checkpoint
  -> commit/push
  -> next agent reads MAP + real diff
```

The CLI never pushes or merges automatically. Git mutation remains explicit.

## Reuse

Run from a repository containing this protocol:

```bash
python tools/agent_handoff.py bootstrap --target ../target-repo --project-name "target-repo"
```

The bootstrap command creates the minimal MAP structure only when files do not already exist. Existing files are preserved unless a future explicit migration command is introduced.

## Versioning

Protocol changes use semantic-style versions:

- patch: wording/template fixes;
- minor: backward-compatible fields or workflow capabilities;
- major: breaking changes to required state or workflow semantics.

Repositories may extend MAP, but extensions should not break the required core files or source-of-truth hierarchy.
