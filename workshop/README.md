# Workshop: reading agent traces for complaint triage

A hands-on exercise in evaluating an AI agent, for people who already know how to evaluate predictive models.

> **These traces are simulated for teaching.** No model produced them in a live session. Each one was scripted to show a realistic agent behavior and then replayed against the files in this folder, so every file read, command output and written file in a trace matches the fixtures exactly. Real agent runs are messier and less predictable. All complaints, people, identifiers and "the Bank" are fictional.

## The scenario

A coding agent (GitHub Copilot in agent mode) has a skill, `complaint-triage`, that labels batches of consumer banking complaints:
- it assigns a product and issue from the Bank's taxonomy
- it flags possible UDAAP or fair lending concerns, quoting evidence
- it redacts personal information
- it writes a CSV and a short summary

Different people (an operations analyst, a product manager, a data scientist) asked the agent to work on different batches. You have the trace of each session.

## What you'll do

1. **Open coding.** Read each trace in `traces/` (about a minute each). Write **one note per trace** describing what happened. If something went wrong, name the *first* step where it went wrong and point at the steps that show it.
2. **Taxonomy.** Cluster your notes into a small set of failure types.
3. **Evals and fixes** (later sessions). Turn each failure type into the cheapest check that would catch it, try fixes, and re-run.

There are no hints in the traces. Some went well.

## Layout

```
.github/skills/complaint-triage/SKILL.md   the skill the agent was given
fixtures/taxonomy.yaml                     allowed product -> issue labels
fixtures/batches/batch_XX.csv              the complaint batches (5-6 each)
traces/TXX.md                              each trace, rendered for reading
traces/TXX.jsonl                           the same trace, one JSON step per line
instructor/                                facilitator materials (see below)
```

Each line of a `.jsonl` trace has this shape:

```json
{"step": 1, "type": "user|assistant|skill_load|tool_call|tool_result", "tool": "read_file|run_in_terminal|create_file|list_dir|null", "args": {}, "content": "..."}
```

## For facilitators

`instructor/` holds the facilitator materials. **Remove it before sharing this folder with participants.**

To regenerate the fixtures and traces after editing `instructor/build/`:

```bash
python3 instructor/build/make_fixtures.py
python3 instructor/build/build_traces.py      # replays traces in /home/dev/complaints-workshop
python3 instructor/build/write_key_csv.py
python3 instructor/build/validate.py          # Stage 5 checks; writes instructor/validation_report.md
```

You need Python 3 with `pandas` and `pyyaml`.
