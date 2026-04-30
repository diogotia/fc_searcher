# Facebook Monitor

Python service that pulls Facebook Group posts via the Graph API, stores them in SQLite or PostgreSQL, optionally analyzes trends with Anthropic Claude, sends daily HTML/CSV reports over SMTP, and accepts Meta webhooks for near-real-time updates.

| | |
| --- | --- |
| **Docs** | [MASTER_PLAN.md](MASTER_PLAN.md) (architecture, security, DevOps) |
| **License** | Add a `LICENSE` file before publishing (this repo does not ship one by default). |

## Facebook tokens: App ID / App Secret vs access token

- **App ID** (`FACEBOOK_APP_ID`) and **App Secret** (`FACEBOOK_APP_SECRET`) identify your Meta app. They are **not** a replacement for `FACEBOOK_ACCESS_TOKEN`.
- With `grant_type=client_credentials`, Meta returns an **application access token**. That token is useful for a limited set of app-level or server-to-server calls; it generally **cannot** read group feeds the way a **User** or **Page** access token can (those require login, correct permissions, and often App Review).
- For this project, put a suitable **User or Page access token** (with group access as allowed by Meta) into `FACEBOOK_ACCESS_TOKEN` in `.env`.
- **Never commit** `.env`, never paste **App Secret** or user tokens into issues, chat, or screenshots. If a secret was exposed, **rotate the App Secret** in the Meta Developer Console and re-issue tokens.

### Optional: fetch an *app* access token locally

**Use your real values.** `YOUR_APP_ID` means “replace this with the actual number”, not the words `your app id`. The App ID is **digits only** (Meta for Developers → your app → **App settings → Basic** → *App ID*). Same screen shows *App secret* (click Show).

Either put `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET` in `.env` and run from the repo folder (the script loads `.env` automatically), or export them:

```bash
cd fc_searcher
export FACEBOOK_APP_ID=1234567890123456    # example shape: long numeric ID only
export FACEBOOK_APP_SECRET=your_real_secret_here
python3 scripts/fetch_app_access_token.py --token-only
```

On macOS, use **`python3`** (there is often no `python` command).

If you see **`Invalid Client ID`**, Meta rejected the `client_id` value: wrong digits, extra characters, or you accidentally used placeholder text (e.g. `…your app id…`) instead of the real App ID.

Equivalent `curl` (placeholders — replace with your values via env vars):

```bash
curl -sG "https://graph.facebook.com/v21.0/oauth/access_token" \
  --data-urlencode "client_id=${FACEBOOK_APP_ID}" \
  --data-urlencode "client_secret=${FACEBOOK_APP_SECRET}" \
  --data-urlencode "grant_type=client_credentials"
```

## Requirements

- Python **3.11+** (for local development and tests)
- Docker / Docker Compose (recommended runtime)
- Facebook Graph API token with access to target groups
- Anthropic API key (optional but recommended for analysis)
- SMTP credentials (optional until you enable email)

## Meta: app, user token, and group feed (automation from `.env`)

Steps 1–3 are done in [Meta for Developers](https://developers.facebook.com/) and [Graph API Explorer](https://developers.facebook.com/tools/explorer/) (create app, request current permissions for your product, generate a **user** short-lived token). Permission names and review rules change — always confirm against Meta’s docs for your `GRAPH_API_VERSION`.

**If Explorer will not give you a user token**, use Facebook Login on localhost instead (no Explorer paste):

1. In the Meta app, add **Facebook Login** and set **Valid OAuth Redirect URIs** to the exact URL the script prints (default uses `http://127.0.0.1:8765/oauth/facebook-callback`).
2. Run:

```bash
# Recommended wrapper (scopes: public_profile + groups_access_member_info; override with FACEBOOK_OAUTH_SCOPES)
./scripts/oauth_facebook_user_token_groups.sh

# Or explicit one line (no spaces after commas):
python3 scripts/oauth_facebook_user_token.py --open-browser --scopes public_profile,groups_access_member_info
```

Confirm scope names against [Meta documentation](https://developers.facebook.com/docs/) for your `GRAPH_API_VERSION`; remove or add permissions your app type allows.

3. Copy the printed token into **`FACEBOOK_SHORT_TOKEN`**, then run **`exchange_user_long_lived_token.py`** as below.

**If the browser says Login is unavailable / “обновляем дополнительную информацию” (Meta is updating app information):** that comes from Meta’s servers, not this repo. In [Meta for Developers](https://developers.facebook.com/) open **your app** → **Alerts / Use cases / App settings** and clear every **required action** (privacy policy URL, data-deletion URL, icon, contact email, business verification, data handling questions, etc.). Incomplete **Facebook Login** or **Business** verification often blocks all user login until fixed. Retry after a few hours if the dashboard shows no remaining tasks and the message persists (rare platform maintenance).

**Step 4 — Long-lived user token** (reads `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_SHORT_TOKEN` from the **project root** `.env`, same rules as `admin_request.py` — `export KEY=…` is fine):

```bash
cd fc_searcher
# Put the Explorer token in FACEBOOK_SHORT_TOKEN=... in .env first
python3 scripts/exchange_user_long_lived_token.py
# or: python3 scripts/exchange_user_long_lived_token.py --token-only
```

Copy the printed `access_token` into **`FACEBOOK_ACCESS_TOKEN`** in `.env`.

**Step 5 — Test group feed** (uses `FACEBOOK_ACCESS_TOKEN`, first id in `FACEBOOK_GROUP_IDS`, `GRAPH_API_VERSION`):

```bash
python3 scripts/test_facebook_group_feed.py
# optional: print granted scopes (needs FACEBOOK_APP_ID + FACEBOOK_APP_SECRET)
python3 scripts/test_facebook_group_feed.py --diagnose
# target one numeric group URL without editing `.env` (overrides FACEBOOK_GROUP_IDS for this run):
python3 scripts/test_facebook_group_feed.py --group-url 'https://www.facebook.com/groups/934750153812574'
```

Typical outcomes: **200** + JSON `data` → OK for this monitor; **(#3) Missing Permission** → token/scopes/app mode; wrong id → **(#100)** etc.

**Alternative: your own timeline (no groups)** — if you only need the logged-in user’s posts via Graph **`GET /me/feed`** (not group feeds), set in `.env`:

- `FACEBOOK_SYNC_MODE=me`
- `FACEBOOK_GROUP_IDS=` may be empty.

Then `POST /admin/sync` pulls `/me/feed`; posts are stored with `group_id` **`user`**. Meta usually requires permissions beyond `public_profile` (e.g. **`user_posts`** — confirm current names for your `GRAPH_API_VERSION`). Quick check:

```bash
python3 scripts/test_facebook_me_feed.py
```

**Step 6 —** keep `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_ACCESS_TOKEN`, and either `FACEBOOK_GROUP_IDS` (when `FACEBOOK_SYNC_MODE=groups`) or `FACEBOOK_SYNC_MODE=me` as in [`.env.example`](.env.example).

### Development in the EU / when Meta blocks Login (no live Graph)

There is **no supported public “search the whole of Facebook” API** for arbitrary groups; Meta expects **your app + user consent + often App Review**. Scraping facebook.com is **against Meta’s terms**, brittle, and legally risky in Germany (GDPR, unfair competition, platform rules).

For **local development** (DB, sync, keyword filtering, reports) without calling Meta, use a **fixture file** that looks like a Graph feed response:

1. Copy [tests/fixtures/sample_group_feed.json](tests/fixtures/sample_group_feed.json) or export a real `data` array from Graph when you eventually have access.
2. In `.env` set:

   - `FACEBOOK_MOCK_FEED_JSON=/absolute/or/repo-relative/path/to/feed.json`
   - `FACEBOOK_GROUP_IDS=999` (any numeric id; post IDs are prefixed so they stay unique per group)
   - `FACEBOOK_ACCESS_TOKEN` may be left empty when only the mock path is set.

3. Run sync: `POST /admin/sync` — `/health` shows `facebook_mock_feed_json: true`. Posts are stored with `source` `mock_json`.

Replace the mock path with a real token when Meta finishes app verification and Login works again.

## Quick start (Docker)

```bash
cd fc_searcher
cp .env.example .env
# Edit .env — set FACEBOOK_ACCESS_TOKEN, ADMIN_TOKEN, and either FACEBOOK_GROUP_IDS (default) or FACEBOOK_SYNC_MODE=me

docker compose up --build -d
curl -s http://localhost:5000/health | jq .
```

After you change **`.env`**, either recreate the stack **or** rely on the mounted file (see `docker-compose.yml`: `./.env` → `/app/.env`). On each **`/health`**, **`/admin/*`**, and **scheduled** sync/report, the app re-reads `/app/.env` when present and refreshes settings (so `FACEBOOK_GROUP_IDS` is not “stuck” from an old process snapshot).

```bash
docker compose up -d --force-recreate   # still needed after docker-compose.yml changes
```

`FACEBOOK_GROUP_IDS` is **never** hardcoded in Python; it always comes from your environment / `.env`. If sync still shows an old `group_id`, your `.env` on disk still contains that id—edit the line, save, then call `./scripts/admin_request.sh sync` again (no rebuild required when the mount is active).

### Admin API (protected)

Set `ADMIN_TOKEN` in `.env`, then either use curl or the helper (loads `.env` safely — **do not** `source .env` if any line is not `KEY=value`):

```bash
./scripts/admin_request.sh sync    # needs FACEBOOK_ACCESS_TOKEN + FACEBOOK_GROUP_IDS
./scripts/admin_request.sh report  # builds CSV under ./reports; email if SMTP set
./scripts/admin_request.sh report-browser-html-last   # one email: daily CSVs + latest report/search_*/index.html
./scripts/admin_request.sh search berlin --limit 20   # substring search on stored posts
```

For **`report-browser-html-last`**, the email includes the main **CSV**, **`daily_posts_<run_stamp>.html`** (HTML table with the **same rows** as that CSV), and a copy of the latest Playwright **`report/search_*/index.html`** (`browser_search_<browser_html_search_stamp>_daily_<run_stamp>.html`). JSON includes **`daily_posts_html`** (path to the CSV-aligned file), **`run_stamp`** (daily build id), and **`browser_html_search_stamp`** (Playwright folder UTC id).

With curl (after `export ADMIN_TOKEN=...` from `.env`):

```bash
curl -s -X POST http://localhost:5000/admin/sync \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq .

curl -s -X POST http://localhost:5000/admin/report \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq .

curl -sG "http://localhost:5000/admin/posts/search" \
  --data-urlencode "q=keyword" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | jq .
```

`/admin/sync` returns **HTTP 200** only when every group feed request succeeds (`ok: true`). Graph errors such as `(#3) Missing Permission` set **`ok: false`**, include a short **`error`** summary, and respond with **HTTP 400** so scripts and monitors can treat the run as failed.

### Public keyword search (optional, off by default)

`GET /search?q=…` uses the same stored-post lookup as `/admin/posts/search` but **does not** require `ADMIN_TOKEN`. It is disabled unless you set **`ENABLE_PUBLIC_POST_SEARCH=true`**. Treat it as sensitive: only enable on trusted networks, behind your own auth gateway, or for local demos. `/health` includes `enable_public_post_search` so you can confirm the flag.

```bash
curl -sG "http://localhost:5000/search" --data-urlencode "q=keyword" | jq .
```

### Browser-based Facebook group search sync (Playwright)

This project now also supports an opt-in browser flow that searches Facebook groups for a phrase, opens groups one by one, searches inside them, and stores found posts into the same `posts` table with source `playwright_browser`.

Set these env vars to enable it:

- `ENABLE_BROWSER_SEARCH_SYNC=true`
- `BROWSER_SEARCH_QUERY=job` — phrase for **global** Facebook group discovery (`/search/groups/?q=`)
- Optional: `BROWSER_IN_GROUP_SEARCH_QUERY` — comma-separated **tokens**; each group search phase uses **`BROWSER_SEARCH_QUERY` + space + token** (e.g. `ищу работу` + `малярные работы`). When unset, `BROWSER_SEARCH_QUERY` alone is used for in-group search
- `BROWSER_GROUP_SCAN_LIMIT=20` (max **100**; caps **Facebook `/search/groups`** picks only — **every** `BROWSER_SEED_GROUP_URLS` entry is still scanned, then up to this many extra groups from search)
- `BROWSER_POST_LIMIT_PER_GROUP=25`
- `BROWSER_HEADLESS=false`
- `BROWSER_SEARCH_TIMEOUT_SECONDS=45`
- Optional: `BROWSER_SEED_GROUP_URLS` — comma-separated `https://www.facebook.com/groups/NUMERIC_ID/...` URLs or numeric ids; each is opened **before** results from Facebook group search (so you can always include a known group).

#### Maximizing distinct groups (and reading the daily CSV)

- **Daily report CSV rows are per post**, not per group. The `group_id` column repeats whenever several posts came from the same Facebook group (expected).
- **One global discovery query per browser run**: `BROWSER_SEARCH_QUERY` (or JSON `query` / CLI `--query`) drives a single `/search/groups/?q=…` pass. Different wording (language, city, niche) usually surfaces different group links.
- **Hard cap (discovery only)**: `BROWSER_GROUP_SCAN_LIMIT` and admin `group_limit` are clamped to **100** in code and limit only how many **extra** groups are taken from `/search/groups`. Values above 100 have no effect on discovery.
- **Raise the cap** (up to 100): set `BROWSER_GROUP_SCAN_LIMIT=100` in `.env`, or pass `"group_limit": 100` to `POST /admin/browser-search-sync`, or `--group-limit 100` on `scripts/run_browser_search_once.py`. With Docker, `.env` is mounted read-only in `docker-compose.yml`; after editing, run `docker compose up -d --force-recreate` so the container reloads it (changing only `src/` still needs `docker compose build` to refresh the image).
- **Seeds**: `BROWSER_SEED_GROUP_URLS` (and optional `seed_group_urls` in the admin JSON) list groups that are **all** opened and searched; the scan limit does **not** truncate seeds. Discovery groups are added after seeds, up to the limit.
- **More groups over time**: run additional passes with **different** `query` / `BROWSER_SEARCH_QUERY` (or different seeds) so the database accumulates more distinct `group_id`s across runs.
- **More posts, not more groups**: comma-separated `BROWSER_IN_GROUP_SEARCH_QUERY` (prefixed phases) or JSON `in_group_queries` runs multiple `/groups/…/search/?q=` phrases on the **same** merged group list in one session. JSON `in_group_queries` is passed through **without** auto-prefix (full control from the client).

The first version expects a human to complete Facebook login in the opened browser window during the run.

If Playwright fails with **`listen EINVAL`** on a path under **`/var/folders/.../T/`** (macOS default temp), the runner now forces **`TMPDIR=/tmp/fc-searcher-pw`** for the `npx` process so Unix socket paths stay short. Retry after a normal **`run_browser_search_once`** / MCP run; if it persists, upgrade Node/playwright (`npx --yes @playwright/cli@latest`) or run from a regular Terminal (not a restricted sandbox).

Protected admin trigger:

```bash
curl -s -X POST http://localhost:5000/admin/browser-search-sync \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"job","in_group_query":"ищу работу","group_limit":5,"post_limit_per_group":10,"seed_group_urls":"https://www.facebook.com/groups/934750153812574/"}' | jq .
```

MCP tool (same pipeline as `POST /admin/browser-search-sync`):

- `facebook_browser_search_sync` — optional args: `query` (global discovery), **`in_group_query`** (per-group `/search/?q=`), `group_limit`, `post_limit_per_group`, **`seed_group_urls`** (comma-separated URLs or ids, same as `BROWSER_SEED_GROUP_URLS`)

### Meta webhook

1. Expose `https://<your-domain>/webhook/facebook` to the internet.
2. Set `WEBHOOK_VERIFY_TOKEN` and `FACEBOOK_APP_SECRET` in `.env`.
3. Configure the subscription in Meta; complete the GET verification challenge.

## MCP (optional)

The **`mcp`** package needs **Python 3.10 or newer**. On macOS, **`/usr/bin/python3`** (Xcode) is often **3.9**; installs then fail with *“No matching distribution found for mcp”*. Use Homebrew’s Python or a venv created from **`python3.12`** / **`python3.11`**, not stock `python3` alone.

**Recommended (venv with Homebrew Python 3.12):**

```bash
cd fc_searcher
brew install python@3.12
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mcp.txt
```

(Intel Mac Homebrew: try `/usr/local/bin/python3.12` instead of `/opt/homebrew/bin/`.)

**If pip still says “No matching distribution for mcp”** and log lines show **`./.venv/lib/python3.9/`**, your **`.venv` was created with Python 3.9**. Delete it and recreate with 3.12+ (after `brew install python@3.12`):

```bash
cd fc_searcher
rm -rf .venv
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mcp.txt
```

Or run the helper (prompts before deleting `.venv`; use `RECREATE_VENV_FORCE=1` to skip the prompt):

```bash
./scripts/recreate_venv_for_mcp.sh
```

**Alternative:** [uv](https://docs.astral.sh/uv/) — `uv python install 3.12 && uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements-mcp.txt`

On macOS there is often no **`pip`** on `PATH`; use **`…/python -m pip`** as above.

If you already upgraded pip for user site-packages only, prefer a **`.venv` inside the repo** so dependencies are isolated and Cursor’s `run_mcp_server.sh` picks them up automatically.

**Run the stdio server manually** (from repo root; uses `.venv` / `.venv-py312` if present):

```bash
./scripts/run_mcp_server.sh
```

Equivalent (same interpreter you used for `pip install`):

```bash
.venv/bin/python -m src.mcp_server
```

**Cursor (project MCP):** this repo ships **`.cursor/mcp.json`**. It starts `scripts/run_mcp_server.sh`, sets **`cwd`** to the workspace, and loads **`envFile`** → **`${workspaceFolder}/.env`** so `FACEBOOK_*`, `ENABLE_BROWSER_SEARCH_SYNC`, etc. apply without duplicating secrets in JSON. Restart Cursor after changing `mcp.json` or `.env`.

**Tools:** `facebook_sync_posts`, `facebook_search_group_keyword`, `facebook_browser_search_sync`, `facebook_send_daily_report`.

### Browser sync via MCP (manual Facebook login)

When Graph returns **permission / visibility** errors for a group id that is correct in the URL (for example **code 100**, **subcode 33**), `facebook_sync_posts` will not load the feed; use **`facebook_browser_search_sync`** instead so Playwright can drive a real browser session.

1. In **`.env`**: `ENABLE_BROWSER_SEARCH_SYNC=true`, `BROWSER_HEADLESS=false`, and `BROWSER_SEARCH_TIMEOUT_SECONDS` high enough to log in (e.g. `180`). Optionally set `BROWSER_SEARCH_QUERY` (default `job`).
2. Install **`requirements-mcp.txt`** and ensure **Node** is available for `npx` (or your Codex Playwright wrapper, if you use it).
3. Put **`BROWSER_SEED_GROUP_URLS=https://www.facebook.com/groups/934750153812574`** (or your URLs) in **`.env`** if you want seeds on every run; save the file.
4. **Restart Cursor** (quit the app) so MCP reloads **`mcp.json`** and the server picks up the updated **`.env`** (`envFile` in [`.cursor/mcp.json`](.cursor/mcp.json)).
5. **Cursor Settings → MCP:** confirm **`facebook-monitor`** is enabled and not showing an error.
6. In **Chat / Agent**, ask to run the MCP tool **`facebook_browser_search_sync`** (arguments can be empty — **`seed_group_urls` is optional** when it is already set in `.env`). A browser window should open; **log in to Meta manually**, then wait until the tool returns JSON with `ok`, `upserted`, etc.

**Same run without MCP (terminal):** from the repo root, with `.env` loaded:

```bash
.venv/bin/python scripts/run_browser_search_once.py
# optional: --query "…" --seed-group-urls "https://…" (merges with BROWSER_SEED_GROUP_URLS)
```

If you use bare `python3` on macOS it is often **3.9** — run **`./scripts/recreate_venv_for_mcp.sh`** (or `brew install python@3.12` + new `.venv`), then **`scripts/run_browser_search_once.py`** will **re-exec** with **`.venv-py312`**, **`.venv`** (only if ≥3.10), or **Homebrew `python3.12`**, when the current interpreter is too old.

## Production database overlay

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Do not publish PostgreSQL to the public internet; keep it on the internal Compose network only.

## Tests and lint

```bash
python3 -m pip install -r requirements.txt ruff pytest
ruff check src tests
pytest -q
```

## Layout

- `.cursor/mcp.json` — Cursor MCP stdio config (`facebook-monitor` server)
- `scripts/run_mcp_server.sh` — launcher used by MCP (Python 3.10+ only)
- `scripts/recreate_venv_for_mcp.sh` — rebuild `.venv` with Homebrew 3.12+ for `mcp`
- `scripts/run_browser_search_once.py` — one-shot browser sync from `.env` (no MCP client)
- `wsgi.py` — Gunicorn entry (`wsgi:app`); avoids `--factory` for older Gunicorn builds
- `src/main.py` — Flask app factory and optional APScheduler
- `src/services/` — Graph client, Claude, email, sync/report pipeline
- `src/webhooks/` — Meta signature verification and ingest
- `src/jobs/scheduler.py` — Cron definitions
- `templates/report.html.j2` — HTML email body
- `deploy/prometheus.yml` — optional scrape config (requires `/metrics`)

Gunicorn runs with `--workers 1` so scheduled jobs are not duplicated.
