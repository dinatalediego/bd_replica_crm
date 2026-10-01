# Active Task

Task ID: MAP-001  
Title: Introduce MEDALLIO AGENT PROTOCOL v1.0  
Status: REVIEW_READY  
Owner: chatgpt  
Next agent: claude  
Branch: feat/medallio-agent-protocol  
Base branch: main

## Objective

Create a repository-native, vendor-neutral handoff protocol so ChatGPT/Work can remain the primary working environment while Claude Code can resume/review the latest state with minimal context loss.

## Scope implemented

- OpenAI/Codex entrypoint: `AGENTS.md`
- Claude entrypoint: `CLAUDE.md`
- MAP specification
- project/task/decision/handoff documents
- machine-readable state
- local status/validate/checkpoint/bootstrap utility
- reusable bootstrap template documentation
- GitHub issue template for agent tasks

## Explicit non-scope

- no ETL behavior changes;
- no Redshift scheduling changes;
- no database migrations;
- no automatic Git push or merge;
- no automatic model/API calls.

## Validation state

Repository files are created through the GitHub integration.

Local execution of `tools/agent_handoff.py` should be performed after pulling this branch. Until that command is executed locally, CLI behavior is implementation-complete but runtime validation is still required.

## Acceptance criteria

- [x] shared human-readable state exists;
- [x] machine-readable state exists;
- [x] ChatGPT and Claude have dedicated entrypoints;
- [x] protocol defines authority and handoff rules;
- [x] reusable bootstrap path exists;
- [ ] run `python tools/agent_handoff.py validate` locally;
- [ ] run `python tools/agent_handoff.py status` locally;
- [ ] optionally have Claude perform first adversarial review;
- [ ] merge after review.

## Next action

Pull the branch locally, execute `validate` and `status`, then ask Claude to review MAP-001 from `CLAUDE.md` and the current diff.
