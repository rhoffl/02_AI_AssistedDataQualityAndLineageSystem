# AI-Assisted Data Quality and Lineage System

A portfolio-ready platform that profiles CSV datasets, applies deterministic validation rules, detects drift and multivariate anomalies, explains findings, proposes corrections, requires human approval for important changes, records lineage, and preserves a complete audit history.

## Safety guarantee

The AI component has no mutation capability. It only explains evidence. Corrections follow a separate workflow:

1. A proposal is created.
2. A reviewer, steward, or administrator approves or rejects it.
3. An approved deterministic action may be executed.
4. Execution creates a new immutable dataset version. The source version is retained.

## Included features

- Schema and configurable rule validation
- Missing-value and exact-duplicate detection
- Baseline-relative distribution drift checks
- Isolation Forest anomaly detection
- Dataset-version lineage and transformation history
- Optional LLM explanations with deterministic fallback
- Correction confidence and risk metadata
- Automatically suggested, non-executing correction proposals for supported findings
- Reviewer approve/reject workflow with role enforcement
- Append-only audit events with correlation IDs
- Slack-style notification simulation
- Quality score dashboard
- PostgreSQL, Redis/Celery, FastAPI, and React
- Docker Compose deployment and automated unit tests

## Run locally

Requirements: Docker Desktop or Docker Engine with Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Dashboard: http://localhost:3002
- OpenAPI documentation: http://localhost:8002/docs
- Health check: http://localhost:8002/health

An API key is optional. Without one, findings receive deterministic, evidence-based explanations. If you configure `OPENAI_API_KEY`, the model only receives the finding evidence—not direct database access.

## Demonstration walkthrough

### 1. Create a dataset

Use the dashboard, or:

```bash
curl -X POST http://localhost:8000/api/datasets \
  -H 'Content-Type: application/json' \
  -H 'X-User: ron' \
  -d '{"name":"Customer Orders","description":"Data-quality portfolio demonstration"}'
```

### 2. Add validation rules

Replace `1` with the returned dataset ID.

```bash
curl -X POST http://localhost:8000/api/datasets/1/rules \
  -H 'Content-Type: application/json' \
  -d '{"column_name":"customer_id","rule_type":"unique","parameters":{},"severity":"high"}'

curl -X POST http://localhost:8000/api/datasets/1/rules \
  -H 'Content-Type: application/json' \
  -d '{"column_name":"email","rule_type":"regex","parameters":{"pattern":"^[^@]+@[^@]+\\.[^@]+$"},"severity":"medium"}'

curl -X POST http://localhost:8000/api/datasets/1/rules \
  -H 'Content-Type: application/json' \
  -d '{"column_name":"order_total","rule_type":"min","parameters":{"value":0},"severity":"high"}'

curl -X POST http://localhost:8000/api/datasets/1/rules \
  -H 'Content-Type: application/json' \
  -d '{"column_name":"status","rule_type":"allowed","parameters":{"values":["completed","pending","cancelled"]},"severity":"medium"}'
```

### 3. Upload the intentionally flawed sample

```bash
curl -X POST http://localhost:8000/api/datasets/1/upload \
  -H 'X-User: portfolio-user' \
  -F 'file=@sample-data/customer_orders.csv'
```

The application will identify missing values, duplicates, rule failures, and unusual numerical records. The original file remains unchanged.

### 4. Create a correction proposal

Find the version and finding IDs through `/api/findings` and `/api/datasets`.

```bash
curl -X POST http://localhost:8000/api/versions/1/proposals \
  -H 'Content-Type: application/json' \
  -H 'X-User: quality-agent' \
  -d '{"finding_id":1,"action":"drop_exact_duplicates","parameters":{},"rationale":"Remove one exact duplicate while preserving all distinct records.","confidence":0.99,"risk":"medium"}'
```

Supported deterministic actions are:

- `fill_missing_median`
- `fill_missing_value`
- `drop_exact_duplicates`
- `quarantine_only`

### 5. Review and execute

```bash
curl -X POST http://localhost:8000/api/proposals/1/decision \
  -H 'Content-Type: application/json' \
  -H 'X-User: data-steward' \
  -H 'X-Role: steward' \
  -d '{"decision":"approved","comment":"Evidence verified against the source."}'

curl -X POST http://localhost:8000/api/proposals/1/execute \
  -H 'X-User: data-steward' \
  -H 'X-Role: steward'
```

Execution produces a corrected child version, adds a lineage edge, re-runs all checks, and appends an audit event.

## Quality-score model

The MVP begins at 100 and applies transparent severity penalties:

- Low: 1 point
- Medium: 3 points
- High: 7 points
- Critical: 20 points

This is intentionally explainable. A production system should weight quality dimensions according to downstream business impact and cap the score when critical controls fail.

## API roles

For demonstration, identity is supplied through `X-User` and `X-Role`. Approval and execution require `reviewer`, `steward`, or `admin`. Replace these headers with OIDC/JWT verification before production use.

## Tests

```bash
docker compose run --rm api pytest -q
```

## Production hardening

- Replace demo headers with Entra ID, Auth0, Okta, or Keycloak JWT validation.
- Use S3 object locking or immutable blob retention for raw versions.
- Add Alembic migrations instead of runtime table creation.
- Add Great Expectations or Pandera rule suites for larger rule catalogs.
- Emit OpenLineage events to Marquez or another metadata platform.
- Mask sensitive values before profiling or LLM calls.
- Add tenant isolation, row-level security, signed downloads, and secret management.
- Calibrate correction confidence from reviewer outcomes; never interpret raw LLM confidence as probability.

## License

MIT
