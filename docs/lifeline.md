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

## Model-name auto-correction

Typos, retired ids and aliases get fixed against the live list: `claude-sonnet-5-5` on an account that only has
`claude-sonnet-4-5-20250929` resolves to it (newest version wins, then newest date); `sonnet` / `opus` / `haiku`
always mean "the newest one you have"; close matches use fuzzy matching; otherwise the provider's known-good list
(`MODEL_FALLBACKS`) is tried.

## Startup guarantee

At boot CHODE checks the configured provider can plausibly answer (key present, server up). If not, it switches
to the best rung for the session and tells you why, instead of failing on your first message.

## `chode fix` / `/fix` — the connection doctor

A tiny agent that runs on whatever rung answers, with four tools and one job:

| tool | does |
|---|---|
| `list_models [provider]` | the provider's live model ids |
| `test_connection [provider] [model]` | one-token probe → OK, or the error kind + hint |
| `set_config key value` | provider · model · base_urls.* · fallbacks · stream · max_tokens · temperature — **never API keys** |
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
