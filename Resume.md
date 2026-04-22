# MERCI RAYMOND — Rapport Automation (Resume)

## What this project is (business goal + user value)

**Business goal**: automate the production of **professional, client-facing gardening intervention reports** for MERCI RAYMOND by converting informal weekly field updates (Google Chat) into structured Notion content (Interventions + Reports) with photos, clean formatting, and consistent language. A **separate** headless path (`run_scanner.py`) can also push **operational** signals from the same chat channels into **SUIVI REMPLA** and **Planning (BRIEF)** without using the report UI.

**Who uses it**:
- **Office team**: generates reports for one or many sites for a date range, without manual copy/paste.
- **Clients (indirectly)**: consume clearer reports, consistent layout, and before/after photo sections when present.

**Main outputs**:
- A **Notion report page** in the “Rapports” database (with cover + icon assets, professional layout, and intervention sections).
- One **Notion record per intervention** in the “Interventions” database (linked to the client + the report).


## High-level architecture (data flow)

### Primary pipeline (Python)
1. **Select period + clients** in Streamlit UI (`main.py`).
2. **Load client↔chat mapping** from Notion “Clients” DB (dynamic mapping; no hardcoded list in UI).
3. **Fetch messages** from Google Chat API for each selected client and date range.
4. **Apply ON/OFF filtering** (`apply_on_off_filtering()`), then **group messages into interventions** (same author + same Paris day).
5. **Enhance intervention text** using AI (LangChain + Google Gemini 3.1 Flash-Lite).
6. **Download and optimize images**, then upload them to Notion via **File Upload API**, attach as blocks.
7. **Create report page** in Notion with standardized formatting and images.
8. **Create intervention records** in “Interventions” DB and link them to the report.

### Optional publishing pipeline (Node/Puppeteer)
Notion’s API does not “publish to web” a page. This repo includes a **Puppeteer-based automation service** to publish Notion pages via browser automation (intended for n8n workflows).
- See `notion-publisher-service/` and `notion-publisher-service/N8N_CODE_NODE.md` (architecture and n8n Code node integration).

### REMPLA & BRIEF channel scanner (separate from Streamlit report generation)
A **scheduled, headless** path: `run_scanner.py` + `src/scanner/` — intended to run **hourly on a VPS (e.g. Hostinger)** via cron. It reuses the same Notion “Clients” / Sites DB and Google Chat client as the main app, but does **not** go through `main.py` or the intervention/report pipeline.

- **Input**: all sites with a `Canal Chat` URL; fetches new messages per space since the last run (state file + chat filter).
- **Markers**: `(REMPLA)` → one new row in the **SUIVI REMPLA** Notion DB (fields: title, site relation, request date, “QUI ?” from author email via Notion users list, végétaux / taille / lieu; optional Gemini JSON fallback for messy or multi-plant text). `BRIEF` (any case) → full message into **Planning** DB on the **next** row for that site with `Date` on or after today, sorted by `Date` ascending, **only if** that row’s `BRIEF` is still empty.
- **State & dedup**: `scanner_state.json` — `processed_message_ids` (primary guard) + `last_scan_per_channel` (query window). BRIEF also skips if the target `BRIEF` property is already non-empty.
- **Config**: `config.py` adds lazy getters `get_notion_db_rempla()` and `get_notion_db_planning()` (env: `NOTION_DATABASE_ID_REMPLA`, `NOTION_DATABASE_ID_PLANNING`; defaults include the agreed UUIDs). Manual Notion step: add **Lieu** (Rich text) on the REMPLA DB if you want that column filled; otherwise the writer omits it (schema check in `src/scanner/notion_writer.py`).
- **Entry & docs**: `run_scanner.py` (CLI: `--state-file`, `--cold-start-hours`); deploy/cron/logrotate notes are in the module docstring (no separate deploy `.md` by convention).


## Tech stack (main frameworks + services)

### Python app (core)
- **UI**: Streamlit (`main.py`)
- **Google APIs**:
  - Google Chat API for messages + attachments (`src/google_chat/client.py`)
  - Google People API for resolving `users/{id}` → real names (`src/google_chat/people_resolver.py`)
- **Notion**:
  - Notion API via `notion-client` + direct REST for querying (`src/notion/client.py`)
  - **Data Source API support**: databases with multiple data sources use `Notion-Version: 2025-09-03` and `/v1/data_sources/{id}/query`; legacy DBs use `2022-06-28` and `/v1/databases/{id}/query`. Auto-fallback on 400.
  - Databases + page creation + block building (`src/notion/database.py`, `src/notion/page_builder.py`)
  - Notion **File Upload API** for images/assets to avoid 413 payload errors (`src/notion/client.py`, `src/utils/image_handler.py`)
- **AI**: LangChain + Google Gemini (`langchain-google-genai`, `ChatGoogleGenerativeAI`) — model `gemini-3.1-flash-lite-preview` (`src/ai_processor/text_enhancer.py`, prompts in `src/ai_processor/prompts.py`)

### Node service (optional)
- Express + Puppeteer (`notion-publisher-service/server.js`, deps in `notion-publisher-service/package.json`)


## Notion data model (3 databases + scanner targets)

The **Streamlit report pipeline** expects a **3-database relational setup** in Notion:
- **Clients** (Sites): source of truth for which sites exist + which Google Chat space to read from. (Can be a **data-source database** with one or more data sources; the code supports this—see “Notion Data Source API” in Core logic.) The REMPLA/BRIEF **scanner** also reads this DB (same ID as `NOTION_DB_CLIENTS` / `get_notion_db_clients()`), including `Canal Chat` and optionally `INT EXT ?` for context; it does not write to Clients.
- **Interventions**: one record per grouped intervention (text + images, responsible, etc.).
- **Rapports**: report entries, each linked to a client and to the intervention records included.

**Additional databases (scanner only)**: **SUIVI REMPLA** (one row per `(REMPLA)` message) and **Planning** (intervention rows; scanner patches `BRIEF` on the next upcoming date per site). IDs and property names are aligned in `src/scanner/notion_writer.py` and `config.py` getters above.

Setup steps and intended properties are described in:
- `SETUP.md` (Notion database creation section, properties list) — see `SETUP.md` around L72-L111.
- Repo architecture context: `MD/CONTEXT.md` (3-db structure) — see `MD/CONTEXT.md` L16-L26.

**Important reality check (code vs setup docs)**:
- The code uses a French property mapping in `src/notion/database.py` (`PROPERTY_NAMES`).
- Some properties described in `SETUP.md` (like “Commentaire Brut”, “Catégorie”, etc.) are currently **not fully written by the code** (the pipeline prepares them in `main.py`, but `NotionDatabaseManager.add_intervention_to_db()` currently persists only a subset; it appends images as blocks, not as a database “Files & media” property).
  - If you want those fields populated, plan a small alignment pass between `SETUP.md` schema and `src/notion/database.py` writes (see “Next steps”).


## Core logic & strategies (what makes it robust)

### 1) Message ingestion + normalization (Google Chat)
- Uses `spaces().messages().list()` with createTime filters and pagination.
- **Critical quirk**: Google Chat raw payload uses `attachment` (singular), not `attachments`. The code standardizes into `attachments` in processed messages.
  - Fix explained in `IMAGE_ONLY_MESSAGE_FIX.md` (root cause and one-line fix) — see `IMAGE_ONLY_MESSAGE_FIX.md` L13-L37.
  - Implementation in `src/google_chat/client.py` ensures image-only messages are not dropped — see `src/google_chat/client.py` L100-L105 and L176-L189.

### 2) ON/OFF toggles (pre-grouping filter, privacy/irrelevance)
The live pipeline uses **`apply_on_off_filtering()`** in `src/utils/data_extractor.py` (alias: `apply_off_rule_filtering`). It is **not** only a static “cut at OFF” rule: state is per **(author key, Paris calendar day)**. Markers in message text advance a small state machine (`config.OFF_MARKERS_PATTERN` / `config.ON_MARKERS_PATTERN` — see `config.py` for the French-“on” vs `(ON)` / bare `ON` distinction). The older doc `OFF RULES ETC_IMPLEMENTATION.md` is still a useful background read but may describe an earlier variant; **trust the code and `test_new_features.py` for current behavior.**
- Field authors default **on** (included until OFF); **office** names in `config.OFFICE_TEAM_MEMBERS` default **off** until a valid ON marker (see “Office team exclusion” below).
- Messages with **no parseable `createTime`** are **dropped** by the filter (not passed through unfiltered). Optional `trace_out` on `apply_on_off_filtering(..., trace_out=…)` appends one audit row per sorted message (state in/out, included flag, short text preview, skip reasons for bad date/author).
- Doc refresh: `OFFICE_AND_AVANT_APRES_FIXES.md` (Issue 1) explains office + grouping vs. the older “filter inside `group_messages_by_intervention`” story.

### 3) Intervention grouping strategy

The current grouping rule is:
- **One intervention = same author + same calendar day in Paris timezone** (no “30 min threshold” anymore).
- This matches real-world behavior (field team may post images then text hours later).

Implementation details:
- Implemented in `src/utils/data_extractor.py` (`group_messages_by_intervention()`), using `config.PARIS_TIMEZONE`.
- **Office** traffic is not dropped again inside grouping; it is already shaped by `apply_on_off_filtering()` upstream (default off for known office display names until ON). `group_messages_by_intervention()` docstring states this explicitly.

Doc reference: the refactor and “breaking change” away from the 30-minute threshold is described in `OFF RULES ETC_IMPLEMENTATION.md` — see L55-L65 and L188-L195.

### 4) Date extraction strategy (for better reporting)

The system extracts an intervention date in this priority order:
1. If text contains a DD/MM pattern, use it (`extract_date_from_text()`).
2. Otherwise fall back to the message timestamp.

Why this exists:
- Field messages often contain the real intervention date in text even if posted later.

Reference: `OFF RULES ETC_IMPLEMENTATION.md` (date extraction function + usage) — see L33-L37 and L47-L52.

### 5) AVANT / APRÈS (before/after) support

Goal: reports show clean AVANT / APRÈS columns when gardeners follow one of the supported patterns, and “regular” images can still appear outside those sections.

**Two input patterns (both supported):**
1. **Sequential markers** — `Avant` (and photos), then `Après` (and photos): state machine in `detect_avant_apres_sections()` as before.
2. **Combined marker** — a single line matching `config.COMBINED_AVANT_APRES_PATTERN` (e.g. `Avant/après`, `Avant/arpès`, `before|after` on its own, not a long sentence):
   - **One image** in the same message → name listed in `composite_split_image_names` for downstream left/right *collage* split (unchanged).
   - **Two or more images** in the same message (typical: two side-by-side in the client) → **first `n//2` attachments** → `avant_images`, **rest** → `apres_images` (helper `split_combined_images()` in `src/utils/data_extractor.py`).
   - **Text-only combined message**, then image-only follow-ups → images accumulated in an `in_combined` state, then split 50/50 on flush; avoids leaking state into the next non–avant/après messages (bug fixed 2026-04).

Key rules (unchanged):
- Standalone **AVANT/APRÈS** markers are not confused with the word *avant* in normal sentences (`OFFICE_AND_AVANT_APRES_FIXES.md` — marker detection L67-L87).
- Categorization by attachment name at **Notion upload** in `src/utils/image_handler.py` (ordering vs slices).

Doc reference: `OFFICE_AND_AVANT_APRES_FIXES.md` (L25-L60 ordering + Notion path). Regression: `test_new_features.py` — `test_combined_avant_apres_marker_detection` and `test_avant_apres_detection`.

### 6) Office team (gardener list + default OFF until ON in chat)
- **Single source of “who is office”**: `config.OFFICE_TEAM_MEMBERS` plus **`config.normalize_display_name_for_office_match()`** and **`config.is_office_team_display_name()`** (NFC, collapsed whitespace, lowercase). Known directory variants are listed in `config.py` (e.g. `Vincent Da Silva` vs `Vincent Dasilva`, `Salome Cremona` without accent). **Display names from Google Chat / People must match** one of these strings after normalization — or the person is treated like a field user (everything on until their own OFF/ON flow).
- **Gardener / INTERVENANTS list**: `extract_team_members()` and `src/notion/page_builder.py` use `is_office_team_display_name` so office names don’t pollute the list.
- **Interventions**: same names get **default state OFF** per Paris day in `apply_on_off_filtering()`; content appears after valid `(on)` / `(ON)` / bare `ON` per `ON_MARKERS_PATTERN`, and the same day can include follow-up messages without repeating the marker while state stays on (until OFF). There is **no** second “drop all office” pass inside `group_messages_by_intervention()` — that would break intentional post-`(ON)` office posts.
- **Operational gotcha**: accidental **capital `ON` as an English word** in running text can still act as a marker; French pronoun *on* is not matched as bare `on` (see `config.ON_MARKERS_PATTERN`).

Doc reference: `OFFICE_AND_AVANT_APRES_FIXES.md` (updated Issue 1); `MD/CONTEXT.md` L165-L177 for historical context; regression coverage in `test_new_features.py` (office default OFF, aliases, name-only author key, `trace_out`, French pronoun vs `(on)`).

### 7) @mention extraction (include "binôme" / mentioned gardeners)

Problem solved: often a message is authored by one person but mentions a teammate (e.g., "en binôme avec @Alice MARTIN"). We want both in the INTERVENANTS list.

Implemented via:
- `extract_mentions_from_text()` + updated `extract_team_members()` in `src/utils/data_extractor.py`.

Doc reference: `MD/MENTION_EXTRACTION_IMPLEMENTATION.md` — see L8-L38 and L97-L128.

### 8) Performance optimizations (parallel processing)

**Problem**: Report generation was slow (~6.4 minutes for 13 interventions with 25 images), making the system impractical for regular use.

**Solution**: Implemented parallel processing for I/O-bound operations using Python's `ThreadPoolExecutor`:

- **Parallel AI enhancement** (`src/ai_processor/text_enhancer.py`):
  - Changed `batch_enhance_interventions()` from sequential to parallel execution
  - Uses `ThreadPoolExecutor` with max 5 workers to process multiple Gemini API calls concurrently
  - **Result**: Reduced from ~160s to ~34s for 14 interventions (78% faster)

- **Parallel DB writes** (`main.py`):
  - Intervention database writes now execute in parallel (max 5 concurrent Notion API calls)
  - **Result**: Reduced from ~65s to ~21s for 14 interventions (67% faster)

- **Image processing remains sequential**:
  - Attempted parallelization caused memory corruption (Google API client and PIL are not thread-safe)
  - Sequential processing is safer and still acceptable (~109s for 27 images)

**Overall impact**: Total generation time reduced from **~385s (6.4 min) to ~184s (3.1 min)** — **52% improvement**.

**Technical note**: LangChain provides built-in `.batch()` method with `max_concurrency` parameter that could replace `ThreadPoolExecutor` for AI calls, but current implementation works well and is already in place.

### 9) Notion Data Source API (databases with multiple data sources)

**Problem**: Notion’s newer “data source” model: a database can be a **container for one or more data sources**. The legacy `/v1/databases/{id}/query` returns **400 Bad Request** for such DBs (“Databases with multiple data sources are not supported in this API version”).

**Solution** (in `src/notion/client.py`):
- **API versions**: `LEGACY_API_VERSION = "2022-06-28"`, `DATA_SOURCE_API_VERSION = "2025-09-03"`.
- **`query_database()`**: tries legacy `POST /v1/databases/{id}/query` first; on 400, falls back to Data Source API: (1) `_get_data_source_id(db_id)` — `GET /v1/databases/{id}` with `Notion-Version: 2025-09-03`, reads `data_sources[0].id`; (2) `_query_data_source(ds_id, ...)` — `POST /v1/data_sources/{id}/query` with same version.
- **`get_database()`**: uses `2025-09-03` by default so `GET /v1/databases/{id}` works for data-source DBs.

**Behavior**: Backwards compatible. Legacy DBs keep the old endpoint; data-source DBs (e.g. “double datasource” Clients DB) are handled automatically. No config change needed; ensure the integration has access to the database.


### 10) AI provider: Gemini 3.1 Flash-Lite + intervention-description-only output

**Provider/model**: The app uses **Google Gemini** for text enhancement (replacing OpenAI). Model: `gemini-3.1-flash-lite-preview`. Config: `config.AI_MODEL`, `config.get_gemini_api_key()` (reads `GEMINI_API_KEY` or `GOOGLE_API_KEY` from Streamlit secrets or env). Dependency: `langchain-google-genai`; `TextEnhancer` uses `ChatGoogleGenerativeAI`.

**Cost (order of magnitude)**: At 150 reports/month and 3–4 interventions per report (~525 enhancement calls + 150 actions-extraction calls), token usage is ~1.3M input + ~0.11M output/month. Gemini 3.1 Flash-Lite pricing: $0.25/1M input, $1.50/1M output. **Estimated ~$0.50–0.55/month** (~$5–7/year) for the AI part.

**Intervention output format**: The model must return **only** the professional description paragraph(s), with no introductory phrase (e.g. "Voici une proposition de synthèse pour votre rapport client :") and no date/title line (e.g. "Intervention du 17/02", "Rapport d'intervention du 03/03"). The report UI already shows the intervention date in the section header. Implemented via: (1) **Prompt** (`src/ai_processor/prompts.py`): strict OUTPUT FORMAT section instructing the model to return only the description; (2) **Sanitizer** (`src/ai_processor/text_enhancer.py`): `_strip_model_intro_and_date()` removes any remaining intro line and date/title lines from the model response before it is stored and displayed. So reports show only the intervention description body.


## Image pipeline (end-to-end)

### Why it’s non-trivial
- Google Chat attachments must be downloaded via the media endpoint using the attachment’s `attachmentDataRef.resourceName`.
- Notion has strict request body limits; embedding base64 images in a single “create page” request causes HTTP **413 Payload Too Large**.

### Current working flow (the one in code now)
1. Extract attachments from messages (`src/google_chat/client.py`) and preserve `attachmentDataRef`.
2. Download bytes via `media().download_media(resourceName=..., alt='media')` (`src/utils/image_handler.py`).
3. Optimize images (resize ~600x800, JPEG quality ~70) + apply EXIF orientation correction.
4. Upload each image with **Notion File Upload API**:
   - Create upload → send file → use `notion://file_upload/{id}` reference.
5. Create image blocks referencing file uploads (small payload, unlimited images).

Doc references:
- Full pipeline and “413 fix” summary: `MD/SOLUTION_SUMMARY.md` — see L20-L37 and L90-L96.
- The repository-wide image pipeline status and fixes: `MD/CONTEXT.md` — see L27-L69 and L100-L118.


## Report page formatting (professional layout)

The report page is deliberately structured to look like a professional, standardized deliverable (cover + icon assets, fixed sections, spacing, callouts, columns).

Highlights (implemented in `src/notion/page_builder.py` + helper methods in `src/notion/client.py`):
- **Cover + icon** uploaded to Notion as file uploads and set on each report page.
- **Dates de passage** quote block listing the date range + unique intervention dates.
- **Two-column layout**:
  - Left: 👨‍🌾 INTERVENANTS (gardeners list)
  - Right: ✅ ACTIONS EFFECTUÉS (AI-extracted actions list)
- **Intervention sections**: green callout header + description + images
  - Supports AVANT/APRÈS sections with image grids.
- **Markdown bold → Notion rich text bold** conversion.
- **Notion API child limit** handling: chunk append blocks beyond 100.

Doc reference: the formatting changes are summarized in `MD/CONTEXT.md` — see L120-L141.


## Name resolution (People API) + known operational dependency

Problem: depending on auth mode, Google Chat may return authors as `users/{id}` without display names.

Solution:
- Resolve user IDs via **Google People API** (`src/google_chat/people_resolver.py`) with 24h caching.
- Add proper capitalization formatting (`format_name()`).

Important: **People API must be enabled** in the Google Cloud project (and the OAuth token must include the right scope).
- Steps are in `enable_people_api.md` — see L8-L25 and the suggested test run at L34-L38.


## How to run (local)

### Install and configure
- Follow `SETUP.md` end-to-end (Python venv, Google OAuth creds, Notion integration token + DB IDs, AI key).
- Run the Streamlit app:

```bash
streamlit run main.py
```

### What “success” looks like
- Clients load from Notion.
- You pick a date range + client(s) and generate reports.
- A report page appears in “Rapports”, intervention records appear in “Interventions”, linked appropriately.


## Test scripts (useful when debugging)

The repo includes targeted tests and ad-hoc scripts for specific features. Notable ones:
- `test_image_only_messages.py` (image-only message scenario regression)
- `test_new_features.py` (OFF rule + same-day grouping + avant/après + date extraction)
- `test_people_api.py` (People API resolution)
- `test_mention_extraction.py` (@mention extraction)
- `test_page_with_images.py`, `test_image_upload.py` (Notion image handling)

When debugging a pipeline break, run the most relevant test first to isolate the layer (Chat fetch vs extraction vs Notion write).


## Where we are right now (project status)

### Implemented & working (core)
Based on the current repo state and the project context docs, the following are implemented end-to-end:
- Google Chat message extraction with attachments, including **image-only messages** (`IMAGE_ONLY_MESSAGE_FIX.md`).
- ON/OFF filtering (`apply_on_off_filtering`) + same-day grouping (Paris timezone); office default OFF + name aliases (`config.py`, `test_new_features.py`). Background: `OFF RULES ETC_IMPLEMENTATION.md` (may lag the current toggle model).
- AVANT/APRÈS marker detection (robust against "avant" in normal sentences) + correct image categorization; **combined** `Avant/après`-style line with 2+ photos splits half/half to avant/après (`src/utils/data_extractor.py`, `test_new_features.py`).
- Notion File Upload API migration (no more 413 payload issues) (`MD/SOLUTION_SUMMARY.md`).
- Report formatting (cover/icon, callouts, columns, bold conversion, spacing) (`MD/CONTEXT.md`).
- People API resolver (name normalization + caching) — but requires People API enabled (`enable_people_api.md`).
- @mention extraction for team list (`MD/MENTION_EXTRACTION_IMPLEMENTATION.md`).
- **Performance optimizations**: Parallel AI enhancement and parallel DB writes (52% faster report generation).
- **Notion Data Source API**: Automatic fallback to `/v1/data_sources/{id}/query` with `Notion-Version: 2025-09-03` when a database uses multiple data sources (e.g. double-datasource Clients DB); legacy DBs unchanged.
- **AI**: Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite-preview`) via `langchain-google-genai`; API key via `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Intervention output sanitized so reports show only the description (no model intro or date line).
- **REMPLA & BRIEF channel scanner** (separate from reports): `run_scanner.py` + `src/scanner/` — hourly-cron design; state + dedup as in the “REMPLA & BRIEF channel scanner” section above.

### Current codebase “paper cuts” / alignment gaps
These are not blockers to generating reports, but are important if you care about database fields being filled consistently:
- **`test_new_features.py` — `test_composite_split_image_halves`**: calls `ImageHandler._pil_to_jpeg_bytes()` which is **not** defined on `src/utils/image_handler.py` (test/impl drift). Fix by adding a small private helper or inlining JPEG bytes in the test; unrelated to report pipeline runtime.
- **Interventions DB fields not fully populated**: `main.py` prepares fields like `commentaire_brut` and `categorie`, but `src/notion/database.py:add_intervention_to_db()` currently writes only a subset of properties and does not persist “Catégorie” or “Commentaire Brut” (and images are attached as blocks, not as a Files property).
- **Rapports DB fields not fully populated**: the report page creation currently sets `Nom`, `Client`, `Statut`, `Date de création`; it does not currently set “ID Unique” or “URL Page” even though those exist in the intended schema.
- **Asset path portability**: `config.REPORT_ICON_IMAGE_PATH` is an absolute path on one machine; for portability it should be relative (repo path) or configurable via env/secret.


## Next steps (precise, in priority order)

### 1) Make the Notion DB schema and code 100% consistent
Goal: ensure the Notion databases match what the code writes (or vice versa), so the Notion data is clean and queryable.

Do this by auditing and aligning:
- **Interventions DB properties**
  - Compare `SETUP.md` Interventions properties (see `SETUP.md` L86-L97) with `src/notion/database.py` `PROPERTY_NAMES` + `add_intervention_to_db()` writes.
  - Decide whether images should live as:
    - **Page blocks** only (current behavior), or
    - The “Images” **Files & media** property (would require writing property values instead/in addition).
- **Rapports DB properties**
  - Compare `SETUP.md` Rapports properties (see `SETUP.md` L98-L111) with `src/notion/page_builder.py:create_report_page()` and add missing writes:
    - “ID Unique”
    - “URL Page” (use created page URL)
    - “Date Début” / “Date Fin” if you want period fields persisted

### 2) Make People API resolution “always-on” in production
- Ensure People API is enabled in the Google Cloud project (`enable_people_api.md` L12-L25).
- Re-auth if needed and run `python test_people_api.py` (`enable_people_api.md` L34-L38).

### 3) Operate the REMPLA/BRIEF scanner in production
- Deploy the repo on the VPS, install venv + `requirements.txt`, place `.env`, `credentials.json`, and `token.pickle` (or equivalent headless token), add **Lieu** on the REMPLA Notion DB if needed, grant the integration access to REMPLA + Planning DBs.
- Schedule `run_scanner.py` hourly (see docstring in `run_scanner.py` for cron + logrotate). Verify second run does not duplicate rows (`processed_message_ids` in `scanner_state.json`).

### 4) Deployment strategy decision — **Streamlit reports** (unchanged)
Choose one (or combine):
- **Manual generation via Streamlit** (current, simplest).
- **Scheduled automation** for *report generation* (separate from the REMPLA scanner): cron/CI to run the report pipeline on a schedule if product wants it; optionally chain Puppeteer publish.

### 5) (Optional) Automate “publish to web” via n8n + Puppeteer
If you want reports automatically published publicly:
- Use `notion-publisher-service/` in an n8n workflow.
- Start from `notion-publisher-service/N8N_CODE_NODE.md` (integration patterns and error handling).


## Repository map (what lives where)

### Entry points
- `main.py`: Streamlit UI + orchestration pipeline (fetch → filter → group → AI → images → Notion).
- `run_scanner.py`: cron-friendly REMPLA/BRIEF channel scanner (see “REMPLA & BRIEF channel scanner” in architecture).
- `config.py`: secrets loading + DB IDs (including REMPLA/Planning getters) + report assets + patterns (OFF/ON/AVANT/APRÈS/date) + `OFFICE_TEAM_MEMBERS` + `normalize_display_name_for_office_match` / `is_office_team_display_name` + client mapping loader.

### Core modules
- `src/google_chat/`
  - `auth.py`: OAuth + building authenticated API clients (Chat + People).
  - `client.py`: message listing, sender parsing, attachment normalization.
  - `people_resolver.py`: People API resolution + caching + `format_name()`.
- `src/utils/`
  - `data_extractor.py`: ON/OFF filtering (`apply_on_off_filtering`, optional `trace_out`), grouping, date extraction, AVANT/APRÈS detection, mention extraction, team extraction, categorization.
  - `image_handler.py`: download media, resize/optimize, Notion upload + categorization.
- `src/ai_processor/`
  - `prompts.py`: prompt templates (intervention summary, action extraction).
  - `text_enhancer.py`: LangChain chains + **parallel batch enhancement** (ThreadPoolExecutor) + action extraction.
- `src/notion/`
  - `client.py`: Notion API wrapper, block builders, file upload API, chunking children > 100; **Data Source API** (`_get_data_source_id`, `_query_data_source`) and auto-fallback in `query_database()` for DBs with multiple data sources.
  - `database.py`: DB operations, property mapping, linking relations.
  - `page_builder.py`: report layout + intervention sections + AVANT/APRÈS rendering.
- `src/scanner/`: REMPLA/BRIEF **marker detection** (`marker_extractor.py`), **Notion user email → person** (`author_resolver.py`), **REMPLA row + Planning BRIEF patch** (`notion_writer.py`), **orchestration + state** (`channel_scanner.py`).

### Optional publishing
- `notion-publisher-service/`: Puppeteer automation to publish pages + n8n integration docs.


## Configuration & secrets (how it’s wired)

### How secrets are loaded
`config.py` uses a lazy getter pattern:
- Prefer **Streamlit secrets** (`st.secrets`) when running in Streamlit context.
- Fall back to environment variables for local dev/tests.

### Key expected secrets / env vars
- **Google**:
  - `GOOGLE_CREDENTIALS_PATH` (local) OR `GOOGLE_CREDENTIALS_JSON` (Streamlit Cloud-style)
- **Notion**:
  - `NOTION_API_KEY`
  - `NOTION_DATABASE_ID_CLIENTS`
  - `NOTION_DATABASE_ID_RAPPORTS`
  - `NOTION_DATABASE_ID_INTERVENTIONS`
  - **Scanner (optional, defaults in code)**: `NOTION_DATABASE_ID_REMPLA`, `NOTION_DATABASE_ID_PLANNING` — see `config.get_notion_db_rempla()` / `get_notion_db_planning()`.
- **AI** (Gemini):
  - `GEMINI_API_KEY` (or `GOOGLE_API_KEY` as fallback) — also used by the scanner’s REMPLA Gemini fallback in `src/scanner/marker_extractor.py`.

### Client mapping approach (important behavioral detail)
- Clients are loaded from Notion “Clients” DB at runtime: `config.load_clients_from_notion()` (called in `main.py`).
- “Canal Chat” values can be stored as:
  - full Gmail Chat URLs (e.g. `https://mail.google.com/chat/u/0/#chat/space/...`)
  - `spaces/XXXX`
  - or raw `XXXX`
- `config.extract_space_id_from_url()` normalizes these to `spaces/XXXX`.


## Debugging playbook (fast isolation)

When something breaks, isolate by layer:

### 1) Can we load clients from Notion?
- Symptom: “Aucun client trouvé…” or **400 Bad Request** on `POST /v1/databases/{id}/query`.
- Check: Notion integration access + correct Clients DB ID + required properties exist.
- **400 / “Databases with multiple data sources are not supported”**: the code auto-falls back to the Data Source API (`_get_data_source_id` → `_query_data_source` with `Notion-Version: 2025-09-03`). If it still fails, `GET /v1/databases/{id}` may also return 400 with the old API version—`get_database()` uses the new version by default.
- Code paths: `config.load_clients_from_notion()` → `NotionDatabaseManager.get_all_clients_mapping()` → `NotionClient.query_database()`.

### 2) Can we fetch messages from Google Chat?
- Symptom: “Aucun message trouvé…”
- Check: OAuth token validity/scopes, correct space ID format (`spaces/...`), date filters.
- Code paths: `get_messages_for_client()` in `src/google_chat/client.py`.

### 3) Are ON/OFF/grouping rules excluding too much (or letting office through)?
- Symptom: “Tous les messages exclus (OFF rule)” or “Aucune intervention…” or **office content appearing without an obvious marker in one message**
- Check: per-day **(ON)/(OFF)** sequence; **earlier message that day** may have set state ON; **display name** must match `is_office_team_display_name` (else treated as field). Use `trace_out` on `apply_on_off_filtering` to replay. Avoid accidental **ON** in capitals in English text.
- Code paths: `apply_on_off_filtering()` / `apply_off_rule_filtering()` and `group_messages_by_intervention()` in `src/utils/data_extractor.py`.

### 4) Images missing?
- Symptom: interventions appear but no images on Notion pages
- Check: attachment extraction (Chat raw `attachment` vs processed `attachments`), `attachmentDataRef.resourceName` presence, download_media `alt='media'`.
- Code paths: `src/google_chat/client.py` + `src/utils/image_handler.py`.

### 5) Wrong names (“User 1234…”)?
- Symptom: “User XXXXX” shown instead of real names
- Check: People API enabled + OAuth scope granted + run People API test.
- Reference: `enable_people_api.md` L34-L38.


## Session append (2026-04-22): combined Avant/après + two photos

- **Behavior**: Gardeners can post a standalone combined marker (`Avant/après`, `Avant/arpès`, `before|after` — `config.COMBINED_AVANT_APRES_PATTERN`) with **two or more** images in one message: ordering maps to **avant = first half, après = second** (2 images → 1+1; 4 → 2+2). Alternative: marker **text only** then separate image messages → same 50/50 split on flush. Fixes prior behavior where all such images were tagged *avant* and state leaked to later images.
- **Code**: `split_combined_images()` + `detect_avant_apres_sections()` changes (`in_combined`, `flush_combined_pending`) in `src/utils/data_extractor.py`; `test_new_features.py` extended (`test_combined_avant_apres_marker_detection` cases: 2- and 4-image, text+images, no state leak).

## Session append (2026-04-22): office exclusion audit + ON/OFF filter hardening

- **Problem addressed**: Office staff (e.g. Diane, Vincent) could leak into interventions if **Google `displayName` did not match** a single literal in `OFFICE_TEAM_MEMBERS`, or if **`apply_on_off_filtering` bypassed** messages (no `createTime`, no email), or if teams assumed a **second** office drop inside `group_messages_by_intervention` (it does not — by design, so post-`(ON)` office content can still be reported).
- **Config** (`config.py`): `OFFICE_TEAM_MEMBERS` extended with **aliases** (e.g. `Vincent Da Silva`, `Salome Cremona`); `normalize_display_name_for_office_match` + `is_office_team_display_name` centralize matching. Call sites: `src/utils/data_extractor.py` (`_is_office_team_author` → config helper, `extract_team_members`), `src/notion/page_builder.py` (gardener lists).
- **Filter** (`src/utils/data_extractor.py`): `apply_on_off_filtering` now **drops** messages with unparseable dates (no silent passthrough). **Falsy email** + present name → stable key `name:{normalized name}` so office default OFF still applies. Optional second argument `trace_out` for per-message audit rows (state before/after, `included`, skip reasons). Docstring on `group_messages_by_intervention` documents single responsibility for office.
- **Docs**: `OFFICE_AND_AVANT_APRES_FIXES.md` Issue 1 updated to match code (on/off model, not “filter at start of grouping only”). Core resume sections `### 2) ON/OFF…` and `### 6) Office team…` updated here in `Resume.md` to match.
- **Tests** (`test_new_features.py`): aliases, office follow-up after `(ON)` without a second marker (message text must not contain a stray `\bON\b` — e.g. English “no **ON** in…”), no `createTime` exclusion, name-only author, `trace_out` length.
- **Implication for Google Chat use**: team must use **Directory-consistent display names** or add more aliases; every message should have a normal `createTime`; same-day “why did this pass without ON?” is often an **earlier** `(on)`/ON or a **name mismatch**; use `trace_out` to prove chronology in disputes.


## Notes for the next chat (context you likely need to paste once)

- This repo is already past the big "hard parts": **images**, **413 payload limits**, **AVANT/APRÈS** (including combined `Avant/après` + multiple attachments split), **OFF rules**, **People API name resolution**, **professional report formatting**, **performance optimizations**, **Notion Data Source API** (databases with multiple data sources), **Gemini 3.1 Flash-Lite** for AI, and **intervention-description-only output** (no model intro/date in reports) are implemented.
- Report generation is now **~3 minutes** for typical workloads (down from ~6.4 minutes) thanks to parallel AI enhancement and parallel DB writes.
- **AI cost**: Gemini 3.1 Flash-Lite at 150 reports/month, 3–4 interventions/report → ~\$0.50–0.55/month (~\$5–7/year).
- The main remaining work for the **report app** is **schema alignment** (Notion Interventions/Rapports vs code) + **operationalization** of Streamlit (if you want scheduled *reports*). The **REMPLA/BRIEF scanner** is a separate operational path: wire VPS cron, confirm Notion **Lieu** and integration access, and monitor `scanner_state.json` + logs. **One-off test debt**: `test_composite_split_image_halves` vs missing `ImageHandler._pil_to_jpeg_bytes` — see “paper cuts” above.
- **Performance note**: Image processing remains sequential due to thread-safety issues with Google API client. LangChain's `.batch()` method could replace `ThreadPoolExecutor` for AI calls if refactoring is desired, but current implementation works well.
