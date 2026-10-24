"""LLM client: Anthropic native, OpenAI-compatible (incl. Azure), and Plan Bridge.

Messages are kept in a canonical OpenAI-ish format and converted per API style,
so you can switch providers/models mid-conversation. Streaming for both styles.

Resilience (the lifeline):
  * network errors, 429s and 5xxs are retried with exponential backoff (Retry-After honored)
  * every failure is classified (auth · not_found · rate_limit · overloaded · network …) and
    carries a plain-English hint with the provider's docs URL
  * a rejected model name is auto-corrected against the live model list
  * when a provider is truly dead for this session, the client walks the fallback ladder
    (other keys → local servers → keyless free) and keeps going
"""
import json
import re
import time

import requests

from .config import MODEL_FALLBACKS, PROVIDERS, api_key_for, price_for, resolve_model
from .ui import dim


class LLMError(Exception):
    def __init__(self, msg, kind="unknown", status=None, provider="", model="", hint=""):
        super().__init__(msg)
        self.kind = kind
        self.status = status
        self.provider = provider
        self.model = model
        self.hint = hint

    def pretty(self):
        head = f"[{self.kind}] {self}"
        return head + (f"\n  → {self.hint}" if self.hint else "")


CONTEXT_WINDOWS = [("claude", 200_000), ("gpt-5", 400_000), ("gpt-4.1", 1_000_000), ("gpt-4o", 128_000),
                   ("o3", 200_000), ("o4", 200_000), ("gemini", 1_000_000), ("grok-4", 256_000),
                   ("grok", 131_072), ("deepseek", 128_000), ("kimi", 256_000), ("qwen3", 128_000),
                   ("llama", 128_000), ("devstral", 128_000), ("mistral", 128_000)]

_NET_EXC = (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError)


def context_window(model):
    m = (model or "").lower()
    for prefix, n in CONTEXT_WINDOWS:
        if prefix in m:
            return n
    return 128_000


class LLMClient:
    RETRY_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 529}
    MAX_PROVIDER_SWITCHES = 4

    def __init__(self, cfg):
        self.cfg = cfg
        self.total_in = 0
        self.total_out = 0
        self.total_cost = 0.0
        self.cost_known = True
        self.last_input_tokens = 0
        self.calls = 0
        self._plan = None
        self.allow_fallback = True
        self.on_fallback = None          # callable(note) — the UI shows what happened
        self.fallback_notes = []
        self.switched_from = None        # (provider, model) we started the session with
        self._corrected = {}             # provider -> set of model names already tried
        self._good = None                # (provider, model) last remembered as working
        self.auto_login = True           # plan CLI not signed in → open its sign-in
        self._login_tried = set()        # plan providers we already opened a sign-in for

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

    # -- the resilient entry point --------------------------------------------

    def chat(self, system, messages, tools=None, on_text=None):
        """Returns {"content": str, "tool_calls": [{"id","name","arguments"}]}.
        on_text(delta) is called as text streams in (when streaming is on).
        Walks the fallback ladder when the provider is unusable (unless allow_fallback is False)."""
        self.calls += 1
        switches = 0
        tried = set()
        while True:
            try:
                resp = self._chat_once(system, messages, tools, on_text)
                self._remember_good()
                return resp
            except LLMError as e:
                fb = self.cfg.get("fallbacks", "auto")
                if not self.allow_fallback or fb is False or fb == "off":
                    raise
                if e.kind == "not_found" and self._autocorrect_model(e):
                    continue
                tried.add(self.provider)
                if switches >= self.MAX_PROVIDER_SWITCHES:
                    raise
                from . import lifeline
                cands = lifeline.ladder(self.cfg, exclude=tried)
                if not cands:
                    e.hint = (e.hint + "\n  → nothing else is reachable: " if e.hint else "") + lifeline.playbook(self.cfg, e)
                    raise e
                np_, nm = cands[0]
                self._switch(np_, nm, reason=e)
                switches += 1

    def _chat_once(self, system, messages, tools, on_text):
        if self.api_style == "plan":
            from .plans import PlanAuthError, PlanClient
            if self._plan is None or self._plan.provider != self.provider:
                self._plan = PlanClient(self.cfg, self.provider)
            try:
                try:
                    resp = self._plan.chat(system, messages, on_text=on_text)
                except PlanAuthError:
                    if not self._plan_login():
                        raise
                    resp = self._plan.chat(system, messages, on_text=on_text)
            except PlanAuthError as e:
                from .plans import AUTH_ARGS
                cli = self._plan.cli or self.provider
                cmd = " ".join([cli] + AUTH_ARGS.get(cli, (None, []))[1])
                raise LLMError(str(e), kind="auth", provider=self.provider,
                               hint=f"sign in with /login (or run `{cmd}` in a terminal), then try again")
            except RuntimeError as e:
                raise LLMError(str(e), kind="network", provider=self.provider, hint=str(e))
            self._track(resp.get("usage_in", 0), resp.get("usage_out", 0), cost=resp.get("cost"))
            return {"content": resp["content"], "tool_calls": []}
        stream = bool(self.cfg.get("stream", True) and on_text)
        if self.api_style == "anthropic":
            return self._chat_anthropic(system, messages, tools, on_text if stream else None)
        return self._chat_openai(system, messages, tools, on_text if stream else None)

    def _plan_login(self):
        """The plan CLI isn't signed in: open its sign-in once per provider per session. True if it worked."""
        if not self.auto_login or self.provider in self._login_tried:
            return False
        self._login_tried.add(self.provider)
        from . import plans, state
        app = state.app()
        ui = app.ui if app else None
        cli = plans.PLAN_CLIS.get(self.provider, (self.provider,))[0]
        web = getattr(ui, "name", "") == "web"
        msg = (f"  🔑 {cli} isn't signed in — opening its sign-in"
               + (" in a new window (finish it there, then come back)" if web else "") + "…")
        from .ui import Spinner
        Spinner.stop_current()
        if ui:
            ui.notice(msg, "warn")
        ok, note = plans.login(self.provider, inline=False if web else None)
        if ui:
            ui.notice(("  ✓ " if ok else "  ✗ ") + note, "ok" if ok else "error")
        return bool(ok)

    def _notify(self, note):
        self.fallback_notes.append(note)
        if self.on_fallback:
            try:
                self.on_fallback(note)
            except Exception:
                pass

    def _autocorrect_model(self, err):
        """The provider doesn't know this model: find the right name from the live list, else try the
        provider's known fallbacks. Returns True if a new model was set."""
        from . import lifeline
        tried = self._corrected.setdefault(self.provider, set())
        tried.add(self.model)
        available = []
        try:
            available = [m for m in self.list_models() if m]
        except LLMError:
            pass
        new = lifeline.correct_model(self.model, available, self.provider) if available else None
        if not new or new in tried:
            new = next((m for m in MODEL_FALLBACKS.get(self.provider, []) if m not in tried and (not available or m in available)), None)
        if not new:
            return False
        old = self.model
        self.cfg["model"] = new
        self._notify(f"model '{old}' isn't available on {self.provider} → using '{new}' instead")
        return True

    def _switch(self, provider, model, reason=None):
        if self.switched_from is None:
            self.switched_from = (self.provider, self.cfg.get("model", ""))
            self.cfg["_fallback_from"] = self.provider
            self.cfg["_fallback_model"] = self.cfg.get("model", "")
        why = f"{reason.kind}: {str(reason)[:120]}" if reason is not None else "unusable"
        self.cfg["provider"], self.cfg["model"] = provider, model or ""
        self._plan = None
        self._notify(f"{self.switched_from[0] if self.switched_from else '?'} failed ({why}) → falling back to "
                     f"{provider}{(' / ' + model) if model else ''}" + (f"\n  → {reason.hint}" if reason is not None and reason.hint else ""))

    def _remember_good(self):
        key = (self.provider, self.cfg.get("model", ""))
        if self._good != key and self.api_style != "plan":
            self._good = key
            from . import lifeline
            lifeline.remember_good(self.cfg, *key)

    # -- parameter self-healing ---------------------------------------------------
    # Providers retire request parameters (Anthropic 4.7+/5.x: temperature/top_p/top_k; OpenAI reasoning
    # models: temperature, max_tokens→max_completion_tokens; some local servers: stream_options).
    # Instead of dying on the 400, drop the offending parameter, retry, and remember it for this model.

    _REJECT_WORDS = ("deprecated", "not supported", "unsupported", "unknown", "unrecognized", "not allowed",
                     "does not support", "cannot be used", "not permitted", "removed", "extra inputs", "invalid")
    _NEVER_DROP = ("model", "messages", "system", "tools", "stream")

    def _quirks(self):
        return self.cfg.setdefault("param_quirks", {}).setdefault(self.model, [])

    def _apply_quirks(self, payload):
        for p in list(self._quirks()):
            if p == "max_tokens" and "max_tokens" in payload and self.api_style != "anthropic":
                payload["max_completion_tokens"] = payload.pop("max_tokens")
            else:
                payload.pop(p, None)
        return payload

    def _offending_param(self, message, payload):
        low = (message or "").lower()
        if not any(w in low for w in self._REJECT_WORDS):
            return None
        for key in payload:
            if key in self._NEVER_DROP:
                continue
            if re.search(r"(?<![a-z_])" + re.escape(key.lower()) + r"(?![a-z_])", low):
                return key
        return None

    def _remember_quirk(self, param):
        from .paths import CONFIG_FILE
        q = self._quirks()
        if param not in q:
            q.append(param)
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
            data.setdefault("param_quirks", {})[self.model] = list(q)
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _post_healing(self, url, headers, payload, stream=False):
        self._apply_quirks(payload)
        for _ in range(4):
            try:
                return self._post(url, headers, payload, stream=stream)
            except LLMError as e:
                if e.status != 400:
                    raise
                param = self._offending_param(str(e), payload)
                if not param:
                    raise
                if param == "max_tokens" and self.api_style != "anthropic":
                    payload["max_completion_tokens"] = payload.pop("max_tokens")
                else:
                    payload.pop(param, None)
                self._remember_quirk(param)
                self._notify(f"{self.provider} rejected `{param}` for {self.model} — dropped it and retried (remembered for this model)")
        raise LLMError(f"{self.provider} kept rejecting the request shape", kind="bad_request", provider=self.provider,
                       model=self.model)

    # -- HTTP with retries ------------------------------------------------------

    def _post(self, url, headers, payload, stream=False):
        from . import lifeline
        retries = max(0, int(self.cfg.get("retries", 3) or 0))
        last_err = None
        for attempt in range(retries + 1):
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=(15, 600), stream=stream)
            except _NET_EXC as e:
                last_err = e
                if attempt < retries:
                    wait = 1.5 * (2 ** attempt)
                    print(dim(f"\r  can't reach {self.provider} ({type(e).__name__}), retrying in {wait:.0f}s…"))
                    time.sleep(wait)
                    continue
                raise LLMError(f"Could not reach {url} ({type(e).__name__})", kind="network", provider=self.provider,
                               model=self.model, hint=lifeline.hint("network", self.provider, self.model))
            if r.status_code < 400:
                return r
            body = r.text[:1200]
            kind = lifeline.classify(r.status_code, body)
            retryable = r.status_code in self.RETRY_CODES and kind not in ("auth", "not_found") and \
                not any(s in body.lower() for s in ("insufficient_quota", "billing", "exceeded your current quota"))
            if retryable and attempt < retries:
                ra = r.headers.get("Retry-After")
                try:
                    wait = min(20.0, float(ra)) if ra else 2.0 * (attempt + 1)
                except ValueError:
                    wait = 2.0 * (attempt + 1)
                last_err = f"HTTP {r.status_code}"
                print(dim(f"\r  {self.provider}: {last_err}, retrying in {wait:.0f}s…"))
                time.sleep(wait)
                continue
            detail = body
            try:
                j = r.json()
                detail = json.dumps(j.get("error", j), indent=2)[:800]
            except Exception:
                pass
            raise LLMError(f"HTTP {r.status_code} from {self.provider}: {detail}", kind=kind, status=r.status_code,
                           provider=self.provider, model=self.model,
                           hint=lifeline.hint(kind, self.provider, self.model, detail))
        raise LLMError(f"gave up after retries ({last_err})", kind="overloaded", provider=self.provider, model=self.model,
                       hint=lifeline.hint("overloaded", self.provider, self.model))

    def _sse(self, resp):
        """Yield parsed JSON objects from an SSE stream; network drops become LLMError(network)."""
        try:
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
        except _NET_EXC as e:
            from . import lifeline
            raise LLMError(f"stream from {self.provider} was cut off ({type(e).__name__})", kind="network",
                           provider=self.provider, model=self.model, hint=lifeline.hint("network", self.provider, self.model))

    # ---- anthropic ----
    @staticmethod
    def _anthropic_accepts_sampling(model):
        """Claude 4.7, 4.8 and the 5 family reject temperature/top_p/top_k (400). Only send sampling
        params to the models that still take them (3.x, 4, 4.1, 4.5, 4.6)."""
        m = (model or "").lower()
        if re.search(r"fable|mythos", m):
            return False
        if m.startswith("claude-3"):
            return True
        mm = re.search(r"claude-(?:opus|sonnet|haiku)-(\d+)(?:-(\d{1,2})(?!\d))?", m)
        if not mm:
            return False
        major = int(mm.group(1))
        minor = int(mm.group(2)) if mm.group(2) else 0
        return major < 4 or (major == 4 and minor <= 6)

    def sampling(self):
        """Effective sampling params for the current provider/model: global defaults, then per-provider,
        then per-model overrides (config `sampling`). None means 'let the provider decide'."""
        s = self.cfg.get("sampling") or {}
        out = {"temperature": s.get("temperature", self.cfg.get("temperature")), "top_p": s.get("top_p"), "top_k": s.get("top_k")}
        overrides = s.get("overrides") or {}
        for key in (self.provider, self.model, f"{self.provider}/{self.model}"):
            for k, v in (overrides.get(key) or {}).items():
                if k in out:
                    out[k] = v
        return {k: v for k, v in out.items() if v is not None}

    def _explicit_model_override(self):
        """Did the user set sampling for THIS model on purpose? Then we send it even past the model gate
        (and let parameter self-healing drop it if the provider still says no)."""
        overrides = (self.cfg.get("sampling") or {}).get("overrides") or {}
        return any(overrides.get(k) for k in (self.model, f"{self.provider}/{self.model}"))

    def sampling_gate(self):
        """Why sampling params are withheld for the current provider/model, or None when they're sent.
        Single source of truth for the request builders and for `/sampling`."""
        if self.api_style == "plan":
            return "plan providers take no sampling settings (the vendor CLI decides)"
        if self._explicit_model_override():
            return None
        if self.api_style == "anthropic" and not self._anthropic_accepts_sampling(self.model):
            return "Claude 4.7+/5.x reject temperature/top_p/top_k"
        if self.provider == "openai" and self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            return "OpenAI reasoning models reject temperature/top_p/top_k"
        return None

    def _chat_anthropic(self, system, messages, tools, on_text):
        payload = {"model": self.model, "max_tokens": self.cfg["max_tokens"], "system": system,
                   "messages": self._to_anthropic(messages)}
        if self.sampling_gate() is None:
            payload.update(self.sampling())
        if tools:
            payload["tools"] = [{"name": t["name"], "description": t["description"],
                                 "input_schema": t["input_schema"]} for t in tools]
        headers = {"x-api-key": self.api_key(), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = f"{self.base_url}/v1/messages"
        if not on_text:
            return self._parse_anthropic(self._post_healing(url, headers, payload).json())
        payload["stream"] = True
        r = self._post_healing(url, headers, payload, stream=True)
        if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
            parsed = self._parse_anthropic(r.json())
            if parsed["content"]:
                on_text(parsed["content"])
            return parsed
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
                err = ev.get("error") or {}
                etype = str(err.get("type", ""))
                kind = {"overloaded_error": "overloaded", "rate_limit_error": "rate_limit", "not_found_error": "not_found",
                        "authentication_error": "auth", "permission_error": "auth", "api_error": "overloaded"}.get(etype, "unknown")
                from . import lifeline
                raise LLMError(f"stream error from {self.provider}: {json.dumps(err)[:300]}", kind=kind, provider=self.provider,
                               model=self.model, hint=lifeline.hint(kind, self.provider, self.model, json.dumps(err)))
        self._track(tin, tout)
        return {"content": "".join(text_parts), "tool_calls": tool_calls}

    def _parse_anthropic(self, data):
        text_parts, tool_calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_calls.append({"id": block["id"], "name": block["name"], "arguments": block.get("input") or {}})
        usage = data.get("usage", {})
        self._track(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        return {"content": "\n".join(text_parts), "tool_calls": tool_calls}

    # ---- openai-compatible ----
    def _openai_headers_url(self):
        if self.api_style == "azure":
            if not self.base_url:
                raise LLMError("azure needs a base URL like https://RESOURCE.openai.azure.com/openai/deployments/DEPLOYMENT — "
                               "set it with: /config base_urls.azure <url> (or chode setup)", kind="bad_request", provider="azure")
            headers = {"api-key": self.api_key(), "Content-Type": "application/json"}
            url = f"{self.base_url}/chat/completions?api-version={self.cfg.get('azure_api_version', '2024-06-01')}"
        else:
            headers = {"Content-Type": "application/json"}
            if self.provider not in ("pollinations",) or api_key_for(self.cfg, self.provider):
                headers["Authorization"] = f"Bearer {self.api_key()}"
            if self.provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/chchchadzilla/chode"
                headers["X-Title"] = "CHODE"
            url = f"{self.base_url}/chat/completions"
        return headers, url

    def _chat_openai(self, system, messages, tools, on_text):
        payload = {"model": self.model, "messages": self._to_openai(messages, system)}
        if self.provider == "openai" and (self.model.startswith(("gpt-5", "o1", "o3", "o4"))):
            payload["max_completion_tokens"] = self.cfg["max_tokens"]
        else:
            payload["max_tokens"] = self.cfg["max_tokens"]
        if self.sampling_gate() is None:
            payload.update(self.sampling())
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}} for t in tools]
        headers, url = self._openai_headers_url()
        if not on_text:
            return self._parse_openai(self._post_healing(url, headers, payload).json())
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        r = self._post_healing(url, headers, payload, stream=True)
        if "text/event-stream" not in (r.headers.get("Content-Type") or ""):
            parsed = self._parse_openai(r.json())
            if parsed["content"]:
                on_text(parsed["content"])
            return parsed
        text_parts, tools_acc, usage = [], {}, {}
        for chunk in self._sse(r):
            if chunk.get("error"):
                from . import lifeline
                err = chunk["error"]
                kind = lifeline.classify(None, json.dumps(err))
                raise LLMError(f"stream error from {self.provider}: {json.dumps(err)[:300]}", kind=kind, provider=self.provider,
                               model=self.model, hint=lifeline.hint(kind, self.provider, self.model, json.dumps(err)))
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
        if not tin:
            tin = sum(len(m.get("content") or "") for m in messages) // 4 + len(system) // 4
            tout = len("".join(text_parts)) // 4
        self._track(tin, tout)
        return {"content": "".join(text_parts), "tool_calls": tool_calls}

    def _parse_openai(self, data):
        if not isinstance(data, dict) or not data.get("choices"):
            from . import lifeline
            body = json.dumps(data)[:500]
            kind = lifeline.classify(None, body) if isinstance(data, dict) and data.get("error") else "unknown"
            raise LLMError(f"No choices in response from {self.provider}: {body}", kind=kind, provider=self.provider,
                           model=self.model, hint=lifeline.hint(kind, self.provider, self.model, body))
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
        if self.provider in ("ollama", "lmstudio", "local", "pollinations"):
            return line + "   cost: $0 (free)"
        if self.total_cost and self.cost_known:
            line += f"   est. cost: ${self.total_cost:.4f}"
        elif self.total_cost:
            line += f"   est. cost: ≥${self.total_cost:.4f} (some models unpriced)"
        else:
            line += "   est. cost: unknown for this model (or free/local)"
        return line

    # -- discovery ----------------------------------------------------------------

    def list_models(self, provider=None):
        """Model ids the provider advertises. Raises LLMError (classified) when it can't."""
        from . import lifeline
        prov = provider or self.provider
        style, default_url, key_env, _ = PROVIDERS[prov]
        base = (self.cfg.get("base_urls", {}).get(prov) or default_url).rstrip("/")
        key = api_key_for(self.cfg, prov) or "not-needed"
        if style == "plan":
            from .plans import PlanClient
            return PlanClient(self.cfg, prov).list_models()
        if style == "anthropic":
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            url = f"{base}/v1/models?limit=100"
        elif style == "azure":
            headers = {"api-key": key}
            url = f"{base}/models?api-version={self.cfg.get('azure_api_version', '2024-06-01')}"
        elif prov == "pollinations":
            headers = {}
            url = base.rsplit("/openai", 1)[0] + "/models"
        else:
            headers = {"Authorization": f"Bearer {key}"}
            url = f"{base}/models"
        try:
            r = requests.get(url, headers=headers, timeout=20)
        except _NET_EXC as e:
            raise LLMError(f"could not reach {prov} to list models ({type(e).__name__})", kind="network", provider=prov,
                           hint=lifeline.hint("network", prov))
        if r.status_code >= 400:
            kind = lifeline.classify(r.status_code, r.text[:500])
            raise LLMError(f"HTTP {r.status_code} listing {prov} models: {r.text[:300]}", kind=kind, status=r.status_code,
                           provider=prov, hint=lifeline.hint(kind, prov, "", r.text[:200]))
        try:
            data = r.json()
        except Exception:
            raise LLMError(f"{prov} returned a non-JSON model list", kind="unknown", provider=prov)
        if isinstance(data, list):
            items = data
        else:
            items = data.get("data") or data.get("models") or []
        out = []
        for m in items:
            if isinstance(m, str):
                out.append(m)
            elif isinstance(m, dict):
                out.append(m.get("id") or m.get("name") or m.get("model") or "")
        return [m for m in out if m]

    def probe(self):
        """A one-token round trip. Returns (ok, LLMError_or_None). Never falls back."""
        old = self.allow_fallback
        self.allow_fallback = False
        old_max = self.cfg["max_tokens"]
        self.cfg["max_tokens"] = 16
        try:
            self.chat("Reply with exactly: pong", [{"role": "user", "content": "ping"}], tools=None)
            return True, None
        except LLMError as e:
            return False, e
        finally:
            self.allow_fallback = old
            self.cfg["max_tokens"] = old_max

    def embed(self, texts, model=None):
        """Embeddings via an OpenAI-compatible /embeddings endpoint (OpenAI, Ollama, LM Studio…)."""
        if self.api_style not in ("openai", "azure"):
            raise LLMError(f"provider '{self.provider}' has no embeddings endpoint — set rag.embedding_model and use an "
                           f"openai-style provider, or leave embeddings off", kind="bad_request", provider=self.provider)
        model = model or self.cfg.get("rag", {}).get("embedding_model") or (
            "text-embedding-3-small" if self.provider == "openai" else "nomic-embed-text")
        headers, _ = self._openai_headers_url()
        url = f"{self.base_url}/embeddings"
        r = self._post(url, headers, {"model": model, "input": texts})
        data = r.json()
        return [d["embedding"] for d in sorted(data.get("data", []), key=lambda d: d.get("index", 0))]
