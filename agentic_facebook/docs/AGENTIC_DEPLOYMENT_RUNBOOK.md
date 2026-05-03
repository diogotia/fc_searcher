# Agentic Facebook Orchestrator — Deployment & Operations Runbook

## Phase 1: Environment Setup (One-Time)

### 1.1 Verify Project Structure

```bash
# Confirm these files exist:
ls -la scripts/run_agentic_facebook_exact_posts.py
ls -la scripts/run_agentic_facebook_once.py
ls -la scripts/run_agentic_facebook_once_exact_year.py
ls -la scripts/run_agentic_facebook_once_anthropic.py  # If using Vision API

# Confirm output directories exist or can be created:
mkdir -p output/agentic_facebook
mkdir -p report/agentic_search
```

### 1.2 Environment Variables (.env)

```bash
# Required for ALL agentic scripts:
export ENABLE_AGENTIC_FACEBOOK_SYNC=true
export BROWSER_SEARCH_QUERY="ищу работу в Германии"
export BROWSER_IN_GROUP_SEARCH_QUERY="ищу работу Бетонщик,ищу работу Арматурщик,ищу работу Каменщик"

# Optional (pre-seed group URLs):
export BROWSER_SEED_GROUP_URLS="https://www.facebook.com/groups/123456,https://www.facebook.com/groups/789012"

# Database connection:
export DATABASE_URL="postgresql://user:pass@host:5432/facebook_monitor"

# Playwright (optional, defaults to local Chrome):
export PLAYWRIGHT_CHROMIUM_PATH="/usr/bin/chromium-browser"

# Output paths (match src/config.py):
export AGENTIC_FACEBOOK_OUTPUT_DIR="output/agentic_facebook"

# Limits (defaults in .env; CLI --group-limit / --post-limit override):
export BROWSER_GROUP_SCAN_LIMIT=50
export BROWSER_POST_LIMIT_PER_GROUP=100

# Logging:
export LOG_LEVEL=INFO
export LOG_FILE="logs/agentic_facebook.log"
```

### 1.3 Python Virtual Environment

```bash
# Create venv if not exists:
python3 -m venv .venv

# Activate:
source .venv/bin/activate

# Install dependencies:
pip install --upgrade pip
pip install -r requirements.txt   # or requirements-mcp.txt for MCP/scripts stack

# Browser automation uses Playwright CLI (`playwright-cli` / project wrapper); ensure Node/npx available if using defaults.
# Optional: install Chromium for `@playwright/test`-style usage — not strictly required if cli uses system Chrome.
```

### 1.4 Facebook Account Setup

```bash
# For manual 2FA/checkpoint handling:
# 1. Open browser: chromium or your local Chrome
# 2. Navigate to facebook.com
# 3. Log in with account credentials
# 4. Complete any 2FA or checkpoint
# 5. Let browser close (session may persist in cache)

# Restart agentic script (will reuse session if available)
```

---

## Phase 2: Pre-Execution Checklist

**Repo shortcut:** from the project root, run **`./scripts/agentic_preflight.sh`** (loads `.env` via `load_repo_env` and checks venv, scripts, and `ENABLE_AGENTIC_FACEBOOK_SYNC`).

The block below is a longer **inline** alternative you can still save as `preflight.sh` if you want extra checks (disk, ping):

```bash
#!/bin/bash
# Save as: preflight.sh (optional extended variant)

echo "=== AGENTIC FACEBOOK ORCHESTRATOR: PREFLIGHT CHECK ==="

# 1. Config
echo "[1/8] Checking environment variables..."
[ -z "$ENABLE_AGENTIC_FACEBOOK_SYNC" ] && echo "  ✗ ENABLE_AGENTIC_FACEBOOK_SYNC not set" && exit 1
[ -z "$BROWSER_SEARCH_QUERY" ] && echo "  ✗ BROWSER_SEARCH_QUERY not set" && exit 1
echo "  ✓ Config OK"

# 2. Directories
echo "[2/8] Checking directories..."
mkdir -p output/agentic_facebook report/agentic_search logs
echo "  ✓ Directories OK"

# 3. Disk space
echo "[3/8] Checking disk space..."
AVAILABLE=$(df output/agentic_facebook | awk 'NR==2 {print $4}')
if [ "$AVAILABLE" -lt 500000 ]; then
  echo "  ✗ Less than 500MB free (have ${AVAILABLE}KB)"
  exit 1
fi
echo "  ✓ Disk space OK (${AVAILABLE}KB free)"

# 4. Python
echo "[4/8] Checking Python environment..."
[ ! -d ".venv" ] && echo "  ✗ Virtual env not found" && exit 1
source .venv/bin/activate
python -c "import playwright, requests, sqlalchemy" || { echo "  ✗ Dependencies missing"; exit 1; }
echo "  ✓ Python OK"

# 5. Database
echo "[5/8] Checking database..."
python -c "
import os
from sqlalchemy import create_engine, text
try:
    engine = create_engine(os.getenv('DATABASE_URL'))
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('  ✓ Database OK')
except Exception as e:
    print(f'  ✗ Database error: {e}')
    exit(1)
"

# 6. Network
echo "[6/8] Checking network..."
ping -c 1 facebook.com > /dev/null 2>&1 || { echo "  ✗ Cannot reach facebook.com"; exit 1; }
echo "  ✓ Network OK"

# 7. Scripts
echo "[7/8] Checking scripts..."
[ ! -f "scripts/run_agentic_facebook_exact_posts.py" ] && echo "  ✗ Missing scripts" && exit 1
echo "  ✓ Scripts OK"

# 8. Logs
echo "[8/8] Checking logs..."
touch logs/agentic_facebook.log || { echo "  ✗ Cannot write to logs"; exit 1; }
echo "  ✓ Logs OK"

echo ""
echo "=== ALL CHECKS PASSED ==="
echo "Ready to execute. Choose script and run:"
echo "  python scripts/run_agentic_facebook_exact_posts.py --query '...' --in-group-query '...'"
```

Run preflight:
```bash
chmod +x preflight.sh
./preflight.sh
```

---

## Phase 3: Execution Runbooks (Choose One)

### **Runbook A: Full-Text Job Posts (exact_posts)**

```bash
#!/bin/bash
# save as: run_job_posts_exact.sh

set -e
source .venv/bin/activate

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
QUERY="${1:-ищу работу в Германии}"
IN_GROUP_QUERY="${2:-ищу работу Бетонщик,ищу работу Арматурщик,ищу работу Каменщик}"
GROUP_LIMIT="${3:-50}"
POST_LIMIT="${4:-100}"

echo "========================================"
echo "AGENTIC FACEBOOK ORCHESTRATOR: EXACT POSTS"
echo "========================================"
echo "Timestamp:       $TIMESTAMP"
echo "Query:           $QUERY"
echo "In-group Query:  $IN_GROUP_QUERY"
echo "Group Limit:     $GROUP_LIMIT"
echo "Post Limit:      $POST_LIMIT"
echo ""

python scripts/run_agentic_facebook_exact_posts.py \
  --query "$QUERY" \
  --in-group-query "$IN_GROUP_QUERY" \
  --in-group-exact-keywords \
  --group-limit "$GROUP_LIMIT" \
  --post-limit "$POST_LIMIT" \
  2>&1 | tee "logs/exact_posts_${TIMESTAMP}.log"

echo ""
echo "Execution completed. Check:"
echo "  - Output: output/agentic_facebook/"
echo "  - Report: report/agentic_search_*/"
echo "  - Logs:   logs/exact_posts_${TIMESTAMP}.log"
```

Usage:
```bash
chmod +x run_job_posts_exact.sh
./run_job_posts_exact.sh "ищу работу в Германии" "бетон,армат,камен" 30 75
```

---

### **Runbook B: Fast Exploratory Scan (once)**

```bash
#!/bin/bash
# save as: run_fast_scan.sh

set -e
source .venv/bin/activate

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
QUERY="${1:-tech jobs}"
GROUP_LIMIT="${2:-20}"
POST_LIMIT="${3:-50}"

echo "========================================"
echo "AGENTIC FACEBOOK ORCHESTRATOR: FAST SCAN"
echo "========================================"
echo "Timestamp:    $TIMESTAMP"
echo "Query:        $QUERY"
echo "Group Limit:  $GROUP_LIMIT"
echo "Post Limit:   $POST_LIMIT"
echo ""

python scripts/run_agentic_facebook_once.py \
  --query "$QUERY" \
  --group-limit "$GROUP_LIMIT" \
  --post-limit "$POST_LIMIT" \
  2>&1 | tee "logs/once_${TIMESTAMP}.log"

echo ""
echo "Execution completed."
```

Usage:
```bash
chmod +x run_fast_scan.sh
./run_fast_scan.sh "tech jobs Berlin" 15 40
```

---

### **Runbook C: Year-Filtered Historical (exact_year)**

```bash
#!/bin/bash
# save as: run_historical_scan.sh

set -e
source .venv/bin/activate

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
QUERY="${1:-Україна Німеччина}"
GROUP_LIMIT="${2:-30}"
POST_LIMIT="${3:-100}"

echo "========================================"
echo "AGENTIC FACEBOOK ORCHESTRATOR: EXACT YEAR (URL filters=)"
echo "========================================"
echo "Timestamp:    $TIMESTAMP"
echo "Query:        $QUERY"
echo "Year filter:  from BROWSER_POST_PUBLICATION_YEAR in .env (required)"
echo "Group Limit:  $GROUP_LIMIT"
echo "Post Limit:   $POST_LIMIT"
echo ""

python scripts/run_agentic_facebook_once_exact_year.py \
  --query "$QUERY" \
  --group-limit "$GROUP_LIMIT" \
  --post-limit "$POST_LIMIT" \
  2>&1 | tee "logs/exact_year_${TIMESTAMP}.log"

echo ""
echo "Execution completed."
```

Usage:
```bash
chmod +x run_historical_scan.sh
./run_historical_scan.sh "Україна Німеччина" 25 80
```

---

## Phase 4: Monitoring During Execution

### **Live Tail (In New Terminal)**

```bash
# Watch logs in real-time:
tail -f logs/agentic_facebook.log

# Watch output directory:
watch -n 5 'ls -la output/agentic_facebook/ | tail -20'

# Monitor system resources:
watch -n 2 'ps aux | grep run_agentic'
```

### **Expected Timing**

```
Group discovery:     3–5 groups/minute
Post scraping:       2–5 posts/second
See-more expansion:  1–2 seconds per post (exact_posts only)
Total time estimate: N groups × (30 sec discovery + posts × 0.5 sec) + overhead
                     ~1–3 minutes for 50 groups, 100 posts each
```

### **Signals That Something Is Wrong**

```
❌ Scraping stalled (0 posts in 60+ seconds)
   → Likely 2FA checkpoint
   → Action: Check browser window; complete checkpoint; restart script

❌ "expand_see_more: false" across all posts
   → Selector mismatch ("Ещё" button not found)
   → Action: Inspect DOM, update script

❌ High CPU / OOM killer
   → Too many posts in memory
   → Action: Reduce --post-limit; split into smaller runs

❌ Database connection fails
   → Network or credentials issue
   → Action: Test DATABASE_URL independently; check firewall

❌ No groups found
   → Query doesn't match Facebook groups
   → Action: Verify query on facebook.com manually
```

---

## Phase 5: Post-Execution Validation

### **5.1 Automated Verification**

```bash
#!/bin/bash
# save as: verify_output.sh

LATEST_DIR=$(ls -td output/agentic_facebook/*/ | head -1)
TIMESTAMP=$(basename "$LATEST_DIR")

echo "Verifying: $LATEST_DIR"
echo ""

# 1. Check files exist
echo "[1] Checking files..."
[ -f "$LATEST_DIR/posts.jsonl" ] && echo "  ✓ posts.jsonl exists" || { echo "  ✗ posts.jsonl missing"; exit 1; }
[ -f "$LATEST_DIR/summary.json" ] && echo "  ✓ summary.json exists" || { echo "  ✗ summary.json missing"; exit 1; }

# 2. Parse summary
echo "[2] Checking summary..."
python -c "
import json
with open('$LATEST_DIR/summary.json') as f:
    s = json.load(f)
    print(f\"  Groups scanned: {s['groups_scanned']}\")
    print(f\"  Posts found: {s['posts_found']}\")
    print(f\"  Posts upserted: {s['posts_upserted']}\")
    if s['ok']:
        print('  ✓ Summary valid')
    else:
        print(f\"  ✗ Errors: {s['errors']}\")
"

# 3. Check JSONL format
echo "[3] Checking JSONL..."
LINE_COUNT=$(wc -l < "$LATEST_DIR/posts.jsonl")
echo "  Posts in JSONL: $LINE_COUNT"
head -1 "$LATEST_DIR/posts.jsonl" | python -m json.tool > /dev/null && echo "  ✓ JSONL valid" || { echo "  ✗ JSONL malformed"; exit 1; }

# 4. Check HTML report
echo "[4] Checking HTML report..."
REPORT_DIR="report/agentic_search_${TIMESTAMP}/"
if [ -d "$REPORT_DIR" ]; then
  echo "  ✓ Report directory exists: $REPORT_DIR"
  [ -f "$REPORT_DIR/index.html" ] && echo "  ✓ index.html exists" || echo "  ⚠ index.html missing"
fi

# 5. Security: No secrets
echo "[5] Checking for secrets..."
if grep -r "password\|secret\|api_key" "$LATEST_DIR" 2>/dev/null; then
  echo "  ✗ Potential secrets found!"
  exit 1
else
  echo "  ✓ No secrets detected"
fi

echo ""
echo "=== VALIDATION COMPLETE ==="
echo "All checks passed. Output ready for use."
```

Run verification:
```bash
chmod +x verify_output.sh
./verify_output.sh
```

### **5.2 Manual Spot Checks**

```bash
# Check a few posts:
head -5 output/agentic_facebook/*/posts.jsonl | python -m json.tool

# Verify keyword matching (exact_posts):
cat output/agentic_facebook/*/posts.jsonl | \
  python -c "
import json, sys
for line in sys.stdin:
    post = json.loads(line)
    if 'metadata' in post and 'body_keyword_match' in post['metadata']:
        print(f\"✓ {post['metadata']['body_keyword_match']}\")
  "

# Count by keyword:
cat output/agentic_facebook/*/posts.jsonl | \
  python -c "
import json, sys
from collections import Counter
keywords = Counter()
for line in sys.stdin:
    post = json.loads(line)
    kw = post.get('metadata', {}).get('body_keyword_match')
    if kw:
        keywords[kw] += 1
for kw, count in keywords.most_common():
    print(f'{kw}: {count}')
  "
```

---

## Phase 6: Troubleshooting by Symptom

| **Symptom** | **Root Cause** | **Fix** |
|-----------|----------------|--------|
| `ERROR: ENABLE_AGENTIC_FACEBOOK_SYNC not found` | `.env` not loaded | `source .env` or add to `.bashrc` |
| `ModuleNotFoundError: playwright` | Missing dependency | `pip install -r requirements.txt` |
| `Facebook checkpoint required` | 2FA / anti-bot | Manually complete in browser, restart script |
| `expand_see_more: false` (all posts) | Selector wrong | Check DOM, update `scripts/run_agentic_facebook_exact_posts.py` line XYZ |
| `0 posts upserted (found 50)` | Keyword filter too strict | Relax `--in-group-query` or remove `--in-group-exact-keywords` |
| `psycopg2.OperationalError: FATAL: password authentication failed` | DB credentials wrong | Check `DATABASE_URL` in `.env` |
| `OSError: No space left on device` | Disk full | `du -sh output/agentic_facebook/` and clean old runs |
| `No groups found` | Query doesn't exist on Facebook | Verify query on facebook.com manually |
| Script hangs (30+ seconds no output) | Likely network stall or browser freeze | Restart; check network (`ping facebook.com`) |

---

## Phase 7: Scheduled Runs (Optional)

### **Cron Job for Daily Runs**

```bash
# Edit crontab:
crontab -e

# Add daily run at 02:00 UTC:
0 2 * * * cd /path/to/fc_searcher && source .venv/bin/activate && python scripts/run_agentic_facebook_exact_posts.py --query "ищу работу в Германии" --in-group-query "бетон,армат,камен" --group-limit 50 --post-limit 100 >> logs/cron.log 2>&1

# Verify:
crontab -l
```

### **Slack Notification (Post-Run)**

```bash
# Add to end of runbook script:

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SUMMARY=$(cat output/agentic_facebook/*/summary.json)

curl -X POST -H 'Content-type: application/json' \
  --data "{
    \"text\": \"✓ Agentic Facebook run completed\",
    \"blocks\": [
      {\"type\": \"section\", \"text\": {\"type\": \"mrkdwn\", \"text\": \"*Groups*: $(echo $SUMMARY | jq .groups_scanned)\n*Posts*: $(echo $SUMMARY | jq .posts_upserted)\"}}
    ]
  }" \
  YOUR_SLACK_WEBHOOK_URL
```

---

## Phase 8: Quick Reference (Print This)

```
╔════════════════════════════════════════════════════════════╗
║ AGENTIC FACEBOOK ORCHESTRATOR: QUICK LAUNCH               ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║ 1. Preflight:                                             ║
║    ./preflight.sh                                         ║
║                                                            ║
║ 2. Choose one:                                            ║
║                                                            ║
║    EXACT POSTS (full text + keywords):                    ║
║    ./run_job_posts_exact.sh                               ║
║                                                            ║
║    FAST SCAN (exploratory):                               ║
║    ./run_fast_scan.sh "query" 20 50                       ║
║                                                            ║
║    HISTORICAL (year-filtered):                            ║
║    ./run_historical_scan.sh "query" 2024 30 100           ║
║                                                            ║
║ 3. Monitor:                                               ║
║    tail -f logs/agentic_facebook.log                      ║
║                                                            ║
║ 4. Verify:                                                ║
║    ./verify_output.sh                                     ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

---

## Common Issues & Fixes at a Glance

```bash
# Issue: "Cannot connect to database"
# Fix:
psql $DATABASE_URL -c "SELECT 1"

# Issue: "No groups found"
# Fix:
# Open facebook.com in browser, search manually, verify query

# Issue: "See-more not expanding"
# Fix:
# Check DOM: right-click post → Inspect → find "Ещё" / "More" button
# Update selector in run_agentic_facebook_exact_posts.py

# Issue: Large DB footprint (want smaller)
# Fix:
# Use exact_posts with --in-group-exact-keywords to filter by keywords

# Issue: Post text still truncated
# Fix:
# exact_posts script attempts best-effort expansion
# If still truncated, it's a Facebook UI limitation (not a bug)

# Issue: Run takes too long
# Fix:
# Reduce --group-limit or --post-limit
# Or split query into multiple runs with different keywords
```

---

**End of Deployment Runbook. Ready to execute!**
