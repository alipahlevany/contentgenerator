# Generation model update

The Responses API now uses `gpt-6-luna` with `reasoning.effort=none` and
`service_tier=default` (Standard). There is no automatic switch to Flex or a
more expensive model. Existing temperature and output limits are retained.

Migration 0055 replaces GPT-4.1 nano/mini aliases and their April 2025 snapshots
in AppSettings with `gpt-6-luna`. Other configured models are preserved.
The settings cache key changes so workers running the new code cannot reuse
the old cached model. Restart all application processes after deployment.

## Deploy

1. Back up the production database with the normal deployment procedure.
2. Pause generation workers and the daily scheduler using the existing service
   manager. Let in-flight generation finish before replacing the code.
3. Deploy these changes using the project's existing deployment process.
4. With the production virtual environment active, run:

   ```sh
   python manage.py check
   python manage.py migrate --plan
   python manage.py migrate --noinput
   ```

5. In App Settings, confirm the active model is `gpt-6-luna`.
6. Restart the web app, generation workers and daily scheduler with their
   existing service names. Preserve the generation queues:
   `generation_standard`, `generation_reply`, `generation_greeting`.
7. Run one item from the admin and verify it completes and the output is saved.
   Resume larger jobs from existing progress; do not reset their counters.

The migration intentionally does not restore retired model names on rollback.
If rolling back application code, also select a model that code supports:
the previous code does not send `reasoning.effort=none` for Luna.

## Verification

```sh
python manage.py test contents.test_ai_generation contents.test_generation_job_bounds contents.test_greeting_generation contents.test_celery_routes contents.test_daily_standard_generation contents.test_daily_greeting_generation
```

Temporary connection, rate-limit and server errors have three API attempts,
with a 60-second request timeout and no nested SDK retries. Permanent API
errors (including missing models, invalid credentials and exhausted quota)
stop the job with the original cause, without triggering dataset refills.
Incomplete responses are rejected instead of being saved as valid content.

References:
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/guides/latest-model
