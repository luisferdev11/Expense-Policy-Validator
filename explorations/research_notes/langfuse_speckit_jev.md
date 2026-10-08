# Web research: Langfuse, Spec Kit, jev (fetched 2026-10-07)

Research subagent output (WebSearch/WebFetch only), kept as the source for 05_technical_spike.md.
Some pages were summarised by the fetch tool, so short quotes are near-verbatim.

## Langfuse

### SDK version
- Latest Python package **langfuse 4.17.0**, released 2026-10-05, Python >=3.10,<4.0. https://pypi.org/project/langfuse/
- Current major **v4** ("Python SDK v3 → v4 — Latest"). https://langfuse.com/docs/observability/sdk/upgrade-path
- v4: `DatasetItemClient.run()` removed, replaced by `dataset.run_experiment()`; requires Pydantic v2; propagated metadata must be `dict[str,str]` (values <= 200 chars); no longer exports all OpenTelemetry spans by default; `api.observations` and `api.metrics` "require Langfuse v4 (Langfuse Cloud, or a self-hosted server upgraded to v4)". https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4

### run_experiment
Signature (https://python.reference.langfuse.com/langfuse):
```python
def run_experiment(self, *, name: str, run_name: Optional[str] = None, description: Optional[str] = None,
    data: Union[List[LocalExperimentItem], List[DatasetItem]],
    task: TaskFunction, evaluators: List[EvaluatorFunction] = [],
    composite_evaluator: Optional[CompositeEvaluatorFunction] = None,
    run_evaluators: List[RunEvaluatorFunction] = [],
    max_concurrency: int = 50, metadata: Optional[Dict[str, str]] = None,
    _dataset_version: Optional[datetime] = None) -> ExperimentResult
```
- Returns `ExperimentResult` (`run_name`, `item_results`, `run_evaluations`, `experiment_id`, `dataset_run_id`, `dataset_run_url`). `Evaluation` has `name`, `value`, `comment`, `metadata`, `data_type`, `config_id`.
- Loops "your applications or prompts through a dataset", handles concurrency, traces each execution, isolates errors per item. https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk
- Task: `def my_task(*, item, **kwargs)`; local data `item["input"]`, hosted dataset `item.input`. Item evaluators get `input`, `output`, `expected_output`, `metadata` and return `Evaluation(name, value, comment)`. Run evaluators get `item_results`. Async supported.
- Local data: list of dicts to `langfuse.run_experiment(...)`; appears under Experiments without a hosted dataset, results still sent to the configured instance. Hosted: `langfuse.get_dataset("...").run_experiment(...)` creates a comparable dataset run; can pin a dataset version.
- Results: `print(result.format())` in the terminal; in the UI each item is a trace and evaluator outputs are scores.

### Self-hosting with Docker Compose
- Services in https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml: `langfuse-web` (`langfuse/langfuse:4`, port 3000), `langfuse-worker` (`langfuse/langfuse-worker:4`, 127.0.0.1:3030), `postgres:17`, `clickhouse-server:25.12`, `redis:7`, `minio`. Web and worker wait for the four backing services to be healthy.
- Roles (https://langfuse.com/self-hosting): Postgres "the main database for transactional workloads"; ClickHouse "stores traces, observations, and scores"; Redis/Valkey "used for queue and cache operations"; S3/blob persists "all incoming events, multi-modal inputs, and large exports".
- Resources: "We recommend that you use at least 4 cores and 16 GiB of memory, e.g. a t3.xlarge on AWS", disk "e.g. 100GiB". https://langfuse.com/self-hosting/deployment/docker-compose
- Steps: clone, edit `# CHANGEME` lines, `docker compose up`, wait 2–3 minutes for "Ready".
- Not for production: "The docker compose setup lacks high-availability, scaling capabilities, and backup functionality"; "For high-availability and high-throughput, we recommend using Kubernetes."

### Langfuse Cloud Hobby tier (https://langfuse.com/pricing)
- "50k units / month included", no overage; "30 days data access"; "2 users"; ingestion up to 1,000 req/min, general API 30 req/min, Datasets API 100 req/min, Metrics API 100 req/day; regions US, EU, JP. Next tier Core $29/month.

## GitHub Spec Kit (`specify` CLI)

- Latest **v1.1.2, released 2026-10-07**. https://github.com/github/spec-kit/releases, https://pypi.org/project/specify-cli/ (Python >=3.11). v1.1.0 (2026-10-02) deprecated `/speckit.taskstoissues`.
- Install (https://github.github.com/spec-kit/installation.html): `uv tool install specify-cli`, or pinned `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@vX.Y.Z`; `specify version`; `specify self check`.
- Existing repo: `specify init --here --force --non-interactive --integration claude`. `--here` = current directory; `--force` "allows initialization in a non-empty directory and may replace files at conflicting managed paths" and "does not delete the rest of your application". Commit first, work on a branch, review the diff. https://github.github.com/spec-kit/guides/existing-projects.html
- Non-interactive default integration is Copilot, so pass `claude`. `--script sh|ps|py` (default `sh`). `--ignore-agent-tools`. Older `--ai claude` appears in third-party docs (https://www.mintlify.com/github/spec-kit/cli/init); confirm with `specify init --help`.
- Git branches are an opt-in extension; active feature tracked in `.specify/feature.json`. https://github.github.com/spec-kit/quickstart.html
- Creates `.specify/` (constitution at `.specify/memory/constitution.md`, templates, scripts) plus command/skill files; does not rewrite application code. https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/constitution.md
- Claude Code: "Skills-based integration; installs skills in `.claude/skills`". https://github.github.com/spec-kit/reference/integrations.html. `.claude/commands` deprecated (https://github.com/github/spec-kit/pull/1451). Skills are `/speckit-*`.
- Flow: `/speckit-constitution` → `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-checklist` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement` → `/speckit-converge` (new). `/speckit-specify` writes `specs/<prefix>-<short-name>/spec.md`, `checklists/requirements.md`, `.specify/feature.json`. https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/specify.md
- Advice: "Do not invent standards merely to fill the constitution template."

## jev (TypeSafe AI)

- Site https://typesafe.ai/, docs https://docs.typesafe.ai/, console https://console.typesafe.ai/. "Try our first System One Model, Jev, in early access"; returns "typed decisions with calibrated probabilities"; trained with "Reinforcement Learning for Calibrated Decisions (RLCD)".
- Launch post dated Sep 15, 2026: "available today in early access", bringing developers "off the waitlist". https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Keys from https://console.typesafe.ai/keys (https://docs.typesafe.ai/introduction/quickstart).
- Third parties disagree on access: waitlist and "no free tier" (https://www.layer3labs.io/guides/jev-pricing); claims of $5 credit and signup pause not verifiable on an official page (https://opentweet.io/jev/api-access, https://www.eesel.ai/blog/typesafe-jev-pricing).
- Gateways: OpenRouter `typesafe/jev-1.13` / `~typesafe/jev-latest` (https://openrouter.ai/blog/insights/what-is-jev/), Cloudflare Workers AI `typesafe/jev` (https://developers.cloudflare.com/ai/models/typesafe/jev/).
- Price: "$0.042 / MTok" input; output "FREE (too cheap to meter)"; no official free tier.
- API: `POST https://api.typesafe.ai/v1/systemone`, Bearer auth; `pip install typesafe-sdk`; request `model`, `state`, `questions` (`noul|choice|score`); response `answers`, `usage`. Choice returns `choice`, `probabilities`, `confidence`; up to 255 options. On OpenRouter it is `POST https://openrouter.ai/api/alpha/decisions`, not chat-completions. Text only, 32k context.
- Calibration: the launch post reports no ECE, Brier or N. `confidence` is a statistic of the distribution (1 = all mass on one outcome), not an empirical calibration measure; docs say "test with your own data". https://docs.typesafe.ai/confidence
- Independent: Pinocchio paper (https://arxiv.org/html/2609.24881v2) used Jev zero-shot as a correctness predictor on N = 1,718: AUROC 0.666 [0.638, 0.691], Brier 0.240, ECE 0.133; non-deterministic (~0.02 run-to-run). "Just Ask Jev" (https://arxiv.org/abs/2609.29429): median AUROC 0.886 on alignment-failure detection, no calibration metric. OpenRouter's article saw 0.79 vs 0.84 on repeated calls.
- Bottom line: cheap, typed Choice primitive fits classification; non-deterministic; calibration unproven on our data; access path uncertain.
