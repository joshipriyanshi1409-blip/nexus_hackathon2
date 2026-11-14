# ECHO: local-first verification checklist

Use this guide to run ECHO on your own computer, verify it, and only then push it to GitHub.

## Important: what runs locally and what remains online

The FastAPI application runs on your computer at `http://127.0.0.1:8000`. ECHO still uses a Supabase project for authentication, Postgres data, and private file storage. So this is a local application connected to your configured Supabase project, not a fully offline database.

For a safe first run, use a **separate Supabase project for testing**. Do not point the demo connector at production customer data: simulated Gmail and Google Play records are written into the same feedback table and will appear in complaint analytics until removed.

## 1. Prerequisites

- Python 3.10 or newer.
- A Supabase project that you can use for development/testing.
- The Supabase Project URL, service-role key, database connection URI, and a strong temporary CEO password.
- Optional: a Gemini or Anthropic API key for AI-powered review. Basic deterministic rule checks work without an AI key.

Keep service-role keys, database passwords, model keys, OAuth tokens, and service-account JSON only in your local `.env` file. Never paste them into source code, screenshots, GitHub, or a shared ZIP.

## 2. Windows: first local run

1. Extract the ZIP.
2. Open the `inkloom-ai` folder.
3. Double-click `setup.bat` once. It creates `.env` from `.env.example` and exits.
4. Open `.env` in a text editor and fill in at least:

   ```dotenv
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_SERVICE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
   SUPABASE_DB_URL=YOUR_SUPABASE_DATABASE_CONNECTION_URI
   ADMIN_USERNAME=itz_ceo
   ADMIN_PASSWORD=YOUR_UNIQUE_STRONG_TEMPORARY_PASSWORD
   APP_ENV=development
   DEMO_LOGIN_ENABLED=0
   ```

   Keep the exact database host and port from Supabase's **Project Settings → Database → Connection string**. If the direct connection is unavailable on your network, use the connection-pooler URI and port shown by Supabase.

5. Double-click `setup.bat` a second time. It creates the Python virtual environment, installs backend dependencies, applies database migrations, and creates/updates the CEO login.
6. Double-click `run.bat`.
7. Open `http://127.0.0.1:8000` and sign in with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from your local `.env`.

If setup stops, read the terminal error before retrying. Do not repeatedly run migrations against a production database while troubleshooting.

## 3. macOS / Linux: first local run

From the extracted `inkloom-ai` directory:

```bash
make setup
```

Edit `.env` with the Supabase settings and a strong `ADMIN_PASSWORD`, then run:

```bash
make migrate
.venv/bin/python -m backend.create_ceo
make run
```

Open `http://127.0.0.1:8000`.

## 4. Verify the app before pushing

In another terminal, run the health check:

```bash
curl -i http://127.0.0.1:8000/health
```

Then verify the important flows manually:

- Sign in as the CEO.
- Open the main dashboard and check that the data loads.
- Open Customer voice and verify that it is accessible to the CEO.
- Inspect the simulated Gmail and Google Play previews.
- Run the simulated connector sync **only in your test workspace**; confirm the UI labels the data as simulated and displays import/duplicate/PII counts.
- Run the complaint grouping demo.
- Add or inspect approved facts and run the fact-checking flow.
- Sign out and verify that protected pages require authentication.

The simulated connector does not contact Google. Live Gmail and Play Store collection requires the separate OAuth/service-account configuration documented in `README.md`.

## 5. Run the automated checks

Install the development/test dependencies in your active environment:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q backend tests
python -m pytest -q
python tests/run_evaluation.py
```

The test suite is offline and uses mocked external services. Passing it does not prove that your own Supabase project, AI key, or live Google credentials are configured correctly. The rules-only benchmark is a reproducible sample evaluation, not a guarantee of production accuracy. Run `python tests/run_evaluation.py --llm` only when you intentionally want to spend real model API credits.

## 6. Before pushing to GitHub

From the project root:

```bash
git init
git status --short
git check-ignore .env
```

`git check-ignore .env` should print `.env` (or the matching ignore rule). If it does not, **stop** and fix `.gitignore` before staging files.

Then:

```bash
git add .
git status --short
git commit -m "Prepare ECHO for local verification"
```

Review `git status` carefully before committing. Do not commit `.env`, service-role keys, database URLs/passwords, OAuth refresh tokens, Google service-account JSON, real customer exports, or judge passwords. `.env.example` is safe to commit because it contains blank placeholders.

Push to a private repository first if the project contains internal or non-public information. After local verification, follow the Vercel deployment instructions in `README.md` and configure secrets through Vercel Environment Variables, not in Git.

## 7. Demo-data cleanup

The simulated connector inserts rows with sources `Demo Gmail` and `Demo Google Play` and external IDs beginning `demo_connector:`. To remove only these rows from your **test workspace**, run this in the Supabase SQL editor:

```sql
DELETE FROM public.feedback
WHERE source IN ('Demo Gmail', 'Demo Google Play')
  AND external_id LIKE 'demo_connector:%';
```

Do not run that cleanup against a production workspace unless you have confirmed those rows are only synthetic demo records.
