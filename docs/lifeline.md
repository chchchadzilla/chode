# The lifeline — CHODE never dies on a connection error

The worst first-run experience is a stack trace. CHODE's rule: **something always answers**, and
when it can't, you get a plain-English reason, a numbered list of fixes, and a `/fix` command
that does them for you.

## What happens when a request fails

```
request → network error / 429 / 5xx?   → retry with backoff (Retry-After honored), up to `retries` (3)
        → still failing → classify:  auth · not_found · rate_limit · overloaded · network · bad_request
        → not_found?   → fetch the provider's live model list, auto-correct the name, retry
        → anything else → walk the fallback ladder: next provider that can plausibly answer
        → ladder exhausted → error + hint + playbook, and the offer to run /fix
```

Every switch is announced in the session (`🪢 anthropic failed (auth: …) → falling back to groq / llama-3.3-70b-versatile`),
written to the ledger, and **never saved as your default** unless you say `/provider keep`.
What CHODE does remember automatically is `last_known_good`, which goes to the top of the ladder next time.

## The ladder (`chode lifeline`, `/lifeline`)

With `fallbacks: "auto"` (the default), in order:

1. the provider you configured, if it can plausibly work (key present / server running / keyless);
2. `last_known_good`;
3. any other provider with a key in your environment or config, best first:
   anthropic → openai → gemini → xai → groq → openrouter → deepseek → mistral → cerebras → together → moonshot → huggingface;
4. local servers that are **actually running**: Ollama (picks your best installed coder model), LM Studio, `local`;
5. the keyless free rung: `pollinations`.

Pin an order: `/config fallbacks '["groq","ollama:qwen2.5-coder:7b","pollinations"]'`. Turn it off: `/config fallbacks false`.

## Model names: what you type vs what the API wants

Two layers, both automatic:

1. **Normalization** (pure, no network, `config.normalize_model`): `anthropic/opus-5.5` → `claude-opus-5-5`,
   `Opus 5.5` → `claude-opus-5-5`, `gpt5 mini` → `gpt-5-mini`, `models/gemini-2.5-flash` → `gemini-2.5-flash`,
   `Grok 4` → `grok-4`. OpenRouter ids are left alone because `vendor/model` *is* its format. Applied when the config
   is loaded (so an old saved mistake is fixed), on `/model`, `/provider p m`, `/config model`, `chode --model`, in the
   wizard and in the fixer's `set_config model`.
2. **Live verification** (`lifeline.verify_model`): the name is looked up in the provider's `/models` list the moment
   you set it. Exact (case-insensitive) match → confirmed. Alias (`sonnet`) → the newest matching id. Typo → the closest
   real id, announced (`'mock-l' isn't a model local knows → using 'mock-1'`). Nothing close → kept, with a note that
   `/models` shows the list and CHODE will try again on first use. Can't reach the provider → kept, with the reason.
   It never guesses wildly: a totally unrelated name is not replaced.

At request time the same correction runs again on a `not_found` error (`correct_model` against the live list, newest
version wins, then newest date; then the provider's known-good `MODEL_FALLBACKS`).

## Request settings a model won't take

Providers retire parameters: Anthropic's 4.7+/5.x models reject `temperature`/`top_p`/`top_k` with a 400
("`temperature` is deprecated for this model"); OpenAI's reasoning models reject them and want `max_completion_tokens`.
Other models (OpenRouter, Ollama, Groq, Gemini, Claude ≤ 4.6) take them fine. CHODE:

- knows the known cases up front (`LLMClient.sampling_gate`) and doesn't send what will be rejected;
- learns the rest live: a 400 that names a payload field → drop it (or rename `max_tokens`), retry, and **remember it
  for that model** in `param_quirks` so it's never sent again;
- lets you get granular: `/sampling` shows exactly what's sent to the current model and why, and sets
  temperature / top_p / top_k globally, per provider, or per model. A per-model override is a deliberate "send it
  anyway" and clears a remembered rejection for that setting. See [sampling.md](sampling.md).

## The failure block

Every connection failure — in the wizard's connection test, `chode health`, and in a session — prints the same
`lifeline.what_now` block, keyed by the error kind:

```
WHAT HAPPENED                 one plain-English sentence about THIS error
WHAT CHODE ALREADY DID        retries · model-list matching · dropped settings · fallbacks
DO THIS NOW                   numbered, specific: the keys page + env var + key prefix for auth; the corrected name for
                              not_found; the setting to flip for a rejected parameter; `ollama serve` for a dead local server…
ANY OF THESE GETS YOU CODING  pollinations (no key) · Ollama (local, with the exact command for this machine) · a free key
IN UNDER 2 MINUTES
OR LET CHODE DO IT            /fix · chode fix
```

The old one-line "tip: run chode import" after a failed test is gone; the import tip only shows when the test passed.

## Startup guarantee

At boot CHODE checks the configured provider can plausibly answer (key present, server up). If not, it switches
to the best rung for the session and tells you why, instead of failing on your first message.

## `chode fix` / `/fix` — the connection doctor

A tiny agent that runs on whatever rung answers, with four tools and one job:

| tool | does |
|---|---|
| `list_models [provider]` | the provider's live model ids |
| `test_connection [provider] [model]` | one-token probe → OK, or the error kind + hint |
| `set_config key value` | provider · model (normalized + verified) · base_urls.* · fallbacks · stream · max_tokens · sampling.* — **never API keys** |
| `web_fetch` | read the provider's docs page when the model list isn't enough |

It follows the built-in `connection-doctor` skill: test → read the error kind → list models / read docs /
switch provider → test again → stop at the first OK → three lines of explanation. If literally nothing can answer,
it prints the manual playbook instead.

## Free rungs, honestly described

| rung | cost | needs | quality for tool-calling | caveats |
|---|---|---|---|---|
| Ollama (`qwen2.5-coder:7b`, `qwen3:8b`, …) | $0 | install + a 4–5 GB download, ~8 GB RAM | good | slower on CPU-only machines |
| `pollinations` | $0 | nothing — no key, no signup | basic but workable | community-run, rate-limited, may change without notice. Great for fixing your config, fine for small tasks |
| Gemini free tier | $0 | a Google account, 2 minutes | strong | daily request limits |
| Groq free tier | $0 | an account, 2 minutes | good, very fast | daily token limits |
| OpenRouter `:free` models | $0 | an account, 2 minutes | varies by model | shared rate limits |
| Mistral / Cerebras / Hugging Face free tiers | $0 | an account | good | limits vary |

The wizard's **"Just make it work (free)"** picks the best free rung available on your machine; **"Free key, 2 minutes"**
opens the signup page for you and only asks you to paste the key.

## Configuration

| key | default | |
|---|---|---|
| `fallbacks` | `"auto"` | `"auto"` · a list of `"provider"` / `"provider:model"` · `false` |
| `retries` | `3` | per-request retries for network / 429 / 5xx |
| `last_known_good` | `{}` | written automatically; `/provider keep` promotes the current one to default |
| `param_quirks` | `{}` | `{"<model>": ["temperature", …]}` — settings a model rejected; written automatically, cleared with `/sampling forget` |
| `sampling` | see [sampling.md](sampling.md) | temperature / top_p / top_k defaults + per-provider / per-model overrides |
