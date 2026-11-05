# ServicePilot AI

A small service-request platform (HVAC, plumbing, electrical, appliance, other).
Customers submit tickets through a Streamlit form that calls an AWS API; admins
manage them in a Streamlit dashboard backed by DynamoDB, with optional
Amazon Bedrock triage suggestions.

> **Status:** the customer form, admin dashboard and shared logic are in this
> repo and covered by automated tests that run against local emulators. The
> API Gateway + Lambda that stores tickets is **not** in this repo and has not
> been verified. See [docs/architecture.md](docs/architecture.md).

## Features

- Customer form with validation, clear errors, and duplicate-submit protection (per browser session)
- Admin login: PBKDF2-hashed password, lockout after repeated failures, 30-minute idle timeout
- Dashboard: totals, status/priority/service charts, urgent-and-unresolved count
- Search, filter (status/priority/service), sort, and paging
- Ticket lifecycle `Open → In Progress → Resolved` with timestamps and change history
- Safe concurrent edits: updates are rejected if the ticket changed since it was loaded
- Delete confirmations; "delete all" requires typing a phrase
- Optional Bedrock triage (summary, suggested category/priority, urgency flag, troubleshooting ideas, draft reply). Off by default, advisory only, schema-validated, never auto-applied.

## Stack

Python, Streamlit, boto3, DynamoDB, API Gateway + Lambda (external), optional Amazon Bedrock; pytest, moto, ruff, GitHub Actions.

## Layout

```
app.py                 customer form
pages/admin.py         admin dashboard
servicepilot/          config, models/validation, store (DynamoDB), stats, auth, client, ai
scripts/               hash_password.py, migrate_status.py (dry-run by default)
tests/                 pytest suite (moto + fakes; no AWS credentials needed)
docs/architecture.md   architecture, data model, unverified areas
```

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
python scripts/hash_password.py        # paste the output [admin] block into secrets.toml
streamlit run app.py                   # admin panel: sidebar page "admin"
```

### Environment variables

See [.env.example](.env.example). All are optional.

| Variable | Default | Purpose |
|---|---|---|
| `SERVICEPILOT_AWS_REGION` | `us-west-1` | Region of the DynamoDB table the admin reads |
| `SERVICEPILOT_TABLE_NAME` | `ServicePilotTickets` | Table name |
| `SERVICEPILOT_AWS_PROFILE` | unset | Named AWS CLI profile |
| `SERVICEPILOT_API_URL` | existing endpoint | Ticket-creation URL |
| `SERVICEPILOT_AI_ENABLED` | `false` | Turn on Bedrock suggestions |
| `SERVICEPILOT_AI_MODEL_ID` | unset | Bedrock model you have enabled (required if AI on) |
| `SERVICEPILOT_AI_REGION` | table region | Bedrock region |

AWS credentials are never stored in this project; use `aws configure`/`aws login`/SSO/IAM roles.
The admin sidebar shows the region, table and profile in use (never secrets).

## Testing

```bash
python -m pytest -q
python -m ruff check .
```

Tests use moto and fakes only. No AWS credentials are needed and no real
Bedrock calls are made. They verify the admin-side logic, **not** that your
deployed Lambda/API works.

## AWS notes

Minimum IAM for the admin identity (replace placeholders):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["dynamodb:Scan", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"],
    "Resource": "arn:aws:dynamodb:<region>:<account-id>:table/ServicePilotTickets"
  }]
}
```

For Bedrock add `bedrock:InvokeModel` (and `bedrock:Converse` if required by your setup) scoped to the model you use.

If tickets don't appear in the admin: confirm the sidebar region/table match where your Lambda writes, that your credentials are valid (`aws sts get-caller-identity`), and that the identity has `dynamodb:Scan`.

## Security

Implemented: hashed admin password with constant-time check, in-process login lockout, idle session timeout, input validation and control-character stripping, user text rendered as plain text (not markdown/HTML), conditional writes, no secrets or PII in logs, generic error messages.

Limitations (not production-hardened): one shared admin password rather than per-user auth/MFA; the login limiter and session live in server memory (reset on restart, not shared across instances); duplicate-submit protection is client-side only; the public API's validation and rate limiting live in infrastructure not reviewed here; admin uses whatever AWS identity runs the server, so protect and scope it. Put the app behind HTTPS.

## Cost

Everything here is serverless/pay-per-request and should be near-free at low volume (DynamoDB on-demand, Lambda, API Gateway). The admin scans the whole table (cached 30 s), fine for small data but it does not scale to very large tables. Bedrock is billed per token: it's off by default, one call per click, cached per ticket version. Set up an AWS Budget alert (Billing → Budgets) before enabling it.

## Screenshots

None committed yet. After running locally, capture the customer form and admin dashboard and add them under `docs/screenshots/`.

## Known limitations / future work

- Lambda/API source and infrastructure-as-code are not in this repo (verify and add)
- Server-side idempotency and API rate limiting
- Per-user admin accounts / SSO, audit log tied to named users
- DynamoDB Query/GSI instead of Scan for large tables
- Customer email notifications (e.g. SES)
