# Workshop: reading agent traces

> These traces are **simulated for teaching**. All complaints, people, account details and "the Bank" are fictional.

## The scenario

An AI coding agent (GitHub Copilot in agent mode) was given a skill, `complaint-triage`, for labeling batches of consumer banking complaints. Different people asked it to work on different batches. You have a record (a *trace*) of each of those 16 sessions.

The skill's instructions are in `.github/skills/complaint-triage/SKILL.md`. **Read it first.** It tells you what the agent was supposed to do.

## Your task

1. Read each trace, starting with `traces/T01.md`.
2. In `notes.csv`, write **one short note per trace** about what happened. If something went wrong, say where (the step number) and how you can tell.
3. Bring your notes to the group discussion.

You can open the files the agent worked with (the complaint batches and the taxonomy in `fixtures/`) to check what it did.

## What's in this repo

```
.github/skills/complaint-triage/SKILL.md   the instructions the agent was given
fixtures/taxonomy.yaml                     the allowed product and issue labels
fixtures/batches/batch_XX.csv              the complaint batches the agent worked on
traces/TXX.md                              each session, easy to read (start here)
traces/TXX.jsonl                           the same session, one JSON step per line
traces_otel/                               the same sessions as OpenTelemetry data (optional)
notes.csv                                  your notes, one row per trace
```

Each trace's first message names the batch it used (for example, `batch_06`). File paths in the traces, such as `fixtures/...`, are relative to the root of this repo.

## Optional: the telemetry view

`traces_otel/` holds the same sessions in the format an observability tool would record, with much more detail. `TXX.tree.txt` gives a quick overview, and `TXX.spans.jsonl` loads into pandas:

```bash
pip install -r requirements.txt
```

```python
import json, pandas as pd
spans = pd.DataFrame(json.loads(l) for l in open("traces_otel/T01.spans.jsonl"))
```
