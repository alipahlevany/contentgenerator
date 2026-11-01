# OpenAI account usage

The administrator's dashboard reads token totals from OpenAI's organization
Usage API, separately from the local `AIUsageLog` chart and cost estimate.
The card reports Responses / Chat Completions input, output, cached input,
requests, and today's tokens over the selected 7 or 30 calendar days in UTC.
Cached input is already part of input and is never added to the total again.
Other API products such as embeddings are outside this card's scope.

## Connect

Create an organization Admin API key at
https://platform.openai.com/settings/organization/admin-keys and store it only
in the server's `/var/www/contentgenerator/.env`:

```dotenv
OPENAI_ADMIN_KEY=your-organization-admin-key
OPENAI_USAGE_PROJECT_IDS=
```

Keep `OPENAI_API_KEY` unchanged: generation uses that separate credential.
An empty project list means all projects in the key's organization. To match
a specific project selection in OpenAI Usage, set comma-separated project IDs.
The card always displays its scope and UTC date range. Organization usage cannot
identify greetings versus standard content when they share a key/project;
that split remains explicitly labeled as application-recorded data.

Reload the web service after changing the environment:

```sh
systemctl restart contentgenerator-gunicorn
```

No database migration, generation-worker restart, or billable generation is
required. Sign into the dashboard as an active superuser to see the card.
Credentials and raw provider errors are never sent to the browser.

## Refresh and failures

The protected `/dashboard/openai-usage/` endpoint uses shared five-minute
caching and a refresh lock. It does not fetch from OpenAI while rendering the
dashboard HTML. API reads have bounded timeouts and pagination; incomplete
page sets are not published. Failures are retried after a one-minute cooldown.
A saved successful result is labeled stale with its original fetch time;
authorization failures discard it. A changed key, scope, period, or UTC day
uses a separate cache. There is no fallback from account totals to local logs.

OpenAI can report recent activity later. Compare the same organization,
project filters, endpoint category, UTC dates, and refresh time in both views.

References:
- https://developers.openai.com/api/docs/guides/admin-apis
- https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions
