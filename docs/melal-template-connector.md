# Melal template connector

Disabled by default. This connector sends newly generated template HTML, preserving the content and unsubscribe tags. It does not backfill existing templates or generate extra AI content.

After deploying both applications separately, apply generator migration 0061 and Melal migration 0051. Configure these generator environment variables:

```
MELAL_TEMPLATE_ENABLED=true
MELAL_TEMPLATE_ENDPOINT=https://YOUR-MELAL-HOST/templates/import/
MELAL_TEMPLATE_API_KEY=YOUR-STAFF-API-KEY
MELAL_TEMPLATE_SOURCE=YOUR-UNIQUE-GENERATOR-INSTANCE
```

Keep SOURCE stable and unique per generator database. Keep the API key in the environment, never in source control. The Melal account must be active staff with exactly one matching key. HTTP is rejected outside explicit local test settings. Redirects are not followed.

Run Celery workers consuming `delivery` and `maintenance`, plus Celery Beat. Generation commits an HTML snapshot and durable outbox together. Delivery starts after commit. Beat checks due pending rows every minute, including after broker interruptions. Existing generated templates are not queued automatically.

The outbox stores status, attempts, remote ID and a sanitized error. Temporary errors (connection errors, malformed success responses, HTTP 408/429/5xx) retry with exponential backoff, up to eight attempts. Other HTTP failures stop immediately. Pending rows with missing/changed configuration are held; restore the original endpoint before retrying. After resolving a permanent error, an operator can reset the row to pending, attempts to zero and next_attempt_at to now. Preserve its external_id and HTML to retain idempotency.

Melal imports remain inactive (`status=false`), requiring activation in Melal before use. Repeated requests with the same identifier and HTML return the existing record. Changed HTML with the same identifier returns HTTP 409.

Local tests: `python3 manage.py test contents.test_melal_templates --keepdb`. The live test additionally needs MELAL_SIM_URL (loopback only), MELAL_SIM_KEY and MELAL_SIM_SOURCE, with an isolated local Melal API and database. It executes the Celery task synchronously while using real HTTP and real databases. It does not exercise a production broker or worker.

## Real worker verification (2026-11-18)

Verified with a dedicated Redis instance on loopback port 16379, a separate Celery worker process using two threads, a separate Beat process, an isolated PostgreSQL generator database and a local MySQL Melal database. Two generated templates were delivered automatically. Eight duplicate tasks produced no additional delivery, and Beat recovered an outbox row whose broker message was removed deliberately. Beat used a one-second test interval; the deployed schedule remains 60 seconds. Production prefork behavior and remote infrastructure still require post-deployment smoke testing.

## Deployment order

1. Back up both application releases and databases; inspect the actual target services and migration plans.
2. Deploy the Melal import endpoint and migration 0051 first. Verify HTTPS and active staff API-key authentication. Keep imported templates inactive.
3. Deploy generator migration 0061 and connector code with MELAL_TEMPLATE_ENABLED=false. Restart delivery and maintenance workers and Beat to load the new tasks and schedule.
4. Configure the endpoint, dedicated staff API key and stable source identifier securely. Enable the connector and restart the relevant services.
5. Generate one controlled template. Confirm outbox status sent, matching remote ID/HTML and inactive Melal template. Repeat delivery of that same identifier to confirm no duplicate record.
6. For rollback, disable the connector and restart workers/Beat before restoring the prior code. Preserve outbox and import records to retain idempotency; do not reverse data migrations blindly.

The repository has unrelated pre-existing edits. Review and package only the connector changes and required dependencies before deployment.
