# Agentic Facebook Orchestrator — Decision Trees & Routing

## 1. Script Selection Flow (5-Second Decision)

```
┌─────────────────────────────────────────────────────────────────┐
│ TASK: What are you trying to do?                                │
└─────────────────────────────────────────────────────────────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
        [User Input]         [Script Choice]
                │                     │
    ┌───────────┼───────────┐        │
    │           │           │        │
   1A          1B          1C        │
    │           │           │        │
    
1A: "I need EVERY post, truncation is OK"
    ↓
    ├─ "...but from specific YEARS"
    │  └─ → run_agentic_facebook_once_exact_year.py
    │
    └─ "...just fast scan"
       └─ → run_agentic_facebook_once.py

1B: "I need FULL post text (no truncation)"
    ↓
    └─ "...and filter by keywords"
       └─ → run_agentic_facebook_exact_posts.py --in-group-exact-keywords

1C: "I need FULL text + keyword filtering"
    ↓
    └─ → run_agentic_facebook_exact_posts.py --in-group-exact-keywords
```

---

## 2. Pre-Execution Checklist (Deploy Readiness)

```
BEFORE running ANY script:

┌────────────────────────────────┐
│ ENVIRONMENT READY?             │
├────────────────────────────────┤
│ □ ENABLE_AGENTIC_FACEBOOK_SYNC │ = true
│ □ BROWSER_SEARCH_QUERY         │ set (discovery phrase)
│ □ BROWSER_IN_GROUP_SEARCH_QUERY│ set (in-group term)
│ □ Python venv activated        │ (.venv/bin/python)
│ □ No secrets in console logs   │ (check logging config)
│ □ Network access to facebook.com
│ □ Disk space for artifacts     │ (>500MB recommended)
└────────────────────────────────┘
       ↓
   All YES? → PROCEED to script selection
   ANY NO?  → Fix missing config, then retry
```

---

## 3. Execution Phase Flow (During Run)

```
RUN_STARTED
     │
     ├─ [ROUTER] Classify task → Recommend script
     │
     ├─ [ANALYST] Verify config (checklist above)
     │   ├─ Config invalid? → HALT, report errors
     │   └─ Config valid? ↓
     │
     ├─ [PLANNER] Write numbered action plan + stop conditions
     │
     ├─ [BROWSER] Execute Playwright actions in sequence
     │   ├─ Navigate group search
     │   ├─ Discover groups (up to --group-limit)
     │   │
     │   └─ FOR each group:
     │       ├─ Navigate to group
     │       ├─ [For exact_posts only] Click "Ещё" / "See more" (best-effort)
     │       ├─ Scrape post text
     │       ├─ [For exact_posts only] Filter body by keywords
     │       ├─ Screenshot/snapshot as evidence
     │       └─ Repeat until --post-limit or group exhausted
     │
     ├─ [CRITIC] Validate extraction batch
     │   ├─ No duplicates?
     │   ├─ Correct group IDs?
     │   ├─ Recent dates?
     │   ├─ Truncation expanded? (if exact_posts)
     │   ├─ Keyword match confirmed? (if exact_posts)
     │   └─ PASS all checks? ↓ YES: upsert
     │                        NO:  flag + skip
     │
     ├─ [WRITER] Generate DB payloads + artifacts
     │   ├─ Posts → output/agentic_facebook/<timestamp>/posts.jsonl
     │   ├─ Summary JSON → same dir
     │   └─ HTML report → report/agentic_search_<timestamp>/index.html
     │
     └─ [TESTER] Verify output
         ├─ Schema valid?
         ├─ DB upserts succeeded?
         ├─ Artifacts accessible?
         ├─ No secrets leaked?
         └─ Return compact JSON summary to operator
```

---

## 4. Error Branching (Troubleshooting)

```
ERROR: "Facebook checkpoint required"
     └─ ACTION: Manually complete 2FA/checkpoint in browser
        Then: Restart run with same parameters (posts are idempotent via ID)

ERROR: "No groups found"
     └─ ACTION: Verify --query matches actual group names
        Then: Check Facebook.com group search manually
        Then: Update BROWSER_SEARCH_QUERY and retry

ERROR: "expand_see_more: false" (in exact_posts output)
     └─ ACTION: Check "Ещё" button selector in DOM
        Then: Update selector in run_agentic_facebook_exact_posts.py
        Then: Retry

ERROR: "Keyword filter too strict (0 posts upserted)"
     └─ ACTION: Check body text contains expected keywords
        Then: Relax --in-group-query OR remove --in-group-exact-keywords
        Then: Retry

ERROR: "DB connection failed"
     └─ ACTION: Check DATABASE_URL env var
        Then: Verify DB is reachable (nc -zv <host> <port>)
        Then: Restart run (posts queue, will resume)

ERROR: "Disk full"
     └─ ACTION: Clean up old artifacts: rm -rf output/agentic_facebook/old_*
        Then: Verify >500MB free
        Then: Restart run
```

---

## 5. Script Comparison Matrix (Quick Ref)

| **Dimension** | **exact_posts** | **once** | **exact_year** |
|---------------|-----------------|----------|----------------|
| **See-more expansion** | ✓ YES | ✗ NO | ✗ NO |
| **Body keyword filter** | ✓ YES | ✗ NO | ✗ NO |
| **Year filtering** | ✗ NO | ✗ NO | ✓ YES |
| **Execution speed** | Slowest | Fast | Medium |
| **DB footprint** | Smallest | Largest | Medium |
| **Use case** | Production, quality | Exploratory | Historical |
| **Output fields** | Includes `expand_see_more`, `body_keyword_union` | Standard | Includes `year_filter` |

---

## 6. Parameter Cheat Sheet

### **run_agentic_facebook_exact_posts.py**

```bash
python scripts/run_agentic_facebook_exact_posts.py \
  --query "<DISCOVERY_PHRASE>" \
  --in-group-query "<TOKEN1>,<TOKEN2>,<TOKEN3>" \
  --in-group-exact-keywords \
  --group-limit <INT:50-500> \
  --post-limit <INT:50-500>
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `--query` | str | (required) | Group discovery phrase |
| `--in-group-query` | str | (required) | Comma-separated post search terms |
| `--in-group-exact-keywords` | flag | false | Token-based (not substring) matching |
| `--group-limit` | int | 50 | Stop after N groups discovered |
| `--post-limit` | int | 100 | Stop after N posts per group |

### **run_agentic_facebook_once.py**

```bash
python scripts/run_agentic_facebook_once.py \
  --query "<DISCOVERY_PHRASE>" \
  --group-limit 50 \
  --post-limit 100
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `--query` | str | (required) | Group discovery phrase |
| `--group-limit` | int | 50 | Groups to scan |
| `--post-limit` | int | 100 | Posts per group |

### **run_agentic_facebook_once_exact_year.py**

Requires **`BROWSER_POST_PUBLICATION_YEAR`** in `.env` (no `--year` CLI flag).

```bash
python scripts/run_agentic_facebook_once_exact_year.py \
  --query "<DISCOVERY_PHRASE>" \
  --group-limit 50 \
  --post-limit 100
```

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `--query` | str | from `.env` if omitted | Group discovery phrase |
| `--group-limit` | int | from settings | Overrides `BROWSER_GROUP_SCAN_LIMIT` when set |
| `--post-limit` | int | from settings | Overrides `BROWSER_POST_LIMIT_PER_GROUP` when set |
| Year filter | env | **required** | **`BROWSER_POST_PUBLICATION_YEAR`** builds `filters=` on URLs |

---

## 7. Expected Output Artifacts

### **Directory Structure**

```
output/agentic_facebook/
└─ 20260503_143000/               ← Timestamp (YYYYMMDD_HHMMSS)
   ├─ posts.jsonl                 ← One post per line (newline-delimited JSON)
   ├─ summary.json                ← Execution summary
   └─ screenshots/                ← Evidence (before/after interactions)
       ├─ group_discovery_1.png
       ├─ group_1_before_expand.png
       ├─ group_1_after_expand.png
       └─ ...

report/agentic_search_20260503_143000/
└─ index.html                      ← Human-readable HTML report
```

### **Summary JSON Schema**

```json
{
  "ok": true,
  "flow": "agentic_facebook",
  "query": "ищу работу в Германии",
  "in_group_query": "ищу работу Бетонщик,ищу работу Арматурщик",
  "groups_scanned": 35,
  "groups_found": 42,
  "posts_found": 450,
  "posts_upserted": 120,
  "expand_see_more": true,
  "body_keyword_union": true,
  "body_keyword_needles_count": 3,
  "in_group_exact_keywords": true,
  "errors": [],
  "execution_time_seconds": 345,
  "artifacts_dir": "output/agentic_facebook/20260503_143000",
  "html_report_dir": "report/agentic_search_20260503_143000"
}
```

---

## 8. One-Liner Recipes

**Quick job posts scan:**
```bash
python scripts/run_agentic_facebook_exact_posts.py --query "ищу работу в Германии" --in-group-query "бетон,аромат,камен" --in-group-exact-keywords --group-limit 30 --post-limit 50
```

**Year-scoped group search URLs** (year from **`BROWSER_POST_PUBLICATION_YEAR`**):
```bash
python scripts/run_agentic_facebook_once_exact_year.py --query "Україна Німеччина" --group-limit 20
```

**Exploratory fast scan:**
```bash
python scripts/run_agentic_facebook_once.py --query "tech jobs" --group-limit 15 --post-limit 30
```

---

## 9. Common Mistakes → Fixes

| **Mistake** | **Symptom** | **Fix** |
|------------|-----------|--------|
| Forgot `--in-group-exact-keywords` on exact_posts | Large DB footprint; many irrelevant posts | Add flag OR use `once.py` instead |
| Used `exact_year.py` but want body filtering | Year URL filter only; no body union | Use **`run_agentic_facebook_exact_posts.py`** for union filter (no combined script today) |
| `BROWSER_SEARCH_QUERY` not set | "KeyError: BROWSER_SEARCH_QUERY" | Set in `.env` or pass `--query` |
| Facebook login failed, bot restarted | Old browser session lost; must re-login | Manual login in browser, then restart script |
| Post text still truncated (exact_posts) | "Ещё" click didn't work | Check DOM selector; update script |

---

## 10. Monitoring & Validation

**During execution, watch for:**

```
✓ Group discovery rate: 3–5 groups/minute (normal)
✓ Post scraping: 2–5 posts/second (normal)
✓ CPU usage: 20–40% (normal)
✓ Memory: <1GB (normal)

⚠ If scraping stalls (0 posts/min):
  └─ Likely: anti-bot or 2FA checkpoint
  └─ Action: Check browser, complete 2FA, restart

⚠ If "Ещё" expansion is 0% success:
  └─ Likely: selector changed in Facebook UI
  └─ Action: Inspect DOM, update selector, retry
```

**After execution, verify:**

```
✓ Summary JSON written?
✓ Posts JSONL not empty?
✓ HTML report renders?
✓ All artifacts under output/agentic_facebook/?
✓ No .env secrets in logs?
✓ Upserted count > 0?
```

---

## Quick Decision Tree (Print & Tape to Monitor)

```
┌─────────────────────────────────────────────────────────────────┐
│ FACEBOOK SCRIPT SELECTOR (5-SECOND DECISION)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Q1: Need full text (truncation matters)?                       │
│      YES → Q2                                                   │
│      NO  → Q3                                                   │
│                                                                  │
│  Q2: Filter by keywords?                                        │
│      YES → run_agentic_facebook_exact_posts.py ✓               │
│      NO  → run_agentic_facebook_once.py ✓                      │
│                                                                  │
│  Q3: Need year filtering?                                       │
│      YES → run_agentic_facebook_once_exact_year.py ✓           │
│      NO  → run_agentic_facebook_once.py ✓                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
