# Test Case DQ-001: Governed Data-Quality Correction

## Objective

Validate the complete process from dataset ingestion through human-approved correction while proving that the AI-assisted workflow cannot silently modify the source data.

## Preconditions

- The API is available.
- The test uses an isolated SQLite database and temporary object-storage directory.
- No LLM API key is supplied, so explanations use the deterministic evidence-grounded fallback.

## Test data

The CSV fixture contains:

- A missing email
- A missing numerical value
- An invalid negative order total
- An unapproved status value
- An exact duplicate row
- A large numerical outlier

## Procedure and expected results

| Step | Action | Expected result |
|---|---|---|
| 1 | Register a dataset | Dataset ID is returned and creation is audited |
| 2 | Add uniqueness, null, range, and allowed-value rules | Rules are stored successfully |
| 3 | Upload the defective CSV | An immutable version and checksum are created |
| 4 | Run analysis | Missing values, duplicates, rule failures, and Isolation Forest anomalies are found |
| 5 | Inspect explanations | Every finding has a natural-language explanation grounded in detector evidence |
| 6 | Inspect suggestions | A duplicate-removal proposal exists with a confidence score and pending-review status |
| 7 | Attempt approval as a submitter | API returns HTTP 403 and proposal remains pending |
| 8 | Approve as a data steward | Reviewer identity and decision are recorded |
| 9 | Execute the approved deterministic plan | A new child version is created with one fewer duplicate row |
| 10 | Recheck the original | Original bytes and SHA-256 checksum are unchanged |
| 11 | Inspect lineage | Dataset correction and field-level lineage edges exist |
| 12 | Inspect governance evidence | Approval, execution, Slack/email notifications, and audit events exist |

## Automated execution

From the project directory:

```bash
docker compose run --rm api pytest -q tests/test_governed_process.py
```

Expected summary:

```text
1 passed
```

To execute every backend test:

```bash
docker compose run --rm api pytest -q
```

## Acceptance criteria

- All assertions pass.
- Unauthorized approval is rejected.
- The correction is impossible before approval.
- The corrected dataset is a new child version.
- The original dataset remains byte-for-byte unchanged.
- Lineage, reviewer identity, notifications, and audit actions are traceable.

