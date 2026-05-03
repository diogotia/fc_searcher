# Playwright Action Plan

The agentic flow uses the same browser primitives as the classic Playwright search, but it runs behind separate entrypoints and artifacts.

## Login

1. Navigate to `https://facebook.com`.
2. Take a screenshot and snapshot to confirm the page state.
3. If `FACEBOOK_WEB_LOGIN` and `FACEBOOK_WEB_PASSWORD` are set, fill the login form and submit.
4. Wait for a logged-in signal.
5. If Facebook shows 2FA, checkpoint, captcha, or passkey UI, stop and ask for manual action.

## Group Discovery

1. Navigate to `https://www.facebook.com/search/groups/?q=<query>`.
2. Wait for search results.
3. Evaluate JavaScript to collect group URLs and labels.
4. Deduplicate by canonical group URL.
5. Merge groups in this order:
   - all unique `BROWSER_SEED_GROUP_URLS`
   - discovered groups up to `BROWSER_GROUP_SCAN_LIMIT`

## In-Group Search

For each group and each in-group phrase:

1. Navigate to `/groups/<id>/search/?q=<phrase>`.
2. Wait for feed content.
3. Evaluate JavaScript to extract post IDs, URLs, message text, author names, and inferred timestamps.
4. Scroll for lazy-loaded posts.
5. Repeat extraction until the post limit or retry limit is reached.
6. Return normalized post payloads to the Writer step.

## Critic Checks

The Critic validates:

- post has an ID or deterministic fallback ID
- group URL matches the current group
- message text is non-empty
- duplicate post IDs are skipped inside the same group
- `global_message_contains` matches when configured
- `BROWSER_POST_PUBLICATION_*` filters pass when configured

## Stop Conditions

Stop and report clearly when:

- login cannot complete within timeout
- Facebook shows a manual checkpoint
- the page structure no longer exposes group or post data
- four attempts fail without new evidence
- the run would require printing or storing secrets
