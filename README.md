# Workshop: reading agent traces

> These traces are **simulated for teaching**. All complaints, people, account details and "the Bank" are fictional.

## The scenario

An AI coding agent (GitHub Copilot in agent mode) was given a skill, `complaint-triage`, for labeling batches of consumer banking complaints. Different people asked it to work on different batches. You have a record (a *trace*) of each of those 16 sessions.

The skill's instructions are in `.github/skills/complaint-triage/SKILL.md`. **Read it first.** It tells you what the agent was supposed to do.

## Your task

1. Read each trace in `traces/`, starting with `T01.jsonl`.
2. In `notes.csv`, write **one short note per trace** about what happened. If something went wrong, say where (the step number) and how you can tell.
3. Bring your notes to the group discussion.

You can open the files the agent worked with (the complaint batches and the taxonomy in `fixtures/`) to check what it did.

## What's in this repo

```
.github/skills/complaint-triage/SKILL.md   the instructions the agent was given
fixtures/taxonomy.yaml                     the allowed product and issue labels
fixtures/batches/batch_XX.csv              the complaint batches the agent worked on
traces/TXX.jsonl                           the 16 traces (start here)
traces_otel/TXX.spans.jsonl                the same traces as OpenTelemetry spans (optional)
notes.csv                                  your notes, one row per trace
```

## Reading a trace

Each line of a trace file is one step of the session:

```json
{"step": 1, "type": "user|assistant|skill_load|tool_call|tool_result", "tool": "read_file|run_in_terminal|create_file|list_dir|null", "args": {}, "content": "..."}
```

The first step is the user's request, which names the batch the agent worked on. File paths in the traces, such as `fixtures/...`, are relative to the root of this repo.

Long tool outputs are hard to read as raw JSON. To print a trace step by step:

```bash
python3 -c "import json,sys; [print(f\"\n--- step {s['step']} | {s['type']} {s['tool'] or ''}\n{s['content'] or json.dumps(s['args'], indent=1)}\") for s in map(json.loads, open(sys.argv[1]))]" traces/T01.jsonl
```

## Optional: the telemetry view

`traces_otel/` holds the same sessions in the format an observability tool would record, with much more detail. Each line is one span. To load one into pandas (`pip install -r requirements.txt` first):

```python
import json, pandas as pd
spans = pd.DataFrame(json.loads(l) for l in open("traces_otel/T01.spans.jsonl"))
```
