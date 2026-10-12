"""Convert traces/TXX.jsonl into OpenTelemetry traces with OpenInference attributes.

Writes, per trace:
  traces_otel/TXX.otlp.json    OTLP/JSON export (resourceSpans -> scopeSpans -> spans)
  traces_otel/TXX.spans.jsonl  one flattened span per line (attributes as a dict)
  traces_otel/TXX.tree.txt     indented span tree for reading

The eval-relevant content (user message, skill load, every LLM turn, every tool
call and result, final answer) is carried losslessly; see otel_to_steps() in
validate.py, which rebuilds traces/TXX.jsonl from the spans. Everything else
(auth, context collection, embeddings, guardrails, HTTP, filesystem, terminal
internals, title generation, telemetry) is realistic platform noise.

Timings, token counts, IDs and versions are synthetic and deterministic.

Usage: python3 instructor/build/build_otel.py
"""
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from batches_data import BATCHES  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "traces_otel"
SKILL_PATH = ".github/skills/complaint-triage/SKILL.md"

INTERNAL, CLIENT = 1, 3
UNSET, OK, ERROR = 0, 1, 2

SCOPE_OI = ("openinference.instrumentation.vscode-chat", "0.4.2")
SCOPE_HTTP = ("@opentelemetry/instrumentation-undici", "0.10.1")
SCOPE_PLATFORM = ("vscode.chat.platform", "1.104.0")

MODEL = "agent-model-2026-08"
TITLE_MODEL = "agent-model-mini-2026-06"

SKILL_DESCRIPTION = re.search(r"description: >\n((?:  .*\n)+)",
                              (ROOT / SKILL_PATH).read_text()).group(1)
SKILL_DESCRIPTION = " ".join(l.strip() for l in SKILL_DESCRIPTION.splitlines())

SYSTEM_PROMPT = (
    "You are an AI programming assistant working inside the user's VS Code workspace. "
    "You can read and create files, list directories and run commands in the integrated terminal. "
    "Keep answers concise and use Markdown. Prefer doing the work over describing it.\n\n"
    "<skills>\n"
    "The following skills are available in this workspace. When the user's request matches a skill, "
    "its SKILL.md is attached to the conversation and you must follow it.\n"
    f"<skill name=\"complaint-triage\" path=\"{SKILL_PATH}\">{SKILL_DESCRIPTION}</skill>\n"
    "</skills>\n\n"
    "<environment>\nOS: Linux\nShell: bash\nWorkspace root: /home/dev/complaints-workshop\n</environment>"
)

TOOLS = [
    ("read_file", "Read the contents of a file. Line numbers are 1-based.",
     {"type": "object", "properties": {"filePath": {"type": "string"}, "startLine": {"type": "integer"},
                                       "endLine": {"type": "integer"}}, "required": ["filePath", "startLine", "endLine"]}),
    ("list_dir", "List the contents of a directory.",
     {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ("create_file", "Create a new file with the given content. Creates parent directories as needed.",
     {"type": "object", "properties": {"filePath": {"type": "string"}, "content": {"type": "string"}},
      "required": ["filePath", "content"]}),
    ("run_in_terminal", "Run a shell command in the integrated terminal and return its output.",
     {"type": "object", "properties": {"command": {"type": "string"}, "explanation": {"type": "string"},
                                       "isBackground": {"type": "boolean"}}, "required": ["command", "explanation", "isBackground"]}),
    ("grep_search", "Search for a text pattern across files in the workspace.",
     {"type": "object", "properties": {"query": {"type": "string"}, "isRegexp": {"type": "boolean"}}, "required": ["query"]}),
    ("semantic_search", "Find code or text in the workspace relevant to a natural-language query.",
     {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    ("get_errors", "Get compile or lint errors for files.",
     {"type": "object", "properties": {"filePaths": {"type": "array", "items": {"type": "string"}}}, "required": ["filePaths"]}),
]


def tok(text):
    return max(1, round(len(text) / 4))


class Builder:
    def __init__(self, tid, steps):
        self.tid = tid
        self.steps = steps
        self.rng = random.Random(tid)
        self.trace_id = hashlib.sha256(f"trace:{tid}".encode()).hexdigest()[:32]
        self.n = 0
        self.spans = []
        b = int(re.search(r"batch_(\d+)", steps[0]["content"]).group(1))
        last = max(d for _, d, _, _, _ in BATCHES[b])
        start = datetime.fromisoformat(last).replace(tzinfo=timezone.utc) + timedelta(
            days=1, hours=13, minutes=self.rng.randint(0, 240), seconds=self.rng.randint(0, 59))
        self.t = int(start.timestamp() * 1e9)
        self.session = hashlib.sha256(f"session:{tid}".encode()).hexdigest()[:8] + "-" + \
            hashlib.sha256(f"s2:{tid}".encode()).hexdigest()[:4] + "-4" + hashlib.sha256(f"s3:{tid}".encode()).hexdigest()[:3]
        self.user = "u_" + hashlib.sha256(f"user:{tid}".encode()).hexdigest()[:10]
        self.prev_prompt_tokens = 0
        self.call_n = 0

    # ---------------------------------------------------------------- helpers
    def sid(self):
        self.n += 1
        return hashlib.sha256(f"{self.tid}:span:{self.n}".encode()).hexdigest()[:16]

    def ms(self, lo, hi):
        return int(self.rng.uniform(lo, hi) * 1e6)

    def span(self, name, parent, start, end, attrs, scope=SCOPE_PLATFORM, kind=INTERNAL,
             status=(OK, ""), events=None):
        s = {"traceId": self.trace_id, "spanId": self.sid(), "parentSpanId": parent or "",
             "name": name, "kind": kind, "startTimeUnixNano": start, "endTimeUnixNano": end,
             "attributes": attrs, "events": events or [], "status": {"code": status[0], "message": status[1]},
             "_scope": scope}
        self.spans.append(s)
        return s

    def leaf(self, name, parent, lo, hi, attrs, **kw):
        start = self.t
        self.t += self.ms(lo, hi)
        s = self.span(name, parent, start, self.t, attrs, **kw)
        self.t += self.ms(0.1, 2)
        return s

    def open(self, name, parent, attrs, **kw):
        s = self.span(name, parent, self.t, None, attrs, **kw)
        self.t += self.ms(0.2, 3)
        return s

    def close(self, s, extra=None):
        self.t += self.ms(0.2, 4)
        s["endTimeUnixNano"] = self.t
        if extra:
            s["attributes"].update(extra)

    def http(self, parent, method, url, status, lo, hi, req_size=None, resp_size=None):
        attrs = {"http.request.method": method, "url.full": url,
                 "server.address": url.split("/")[2], "server.port": 443,
                 "http.response.status_code": status, "network.protocol.version": "2"}
        if req_size:
            attrs["http.request.body.size"] = req_size
        if resp_size:
            attrs["http.response.body.size"] = resp_size
        st = (ERROR, "") if status >= 400 else (UNSET, "")
        if status >= 400:
            attrs["error.type"] = str(status)
        return self.leaf(f"{method}", parent, lo, hi, attrs, scope=SCOPE_HTTP, kind=CLIENT, status=st)

    # ------------------------------------------------------------ the session
    def build(self):
        steps = self.steps
        user_msg = steps[0]["content"]
        final_msg = [s for s in steps if s["type"] == "assistant"][-1]["content"]
        root = self.open("chat.agent.turn", None, {
            "openinference.span.kind": "AGENT", "agent.name": "copilot-agent",
            "session.id": self.session, "user.id": self.user,
            "input.value": user_msg, "input.mime_type": "text/plain",
            "metadata": json.dumps({"chat.location": "panel", "chat.mode": "agent", "vscode.version": "1.104.0",
                                    "copilot.chat.version": "0.31.0", "request.id": self.sid()}),
            "tag.tags": json.dumps(["agent-mode", "workspace"]),
        }, scope=SCOPE_OI)
        R = root["spanId"]

        # platform preamble (noise)
        self.http(R, "POST", "https://auth.agent-gateway.example/copilot_internal/v2/token", 200, 40, 140, resp_size=812)
        ctx = self.open("context.collect", R, {"openinference.span.kind": "CHAIN",
                                               "input.value": user_msg, "input.mime_type": "text/plain"}, scope=SCOPE_OI)
        files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "fixtures").rglob("*") if p.is_file()) + [SKILL_PATH]
        self.leaf("workspace.list_files", ctx["spanId"], 4, 25, {"workspace.file_count": len(files),
                                                                  "workspace.root": "/home/dev/complaints-workshop"})
        self.leaf("editor.active_document", ctx["spanId"], 0.3, 2, {"editor.document.uri": "", "editor.visible_editors": 0})
        self.leaf("embeddings", ctx["spanId"], 60, 220, {
            "openinference.span.kind": "EMBEDDING", "embedding.model_name": "text-embedding-small-2025",
            "embedding.embeddings.0.embedding.text": user_msg}, scope=SCOPE_OI)
        self.close(ctx, {"output.value": json.dumps({"files_considered": len(files), "attached": []}),
                         "output.mime_type": "application/json"})
        self.leaf("content_exclusion.check", R, 3, 18, {
            "openinference.span.kind": "GUARDRAIL", "input.value": json.dumps(files), "input.mime_type": "application/json",
            "output.value": json.dumps({"excluded": []}), "output.mime_type": "application/json"}, scope=SCOPE_OI)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        i = 1
        if steps[1]["type"] == "skill_load":
            sk = steps[1]
            skill_text = (ROOT / SKILL_PATH).read_text()
            self.leaf("skill.load", R, 2, 9, {
                "openinference.span.kind": "CHAIN", "skill.name": sk["args"]["name"], "skill.path": sk["args"]["path"],
                "input.value": sk["args"]["name"], "input.mime_type": "text/plain",
                "output.value": skill_text, "output.mime_type": "text/markdown"}, scope=SCOPE_OI)
            messages.append({"role": "system", "content": f"<attachment skill=\"complaint-triage\" path=\"{SKILL_PATH}\">\n{skill_text}</attachment>"})
            i = 2
        messages.append({"role": "user", "content": user_msg})

        # agent loop: each LLM call emits optional text and at most one tool call
        pending_text = None
        while i < len(steps):
            s = steps[i]
            if s["type"] == "assistant":
                nxt = steps[i + 1] if i + 1 < len(steps) else None
                if nxt and nxt["type"] == "tool_call":
                    pending_text = s["content"]
                    i += 1
                    continue
                self.llm_call(R, messages, s["content"], None)
                messages.append({"role": "assistant", "content": s["content"]})
                i += 1
            elif s["type"] == "tool_call":
                result = steps[i + 1]
                call_id = "call_" + hashlib.sha256(f"{self.tid}:call:{s['step']}".encode()).hexdigest()[:24]
                self.llm_call(R, messages, pending_text or "", (call_id, s))
                messages.append({"role": "assistant", "content": pending_text or "",
                                 "tool_calls": [{"id": call_id, "name": s["tool"], "arguments": json.dumps(s["args"])}]})
                self.tool_span(R, call_id, s, result)
                messages.append({"role": "tool", "tool_call_id": call_id, "name": s["tool"], "content": result["content"]})
                pending_text = None
                i += 2
            else:
                raise ValueError(f"{self.tid}: unexpected step {s}")

        # platform epilogue (noise)
        batch = re.search(r"batch_(\d+)", user_msg).group(1)
        self.title_llm(R, user_msg, f"Complaint batch {batch} review")
        self.t += self.ms(20, 120)
        self.http(R, "POST", "https://telemetry.agent-gateway.example/v1/metrics", 202, 30, 90, req_size=6000 + self.n * 120)
        self.close(root, {"output.value": final_msg, "output.mime_type": "text/markdown"})
        return self.spans

    def llm_call(self, parent, messages, text, call):
        self.call_n += 1
        prompt_tokens = sum(tok(m["content"]) + 4 for m in messages) + sum(tok(json.dumps(t[2])) + 12 for t in TOOLS)
        out = text + (json.dumps(call[1]["args"]) if call else "")
        completion_tokens = tok(out) + (12 if call else 0)
        attrs = {
            "openinference.span.kind": "LLM", "llm.system": "openai", "llm.provider": "copilot",
            "llm.model_name": MODEL,
            "llm.invocation_parameters": json.dumps({"temperature": 0.1, "top_p": 1, "max_tokens": 16384,
                                                     "stream": True, "tool_choice": "auto", "n": 1}),
            "input.mime_type": "application/json",
            "input.value": json.dumps({"model": MODEL, "messages": [_wire(m) for m in messages],
                                       "tools": [{"type": "function", "function": {"name": n}} for n, _, _ in TOOLS]}),
        }
        for k, (name, desc, schema) in enumerate(TOOLS):
            attrs[f"llm.tools.{k}.tool.json_schema"] = json.dumps(
                {"type": "function", "function": {"name": name, "description": desc, "parameters": schema}})
        for k, m in enumerate(messages):
            p = f"llm.input_messages.{k}.message"
            attrs[f"{p}.role"] = m["role"]
            if m["content"]:
                attrs[f"{p}.content"] = m["content"]
            if m["role"] == "tool":
                attrs[f"{p}.tool_call_id"] = m["tool_call_id"]
                attrs[f"{p}.name"] = m["name"]
            for j, tc in enumerate(m.get("tool_calls", [])):
                attrs[f"{p}.tool_calls.{j}.tool_call.id"] = tc["id"]
                attrs[f"{p}.tool_calls.{j}.tool_call.function.name"] = tc["name"]
                attrs[f"{p}.tool_calls.{j}.tool_call.function.arguments"] = tc["arguments"]
        o = "llm.output_messages.0.message"
        attrs[f"{o}.role"] = "assistant"
        if text:
            attrs[f"{o}.content"] = text
        if call:
            attrs[f"{o}.tool_calls.0.tool_call.id"] = call[0]
            attrs[f"{o}.tool_calls.0.tool_call.function.name"] = call[1]["tool"]
            attrs[f"{o}.tool_calls.0.tool_call.function.arguments"] = json.dumps(call[1]["args"])
        attrs["output.mime_type"] = "application/json"
        attrs["output.value"] = json.dumps({"choices": [{"index": 0, "finish_reason": "tool_calls" if call else "stop",
                                                         "message": {"role": "assistant", "content": text or None,
                                                                     "tool_calls": [{"id": call[0], "type": "function", "function": {
                                                                         "name": call[1]["tool"], "arguments": json.dumps(call[1]["args"])}}] if call else None}}]})
        attrs["llm.token_count.prompt"] = prompt_tokens
        attrs["llm.token_count.completion"] = completion_tokens
        attrs["llm.token_count.total"] = prompt_tokens + completion_tokens
        attrs["llm.token_count.prompt_details.cache_read"] = self.prev_prompt_tokens
        self.prev_prompt_tokens = prompt_tokens

        llm = self.open("ChatCompletion", parent, attrs, scope=SCOPE_OI)
        L = llm["spanId"]
        self.leaf("prompt.render", L, 2, 14, {"openinference.span.kind": "CHAIN", "prompt.budget.tokens": 128000,
                                              "prompt.tokens.used": prompt_tokens, "prompt.truncated": False,
                                              "prompt.template": "agent/v7"}, scope=SCOPE_OI)
        url = "https://api.agent-gateway.example/chat/completions"
        if self.tid in ("T01", "T07", "T12") and self.call_n == 2:
            self.http(L, "POST", url, 429, 80, 160, req_size=len(attrs["input.value"]))
            self.leaf("retry.backoff", L, 400, 1100, {"retry.attempt": 1, "retry.reason": "rate_limited"})
        ttft = self.ms(350, 1400)
        gen = int(completion_tokens * self.rng.uniform(9, 16) * 1e6)
        start = self.t
        h = self.http(L, "POST", url, 200, 1, 2, req_size=len(attrs["input.value"]), resp_size=len(attrs["output.value"]))
        h["startTimeUnixNano"] = start
        h["endTimeUnixNano"] = start + ttft + gen
        self.t = start + ttft + gen + self.ms(0.5, 3)
        llm["events"].append({"timeUnixNano": start + ttft, "name": "first_token", "attributes": {}})
        self.leaf("rai.content_filter", L, 1, 6, {
            "openinference.span.kind": "GUARDRAIL", "guardrail.categories": json.dumps(["hate", "self_harm", "sexual", "violence"]),
            "output.value": json.dumps({"filtered": False}), "output.mime_type": "application/json"}, scope=SCOPE_OI)
        self.close(llm)

    def tool_span(self, parent, call_id, call, result):
        name = call["tool"]
        desc = next(d for n, d, _ in TOOLS if n == name)
        args = call["args"]
        tool = self.open(name, parent, {
            "openinference.span.kind": "TOOL", "tool.name": name, "tool.description": desc,
            "tool.parameters": json.dumps(next(s for n, _, s in TOOLS if n == name)),
            "tool_call.id": call_id,
            "input.value": json.dumps(args), "input.mime_type": "application/json"}, scope=SCOPE_OI)
        T = tool["spanId"]
        content = result["content"]
        if name == "read_file":
            size = len((ROOT / args["filePath"]).read_text())
            self.leaf("fs.read", T, 0.3, 4, {"file.path": args["filePath"], "file.size": size})
            if "[File content truncated" in content:
                self.leaf("tool.output.truncate", T, 0.1, 1, {"tool.output.limit_chars": 2000, "tool.output.original_chars": size})
        elif name == "list_dir":
            self.leaf("fs.readdir", T, 0.2, 2, {"file.path": args["path"], "fs.entries": len(content.splitlines())})
        elif name == "create_file":
            self.leaf("fs.stat", T, 0.1, 1, {"file.path": args["filePath"], "fs.exists": False})
            self.leaf("fs.write", T, 0.4, 5, {"file.path": args["filePath"], "file.size": len(args["content"].encode())})
            self.leaf("editor.open_document", T, 3, 20, {"editor.document.uri": "file:///home/dev/complaints-workshop/" + args["filePath"]})
        elif name == "run_in_terminal":
            self.leaf("tool.confirmation", T, 0.2, 2, {"confirmation.mode": "auto_approved", "confirmation.rule": "workspace.terminal.autoApprove"})
            self.leaf("terminal.shell_integration.wait", T, 5, 60, {"terminal.id": 1, "terminal.shell": "bash"})
            exit_code = 1 if ("Traceback" in content or (args["command"].startswith("grep -c") and content.strip() == "0")) else 0
            dur = 2500 if "pandas" in args["command"] or "python3" in args["command"] else 40
            self.leaf("terminal.exec", T, dur * 0.6, dur * 1.3, {
                "process.command_line": args["command"], "process.exit.code": exit_code,
                "terminal.output.chars": len(content)})
            if "(output truncated," in content:
                self.leaf("tool.output.truncate", T, 0.1, 1, {"tool.output.limit_chars": 2000})
        self.close(tool, {"output.value": content, "output.mime_type": "text/plain"})

    def title_llm(self, parent, user_msg, title):
        msgs = [{"role": "system", "content": "Write a short title (max 6 words) for this chat."},
                {"role": "user", "content": user_msg}]
        attrs = {"openinference.span.kind": "LLM", "llm.system": "openai", "llm.provider": "copilot",
                 "llm.model_name": TITLE_MODEL,
                 "llm.invocation_parameters": json.dumps({"temperature": 0.3, "max_tokens": 20, "stream": False}),
                 "input.value": json.dumps({"model": TITLE_MODEL, "messages": msgs}), "input.mime_type": "application/json",
                 "output.value": title, "output.mime_type": "text/plain",
                 "llm.output_messages.0.message.role": "assistant", "llm.output_messages.0.message.content": title,
                 "llm.token_count.prompt": sum(tok(m["content"]) + 4 for m in msgs), "llm.token_count.completion": tok(title),
                 "llm.token_count.total": sum(tok(m["content"]) + 4 for m in msgs) + tok(title),
                 "metadata": json.dumps({"purpose": "chat.title"})}
        for k, m in enumerate(msgs):
            attrs[f"llm.input_messages.{k}.message.role"] = m["role"]
            attrs[f"llm.input_messages.{k}.message.content"] = m["content"]
        llm = self.open("ChatCompletion", parent, attrs, scope=SCOPE_OI)
        self.http(llm["spanId"], "POST", "https://api.agent-gateway.example/chat/completions", 200, 250, 700, req_size=len(attrs["input.value"]))
        self.close(llm)


def _wire(m):
    w = {"role": m["role"], "content": m["content"] or None}
    if m.get("tool_calls"):
        w["tool_calls"] = [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t["arguments"]}}
                           for t in m["tool_calls"]]
    if m["role"] == "tool":
        w["tool_call_id"] = m["tool_call_id"]
    return w


# --------------------------------------------------------------------- output
def otlp_value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def to_otlp(spans):
    resource = {"service.name": "vscode-copilot-chat", "service.version": "0.31.0",
                "telemetry.sdk.name": "opentelemetry", "telemetry.sdk.language": "nodejs", "telemetry.sdk.version": "1.30.1",
                "os.type": "linux", "host.arch": "amd64", "deployment.environment.name": "workshop",
                "workshop.simulated": True}
    by_scope = {}
    for s in spans:
        by_scope.setdefault(s["_scope"], []).append(s)
    return {"resourceSpans": [{
        "resource": {"attributes": [{"key": k, "value": otlp_value(v)} for k, v in resource.items()]},
        "scopeSpans": [{
            "scope": {"name": sc[0], "version": sc[1]},
            "spans": [{
                "traceId": s["traceId"], "spanId": s["spanId"], "parentSpanId": s["parentSpanId"], "name": s["name"],
                "kind": s["kind"], "startTimeUnixNano": str(s["startTimeUnixNano"]), "endTimeUnixNano": str(s["endTimeUnixNano"]),
                "attributes": [{"key": k, "value": otlp_value(v)} for k, v in s["attributes"].items()],
                "events": [{"timeUnixNano": str(e["timeUnixNano"]), "name": e["name"], "attributes": []} for e in s["events"]],
                "status": {"code": s["status"]["code"], **({"message": s["status"]["message"]} if s["status"]["message"] else {})},
            } for s in ss]} for sc, ss in by_scope.items()]}]}


def iso(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_flat(spans):
    status = {0: "UNSET", 1: "OK", 2: "ERROR"}
    kind = {1: "INTERNAL", 3: "CLIENT"}
    for s in sorted(spans, key=lambda s: s["startTimeUnixNano"]):
        yield {"trace_id": s["traceId"], "span_id": s["spanId"], "parent_id": s["parentSpanId"] or None,
               "name": s["name"], "span_kind": s["attributes"].get("openinference.span.kind"), "otel_kind": kind[s["kind"]],
               "scope": s["_scope"][0], "start_time": iso(s["startTimeUnixNano"]), "end_time": iso(s["endTimeUnixNano"]),
               "duration_ms": round((s["endTimeUnixNano"] - s["startTimeUnixNano"]) / 1e6, 3),
               "status_code": status[s["status"]["code"]], "attributes": s["attributes"],
               "events": [{"name": e["name"], "time": iso(e["timeUnixNano"])} for e in s["events"]]}


def to_tree(tid, spans):
    kids = {}
    for s in spans:
        kids.setdefault(s["parentSpanId"], []).append(s)
    for v in kids.values():
        v.sort(key=lambda s: s["startTimeUnixNano"])
    t0 = min(s["startTimeUnixNano"] for s in spans)
    counts = {}
    for s in spans:
        k = s["attributes"].get("openinference.span.kind", "(none)")
        counts[k] = counts.get(k, 0) + 1
    lines = [f"Trace {tid}  trace_id={spans[0]['traceId']}",
             f"{len(spans)} spans: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), ""]

    def summary(s):
        a = s["attributes"]
        bits = []
        if "tool.name" in a:
            arg = json.loads(a["input.value"])
            bits.append(arg.get("filePath") or arg.get("path") or arg.get("command", "").split("\n")[0][:60])
        if "llm.token_count.total" in a:
            bits.append(f"{a['llm.model_name']} tokens={a['llm.token_count.prompt']}+{a['llm.token_count.completion']}")
            if "llm.output_messages.0.message.tool_calls.0.tool_call.function.name" in a:
                bits.append("-> " + a["llm.output_messages.0.message.tool_calls.0.tool_call.function.name"])
        if "http.response.status_code" in a:
            bits.append(str(a["http.response.status_code"]))
        if "process.exit.code" in a:
            bits.append(f"exit={a['process.exit.code']}")
        if "skill.name" in a:
            bits.append(a["skill.name"])
        return "  " + " ".join(bits) if bits else ""

    def walk(s, depth):
        a = s["attributes"]
        kind = a.get("openinference.span.kind", "")
        st = {0: "", 1: "", 2: " ERROR"}[s["status"]["code"]]
        off = (s["startTimeUnixNano"] - t0) / 1e6
        dur = (s["endTimeUnixNano"] - s["startTimeUnixNano"]) / 1e6
        lines.append(f"{off:9.0f}ms {'  ' * depth}{s['name']}" + (f" [{kind}]" if kind else "") +
                     f" {dur:.0f}ms{st}{summary(s)}")
        for c in kids.get(s["spanId"], []):
            walk(c, depth + 1)

    for r in kids.get("", []):
        walk(r, 0)
    return "\n".join(lines) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    for p in sorted((ROOT / "traces").glob("T*.jsonl")):
        tid = p.stem
        steps = [json.loads(l) for l in p.open()]
        spans = Builder(tid, steps).build()
        (OUT / f"{tid}.otlp.json").write_text(json.dumps(to_otlp(spans), indent=1, ensure_ascii=False) + "\n")
        with open(OUT / f"{tid}.spans.jsonl", "w") as f:
            for row in to_flat(spans):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        (OUT / f"{tid}.tree.txt").write_text(to_tree(tid, spans))
    print(f"built {len(list(OUT.glob('*.otlp.json')))} OTel traces")


if __name__ == "__main__":
    main()
