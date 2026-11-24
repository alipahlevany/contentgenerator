# Generator review — 2026-11-24

Reviewed generation scheduling/recovery, Greeting and Reply paths, callback delivery, Melal outbox, API permissions/idempotency, exports, settings and installation requirements.

## Local fixes

- Persist generation dispatch intent before publishing to Celery so an initial broker outage does not strand a pending job. Migration 0062 adds the nullable timestamp.
- Hold a PostgreSQL session advisory lock across callback HTTP delivery to prevent concurrent workers posting the same record.
- Retry HTTP 408 and 429 in addition to server failures.
- Preserve callback rows when broker publication fails; recover pending/stale processing callbacks through a bounded maintenance dispatcher every five minutes.
- Correct Swagger API key header documentation to X-API-Key.
- Remove machine-specific AppleInternal dependency paths from requirements.

## Validation and limits

Targeted recovery/delivery tests passed (29). Full suite: 337 tests, 336 passed and 1 skipped (48.110 seconds). Migration consistency check and git diff whitespace check passed.

These review changes are local, not pushed or deployed. Deployment requires migration 0062 and restarting relevant workers and beat. No production configuration or data was changed during this review.

PostgreSQL concurrency tests exercise real local database locks; external HTTP/OpenAI responses are mocked. This is not a guarantee of zero defects or a live production delivery test. Greeting skip reduction requires observation of a subsequent real generation run. Concurrent delivery is guarded, but exactly-once delivery across a process crash after remote acceptance still requires receiver-side idempotency. A dependency vulnerability scan and a clean environment installation were not performed.
