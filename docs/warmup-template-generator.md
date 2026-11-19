# Empty HTML template generator

The template generator creates **empty email shells**, not email copy. Melal supplies the existing message through `{{content}}` and its unsubscribe output through `{{unsubscribe}}`. The generator adds no headline, introduction, message, date, masthead or hidden preheader text. The only fixed visible text is the English reading button and photo attribution.

## Designs and previews

Six table-based layouts rotate with the date and sequence: Editorial, Postcard, Studio, Gallery, After hours and Letter. Six coordinated palettes vary the appearance. Every layout has one remote photo, a full-width content area and a centered **Read more** button. The Letter design places content before the photo; After hours uses a dark reading surface. Layouts use system fonts, inline critical styling and responsive widths.

The admin gallery at `/admin/contents/warmuptemplate/sample/` shows all six designs on desktop and mobile. Its fixed example photo and preview-only message make the content placement visible without generating content or calling OpenAI. Downloaded HTML retains the literal Melal placeholders. Existing saved templates are not rewritten by a code deployment; new generations use the empty-shell renderer.

All dashboard labels, controls, help text and template UI are English. Django's configured interface language is `en-us`; dashboard number and date formatting explicitly uses `en-US`. Existing stored content is separate from interface copy.

## Setup and scheduling

1. `WARMUP_TEMPLATE_PHOTO_PROVIDER=auto` selects Pexels when `PEXELS_API_KEY` is present, otherwise Picsum. Set `picsum` or `pexels` explicitly to pin the provider. Picsum needs no photo API key.
2. New templates select a Medium story from topic RSS feeds. `WARMUP_TEMPLATE_ARTICLE_TOPICS` is a comma-separated list of Medium topic slugs. The selected URL is saved in the template prompt and used by both the image and button. `WARMUP_TEMPLATE_LINK_URL` remains a sample-preview destination only. Recipient-specific tracking links are rejected.
3. Apply the existing template migrations (`0057` and `0058`), collect static assets and restart the web app and workers when installing the feature. This design revision adds no database migration.
4. Save the count (1–50), daily time and delay under **Warmup Template Settings**. The time uses the application's `TIME_ZONE`. **Generate now** works independently of the daily schedule and queues the saved count.

Daily jobs use the `generation_standard` queue. A batch/sequence title plus a shared lock prevents duplicate saved slots. A five-minute manual cooldown prevents accidental repeat batches. Transient photo requests and slot-lock conflicts use the existing task retry mechanism. Other terminal failures are reported in the settings screen. Photo configuration errors are reported without continuously adding identical log messages.

Manual buttons on the template list, settings list and settings detail page now show live batch progress without reloading the page. Each completed template gets **Open preview** and **Download HTML** links. Queue failures, partial failures and unusually slow batches have distinct messages. The button shows the remaining cooldown and unlocks automatically. Without JavaScript, submission opens the template list with the batch results.

The saved count and delay are captured when a manual batch is submitted. Progress metadata and independent per-slot states use the shared cache for 24 hours; saved HTML remains in PostgreSQL. The URL carries the batch identifier so reloading can recover the same results. The authenticated status endpoint reads only that batch; it does not generate content or make OpenAI calls. Polling pauses while the page is hidden and stops when all slots finish. After progress expires, saved templates remain available in the list.

The settings summary counts only `warmup_template` content. Its latest-preview link cannot point to a standard content item, and the daily total is shown separately from the per-batch count.

## Cost and storage

Template generation makes **zero OpenAI requests**, so its additional OpenAI API cost is **$0**, regardless of the configured template count. The existing content generator still has its own API costs. Hosting, email sending and any externally selected photo service are separate. `WARMUP_TEMPLATE_MODEL` is no longer used; it can be removed from old environment files during normal configuration maintenance.

Only image and article URLs are saved; this application never downloads or stores photo or article bytes. Photos are centered in their image area and displayed at a maximum width of 400px, shrinking to fit smaller mobile screens. Picsum URLs retain a 1200 × 800 source for sharp images; their displayed desktop height is about 267px. Picsum catalogue metadata is cached for 24 hours and Medium RSS metadata for six hours. Pexels requests small search metadata responses. Photo selection prefers IDs not used for 45 days; when the finite Picsum catalogue is exhausted, it rotates the oldest eligible image, excluding those used within 24 hours. Article selection prefers URLs unused for 45 days and never repeats one within 24 hours. If no article is available, generation reports an error instead of reusing a fixed destination. Availability still depends on the external providers.

Templates remain compact HTML. PostgreSQL row/index overhead and cached metadata use additional space, but there is no local image library to maintain.

Six real local generations on 2026-11-17 (IDs 403–408) produced 2,946–3,179 byte HTML shells, with zero OpenAI calls, zero new usage records and zero deliveries. At those sizes, 300 templates use about 0.9 MB of raw HTML. Repeating each generation returned the same saved record.

## Melal contract

Rechecked directly against the **Html** field of [Melal WarmupTemplate 485](https://melal.org/admin/main/warmuptemplate/485/change/) on 2026-11-17:

- `{{content}}` occurs once in the message body.
- `{{unsubscribe}}` occurs once in the footer body. It is not an `href` URL: Melal replaces it with its unsubscribe output.
- The image and reading button use the same original HTTPS article URL.
- Recipient tracking wrappers are supplied by the sending system, not copied into generated HTML.
- Our independent photo source receives a separate attribution link; Melal's images are not reused.

The renderer validates these placeholders, links and remote-image domains before saving. API listing/delivery excludes templates until the dedicated Melal template connector is specified. Reading the admin form does not establish the create-template API contract.

## Verification and deployment

Focused tests cover placeholder/link validation, all six layouts, zero OpenAI usage, idempotent persistence and retries, manual generation without an additional OpenAI key, CSRF/permissions, cooldowns, scheduling, photo rotation and exclusion from content delivery. Dashboard and existing AI generation regressions are checked separately.

The combined focused suite passed 53 tests. Browser checks covered 36 cases: six designs, empty or long content, at 320px, 360px and 640px. All fit the viewport; buttons were centered within one pixel, all source images loaded at 1200px, and no generated headings or Persian UI text appeared. These are browser checks, not certification of every Gmail/Outlook rendering engine.

Before deployment, compare the reviewed source hashes against production, preserve application and database backups, drain active generation, install only manifest-listed files, collect static assets and restart the existing services. Verify the deployed gallery, English dashboard and worker health. Keep the previous files available for rollback. Do not enable the daily schedule or change its count as a side effect of deployment.


## English email buttons

The versioned `warmup_button_labels_en_v1.json` catalogue contains 1,000 distinct
English labels, including short reading prompts and longer wording variants.
These are static text choices, independent of photo IDs, colours and layouts.
No AI request is made to select a label. Do not reorder or remove labels within
a bank version.

`WarmupButtonRotation` stores the next position in PostgreSQL. Generation locks
that version's row and saves the template and cursor in one transaction, after
photo retrieval. Failed saves do not consume a position; repeated slots return
their saved template. Manual and scheduled batches share the same cursor,
which survives cache clears, worker restarts and deletion of saved templates.
A label repeats only after all 1,000 positions have been used. Pre-existing
templates keep their original labels. Preview renders do not advance the cursor.

New templates retain plain-text photographer/source attribution, with no
credit hyperlink. Their only links are the photo and CTA destination; the
`{{unsubscribe}}` slot remains for Melal. Older saved templates with valid
credit hyperlinks remain viewable.

Run migration `0060_warmup_button_rotation` before starting updated workers.
