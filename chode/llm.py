"""LLM client: Anthropic native, OpenAI-compatible (incl. Azure), and Plan Bridge.

Messages are kept in a canonical OpenAI-ish format and converted per API style,
so you can switch providers/models mid-conversation. Streaming for both styles.
"""
import json
import time

import requests

from .config import PROVIDERS, api_key_for, price_for, resolve_model
from .ui import dim


class LLMError(Exception):
    pass


CONTEXT_WINDOWS = [("claude", 200_000), ("gpt-5", 400_000), ("gpt-4.1", 1_000_000), ("gpt-4o", 128_000),
                   ("o3", 200_000), ("o4", 200_000), ("gemini", 1_000_000), ("grok-4", 256_000),
                   ("grok", 131_072), ("deepseek", 128_000), ("kimi", 256_000), ("qwen3", 128_000),
                   ("llama", 128_000), ("devstral", 128_000), ("mistral", 128_000)]


def context_window(model):
    m = (model or "").lower()
    for prefix, n in CONTEXT_WINDOWS:
        if prefix in m:
            return n
    return 128_000


class LLMClient:
    RETRY_CODES = {408, 409, 429, 500, 502, 503, 504, 529}

    def __init__(self, cfg):
        self.cfg = cfg
        self.total_in = 0
        self.total_out = 0
        self.total_cost = 0.0
        self.cost_known = True
        self.last_input_tokens = 0
        self.calls = 0
        self._plan = None

    @property
    def provider(self): return self.cfg["provider"]
    @property
    def api_style(self): return PROVIDERS[self.provider][0]
    @property
    def base_url(self):
        return (self.cfg.get("base_urls", {}).get(self.provider) or PROVIDERS[self.provider][1]).rstrip("/")
    @property
    def model(self): return resolve_model(self.cfg)

    def api_key(self):
        return api_key_for(self.cfg, self.provider) or "not-needed"

    def context_pct(self):
        return min(100, int(100 * self.last_input_tokens / context_window(self.model)))

    # -- conversions ---------------------------------------------------------

    @staticmethod
    def _to_anthropic(messages):
        out = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": [{"type": "text", "text": m["content"] or " "}]})
            elif m["role"] == "assistant":
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": " "}]})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                         "content": [{"type": "text", "text": m["content"] or "(empty)"}]}
                if out and out[-1]["role"] == "user" and any(b.get("type") == "tool_result" for b in out[-1]["content"]):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        # Anthropic requires alternating roles starting with user; merge adjacent users.
        merged = []
        for m in out:
            if merged and merged[-1]["role"] == m["role"] == "user":
                merged[-1]["content"].extend(m["content"])
            else:
                merged.append(m)
        return merged

    @staticmethod
    def _to_openai(messages, system):
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("content") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": tc["id"], "type": "function",
                                          "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                                         for tc in m["tool_calls"]]
                out.append(msg)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"] or "(empty)"})
            else:
                out.append({"role": "user", "content": m["content"]})
        return out

    # -- calls ----------------------------------------------------------------

    def chat(self, system, messages, tools=None, on_text=None):
        """Returns {"content": str, "tool_calls": [{"id","name","arguments"}]}.
        on_text(delta) is called as text streams in (when streaming is on)."""
        self.calls += 1
        if self.api_style == "plan":
            from .plans import PlanClient
            if self._plan is None or self._plan.provider != self.provider:
                self._plan = PlanClient(self.cfg, self.provider)
            resp = self._plan.chat(system, messages, on_text=on_text)
            self._track(resp.get("usage_in", 0), resp.get("usage_out", 0), cost=resp.get("cost"))
            return {"content": resp["content"], "tool_calls": []}
        stream = bool(self.cfg.get("stream", True) and on_text)
        if self.api_style == "anthropic":
            return self._chat_anthropic(system, messages, tools, on_text if stream else None)
        return self._chat_openai(system, messages, tools, on_text if stream else None)

    def _post(self, url, headers, payload, stream=False):
        last_err = None
        for attempt in range(4):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=600, stream=stream)
            except requests.exceptions.ConnectionError:
                raise LLMError(f"Could not connect to {url} — is the server running? (see /config)")
            except requests.exceptions.Timeout:
                raise LLMError("Request timed out.")
            if r.status_code in self.RETRY_CODES and attempt < 3:
                wait = 2 * (attempt + 1)
                last_err = f"HTTP {r.status_code}"
                print(dim(f"\r  {last_err}, retrying in {wait}s…"))
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                detail = r.text[:800]
                try:
                    j = r.json()
                    detail = json.dumps(j.get("error", j), indent=2)[:800]
                except Exception:
                    pass
                raise LLMError(f"HTTP {r.status_code} from {self.provider}: {detail}")
            return r
        raise LLMError(f"gave up after retries ({last_err})")

    @staticmethod
    def _sse(resp):
        """Yield parsed JSON objects from an SSE stream."""
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    continue

    # ---- anthropic ----
    def _chat_anthropic(self, system, messages, tools, on_text):
        payload = {"model": self.model, "max_tokens": self.cfg["max_tokens"],
                   "temperature": self.cfg["temperature"], "system": system,
                   "messages": self._to_anthropic(messages)}
        if tools:
            payload["tools"] = [{"name": t["name"], "description": t["description"],
                                 "input_schema": t["input_schema"]} for t in tools]
        headers = {"x-api-key": self.api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = f"{self.base_url}/v1/messages"
        if not on_text:
            data = self._post(url, headers, payload).json()
            text_parts, tool_calls = [], []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({"id": block["id"], "name": block["name"], "arguments": block.get("input") or {}})
            usage = data.get("usage", {})
            self._track(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            return {"content": "\n".join(text_parts), "tool_calls": tool_calls}
        payload["stream"] = True
        r = self._post(url, headers, payload, stream=True)
        if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
            # server ignored `stream` and answered with plain JSON — handle it gracefully
            data = r.json()
            text_parts, tool_calls = [], []
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    tool_calls.append({"id": block["id"], "name": block["name"], "arguments": block.get("input") or {}})
            usage = data.get("usage", {})
            self._track(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
            if text_parts:
                on_text("".join(text_parts))
            return {"content": "\n".join(text_parts), "tool_calls": tool_calls}
        text_parts, tool_calls = [], []
        cur_tool, cur_json = None, []
        tin = tout = 0
        for ev in self._sse(r):
            t = ev.get("type")
            if t == "message_start":
                tin = (ev.get("message", {}).get("usage") or {}).get("input_tokens", 0)
            elif t == "content_block_start":
                cb = ev.get("content_block", {})
                if cb.get("type") == "tool_use":
                    cur_tool, cur_json = {"id": cb["id"], "name": cb["name"], "arguments": {}}, []
                elif cb.get("type") == "text" and cb.get("text"):
                    text_parts.append(cb["text"]); on_text(cb["text"])
            elif t == "content_block_delta":
                d = ev.get("delta", {})
                if d.get("type") == "text_delta":
                    text_parts.append(d["text"]); on_text(d["text"])
                elif d.get("type") == "input_json_delta":
                    cur_json.append(d.get("partial_json", ""))
            elif t == "content_block_stop":
                if cur_tool is not None:
                    raw = "".join(cur_json).strip() or "{}"
                    try:
                        cur_tool["arguments"] = json.loads(raw)
                    except json.JSONDecodeError:
                        cur_tool["arguments"] = {"_raw": raw}
                    tool_calls.append(cur_tool)
                    cur_tool, cur_json = None, []
            elif t == "message_delta":
                tout = (ev.get("usage") or {}).get("output_tokens", tout)
            elif t == "error":
                raise LLMError(f"stream error: {json.dumps(ev.get('error'))[:400]}")
        self._track(tin, tout)
        return {"content": "".join(text_parts), "tool_calls": tool_calls}

    # ---- openai-compatible ----
    def _openai_headers_url(self):
        if self.api_style == "azure":
            if not self.base_url:
                raise LLMError("azure needs a base URL like https://RESOURCE.openai.azure.com/openai/deployments/DEPLOYMENT — set it with: /config base_urls.azure <url> (or chode setup)")
            headers = {"api-key": self.api_key(), "Content-Type": "application/json"}
            url = f"{self.base_url}/chat/completions?api-version={self.cfg.get('azure_api_version', '2024-06-01')}"
        else:
            headers = {"Authorization": f"Bearer {self.api_key()}", "Content-Type": "application/json"}
            if self.provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/chchchadzilla/chode"
                headers["X-Title"] = "CHODE"
            url = f"{self.base_url}/chat/completions"
        return headers, url

    def _chat_openai(self, system, messages, tools, on_text):
        payload = {"model": self.model, "messages": self._to_openai(messages, system)}
        # newer OpenAI reasoning models reject max_tokens/temperature; send the modern key
        if self.provider == "openai" and (self.model.startswith(("gpt-5", "o1", "o3", "o4"))):
            payload["max_completion_tokens"] = self.cfg["max_tokens"]
        else:
            payload["max_tokens"] = self.cfg["max_tokens"]
            payload["temperature"] = self.cfg["temperature"]
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        headers, url = self._openai_headers_url()
        if not on_text:
            data = self._post(url, headers, payload).json()
            return self._parse_openai(data)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        try:
            r = self._post(url, headers, payload, stream=True)
        except LLMError as e:
            if "stream_options" in str(e):
                payload.pop("stream_options", None)
                r = self._post(url, headers, payload, stream=True)
            else:
                raise
        if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
            parsed = self._parse_openai(r.json())
            if parsed["content"]:
                on_text(parsed["content"])
            return parsed
        text_parts, tools_acc, usage = [], {}, {}
        for chunk in self._sse(r):
            if chunk.get("usage"):
                usage = chunk["usage"]
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                if delta.get("content"):
                    text_parts.append(delta["content"]); on_text(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tools_acc.setdefault(idx, {"id": tc.get("id") or "", "name": "", "args": []})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["args"].append(fn["arguments"])
        tool_calls = []
        for idx in sorted(tools_acc):
            slot = tools_acc[idx]
            raw = "".join(slot["args"]).strip() or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"_raw": raw}
            tool_calls.append({"id": slot["id"] or f"call_{idx}", "name": slot["name"], "arguments": args})
        tin = usage.get("prompt_tokens", 0)
        tout = usage.get("completion_tokens", 0)
        if not tin:  # server didn't report usage: rough estimate so the status line isn't blank
            tin = sum(len(m.get("content") or "") for m in messages) // 4 + len(system) // 4
            tout = len("".join(text_parts)) // 4
        self._track(tin, tout)
        return {"content": "".join(text_parts), "tool_calls": tool_calls}

    def _parse_openai(self, data):
        if not data.get("choices"):
            raise LLMError(f"No choices in response: {json.dumps(data)[:500]}")
        msg = data["choices"][0].get("message") or {}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                args = {"_raw": raw}
            tool_calls.append({"id": tc.get("id") or f"call_{len(tool_calls)}", "name": fn.get("name", ""), "arguments": args})
        usage = data.get("usage") or {}
        self._track(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        return {"content": msg.get("content") or "", "tool_calls": tool_calls}

    def _track(self, tin, tout, cost=None):
        self.total_in += tin or 0
        self.total_out += tout or 0
        if tin:
            self.last_input_tokens = tin
        if cost is not None:
            self.total_cost += cost
            return
        p = price_for(self.model)
        if p:
            self.total_cost += (tin or 0) / 1e6 * p[0] + (tout or 0) / 1e6 * p[1]
        elif (tin or tout) and self.api_style != "plan":
            self.cost_known = False

    def cost_line(self):
        line = f"tokens: {self.total_in:,} in / {self.total_out:,} out"
        if self.api_style == "plan":
            return line + "   cost: covered by your subscription"
        if self.total_cost and self.cost_known:
            line += f"   est. cost: ${self.total_cost:.4f}"
        elif self.total_cost:
            line += f"   est. cost: ≥${self.total_cost:.4f} (some models unpriced)"
        else:
            line += "   est. cost: unknown for this model (or free/local)"
        return line

    def list_models(self):
        if self.api_style == "plan":
            from .plans import PlanClient
            return PlanClient(self.cfg, self.provider).list_models()
        if self.api_style == "anthropic":
            headers = {"x-api-key": self.api_key(), "anthropic-version": "2023-06-01"}
            url = f"{self.base_url}/v1/models"
        elif self.api_style == "azure":
            headers = {"api-key": self.api_key()}
            url = f"{self.base_url}/models?api-version={self.cfg.get('azure_api_version', '2024-06-01')}"
        else:
            headers = {"Authorization": f"Bearer {self.api_key()}"}
            url = f"{self.base_url}/models"
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or data.get("models") or []
            return [m.get("id") or m.get("name", "?") for m in items]
        except Exception as e:
            raise LLMError(f"Could not list models: {e}")

    def embed(self, texts, model=None):
        """Embeddings via an OpenAI-compatible /embeddings endpoint (OpenAI, Ollama, LM Studio…)."""
        if self.api_style not in ("openai", "azure"):
            raise LLMError(f"provider '{self.provider}' has no embeddings endpoint — set rag.embedding_model and use an openai-style provider, or leave embeddings off")
        model = model or self.cfg.get("rag", {}).get("embedding_model") or (
            "text-embedding-3-small" if self.provider == "openai" else "nomic-embed-text")
        headers, _ = self._openai_headers_url()
        url = f"{self.base_url}/embeddings"
        r = self._post(url, headers, {"model": model, "input": texts})
        data = r.json()
        return [d["embedding"] for d in sorted(data.get("data", []), key=lambda d: d.get("index", 0))]
