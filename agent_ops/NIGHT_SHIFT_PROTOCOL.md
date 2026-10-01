# MEDALLIO NIGHT SHIFT OS

Version: 0.1
Status: Pilot — 2026-10-01 to 2026-10-07

## Purpose

Night Shift OS turns a backlog of approved ideas into a governed overnight production queue.

It sits on top of MEDALLIO AGENT PROTOCOL (MAP):

- MAP answers: **what is the current project/task state and how can another agent continue safely?**
- Night Shift OS answers: **which approved task may be worked next, under what limits, and what evidence is required by morning?**

The system is designed for a default 90/10 split:

- ChatGPT / Work / Codex: primary builder and orchestrator.
- Claude Code: selective reviewer/challenger.
- Human: irreversible decisions and production approvals.

## Core loop

```text
approved backlog
    -> READY
    -> CLAIMED
    -> IN_PROGRESS
    -> REVIEW_READY
    -> REVIEWING
    -> READY_FOR_HUMAN
    -> DONE
```

Alternative states:

- BLOCKED
- REWORK_REQUIRED
- CANCELLED
- NEEDS_SCOPING

## Nightly operating window

Pilot window: 2026-10-01 through 2026-10-07.

The queue is intentionally conservative. A task may be worked unattended only if:

1. it is explicitly marked `READY`;
2. its repository is known and accessible;
3. its allowed/forbidden actions are explicit;
4. its acceptance evidence is explicit;
5. it does not require an irreversible production action;
6. it does not depend on unknown credentials or manual business judgment.

## Autonomy boundary

Allowed by default overnight:

- inspect code and docs;
- create a feature branch;
- edit code;
- add tests;
- run tests;
- open or update a draft PR;
- create documentation;
- generate non-production artifacts;
- create Vercel preview deployments only when a project already supports safe previews;
- update MAP/Night Shift state.

Forbidden by default overnight:

- merge to `main`;
- production deploy;
- destructive database migration;
- delete production data;
- alter production CRM records;
- publish to Google Play;
- change billing plans;
- rotate or expose secrets;
- increase Redshift polling frequency;
- execute uncontrolled expensive jobs;
- bypass failing quality gates.

## Quality gates

A task cannot move to `READY_FOR_HUMAN` unless applicable evidence exists.

### Software

- relevant tests executed;
- compile/lint/build evidence where applicable;
- changed files identified;
- draft PR exists or commit evidence exists;
- known limitations are recorded.

### Data / ETL

- no destructive write unless explicitly approved;
- before/after row-count or data-quality evidence;
- source load impact documented;
- heavy Redshift access avoided when Medallio/local data can answer the task.

### ML / probabilistic work

- explicit target/hypothesis;
- baseline;
- leakage check;
- train/validation separation where applicable;
- metric and caveat;
- reproducibility path.

### Web

- build/tests pass;
- preview rather than production deploy;
- major UX change includes visual/route evidence where available.

### Android

- build succeeds;
- tests or static checks where available;
- artifact may be generated;
- no Play Store publication overnight.

## Rework policy

To prevent quota burn:

- maximum automatic rework cycles per task: 1;
- if the same blocker repeats twice, mark `BLOCKED`;
- do not keep retrying external services indefinitely;
- if required context is missing, mark `NEEDS_SCOPING`.

## Cross-agent review

Claude is valuable when it acts differently from the builder.

Recommended review brief:

1. inspect the actual diff;
2. try to falsify assumptions;
3. find missing tests;
4. look for hidden coupling and unnecessary complexity;
5. distinguish critical, important, and minor findings;
6. do not reimplement the feature unless explicitly assigned.

If Claude cannot run unattended under the current subscription/environment, leave the item at `REVIEW_READY` and preserve the handoff for the next available Claude session.

## Morning report

The morning report must prioritize decisions, not narration:

- what completed;
- what is ready for approval;
- what failed;
- what is blocked;
- CI status;
- review findings;
- resource usage notes;
- exact human decisions required;
- next recommended queue item.

## Safety principle

**Machines may work unattended. Irreversible decisions remain human-approved during the pilot.**
