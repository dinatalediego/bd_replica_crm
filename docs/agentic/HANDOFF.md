# Latest Handoff

Protocol: MEDALLIO AGENT PROTOCOL v1.0  
Task: MAP-001  
From: ChatGPT  
To: Claude / human reviewer  
Branch: feat/medallio-agent-protocol  
Status: REVIEW_READY

## What changed

A first version of the cross-agent coordination protocol was added without changing ETL/database behavior.

The protocol provides:

- provider entrypoints;
- durable project/task/decision state;
- machine-readable state;
- a local checkpoint utility;
- a reusable bootstrap path;
- an agent-task issue template.

## Evidence

Created as repository files on an isolated feature branch.

No claim is made yet that the local CLI has executed successfully on the user's Windows environment.

## Review focus

1. Is any instruction ambiguous enough to cause two agents to edit concurrently?
2. Can a new agent infer the exact next action without reading prior chats?
3. Does the CLI avoid automatic push/merge and secrets?
4. Is the bootstrap behavior conservative with existing files?
5. Can the state schema evolve without breaking current repos?

## Next action

Pull the branch and run:

```bash
python tools/agent_handoff.py validate
python tools/agent_handoff.py status
```

Then perform an adversarial review of MAP-001 and record material findings before merge.
