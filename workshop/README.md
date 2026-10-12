# Workshop: reading agent traces

> These traces are **simulated for teaching**. All complaints, people, account details and "the Bank" are fictional.

## The scenario

An AI coding agent was given a skill, `complaint-triage`, for labeling batches of consumer banking complaints. Different people asked it to work on different batches. You have a record (a *trace*) of each of those 16 sessions.

The skill's instructions are in `.github/skills/complaint-triage/SKILL.md`. Read it first. It tells you what the agent was supposed to do.

## Your task

1. Read each trace, starting with `traces/T01.md`.
2. Write **one short note per trace** about what happened. If something went wrong, say where (the step number) and how you can tell.
3. Bring your notes to the group discussion.

## What's in this folder

```
.github/skills/complaint-triage/SKILL.md   the instructions the agent was given
traces/TXX.md                              each session, easy to read (start here)
traces/TXX.jsonl                           the same session, one JSON step per line
traces_otel/                               the same sessions as OpenTelemetry data (optional)
```

`traces_otel/` holds the same sessions in the format an observability tool would record, with much more detail. Use it only if you want to explore it. `TXX.tree.txt` gives a quick overview, and `TXX.spans.jsonl` loads into pandas:

```python
import json, pandas as pd
spans = pd.DataFrame(json.loads(l) for l in open("traces_otel/T01.spans.jsonl"))
```
