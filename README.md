# Thermolayer — Automated S3 Storage Class Lifecycle Cost Optimizer

A cloud cost-optimization tool that inspects the objects in an S3 bucket,
classifies each one by age and access frequency, and recommends the
cheapest S3 storage class it's eligible for — the same decision an S3
Lifecycle rule would make, but explained and quantified up front.

## What it does

1. Reads object metadata (size, age, last-accessed time, 30-day access count)
   from a real bucket via `boto3`, or from a built-in synthetic-data
   generator so the project runs without an AWS account.
2. Applies a rule-based optimizer (`backend/app/optimizer.py`) that walks
   each object through AWS's storage-class eligibility rules (minimum
   duration, minimum object size) and picks the cheapest valid class:
   Standard → Standard-IA → One Zone-IA → Glacier Instant Retrieval →
   Glacier Flexible Retrieval → Glacier Deep Archive.
3. Computes current vs. optimized monthly/annual cost and the savings %.
4. Generates a ready-to-apply AWS S3 Lifecycle Configuration JSON from the
   recommendations.
5. Displays everything in a dashboard: summary stats, a cost-by-class
   breakdown, and a sortable/filterable object table.

## Architecture

```
frontend/   static HTML/CSS/JS dashboard, served by nginx
backend/    FastAPI service — analysis engine + REST API
docker-compose.yml   wires both together
```

Backend endpoints:

| Method | Path                          | Purpose                                   |
|--------|-------------------------------|--------------------------------------------|
| GET    | `/api/health`                 | Liveness + whether AWS creds are configured |
| GET    | `/api/buckets`                | List buckets (real, or the demo bucket)     |
| GET    | `/api/simulate`               | Generate fresh synthetic bucket data        |
| GET    | `/api/analyze/{bucket_name}`  | Run the optimizer, return full report       |
| POST   | `/api/lifecycle-policy`       | Generate S3 Lifecycle Configuration JSON    |
| GET    | `/api/pricing`                | Storage-class pricing table used in costing |

## Running it

```bash
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend docs (Swagger UI): http://localhost:8000/docs

No AWS account is required — it boots straight into demo mode with 220
synthetic objects. To point it at a real bucket instead, set AWS
credentials before starting the stack:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
docker compose up --build
```

Then call `/api/analyze/{your-bucket}?use_live_aws=true`. Real access-
frequency data requires S3 Server Access Logging or Storage Lens activity
metrics to be enabled on the bucket — without those, live-mode objects are
conservatively treated as cold (never recently accessed).

## Applying the generated policy

`/api/lifecycle-policy` returns a JSON document in the exact shape AWS
expects, so it can be applied directly:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket your-bucket \
  --lifecycle-configuration file://policy.json
```

## Notes for the writeup

- Pricing is list-price, us-east-1, and kept in one file
  (`backend/app/pricing.py`) so it's easy to swap in Cost Explorer /
  Pricing API data for a more accurate figure.
- The rule thresholds (30/60/90/180 days, access-count cutoffs) are in
  `optimizer.py` and are deliberately simple so they're easy to defend and
  tune in a viva — real-world versions would fit these against your own
  historical access logs instead of fixed thresholds.
