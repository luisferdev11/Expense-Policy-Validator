## AWS us-east-1 pricing for the expense validator (fetched 2026-10-07)

Research subagent output, kept verbatim as the source for the AWS section of 05_technical_spike.md.

The pricing tables on the aws.amazon.com marketing pages are drawn by JavaScript, so a plain fetch does not return them. The verbatim lines below come from the official **AWS Price List API** offer files for us-east-1 (each one's `publicationDate` is noted). Narrative pages are cited where they add the free tier or worked examples.

### 1. Prices, quoted verbatim

**API Gateway HTTP API** (offer file published 2026-10-02)
- "$1/million requests - API Gateway HTTP API (first 300 million)"
- "$0.9/million requests - API Gateway HTTP API (more than 300 million)"
- For comparison, REST API: "$3.50/million requests - first 333 million requests/month", then "$2.80/million … next 667 million", "$2.38/million … next 19 billion", "$1.51/million … over 20 billion".
- Free tier (pricing page): "one million API calls received for HTTP APIs" per month, for 12 months.
- Request metering: the pricing page's Example 2 meters in 512 KB increments ("4.5 MB/512 KB/request"). Our payloads are well under that.

**Lambda** (offer file published 2026-10-01; pricing page)
- x86 requests: "$0.20 per one million requests" (pricing page).
- x86 duration: "AWS Lambda - Total Compute - US East (Northern Virginia)-Tier-1" 0–6,000,000,000 GB-s at **$0.0000166667**. Tier-2 is $0.0000150000 and Tier-3 is $0.0000133334.
- Arm requests: "AWS Lambda - Total Requests for ARM - US East (Northern Virginia)" at $0.0000002000 per request, which is $0.20 per million.
- Arm duration: "AWS Lambda - Total Compute for ARM - US East (Northern Virginia)-Tier-1" 0–7,500,000,000 GB-s at **$0.0000133334**. Tier-2 is $0.0000120001 and Tier-3 is $0.0000106667.
- Free tier: "one million requests and 400,000 GB-seconds per month."

**S3 Standard** (offer file published 2026-09-28)
- "$0.023 per GB - first 50 TB / month of storage used"
- "$0.005 per 1,000 PUT, COPY, POST, or LIST requests"
- "$0.004 per 10,000 GET and all other requests", which is $0.0004 per 1,000. The pricing page confirms it: "S3 GET requests from the S3 Standard storage class cost $0.0004 per 1,000 requests."

**DynamoDB on-demand, Standard table class** (offer file published 2026-09-11)
- "$0.625 per million write request units (N. Virginia)"
- "$0.125 per million read request units (N. Virginia)"
- "$0.00 per GB-Month of storage for first 25 free GB-Months" and "$0.25 per GB-Month of storage used beyond first 25 free GB-Months"
- Unit sizes: a write unit is 1 KB, rounded up. Read units are "consumed in 4 KB increments". An eventually consistent read costs half a read unit.

**SQS** (offer file published 2026-09-11; pricing page)
- "$0.40 per million Amazon SQS standard requests in Tier1 in US East (N Virginia)", for 0 to 100 billion requests.
- FIFO: "$0.50 per million Amazon SQS FIFO requests in Tier1 …"
- "All customers can make 1 million Amazon SQS requests for free each month."
- "Each 64 KB chunk of a payload is billed as 1 request."

**Secrets Manager** (offer file published 2026-09-11)
- "$0.40 per Secret" per month.
- "$0.05 per 10000 API Requests"

**CloudWatch** (offer file published 2026-10-07)
- Custom log ingestion: "$0.50 per GB custom log data ingested in Standard log class - US East (Northern Virginia)"
- Lambda logs are now billed as vended logs: "$0.50 per GB of vended logs ingested in Standard log class for the first 10TB …", then $0.25 for the next 20 TB, $0.10 for the next 20 TB and $0.05 over 50 TB.
- Log storage: "$0.03 per GB-mo of log storage - US East (Northern Virginia)"
- Custom metrics: "$0.30 per metric-month for the first 10,000 metrics …", then $0.10 for the next 240,000, $0.05 for the next 750,000 and $0.02 over 1,000,000.
- API requests: "$0.01 per 1,000 requests" (CloudWatch API Requests SKU). The narrative page also says "$0.01/M requests" for PutMetricData, which contradicts this. Treat $0.01 per 1,000 as the figure to trust.
- Free tier: "5 GB Data (ingestion, archive storage, and data scanned by Logs Insights queries)", "10 Metrics", "1 Million API requests".

### 2. Rough monthly cost (LLM excluded)

**Assumptions**
- **Volume:** 1.5 M receipts a month.
- **Ingress:** the HTTP API uses a JWT authorizer and integrates directly with SQS SendMessage, so there is no ingest Lambda.
- **Worker:** one worker Lambda per receipt (SQS batch size 1). The baseline is 2 s at 1 GB on x86.
- **SQS:** about 3 requests per receipt (send, receive, delete).
- **DynamoDB cache:** about 2.5 items per receipt, each 1 KB or less. That is one read unit per lookup (conservative) and one write per item in the worst case where every lookup misses.
- **Results:** one 5 KB S3 PUT and one GET per receipt.
- **Logs:** 2 KB per receipt, with 30-day retention.
- **Metrics:** 10 custom metrics, emitted with Embedded Metric Format so there are no PutMetricData calls.
- **Secret:** cached in the container, so roughly 10,000 GetSecretValue calls a month.
- **Free tier:** ignored unless noted.

| Item | Arithmetic | $/month |
|---|---|---|
| API Gateway HTTP | 1.5 M × $1.00/M | 1.50 |
| Lambda requests | 1.5 M × $0.20/M | 0.30 |
| Lambda duration (x86) | 1.5 M × 2 s × 1 GB = 3.0 M GB-s × $0.0000166667 | 50.00 |
| SQS | 4.5 M × $0.40/M | 1.80 |
| DynamoDB reads | 3.75 M read units × $0.125/M | 0.47 |
| DynamoDB writes | 3.75 M write units × $0.625/M | 2.34 |
| DynamoDB storage | about 4 GB, under the 25 GB free allowance | 0.00 |
| S3 PUT | 1,500 × $0.005 | 7.50 |
| S3 GET | 1,500 × $0.0004 | 0.60 |
| S3 storage | 1.5 M × 5 KB = 7.5 GB × $0.023 (grows about $0.17 each month) | 0.17 |
| Secrets Manager | $0.40 + 1 × $0.05 | 0.45 |
| CloudWatch Logs ingestion | 1.5 M × 2 KB = 3 GB × $0.50 | 1.50 |
| CloudWatch Logs storage | 3 GB × $0.03 | 0.09 |
| Custom metrics | 10 × $0.30 | 3.00 |
| **Total, baseline x86** | | **≈ $69.70** (about $0.047 per 1,000 receipts) |

**Other scenarios**
- **Arm:** duration is 3.0 M GB-s × $0.0000133334 = $40.00, so the total is about $60.
- **Low (1 s, 512 MB, Arm):** 0.75 M GB-s, so duration is $10.00 and the total is about $30.
- **High (3 s, 1 GB, x86):** 4.5 M GB-s, so duration is $75.00 and the total is about $95.
- **With the always-free allowances:** Lambda (1 M requests, 400k GB-s), SQS (1 M), CloudWatch (5 GB, 10 metrics) and the HTTP API's first-year 1 M calls together save roughly $13–15 a month.

Lambda duration is about 70% of the bill, and it is mostly time spent waiting on the OpenRouter HTTPS call, which is billed anyway. Because that work is I/O-bound, the cheapest change is a smaller memory size plus Arm.

### 3. Caveats
- **HTTP API vs REST API:** HTTP API is about 71% cheaper ($1.00 vs $3.50 per million). REST API is needed for API keys and usage plans, request validation, direct AWS WAF attachment and private endpoints. At this volume, REST would cost $5.25 a month instead of $1.50.
- **Lambda on Arm (Graviton):** about 20% cheaper per GB-s ($0.0000133334 vs $0.0000166667) at the same request price.
- **DynamoDB price cut:** AWS cut on-demand throughput prices by 50%, effective 2024-11-01. Pre-2024 articles that quote $1.25 per million writes and $0.25 per million reads are out of date.
- **Lambda logs pricing:** since 2025-05-01, Lambda logs in CloudWatch are billed as vended logs with volume tiers. The rate is still $0.50/GB below 10 TB.
- **Free tier for new accounts:** accounts created from 2025-07-15 get a credits-based Free Tier ("up to $200 in AWS Free Tier credits").
- **Secrets Manager caching matters:** without caching, 1.5 M GetSecretValue calls would cost $7.50 a month instead of about $0.05.
- **S3 PUTs are the second-largest line item.**
- **Data transfer is excluded.**
- Two figures are not quoted from an offer file: the Lambda x86 request price ($0.20/M, from the pricing page text) and the HTTP API 512 KB metering (inferred from a worked example).

### Sources (fetched 2026-10-07)
1. https://aws.amazon.com/api-gateway/pricing/
2. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonApiGateway/current/us-east-1/index.json
3. https://aws.amazon.com/lambda/pricing/
4. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSLambda/current/us-east-1/index.json
5. https://aws.amazon.com/s3/pricing/
6. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json
7. https://aws.amazon.com/dynamodb/pricing/on-demand/
8. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/us-east-1/index.json
9. https://aws.amazon.com/sqs/pricing/
10. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSQueueService/current/us-east-1/index.json
11. https://aws.amazon.com/secrets-manager/pricing/
12. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSSecretsManager/current/us-east-1/index.json
13. https://aws.amazon.com/cloudwatch/pricing/
14. https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/us-east-1/index.json
15. https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-dynamo-db-reduces-prices-on-demand-throughput-global-tables/
16. https://aws.amazon.com/about-aws/whats-new/2025/05/amazon-cloudwatch-tiered-pricing-additional-destinations-aws-lambda-logs/
17. https://aws.amazon.com/blogs/compute/aws-lambda-introduces-tiered-pricing-for-amazon-cloudwatch-logs-and-additional-logging-destinations/
