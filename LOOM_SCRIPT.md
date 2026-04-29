# Loom script (~15 minutes) — Autonomy AI Studio E2E

Use this outline while recording. Speak slowly; show the repo and terminal side by side.

## 1. Intro (1 min)

- “This is an end-to-end suite for Autonomy AI Studio using Playwright and TypeScript.”
- “Goal: prove critical journeys while accepting that AI outputs are non-deterministic.”

## 2. Run tests headless (2 min)

- Show `.env.local` **without** revealing secrets (blur or use dummy values in the recording).
- Run `npm test` or `npm run test:smoke` for a shorter clip.
- Open `playwright-report/index.html` after a local run and scroll the HTML report.

## 3. Page Object pattern (3 min)

- Open `tests/pages/LoginPage.ts` and `TaskPage.ts`.
- “Selectors and intent live here; specs orchestrate user goals.”
- Point at `tests/pages/selectors.ts` — “Stage copy is centralized so product wording changes are one edit.”

## 4. AI non-determinism strategy (3 min)

- Open `tests/helpers/retry.ts` — polling instead of fixed sleeps.
- Open `tests/e2e/task-lifecycle.spec.ts` — “Assertions target lifecycle and output **surface**, not exact model text.”
- Mention traces and screenshots on failure (`playwright.config.ts`).

## 5. Auth reuse (2 min)

- `tests/e2e/auth.setup.ts` saves `playwright/.auth/user.json`.
- `playwright.config.ts` wires `storageState` for the authenticated project.
- “Login specs run in a separate project without storage to test invalid credentials cleanly.”

## 6. CI/CD (2 min)

- Walk through `.github/workflows/e2e.yml`: PR checks, nightly, `workflow_dispatch`.
- Mention GitHub secrets: `BASE_URL`, `TEST_EMAIL`, `TEST_PASSWORD`, optional `TEST_GITHUB_REPO`.

## 7. Bugs and roadmap (1 min)

- Skim `BUGS.md` — five severities with repro templates.
- Skim `ROADMAP.md` — pyramid, priorities, contract testing.

## 8. AI tooling disclosure (1 min)

- State plainly where an assistant helped (scaffolding, docs structure) vs. what you validated on the real product (selectors, timings, bug text).

## 9. Close (30 s)

- “With more time: tag smoke tests, add API waits for job status, and pin stable project fixtures.”

---

**Checklist before export**

- [ ] No real passwords on screen  
- [ ] Show at least one failing-trace artifact path  
- [ ] Mention how to reproduce locally using `README.md`
