# Architecture

## What is verified vs. not

| Component | Status |
|---|---|
| Streamlit customer form (`app.py`) | In this repo, tested |
| Streamlit admin panel (`pages/admin.py`) | In this repo, tested against moto (a local AWS emulator) |
| `servicepilot/` shared package | In this repo, tested |
| API Gateway route `POST /tickets` | **Not in this repo; not verified** |
| Lambda that writes tickets | **Not in this repo; not verified** |
| DynamoDB table `ServicePilotTickets` | Assumed from the original admin code (`ticket_id` string hash key); **not verified against real AWS** |

The Lambda source was never committed, so its validation, ID generation and
field names are unknown. Tests with moto prove the admin side behaves correctly
against a table shaped like the one it expects. They do **not** prove the live
integration works.

## Request flow

```
Customer ──► Streamlit app.py ──validate──► POST API Gateway ──► Lambda ──► DynamoDB
                                                                              │
Admin ─► Streamlit pages/admin.py ─(boto3 scan/update/delete, region+table from env)─┘
                          │
                          └─(optional, off by default)─► Amazon Bedrock (advisory suggestions only)
```

1. The customer form validates input (`servicepilot/models.py`), fingerprints
   the payload to avoid double submits in a session, and POSTs it to the API.
2. The API/Lambda stores the ticket (unverified here).
3. The admin panel logs in (PBKDF2 hash, rate limit, idle timeout), scans the
   table (following pagination), normalises items (legacy `Completed` →
   `Resolved`, `Decimal` → int, missing fields defaulted) and renders stats,
   filters, sorting and pages.
4. Updates use a conditional write on a `version` attribute so two admins
   cannot silently overwrite each other, and append an entry to `history`.

## Data model

Existing attributes are untouched. New optional attributes written on update:
`updated_at` (ISO UTC), `version` (int), `history` (list of change entries).
Items without them (all existing data) keep working; `version` absent is
treated as "not yet versioned".

Statuses: `Open`, `In Progress`, `Resolved`. Allowed moves: Open → In Progress |
Resolved; In Progress → Open | Resolved; Resolved → Open (reopen).

## Migration

None is required. `scripts/migrate_status.py` optionally rewrites stored
`Completed` to `Resolved` (dry run by default; `--apply` to write).

## Candidate causes of "tickets don't show in admin" (to verify with real AWS)

These are hypotheses, not findings:

1. Admin credentials invalid/expired or from the wrong profile (observed locally:
   both configured profiles failed authentication).
2. Admin region/table differs from where the Lambda writes (AWS CLI default here
   is `us-east-1`; the project uses `us-west-1`). Now explicit via
   `SERVICEPILOT_AWS_REGION` / `SERVICEPILOT_TABLE_NAME` and shown in the sidebar.
3. Lambda writes different attribute names than the admin expects.
4. IAM policy on the admin identity lacks `dynamodb:Scan`.

The admin panel now shows the exact region, table and profile it uses and a
safe error code when AWS rejects a call.
