---
description: Agentic Facebook Orchestrator — script selection matrix, clear decision flow, operational examples
---

# Agentic Facebook Orchestrator v2

**Goal:** Decompose Facebook monitoring tasks into safe, isolated agent pipelines without touching the classic browser-sync flow.

---

## 🎯 Script Selection Matrix

| **Need** | **Script** | **Key Features** | **Best For** |
|----------|-----------|-----------------|------------|
| **Full post text + keyword filter** | `run_agentic_facebook_exact_posts.py` | • Clicks "Ещё" / "See more" before scrape<br>• Body keyword union (**OR** across needles)<br>• Smaller DB footprint | Production runs; German job posts with multiple role keywords |
| **Standard in-group search** | `run_agentic_facebook_once.py` | • Fast in-group post collection<br>• No see-more expansion<br>• All discovered posts upserted | Quick scans; exploratory searches |
| **Year-filtered in-group URLs** | `run_agentic_facebook_once_exact_year.py` | • Appends Facebook UI **`filters=`** (base64 token derived from **`BROWSER_POST_PUBLICATION_YEAR`**) to each in-group search URL<br>• No see-more expansion<br>• No body keyword union | Same-year results as Meta’s group-search “creation time” filter |

**Decision Tree:**
```
START: Facebook monitoring task
  │
  ├─ Need FULL post text (truncation matters)?
  │   └─ YES → Use run_agentic_facebook_exact_posts.py ✓
  │       └─ Multiple keywords to filter body?
  │           └─ YES → Add --in-group-exact-keywords
  │
  ├─ Need year filtering on in-group URLs?
  │   └─ YES → Use run_agentic_facebook_once_exact_year.py ✓
  │       └─ (Do NOT combine with see-more expansion)
  │
  └─ Default (fast scan, keep all posts)?
      └─ Use run_agentic_facebook_once.py ✓
```

---

## 📋 Core Concepts

### **run_agentic_facebook_exact_posts.py** (OPTIMIZED FOR QUALITY)

**What it does:**

1. Searches for groups using `--query` (discovery phrase)
2. Within each group, searches posts using `--in-group-query` tokens
3. **Before scraping text**, clicks "Ещё" / "See more" controls (best-effort)
4. Extracts full post body from DOM
5. **Upserts only posts where body contains ≥1 of:**
   - Any token from `--in-group-query` (comma-separated), **OR**
   - The discovery phrase from `--query`
6. All matches are case-insensitive substring matches

**Output:**
- Fewer rows in DB (quality > quantity)
- Richer post content (truncation resolved where possible)
- JSON summary fields:
  - `expand_see_more`: bool (whether expansion was attempted)
  - `body_keyword_union`: bool (whether filter was applied)
  - `body_keyword_needles_count`: int (number of filter terms)
  - `in_group_exact_keywords`: bool (whether exact-token mode was used)

---

### **run_agentic_facebook_once.py** (FAST, STANDARD)

**What it does:**

1. Discovers groups via `--query`
2. Collects all posts from each group (no keyword filtering)
3. Scrapes visible text as-is (no "See more" expansion)
4. Upserts everything (all-in DB strategy)

**Output:**
- Larger DB footprint (but complete raw data)
- Faster execution (fewer DOM interactions)
- Use when: exploratory work or truncation is acceptable

---

### **run_agentic_facebook_once_exact_year.py** (YEAR ON SEARCH URL)

**What it does:**

1. Same CLI shape as `run_agentic_facebook_once.py`, but always passes **`facebook_ui_year_filter=True`** into sync.
2. Requires **`BROWSER_POST_PUBLICATION_YEAR`** in `.env` (e.g. `2026` or `auto`). The code builds the same **`filters=`** query token Facebook uses for “creation time” calendar year on group search — **not** a literal `filters=year:YYYY` string.
3. No body keyword union; no see-more expansion (use `exact_posts` separately if you need those).

**Output:**
- JSON may include `facebook_ui_year_filter`, `facebook_ui_filter_year`.
- Use when: you want Meta’s year-scoped group search URLs aligned with that setting.

---

## 🔧 Agent Execution Sequence

### **Phase 1: ROUTER → Task Classification**

```
Input: User task
├─ Has "full text" / "complete posts" / "truncation" concern?
│  └─ YES: Flag for exact_posts script
├─ Has "year:" / "2024" / "2023" in constraints?
│  └─ YES: Flag for exact_year script
└─ Otherwise: Use standard once script
```

**Output:** Recommended script + parameter template

---

### **Phase 2: ANALYST → Environment & Parameter Verification**

**Checks:**
- [ ] `ENABLE_AGENTIC_FACEBOOK_SYNC=true` in `.env`
- [ ] `BROWSER_SEARCH_QUERY` set (discovery phrase)
- [ ] `BROWSER_IN_GROUP_SEARCH_QUERY` set (in-group search term)
- [ ] `BROWSER_SEED_GROUP_URLS` set if pre-seeding (optional)
- [ ] `--group-limit` and `--post-limit` reasonable (50–100 typical)
- [ ] Secrets not in logs (`.env` not printed)

**Output:** ✓ Ready to plan, or ✗ Fix config before proceeding

---

### **Phase 3: PLANNER → Action Plan with Stop Conditions**

**Example (exact_posts run):**

```
PLAN:
1. Navigate to Facebook.com
   STOP IF: Login required but 2FA/checkpoint halts bot
2. Search groups: "ищу работу в Германии"
   STOP IF: No groups found (0 results)
3. For each discovered group (up to --group-limit):
   a. Navigate to group
   b. Search posts: "ищу работу Бетонщик,ищу работу Арматурщик,ищу работу Каменщик"
   c. Scroll + click "Ещё" controls (best-effort, do not hang)
   d. Scrape DOM for post text
   STOP IF: Scrape timeout (>30s per post)
4. Filter: Keep only posts whose body contains ≥1 keyword
5. Upsert to DB with source="playwright_agentic"
   STOP IF: DB connection fails (log error, continue to next group)
6. Write results to output/agentic_facebook/<timestamp>/
   STOP IF: Disk full
7. Generate HTML summary to report/agentic_search_<timestamp>/
```

---

### **Phase 4: BROWSER → Execute Primitives**

Each action is deliberate and logged:

```python
# Example: expand see-more in a post
browser.navigate("https://www.facebook.com/groups/12345/posts/67890/")
browser.screenshot("before_expand")

# Best-effort see-more expansion
browser.click('//span[contains(text(), "Ещё")]')  # Russian "More"
browser.wait_for(2)  # Wait for DOM update
browser.screenshot("after_expand")

# Scrape full text
text = browser.evaluate("document.body.innerText")
```

**Evidence collection:**
- Screenshot before/after each interaction
- Snapshot of DOM state before scrape
- Timestamps for each action

---

### **Phase 5: CRITIC → Validation Before Upsert**

**Checks per extraction batch:**
- [ ] No duplicate posts (compare post ID)
- [ ] Posts belong to discovered group (group ID in URL)
- [ ] Publication date is recent (or within expected range if year-filtered)
- [ ] Post body was expanded (compare see-more attempts vs text length)
- [ ] No stale posts from cache
- [ ] Keyword match confirmed in body (spot-check 1–2 rows)

**Output:** ✓ Safe to upsert, or ✗ Flag row + reason (don't upsert)

---

### **Phase 6: WRITER → DB Payload & Artifacts**

**Payload (JSON) for each post:**

```json
{
  "id": "post_12345",
  "group_id": "group_67890",
  "group_name": "Работа в Германии",
  "message": "Ищу работу бетонщиком в Берлине...",
  "created_at": "2026-05-03T14:30:00Z",
  "source": "playwright_agentic",
  "metadata": {
    "expand_see_more": true,
    "expanded_text_length": 450,
    "original_truncated_length": 200,
    "body_keyword_match": "бетонщик",
    "script": "run_agentic_facebook_exact_posts.py"
  }
}
```

**Artifacts:**
- Output: `output/agentic_facebook/<YYYYMMDD_HHMMSS>/posts.jsonl`
- Report: `report/agentic_search_<YYYYMMDD_HHMMSS>/index.html`

---

### **Phase 7: TESTER → Verification**

**Checks:**
- [ ] Result JSON shape matches schema (required fields present)
- [ ] DB upserts succeeded (log row count)
- [ ] Report HTML renders without 404 links
- [ ] Operator can view artifacts directory
- [ ] No secrets in logs or JSON
- [ ] Summary counts match (groups scanned vs groups found vs posts upserted)

**Output:** Compact JSON summary

---

## 🚀 Operational Examples

### **Example 1: Full-Text German Job Posts (exact_posts)**

**Goal:** Find all construction worker job posts in German Facebook groups; expand truncated text; keep only posts matching specific trades.

```bash
.venv/bin/python scripts/run_agentic/run_agentic_facebook_exact_posts.py \
  --query "ищу работу в Германии" \
  --in-group-query "ищу работу Бетонщик,ищу работу Арматурщик,ищу работу Каменщик" \
  --in-group-exact-keywords \
  --group-limit 50 \
  --post-limit 100
```

**Expected output:**
- Groups scanned: ~35
- Posts found: ~450
- Posts upserted (after keyword filter): ~120
- Artifacts: `output/agentic_facebook/20260503_143000/posts.jsonl`
- Report: `report/agentic_search_20260503_143000/index.html`
- Summary JSON includes `expand_see_more: true`, `body_keyword_union: true`, `body_keyword_needles_count: 3`

---

### **Example 2: Quick Group Scan (standard once)**

**Goal:** Fast exploratory scan; all posts kept.

```bash
.venv/bin/python scripts/run_agentic/run_agentic_facebook_once.py \
  --query "tech jobs Berlin" \
  --group-limit 20 \
  --post-limit 50
```

**Expected output:**
- Groups scanned: ~18
- Posts found: ~420 (all kept, no filtering)
- Execution time: ~2–3 min
- Use for: feasibility check, initial data overview

---

### **Example 3: Year filter on in-group URLs (exact_year)**

**Goal:** Run in-group searches with Facebook’s creation-year filter for the year configured in `.env`.

Set **`BROWSER_POST_PUBLICATION_YEAR=2026`** (or another year / `auto` per project docs), then:

```bash
.venv/bin/python scripts/run_agentic/run_agentic_facebook_once_exact_year.py \
  --query "Україна Німеччина" \
  --group-limit 30 \
  --post-limit 150
```

There is **no** `--year` CLI flag; the year comes from **`BROWSER_POST_PUBLICATION_YEAR`**.

**Expected output:**
- In-group URLs include **`&filters=<encoded token>`** for that year (see `encode_facebook_group_search_creation_year_filter` in `src/services/browser_search.py`).
- Summary JSON includes `facebook_ui_year_filter` / `facebook_ui_filter_year` when applicable.
- No see-more expansion; no body keyword union in this executable.

---

## 🛡️ Project Invariants (DO NOT CHANGE)

✓ Agentic flow uses `ENABLE_AGENTIC_FACEBOOK_SYNC=true`  
✓ Agentic posts have source `playwright_agentic`  
✓ Agentic artifacts: `output/agentic_facebook/<timestamp>/`  
✓ Agentic HTML reports: `report/agentic_search_<timestamp>/`  
✓ `BROWSER_SEED_GROUP_URLS` processed before discovery  
✓ Classic browser-sync (`/admin/browser-search-sync`) **stays separate**  
✓ Never print secrets from `.env`  
✓ Facebook login may require manual 2FA/checkpoints  

---

## 🐛 Troubleshooting

| **Issue** | **Root Cause** | **Fix** |
|-----------|----------------|--------|
| `expand_see_more: false` in all posts | Selector mismatch for "Ещё" button | Check DOM, update selector in script |
| Upserted count << found count | Keyword filter too strict | Relax `--in-group-query` or remove `--in-group-exact-keywords` |
| "Facebook checkpoint required" | 2FA or anti-bot trigger | Manual login + checkpoint; restart run after |
| JSON summary missing fields | Old script version | Use `python scripts/run_agentic/run_agentic_facebook_exact_posts.py --version` |
| Report HTML has 404 links | Artifact path misconfigured | Check **`AGENTIC_FACEBOOK_OUTPUT_DIR`** (and repo paths under `report/`) |

---

## 📞 Quick Reference

**When to use each script:**

```
"I need complete post text"              → exact_posts.py ✓
"I need posts from specific years"       → exact_year.py ✓
"I just want a fast count"               → once.py ✓
"I need to filter by keywords"           → exact_posts.py --in-group-exact-keywords ✓
```

**Three-step launch:**

1. **Choose script** (see matrix above)
2. **Set ENV** (`ENABLE_AGENTIC_FACEBOOK_SYNC=true`, `BROWSER_SEARCH_QUERY`, etc.)
3. **Run** with appropriate `--query`, `--group-limit`, `--post-limit`

That's it.
