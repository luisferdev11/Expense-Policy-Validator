# Provider research: OpenRouter, Groq, DeepInfra (fetched 2026-10-07)

Research subagent output (WebSearch/WebFetch only), kept as the source for 05_technical_spike.md
and 05_model_shortlist.yaml. Model ids were then confirmed live by `list_models.py`
(`05_models_live.json`).

Headlines:
- Groq has no cheap model under 14B on a public price: `llama-3.1-8b-instant` shows "ContactSales" / "Enterprise".
- DeepInfra returns 404 for `Qwen/Qwen3-8B`, `Qwen/Qwen3-4B`, `Qwen/Qwen2.5-7B-Instruct`; the current small Qwen is `Qwen/Qwen3.5-9B`.
- OpenRouter lists 23 endpoints for gpt-oss-120b; prices and structured-output support differ: pin the provider.

## OpenRouter

Endpoint snapshots (summarised from raw JSON; re-check before pinning):
https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints and
https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints

| Model | Provider | $/M in | $/M out | response_format / structured_outputs |
|---|---|---|---|---|
| 120b | CoreWeave (fp4) | 0.03 | 0.17 | yes / yes |
| 120b | DekaLLM (bf16) | 0.03 | 0.18 | yes / yes |
| 120b | DeepInfra (bf16) | 0.037 | 0.17 | yes / yes |
| 120b | AkashML (bf16) | 0.037 | 0.187 | yes / yes |
| 120b | Novita (fp4) | 0.05 | 0.25 | yes / no |
| 120b | Groq, Together, Nebius, SiliconFlow, Phala, DeepInfra turbo | 0.15 | 0.60 | yes / yes |
| 120b | Cerebras (fp16) | 0.35 | 0.75 | yes / yes |
| 120b | SambaNova, DigitalOcean, Amazon Bedrock | 0.06–0.15 | 0.42–0.95 | no / no |
| 20b | Darkbloom (fp8) | 0.018 | 0.09 | yes / yes |
| 20b | DeepInfra (bf16) | 0.03 | 0.14 | yes / yes |
| 20b | Groq | 0.075 | 0.30 | yes / yes |
| 20b | Amazon Bedrock | 0.07 | 0.15 | no / no |

Headline prices on the model pages: "$0.03 / $0.17 per 1M" (120b) and "$0.018 / $0.09" (20b):
https://openrouter.ai/openai/gpt-oss-120b/providers, https://openrouter.ai/openai/gpt-oss-20b/providers

- Structured outputs (https://openrouter.ai/docs/features/structured-outputs): `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}`; "Support is determined per endpoint, not just per model"; recommends `provider.require_parameters: true`.
- Routing (https://openrouter.ai/docs/features/provider-routing): `order`, `allow_fallbacks` (default true), `only`, `require_parameters`, `data_collection` (`deny`), `zdr`, `ignore`, `quantizations`, `sort`, `max_price`. Pin: `{"order":["deepinfra"],"allow_fallbacks":false,"require_parameters":true,"data_collection":"deny","zdr":true}`.
- ZDR (https://openrouter.ai/docs/features/zdr): "OpenRouter itself has a ZDR policy; your prompts are not retained unless you specifically opt in to prompt logging."
- Parameters (https://openrouter.ai/docs/api-reference/parameters): temperature "0.0 to 2.0", default 1.0; seed: "Determinism is not guaranteed for some models."
- Reasoning (https://openrouter.ai/docs/use-cases/reasoning-tokens): `reasoning: {effort, max_tokens, exclude, enabled}`; "Reasoning tokens are considered output tokens and charged accordingly." gpt-oss native levels are low/medium/high.
- Cost per request (https://openrouter.ai/docs/use-cases/usage-accounting): `usage.cost` "The total amount charged to your account"; `GET /api/v1/generation?id=` returns `data.total_cost` (https://openrouter.ai/docs/api-reference/get-a-generation).
- `GET /api/v1/key` returns `data.{label, limit, limit_remaining, usage, usage_daily, is_free_tier}` (https://openrouter.ai/docs/api-reference/limits).

## Groq

- Models and prices (https://console.groq.com/docs/models): `openai/gpt-oss-120b` "$0.15 input, $0.60 output"; `openai/gpt-oss-20b` "$0.075 input, $0.30 output"; both 131,072 context. `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` "ContactSales". Preview `qwen/qwen3.8-27b` "$0.80 input, $4.00 output".
- Model pages list "JSON Schema Mode" and "Reasoning": https://console.groq.com/docs/model/openai/gpt-oss-120b, https://console.groq.com/docs/model/openai/gpt-oss-20b. llama-3.1-8b-instant page: "Enterprise", JSON Object Mode only (https://console.groq.com/docs/model/llama-3.1-8b-instant).
- Strict structured outputs (https://console.groq.com/docs/structured-outputs): `strict: true` only on gpt-oss-20b, gpt-oss-120b, qwen3.8-27b; all properties required, `additionalProperties: false`; "Streaming and tool use are not currently supported with Structured Outputs."
- Reasoning (https://console.groq.com/docs/reasoning): `reasoning_effort` low/medium/high for gpt-oss; `include_reasoning: false` drops the reasoning field.
- Free-tier limits (https://console.groq.com/docs/rate-limits): gpt-oss-120b and gpt-oss-20b 30 RPM, 1K RPD, 8K TPM, 200K TPD. Confirmed live: response headers showed 1,000 requests/day and ~8,000 tokens/minute remaining at the start of this run.
- Data (https://console.groq.com/docs/your-data): "By default, Groq does not retain customer data for inference requests"; may log up to 30 days for reliability/abuse; ZDR setting available.

## DeepInfra

- Base URL `https://api.deepinfra.com/v1/openai` (https://docs.deepinfra.com/chat/overview); supports `response_format`, `temperature`, `reasoning_effort`; "We may not be 100% compatible with all OpenAI parameters".
- Structured outputs (https://docs.deepinfra.com/chat/structured-outputs): `json_object` and `json_schema` with `"strict": true`: "The model is constrained to produce only values that match your schema." Models tagged "JSON" support it; all below carry the tag.
- Usage API (https://docs.deepinfra.com/api-reference/billing/usage): `GET https://api.deepinfra.com/payment/usage?from=YYYY.MM` returns `months[].items[]` with `model, units, rate, cost`; amounts in cents. Confirmed live in this run.
- Pricing page: https://deepinfra.com/pricing

| API id | Params | $ in / out per M | Languages | Source |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 117B MoE | 0.037 / 0.17 | — | https://deepinfra.com/openai/gpt-oss-120b |
| `openai/gpt-oss-20b` | 21B MoE | 0.03 / 0.14 | — | https://deepinfra.com/openai/gpt-oss-20b |
| `Qwen/Qwen3-14B` | 14.8B | 0.12 / 0.24 | "100+ languages" | https://deepinfra.com/Qwen/Qwen3-14B |
| `Qwen/Qwen3.5-9B` | 9B | 0.10 / 0.15 | "201 languages" | https://deepinfra.com/Qwen/Qwen3.5-9B |
| `google/gemma-3-12b-it` | 12B | 0.05 / 0.15 | "over 140 languages" | https://deepinfra.com/google/gemma-3-12b-it |
| `google/gemma-3-4b-it` | 4B | 0.05 / 0.10 | "over 140 languages" | https://deepinfra.com/google/gemma-3-4b-it |
| `ibm-granite/granite-4.2-8b` | 8B | 0.06 / 0.25 | lists en, de, es, fr, ja, pt | https://deepinfra.com/ibm-granite/granite-4.2-8b |
| `mistralai/Mistral-Nemo-Instruct-2407` | 12B | 0.019 / 0.03 | lists en/fr/de/es/pt/ja | https://deepinfra.com/mistralai/Mistral-Nemo-Instruct-2407 |
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` | 8B | 0.02 / 0.04 | no ja | https://deepinfra.com/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo |
| `microsoft/phi-4` | 14B | 0.07 / 0.14 | "not intended to support multilingual use" | https://deepinfra.com/microsoft/phi-4 |

- Every model page says "Zero retention". Qwen3/Qwen3.5 think by default; disable with `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.
- Excluded: Llama-3.1-8B (no Japanese), phi-4 (English-only by design), Mistral-Small-3.2 (24B).
