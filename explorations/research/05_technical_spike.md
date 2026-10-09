# 05 · Technical spike

Exploration material, not the deliverable. Every external fact carries its source URL; all pages
were fetched on **2026-10-07** unless a line says otherwise. The full research notes, with more
verbatim quotes, are in `notes/` (`providers.md`, `langfuse_speckit_jev.md`, `aws.md`).
Live facts measured in this run (model ids, rate-limit headers, schema validity) were taken on
**2026-10-08** and live in `05_models_live.json`, `05_live_check.jsonl` and `budget_log.jsonl`.

Each topic is one heading; sub-points are bold paragraphs so that every source stays inside its
topic.

## OpenRouter (provider of the deliverable once the key is renewed)

**State tonight.** The case's key returns HTTP 401 "API key expired." (two real calls to
`GET https://openrouter.ai/api/v1/key` at 2026-10-08T05:53:44Z and 05:54:05Z, rows in
`openrouter_key_checks.jsonl`). No OpenRouter inference was made in this run.

**Who serves gpt-oss and at what price.** The endpoints API lists 23 endpoints for
`openai/gpt-oss-120b` (https://openrouter.ai/api/v1/models/openai/gpt-oss-120b/endpoints, fetched
2026-10-07) and a similar list for 20b
(https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints, fetched 2026-10-07). Headline
prices on the model pages: "$0.03 / $0.17 per 1M" for 120b
(https://openrouter.ai/openai/gpt-oss-120b/providers) and "$0.018 / $0.09" for 20b
(https://openrouter.ai/openai/gpt-oss-20b/providers), both fetched 2026-10-07. DeepInfra (bf16)
serves 120b at $0.037 / $0.17 and 20b at $0.03 / $0.14; Groq serves them at $0.15 / $0.60 and
$0.075 / $0.30. Endpoints on SambaNova, DigitalOcean and Amazon Bedrock list **no** structured
outputs, and Novita (120b, fp4) lists `response_format` but not `structured_outputs`.

**Structured outputs.** `response_format: {type: "json_schema", json_schema: {name, strict: true,
schema}}`; "Support is determined per endpoint, not just per model", and the docs recommend
`provider.require_parameters: true`
(https://openrouter.ai/docs/features/structured-outputs, fetched 2026-10-07).

**Temperature and reasoning effort.** Temperature "0.0 to 2.0", default 1.0; seed: "Determinism
is not guaranteed for some models" (https://openrouter.ai/docs/api-reference/parameters, fetched
2026-10-07). Reasoning is `reasoning: {effort, max_tokens, exclude, enabled}`, and "Reasoning
tokens are considered output tokens and charged accordingly"
(https://openrouter.ai/docs/use-cases/reasoning-tokens, fetched 2026-10-07). gpt-oss only has
low, medium and high natively, so use `"low"`, and leave enough `max_tokens` that reasoning cannot
eat the whole budget (an empty, billed answer).

**Provider routing and pinning.** The `provider` object takes `order`, `allow_fallbacks` (default
true), `only`, `require_parameters`, `data_collection`, `zdr`, `ignore`, `quantizations`, `sort`
and `max_price` (https://openrouter.ai/docs/features/provider-routing, fetched 2026-10-07). For a
reproducible deliverable: `{"order": ["deepinfra"], "allow_fallbacks": false,
"require_parameters": true, "data_collection": "deny", "zdr": true}`, and record the provider
name returned with each generation.

**Data collection and zero retention.** "OpenRouter itself has a ZDR policy; your prompts are not
retained unless you specifically opt in to prompt logging"; ZDR can be enforced per request or
account-wide (https://openrouter.ai/docs/features/zdr, fetched 2026-10-07).

**Per-request cost.** "Full usage details are now always included automatically in every
response", with `usage.cost` "The total amount charged to your account"
(https://openrouter.ai/docs/use-cases/usage-accounting, fetched 2026-10-07).
`GET /api/v1/generation?id=` returns `data.total_cost`, provider name and latency
(https://openrouter.ai/docs/api-reference/get-a-generation, fetched 2026-10-07), and
`GET /api/v1/key` returns `data.usage` and `limit_remaining`
(https://openrouter.ai/docs/api-reference/limits, fetched 2026-10-07). This is what lets the
README's Spend line match the dashboard.

**Implication.** Pin DeepInfra for gpt-oss-120b through OpenRouter: it is the cheapest bf16 host
with strict structured outputs, and package 6 measures exactly that provider directly
(DeepInfra column), so the numbers carry over once the key is renewed.

## Groq

**Models and prices.** Production: `openai/gpt-oss-120b` "$0.15 input, $0.60 output" and
`openai/gpt-oss-20b` "$0.075 input, $0.30 output", both with 131,072 context;
`llama-3.1-8b-instant` and `llama-3.3-70b-versatile` show "ContactSales"
(https://console.groq.com/docs/models, fetched 2026-10-07). The 8B Llama page carries an
"Enterprise" label and only JSON Object Mode
(https://console.groq.com/docs/model/llama-3.1-8b-instant, fetched 2026-10-07). **Groq offers no
model under 14B at a public price**, so it is only useful here for gpt-oss.

**Live ids.** `GET /openai/v1/models` on 2026-10-08 returned 11 ids, including
`openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `openai/gpt-oss-safeguard-20b` and
`qwen/qwen3.8-27b` (`05_models_live.json`).

**Strict json_schema.** `strict: true` works only on gpt-oss-20b, gpt-oss-120b and qwen3.8-27b;
every property must be required and objects need `additionalProperties: false`
(https://console.groq.com/docs/structured-outputs, fetched 2026-10-07). Both gpt-oss model pages
list "JSON Schema Mode" and "Reasoning"
(https://console.groq.com/docs/model/openai/gpt-oss-120b, fetched 2026-10-07).
`reasoning_effort` takes low, medium and high (https://console.groq.com/docs/reasoning, fetched
2026-10-07).

**Free-tier limits.** 30 RPM, 1K RPD, 8K TPM and 200K TPD for each gpt-oss model
(https://console.groq.com/docs/rate-limits, fetched 2026-10-07). Confirmed live: the first
responses on 2026-10-08 reported 999 requests and about 6.8K tokens remaining. **8K tokens per
minute is the binding limit**: at roughly 760 prompt tokens per item the run is paced at one call
every 7.5 s per model.

**Data retention.** "By default, Groq does not retain customer data for inference requests", with
up to 30 days of logging for reliability and abuse unless ZDR is switched on
(https://console.groq.com/docs/your-data, fetched 2026-10-07).

## DeepInfra

**Endpoint and structured outputs.** OpenAI-compatible base URL
`https://api.deepinfra.com/v1/openai`, with the warning "We may not be 100% compatible with all
OpenAI parameters" (https://docs.deepinfra.com/chat/overview, fetched 2026-10-07). It supports
`json_object` and `json_schema` with `"strict": true` for models tagged JSON
(https://docs.deepinfra.com/chat/structured-outputs, fetched 2026-10-07). **Measured exception:**
`ibm-granite/granite-4.2-8b` rejected `json_schema` on 2026-10-08 with HTTP 405
"json_schema response format is not supported for model", so it runs in `json_object` mode.

**Billing API.** `GET https://api.deepinfra.com/payment/usage?from=YYYY.MM` returns
`months[].items[]` with units and rate in cents
(https://docs.deepinfra.com/api-reference/billing/usage, fetched 2026-10-07). It works with this
key; `budget.py` measures spend as a delta from a baseline taken at the start of the run.

**Choosing small models.** Criteria: under 14B (the panel's research focus and their cost
constraint), multilingual including Japanese, JSON-tagged, cheap. From the model pages (all
fetched 2026-10-07; prices per million tokens in / out):

| API id | Params | Price | Languages | Source |
|---|---|---|---|---|
| `Qwen/Qwen3.5-9B` | 9B | 0.10 / 0.15 | "201 languages" | https://deepinfra.com/Qwen/Qwen3.5-9B |
| `google/gemma-3-12b-it` | 12B | 0.05 / 0.15 | "over 140 languages" | https://deepinfra.com/google/gemma-3-12b-it |
| `ibm-granite/granite-4.2-8b` | 8B | 0.06 / 0.25 | lists en, de, es, fr, ja, pt | https://deepinfra.com/ibm-granite/granite-4.2-8b |
| `mistralai/Mistral-Nemo-Instruct-2407` | 12B | 0.019 / 0.03 | lists ja | https://deepinfra.com/mistralai/Mistral-Nemo-Instruct-2407 |
| `meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo` | 8B | 0.02 / 0.04 | no Japanese | https://deepinfra.com/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo |
| `microsoft/phi-4` | 14B | 0.07 / 0.14 | "not intended to support multilingual use" | https://deepinfra.com/microsoft/phi-4 |
| `openai/gpt-oss-120b` | 117B MoE | 0.037 / 0.17 | — | https://deepinfra.com/openai/gpt-oss-120b |
| `openai/gpt-oss-20b` | 21B MoE | 0.03 / 0.14 | — | https://deepinfra.com/openai/gpt-oss-20b |

Llama 3.1 8B (no Japanese) and phi-4 (English-only by design) are excluded. `Qwen/Qwen3-8B`,
`Qwen/Qwen3-4B` and `Qwen/Qwen2.5-7B-Instruct` are no longer served (404); the live list on
2026-10-08 (`05_models_live.json`, 181 ids) confirms every shortlisted id. Qwen3.5 thinks by
default; `chat_template_kwargs: {enable_thinking: false}` turns it off. Every model page says
"Zero retention" (https://deepinfra.com/pricing, fetched 2026-10-07).

## Langfuse

**SDK and experiments.** Latest Python package langfuse 4.17.0, released 2026-10-05
(https://pypi.org/project/langfuse/, fetched 2026-10-07); v4 replaces `DatasetItemClient.run()`
with `dataset.run_experiment()` and requires Pydantic v2
(https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4, fetched 2026-10-07).
`run_experiment(*, name, run_name, description, data, task, evaluators, composite_evaluator,
run_evaluators, max_concurrency=50, metadata)` returns an `ExperimentResult` with item results,
run evaluations and a dataset-run URL (https://python.reference.langfuse.com/langfuse, fetched
2026-10-07). It runs a task over local data or a hosted dataset, traces every item, isolates
per-item errors, and turns evaluator outputs into scores
(https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk, fetched 2026-10-07).

**Fit for this project.** Item evaluators map directly to "category correct" and "restricted
correct"; a run evaluator computes macro F1 and restricted F1 with N; one run per variant gives
the comparison view. Langfuse stays the lab notebook: the committed JSONL remains the source of
truth that the panel re-runs without Langfuse.

**Self-hosting with Docker Compose.** The official compose file starts `langfuse-web`
(`langfuse/langfuse:4`, port 3000), `langfuse-worker`, `postgres:17`, ClickHouse, `redis:7` and
MinIO (https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml, fetched
2026-10-07). Recommended resources: "at least 4 cores and 16 GiB of memory, e.g. a t3.xlarge on
AWS", disk "e.g. 100GiB"; Compose "lacks high-availability, scaling capabilities, and backup
functionality", Kubernetes is recommended for production
(https://langfuse.com/self-hosting/deployment/docker-compose, fetched 2026-10-07). Component
roles: https://langfuse.com/self-hosting (fetched 2026-10-07). On a 16 GB laptop next to ollama
this is tight; Langfuse Cloud Hobby ("50k units / month included", "30 days data access", 2
users) is the fallback (https://langfuse.com/pricing, fetched 2026-10-07).

## Spec Kit (GitHub)

**Version and install.** Latest release v1.1.2, published 2026-10-07
(https://github.com/github/spec-kit/releases, fetched 2026-10-07; https://pypi.org/project/specify-cli/,
fetched 2026-10-07, Python >=3.11). Install with `uv tool install specify-cli`, or pinned
`uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.1.2`
(https://github.github.com/spec-kit/installation.html, fetched 2026-10-07).

**Init in an existing repository.** `specify init --here --force --non-interactive --integration
claude`: `--here` targets the current directory, `--force` "allows initialization in a non-empty
directory and may replace files at conflicting managed paths" and "does not delete the rest of
your application"; commit first and review the diff
(https://github.github.com/spec-kit/guides/existing-projects.html, fetched 2026-10-07). A
non-interactive init defaults to Copilot, so `--integration claude` must be explicit; older docs
show `--ai claude` (https://www.mintlify.com/github/spec-kit/cli/init, fetched 2026-10-07), so
check `specify init --help` on the installed version.

**Flow with Claude Code.** The Claude integration is "Skills-based; installs skills in
`.claude/skills`" (https://github.github.com/spec-kit/reference/integrations.html, fetched
2026-10-07). The flow is `/speckit-constitution` → `/speckit-specify` → `/speckit-clarify` →
`/speckit-plan` → `/speckit-checklist` → `/speckit-tasks` → `/speckit-analyze` →
`/speckit-implement` (plus the new `/speckit-converge`)
(https://github.github.com/spec-kit/quickstart.html, fetched 2026-10-07). `/speckit-specify` writes
`specs/<prefix>-<name>/spec.md` and a requirements checklist
(https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/specify.md, fetched
2026-10-07). Skills load at session start, so restart Claude Code after `specify init`. The labels
firewall must already be in CLAUDE.md before `/speckit-specify`, which reads the input material.

## jev (TypeSafe AI)

**What it is.** "Try our first System One Model, Jev, in early access"; it "returns typed
decisions with calibrated probabilities" (https://typesafe.ai/, fetched 2026-10-07). Launch post
dated Sep 15, 2026, "available today in early access", with a waitlist
(https://typesafe.ai/blog/introducing-system-one-models-and-jev, fetched 2026-10-07).

**Access and pricing.** Keys come from the console once admitted
(https://docs.typesafe.ai/introduction/quickstart, fetched 2026-10-07). Input "$0.042 / MTok",
output "FREE (too cheap to meter)" (launch post above); no official free tier. Third-party pages
disagree on the waitlist (https://www.layer3labs.io/guides/jev-pricing, fetched 2026-10-07).
Gateways: OpenRouter `typesafe/jev-1.13` through an alpha `POST /api/alpha/decisions` endpoint,
not chat completions (https://openrouter.ai/blog/insights/what-is-jev/, fetched 2026-10-07), and
Cloudflare Workers AI `typesafe/jev` (https://developers.cloudflare.com/ai/models/typesafe/jev/,
fetched 2026-10-07).

**API.** Native `POST https://api.typesafe.ai/v1/systemone` with `state` and `questions`
(`noul`, `choice`, `score`); a Choice question returns `choice`, `probabilities` and `confidence`,
up to 255 options (https://docs.typesafe.ai/, fetched 2026-10-07). A 21-way category choice fits
directly.

**Calibration claims against evidence.** The launch post reports no ECE, Brier score or N. The
docs define `confidence` as a statistic of the returned distribution, not as measured
calibration, and say to test on your own data (https://docs.typesafe.ai/confidence, fetched
2026-10-07). An independent paper used Jev zero-shot as a correctness predictor on N = 1,718:
AUROC 0.666, Brier 0.240, ECE 0.133, and found it non-deterministic
(https://arxiv.org/html/2609.24881v2, fetched 2026-10-07). **Implication:** jev stays a measured
challenger, scored on the dev set with Brier, ECE and a reliability diagram, never in the
delivered pipeline; and its non-determinism conflicts with the byte-identical-output rule unless
results are cached.

## AWS services for the design page (us-east-1)

Prices from the official AWS Price List offer files and pricing pages, fetched 2026-10-07 (quotes
verbatim in `notes/aws.md`):

| Service | Price used | Source |
|---|---|---|
| API Gateway HTTP API | "$1/million requests … (first 300 million)" | https://aws.amazon.com/api-gateway/pricing/ |
| Lambda | $0.20 per million requests; $0.0000166667 per GB-s x86, $0.0000133334 Arm | https://aws.amazon.com/lambda/pricing/ |
| S3 Standard | "$0.023 per GB"; "$0.005 per 1,000 PUT…"; $0.0004 per 1,000 GET | https://aws.amazon.com/s3/pricing/ |
| DynamoDB on-demand | "$0.625 per million write request units", "$0.125 per million read request units" | https://aws.amazon.com/dynamodb/pricing/on-demand/ |
| SQS standard | "$0.40 per million … requests"; 1 million free per month | https://aws.amazon.com/sqs/pricing/ |
| Secrets Manager | "$0.40 per Secret"; "$0.05 per 10000 API Requests" | https://aws.amazon.com/secrets-manager/pricing/ |
| CloudWatch | $0.50 per GB logs ingested; "$0.03 per GB-mo"; $0.30 per custom metric-month | https://aws.amazon.com/cloudwatch/pricing/ |

Offer files: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSLambda/current/us-east-1/index.json
and https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/us-east-1/index.json
(fetched 2026-10-07). DynamoDB on-demand prices were halved from 2024-11-01
(https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-dynamo-db-reduces-prices-on-demand-throughput-global-tables/,
fetched 2026-10-07), so older articles overstate it.

**Rough monthly infrastructure cost at 50,000 receipts/day (1.5 M/month), model calls excluded.**
The arithmetic is in `notes/aws.md`: about $70 on x86 (2 s at 1 GB per receipt), about
$60 on Arm, about $30 at 1 s and 512 MB on Arm. Lambda duration is roughly 70 % of it, mostly
time waiting on the model call, so right-sizing memory and moving to Arm matter more than anything
else. Design: HTTP API with a JWT authorizer → SQS (with a DLQ) → worker Lambda → DynamoDB
item-category cache and S3 results; the key in Secrets Manager, cached in the container; policies
versioned in S3 but **deployed with tests**, never hot-swapped. Model cost belongs on top and is
dominated by per-item classification tokens, which the per-item cache cuts.
