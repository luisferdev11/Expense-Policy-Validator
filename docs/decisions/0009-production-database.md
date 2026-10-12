# ADR 0009: The production database on AWS

- **Status:** proposed. Chosen with Luis on 2026-10-12; pending his review in the documentation
  pull request.
- **Date:** 2026-10-12
- **Where it is used:** `docs/aws.md` (the brief's Part 4 page), section 1 and the cost table.

## Context

The AWS page sizes the service for 100,000 receipts a day in production (1.2 a second on average,
about 12 at a 10× peak) and for the brief's 50,000. Two documents disagreed about the store:
ADR 0006 (D7) and ADR 0007 (D1) said the SQLite store mirrors "SQS, DynamoDB, S3", and the AWS
page said Aurora PostgreSQL. The brief suggests a small serverless design as a starting point, and
the compute choice depends on the database (Lambda needs no VPC, NAT or connection proxy with
DynamoDB, and needs all three with Aurora), so the two choices are one decision with two coherent
packages.

Luis fixed two inputs: the production volume is about 100,000 receipts a day, and the insights and
the quality sample stay inside the application.

## What the store has to do (from `ports/store.py` and `adapters/sqlite_store.py`)

| # | Access pattern | Aurora PostgreSQL | DynamoDB with SQS |
|---|---|---|---|
| 1 | One command is one atomic change: event, projection row and outbox row together | The same transaction | `TransactWriteItems` (up to 100 items, 4 MB); each item costs double |
| 2 | Idempotent submit: one row per key, a repeat returns the first outcome | `INSERT … ON CONFLICT` | Conditional put |
| 3 | Work queue with a lease; two workers never hold one row; an expired lease is claimable again | `SELECT … FOR UPDATE SKIP LOCKED`, the same shape as today's `UPDATE … RETURNING` | A different design: a stream or EventBridge Pipe moves the outbox item to SQS; visibility timeout is the lease; a dead-letter queue holds failures |
| 4 | At most one open work item per receipt, revision and stage | Partial unique index | Conditional write on a deterministic key |
| 5 | Which current receipts share a key (employee and day, trip): the cross-receipt cascade | Index on `receipt_keys` | A global secondary index on the key |
| 6 | The queue and the lists: filter by state, disposition and batch; total count; pages | Indexes and `COUNT` | One index per filter; no cheap total; cursor pages instead of offset |
| 7 | Insights over every receipt, the QA sample, and the aggregates in the improvements list (F-02, summaries, `updated_since`) | SQL, on a read replica | No ad hoc queries: an export to S3 and Athena, or a second projection per question |
| 8 | Events are append-only and ordered per receipt | Triggers or permissions; a sequence | An IAM condition and a conditional put on `(receipt, seq)`; no global order |
| 9 | Item size (about 11 KB a receipt result) | Any | Fine, the limit is 400 KB; billed per KB |

Patterns 1 to 5 are possible in both. Patterns 6 and 7 are relational, and Luis keeps the insights
and the quality sample in the application. Pattern 3 is where DynamoDB asks for the most new parts.

## Options

- **A. ECS Fargate, Aurora PostgreSQL Serverless v2, the outbox in the database.** The design in
  `docs/aws.md`.
- **B. API Gateway, Lambda, DynamoDB and SQS.** Fully serverless, as the brief suggests: no ALB, no
  NAT, no cluster.

## Cost at 100,000 receipts a day (3 million receipts, 7.41 million items a month)

Package A is the table in `docs/aws.md`: about **USD 1,100**.

Package B keeps the model (451), Cognito (16) and logs (22), and replaces the rest:

| Line | Arithmetic | USD a month |
|---|---|---|
| Writes | About 100 write units a receipt (about 36 before doubling for transactions and adding index writes; the 11 KB result alone is 11) × 3 M × 0.625 per million | 188 |
| Reads | About 50 read units a receipt × 3 M × 0.125 per million | 19 |
| Storage | 200 GB × 0.25 | 50 |
| SQS | About 12 M requests × 0.40 per million | 5 |
| Reporting | S3 export and Athena for pattern 7, assumed | 15 |
| Lambda and API Gateway | Workers: 3 M receipts × 3.7 s × 0.5 GB × 0.0000166667 = 93; the API and gateway, assumed | 104 |
| **Added by B** | | **≈ 381** |
| Model, Cognito, logs | | 489 |
| **Package B** | | **≈ 870** |

The DynamoDB request prices (USD 0.625 per million write units and 0.125 per million read units,
transactional writes double) were read on the
[DynamoDB pricing page](https://aws.amazon.com/dynamodb/pricing/) on 2026-10-12. The storage price,
the Lambda and API Gateway prices, and the units per receipt (100 and 50) are from memory or
assumed, and are not confirmed. B is about 20 % cheaper; the figure moves with those assumptions.

## Decision

**Option A: Aurora PostgreSQL Serverless v2 on ECS Fargate.** Reasons, all from the code and from
Luis's inputs:

1. The correctness mechanism (patterns 1 and 3) maps one to one, so the move to AWS is one adapter
   and the same contract tests prove it. Package B rebuilds the queue.
2. Patterns 6 and 7 are relational and stay in the application. On DynamoDB each new question is a
   new index or a new export, and the reporting path becomes a pipeline of its own.
3. At 12 receipts a second at peak (about 300 database writes a second), one Aurora writer is far
   from its limit. The scale argument for DynamoDB does not apply yet.
4. The schema is already SQL, so the time to a working AWS version is the shortest.

B is cheaper by about USD 230 a month at this volume. That does not pay for the rewrite and the
reporting pipeline while the reporting stays in the application.

## What would change it

- A volume 30 to 100 times larger (tens of receipts a second), where one writer stops being
  comfortable.
- A team that prefers not to run a database.
- Reporting moved entirely to a warehouse, which removes pattern 7.

Any of these makes option B the better design. The `ReceiptStore` port is the seam for it.

## Consequences

- `docs/aws.md` keeps its single page and links here for the comparison.
- The wording of ADR 0006 D7 and ADR 0007 D1 ("DynamoDB and SQS") is amended with a note pointing
  here.
- Still to measure, both assumptions in the tables: I/O per receipt on Aurora (run the contract
  tests on a Postgres container and read the statistics) and write units per receipt on DynamoDB
  (build the adapter on a local DynamoDB and count). Connection counts at the 10× peak (about 43
  workers) need a check, and may add a connection proxy to the cost.
