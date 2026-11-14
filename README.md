# ECHO – Brand Governance Platform

Checks every post against your brand rules and guidelines before it is published, routes it through a human approval chain, and compares your brand voice with what customers actually say.

**Stack:** FastAPI backend, Supabase (Postgres, Auth, private Storage), a single-file frontend (`frontend/brandhub.html`), Google Gemini for AI review (Anthropic Claude optional).

## What it does
- **Rule checks (always on, no AI needed):** words to avoid, preferred terms, claims that need proof, missing image alt text.
- **AI review (needs a Gemini or Claude key):** the model reviews the post against your uploaded guidelines/facts and must cite the source of each finding.
- **Approval workflow:** Employee submits, Supervisor recommends or sends back, Head approves. AI only suggests; nothing is applied or published automatically. Each finding can be accepted, edited or rejected, and those choices travel with the post into Insights.
- **Delegation:** authority only flows downward (CEO > Head > Supervisor > Employee). Grants can be time-limited (7/30 days, enforced by the server), cannot outlive the person who granted them, and can be taken back. Only the CEO can grant open-ended authority.
- **Departments:** reviewers see only posts from their own department; the CEO sees everything.
- **File vault:** private folders, per-person access with optional expiry, version history and restore, 2-minute signed download links.
- **Customer voice:** import feedback (CSV or public form), emails/phone numbers are masked before storage, and a gap report compares customer perception with your brand targets.

### What citation verification does and does not guarantee
For every AI finding the code checks that (1) the cited source id was one of the guideline excerpts actually sent to the model, (2) the quoted text really appears in the post, and (3) the rule text shown to the user really comes from that source (otherwise the real excerpt is shown instead). It does **not** prove the model's reasoning is right, and it cannot find problems the model misses. Treat findings as suggestions for a human.

## Local-first handoff

Before pushing to GitHub, follow [`LOCAL_FIRST.md`](LOCAL_FIRST.md) for a step-by-step local setup, smoke test, automated checks, and secret-safety checklist. The app runs locally but still requires a Supabase project for Auth, Postgres, and Storage.

## Quick start

**Prerequisites:** Python 3.10+, a [Supabase](https://supabase.com) project, optionally a Gemini API key.

**Windows**
1. Double-click `setup.bat`. The first run creates `.env` from `.env.example` and stops.
2. Open `.env` and fill in `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL`, `GEMINI_API_KEY`, and a strong `ADMIN_PASSWORD` (12+ characters).
3. Run `setup.bat` again (installs packages, applies the migrations, creates the CEO login), then `run.bat`.

**Linux / macOS**
```bash
make setup            # creates .venv and .env
# edit .env, then:
make migrate
.venv/bin/python -m backend.create_ceo
make run
```
Open http://localhost:8000 and sign in as `ADMIN_USERNAME` (default `itz_ceo`) with `ADMIN_PASSWORD`.

**Judge accounts:** Do not publish account passwords in the frontend, README, repository, or ZIP files. Create demo accounts using unique temporary passwords and share them with judges privately. Use the `add_team_member` command with a secure password supplied locally (do not paste secrets into source control). Example:
```powershell
python -m backend.add_team_member --name "Reviewer" --username reviewer1 --role head --department Marketing --password "<USE-A-UNIQUE-TEMPORARY-PASSWORD>" --created-by itz_ceo
```
Set the CEO password in your private `.env` file only:
```
ADMIN_PASSWORD="<YOUR-UNIQUE-ADMIN-PASSWORD>"
```

To add or remove accounts later, edit `DEMO_ACCOUNTS` in `frontend/brandhub.html` and run the matching
`add_team_member` command. **Remove public demo accounts after judging. Never publish passwords or enable public demo login on a production deployment.**

**Sharing just a link (e.g. hackathon judging) with no setup guide:** set `DEMO_LOGIN_ENABLED=1` in `.env` and restart the
server. The sign-in page then shows a second button, "Continue as CEO (demo)", that signs anyone in as the CEO with one
click. It still checks the real `ADMIN_PASSWORD` against Supabase behind the scenes, so it only works if your own CEO
login already works — it is a convenience, not a way around the password. **Turn it back to `0` (or delete the line)
once judging is over**, because while it is `1`, anyone with the link becomes CEO with a single click.

The schema comes from `backend/migrations/001` to `005`, applied in order by `python -m backend.migrate`. Migration 005 adds demo metadata columns used by sample facts; these metadata fields do not restrict accounts or filter shared records. (`backend/schema.sql` is only a pointer; do not paste old SQL over a live database.) If you ran an earlier version of this project, migration 003 moves department tags into a real `department` column and adds the missing `ON DELETE` rules; migration 004 adds complaint intelligence and approved facts.

Stuck on Supabase? See `SUPABASE_SETUP.md` for a step-by-step beginner guide.

Optional demo data: `python -m backend.seed_demo` creates sample Marketing users and posts. Demo passwords are random and printed once at the end (or set `DEMO_PASSWORD`). It refuses to run when `APP_ENV=production`.

## Configuration
Everything is in `.env.example`, with comments. Key points:
- **Gemini only is fine.** Leave `ANTHROPIC_API_KEY` empty. Default model `gemini-2.5-flash`; `GEMINI_FALLBACK_MODELS` is optional.
- With no AI key, rule checks still work and the AI step is skipped.
- `APP_ENV=production` on real deployments. `ENABLE_DOCS=1` turns on `/docs` for local development only.
- `SUPABASE_DB_URL` is used only by the migration runner.

## Tests and benchmark
```bash
pip install -r requirements-dev.txt
python -m pytest -q                         # all offline tests (no network, no database)
RUN_LIVE_TESTS=1 python -m pytest -m live   # real Supabase / model / browser; needs a configured .env
python tests/run_evaluation.py              # rules-only benchmark, offline
python tests/run_evaluation.py --llm        # also runs the real model (costs API calls, ~7 s between calls)
```
Offline tests cover the business logic, the AI pipeline (with the model mocked) and the API's authorization and workflow rules against an in-memory fake database.

**Benchmark, read with care:** 52 hand-labelled posts (37 with a violation, 15 clean). Rules Only scores precision 100%, recall 89.2% (it misses 4 of 5 fact-contradiction posts, which need the model). That number is optimistic because the same people wrote the rules and the samples. Run `--llm` yourself for the model modes; no figures for them are claimed here.

## Deployment
- **Docker:** `docker compose up --build`. The container runs as a non-root user and exposes a health check at `/health`.
- **Vercel (recommended for hosting):** the app is exported directly from `backend.app.main:app` via `pyproject.toml`; `vercel.json` includes `frontend/**` so the HTML page is bundled with the Python function. A root `.python-version` pins Python 3.12 for predictable dependency wheels.
  1. Push this folder to a GitHub repo (`.env` is git-ignored; never commit it).
  2. In Vercel: **Add New -> Project -> Import** that repo. Framework preset: **FastAPI**. Root Directory: the folder containing `pyproject.toml`, `requirements.txt`, `vercel.json`, `backend/`, and `frontend/`. Leave Build Command and Output Directory blank; use `pip install -r requirements.txt` as Install Command if Vercel does not detect it automatically.
  3. Project Settings -> Environment Variables: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY` (and/or `ANTHROPIC_API_KEY`), `GEMINI_MODEL`, `CLAUDE_MODEL`, `APP_ENV=production`. Do **not** add `SUPABASE_DB_URL` or `ADMIN_PASSWORD` to Vercel for the normal login flow.
  4. Deploy. Every later `git push` to `main` redeploys automatically. Check `https://YOUR-APP.vercel.app/health` and `/`.
  5. Database migrations and CEO provisioning are one-time local operations only; do not rerun them during ordinary Vercel deployments.
  - Vercel limits: request bodies max 4.5 MB (uploads are capped at 4 MB there; set `MAX_UPLOAD_MB` to change it elsewhere), and rate limits are in-memory per serverless instance, so they are best-effort on Vercel.
- **GitHub Pages cannot host this app.** It only serves static files, and ECHO needs the FastAPI backend. Keep the code on GitHub and let Vercel deploy from it.

## Security notes
- Browsers never talk to the database; the server uses the Supabase service key, which must stay server-side. RLS is on for all tables.
- Every route checks the caller's *effective* authority (expired or taken-back grants give nothing) and department. Posts outside your scope return "not found".
- Uploaded text is treated as untrusted data in the AI prompt; the frontend escapes user content; a Content-Security-Policy and other security headers are sent.
- The Gemini key is sent in a request header, never in a URL or log.
- Public feedback form never calls the model, masks personal data, and is rate-limited per IP and globally.
- **Known limits:** rate limits are in-memory (per process); the session token lives in `sessionStorage`; the CSP still needs `'unsafe-inline'` because the UI uses inline handlers; the public form can still be spammed to create fake "customer friction" alerts. Free-tier Gemini keys may let Google use submitted text to improve its products, so use a paid key for confidential content.
- **If an earlier `.env` was ever shared or committed, rotate the Supabase service key and Gemini key.**

## Troubleshooting
- **"Please sign in" / session expired:** log out and in again.
- **HTTP 429:** rate limit; wait a minute.
- **"Cannot give powers you do not hold" (403):** you can only delegate powers you have yourself, to a lower role.
- **Migration or CEO step fails:** the message says why (missing `SUPABASE_DB_URL`, weak `ADMIN_PASSWORD`, etc.). Fix `.env` and run again.
- **AI review slow or empty:** check `GEMINI_API_KEY`; on networks where IPv6 DNS stalls set `FORCE_IPV4=1` (automatic on Windows).

## AI and data disclosure
Post text and the most relevant guideline excerpts are sent to the configured model (Gemini by default, Claude if `ANTHROPIC_API_KEY` is set). Customer comments have emails and phone numbers masked before AI analysis and storage; public-form comments are never sent to the model. Supabase hosts the database, login and private files. AI only suggests; all approvals and delegation decisions stay with people.

## Customer intelligence improvements (migration 004)

Apply the latest database migration before deploying the updated application:

```bash
cp .env.example .env
# Fill Supabase settings, then:
python -m backend.migrate
```

Migration `backend/migrations/004_customer_intelligence.sql` adds complaint deduplication metadata and the structured `approved_facts` table. It is idempotent and is applied by the normal migration runner.

### 1) Similar complaint grouping

The Voice of Customer screen now groups similar comments using deterministic token-cosine similarity, shows source-wise counts, example comments, complaint IDs, and 30-day rising/falling comparisons. The manual evaluation box accepts JSON such as `{"12":"payment","15":"payment","18":"delivery"}` and reports pairwise precision, recall and F1. Review the threshold on your own hand-labelled data before treating it as a production accuracy score.

### 2) Automatic feedback collection

The connector sync is read-only. Configure these server-side environment variables:

- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` (OAuth scope: `https://www.googleapis.com/auth/gmail.readonly`)
- `GMAIL_FEEDBACK_QUERY` (defaults to `newer_than:30d`)
- `GOOGLE_PLAY_PACKAGE_NAME`, `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (service account needs permission to view the app and its reviews in Play Console (the collector only issues GET requests))
- `FEEDBACK_SYNC_TOKEN` for scheduled sync

Use the CEO-only **Sync connected sources now** action, or schedule `POST /api/connectors/sync/cron` with the `X-Sync-Token` header (for example every 6 hours). The connector never sends, labels, archives, or deletes mailbox messages. Emails, phone numbers, PAN patterns and Aadhaar-like number patterns are masked before storage (this is not a guarantee that every free-text personal detail is detected), and exact duplicate comments are skipped within each source. The UI reports imports, duplicates and PII redactions. Google Play API access requires the app to be available to the configured Play Console account.

**No Google credentials available? Use the built-in demo.** Sign in as the CEO, open **Customer voice**, inspect the Gmail-style inbox and Play Store-style review previews, and select **Run simulated Gmail + Play Store sync**. This imports synthetic sample messages under the distinct sources `Demo Gmail` and `Demo Google Play`; it does not contact Google or read any real inbox. The rows still pass through the same PII masking, source-scoped duplicate removal, classification, and feedback storage pipeline. Run it again to demonstrate duplicate handling. The UI and API response label these records as **SIMULATED DATA ONLY**. Demo sync writes synthetic rows into the same workspace feedback table, so they appear in complaint analytics and remain until manually removed. Run it only in a demo/test workspace. To remove only these demo rows later, run `delete from public.feedback where source in ('Demo Gmail', 'Demo Google Play') and external_id like 'demo_connector:%';` in the Supabase SQL editor. This demonstrates the integration workflow, not a live Google connection.

### 3) Approved-fact verification

The CEO can add structured approved facts under **Writing standards** in the left sidebar. Give each fact a stable name that appears in the draft (for example `Product price`), its approved value, and the source title/URL. The deterministic checker flags numeric conflicts and attaches the approved source title. It does not claim to verify facts for which no approved fact has been entered.

The CEO can benchmark a labelled post set with `POST /api/facts/evaluate` using `{ "posts": [{"text":"...", "wrong_fact":true}] }`. The response reports precision, recall, F1, false alarms, and whether the configured live AI provider was used. Include `baseline_detected: true/false` on each labelled post to calculate before/after baseline metrics from your old system run. For the promised 52-post benchmark, supply all 52 labelled posts and compare with the baseline run; do not invent results or use unlabelled posts as ground truth.

### Deployment notes

- Never commit `.env` or expose OAuth/service-account credentials in the browser.
- Rotate any credentials that were previously included in a shared ZIP or public repository.
- Connector sync is disabled until credentials are configured; the rest of the platform works without Gmail/Google Play credentials.

For automatic collection every 6 hours on GitHub Actions, add repository Actions secrets `FEEDBACK_SYNC_URL` (your deployed base URL) and `FEEDBACK_SYNC_TOKEN` (the same value as the server environment variable). The workflow at `.github/workflows/sync-feedback.yml` can also be run manually from the Actions tab.


## Judge sample fixtures

The existing `/#/judges` page remains the multi-account account list. Every listed username should correspond to a real Supabase Auth user/profile, and each judge signs in with that account's own password. Existing CEO, Head, Supervisor and Employee permission rules remain in force. The sample-data helper below does not create a special judge user or change any role:

```powershell
python -m backend.seed_judge_samples
```

This loads synthetic complaint examples and approved facts into the shared organisation dataset. An account needs the ordinary `voice` permission to see and evaluate customer feedback. See `JUDGING_GUIDE.md` for account provisioning commands and a judging walkthrough.
