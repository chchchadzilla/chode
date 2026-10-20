# Sampling — temperature · top_p · top_k, per provider or per model

```
/sampling                       what's sent to the current model, where each value comes from, and why anything is withheld
/sampling edit                  the submenu: pick a setting → pick a scope → type a value   (also: launcher menu → Tuning,
                                `chode sampling edit`, and an optional step at the end of `chode setup`)
/sampling temperature 0.7       everywhere (the default)
/sampling top_k 40 provider     every model on the current provider
/sampling top_p 0.9 model       this one model only  (= the current provider/model)
/sampling top_k 40 openrouter   an explicit key: a provider, or provider/model, or a bare model id
/sampling temperature default   stop sending it — let the provider decide
/sampling reset [scope]         drop overrides (all, or one scope)
/sampling forget [model]        forget remembered rejections so a setting is tried again
chode sampling …                the same, from the terminal
```

## How the value is decided

| step | config | example |
|---|---|---|
| 1. defaults | `sampling.temperature` / `top_p` / `top_k` (`null` = don't send) | `{"temperature": 0.2, "top_p": null, "top_k": null}` |
| 2. per provider | `sampling.overrides["<provider>"]` | `"openrouter": {"temperature": 0.7, "top_k": 40}` |
| 3. per model | `sampling.overrides["<provider>/<model>"]` or `["<model>"]` | `"openrouter/qwen/qwen3-coder:free": {"top_p": 0.95}` |
| 4. what the model can take | automatic | see below |

Step 4, in order:

- **Remembered rejection** (`param_quirks["<model>"]`): a setting this model returned a 400 for is dropped. CHODE learns
  this live — the first rejection is caught, the setting dropped, the request retried, the quirk saved — so the user sees
  one notice, not an error.
- **Known gate** (`LLMClient.sampling_gate`): Claude 4.7+/5.x and OpenAI reasoning models (gpt-5, o-series) reject all
  three; CHODE doesn't send them at all. Plan providers (`claude-plan` …) take none: the vendor CLI decides.
- **Your per-model override wins over the gate.** Setting a value for a specific model means "I know; send it", so CHODE
  sends it (and if the provider still refuses, self-healing drops it and remembers — nothing breaks). Setting a per-model
  value also clears a remembered rejection for that setting on that model.
- `top_k` is not part of OpenAI's own API; it is sent to `openai`/`azure` only if you set it, and the first 400 teaches
  CHODE to stop.

So: Claude 5 gets no temperature, your OpenRouter free model gets `temperature 0.7, top_k 40`, your local Ollama model gets
whatever you dialed in for it, and the view tells you which is which:

```
🎚 sampling for openrouter / qwen/qwen3-coder:free
→ temperature  0.7      (provider openrouter)              sent
→ top_p        0.95     (model openrouter/qwen/qwen3-coder:free)  sent
→ top_k        40       (provider openrouter)              sent
· max_tokens   8192  (/config max_tokens N)
```

## Ranges

| setting | range | meaning |
|---|---|---|
| `temperature` | 0 – 2 | randomness; 0 is deterministic, ~0.7 chatty, >1 wild. Coding defaults low (0.2). |
| `top_p` | 0 – 1 | nucleus sampling: only the most likely tokens whose probabilities add up to *p* |
| `top_k` | 1 – 1000 | only the *k* most likely tokens |

`max_tokens` (the longest answer CHODE asks for) is global: `/config max_tokens 16000` or the submenu.

The legacy top-level `temperature` key still works: a config without a `sampling` block feeds it into
`sampling.temperature` on load.
