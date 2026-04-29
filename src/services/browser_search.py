from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import defaultdict
import subprocess
import textwrap
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

from dateutil import parser as date_parser

from src.config import Settings

logger = logging.getLogger(__name__)

_GROUP_URL_RE = re.compile(r"https?://(?:www\.)?facebook\.com/groups/([^/?#]+)")
_POST_ID_PATTERNS = (
    re.compile(r"/posts/([^/?#]+)"),
    re.compile(r"/permalink/([^/?#]+)"),
    re.compile(r"[?&]story_fbid=([^&#]+)"),
    re.compile(r"[?&]multi_permalinks=([^&#]+)"),
)


class BrowserAutomationError(RuntimeError):
    pass


def _parse_playwright_cli_run_code_json_payload(stdout: str) -> Any:
    """Parse JSON from `playwright-cli run-code` stdout.

    Official CLI prints a bare JSON line; Codex-style wrappers emit markdown, e.g.::

        ### Result
        "{\\"logged_in\\":false}"
        ### Ran Playwright code
        ```js
        ...
        ```
    """
    text = (stdout or "").strip()
    if not text:
        raise json.JSONDecodeError("empty playwright stdout", "", 0)

    if "### Error" in text:
        tail = text[text.index("### Error") + len("### Error") :].strip()
        first = tail.splitlines()[0] if tail else "Playwright error"
        raise BrowserAutomationError(first[:1200])

    if "### Result" in text:
        start = text.index("### Result") + len("### Result")
        tail = text[start:].lstrip()
        chunk_lines: list[str] = []
        for line in tail.splitlines():
            stripped = line.strip()
            if stripped.startswith("###") and not stripped.startswith("### Result"):
                break
            if stripped == "```":
                break
            chunk_lines.append(line)
        chunk = "\n".join(chunk_lines).strip()
        if not chunk:
            raise json.JSONDecodeError("no ### Result payload", text, 0)
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            # Sometimes the model prints JSON without quoting the whole line.
            m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", chunk)
            if not m:
                raise
            parsed = json.loads(m.group(0))
        if isinstance(parsed, str):
            inner = parsed.strip()
            if inner.startswith(("{", "[")):
                return json.loads(inner)
        return parsed

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line == "```":
            continue
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    line = text.splitlines()[-1].strip() if text.splitlines() else ""
    return json.loads(line)


def _wrap_playwright_cli_run_code_json(
    *,
    page_evaluate_body: str,
    scroll_rounds: int = 0,
    scroll_pause_ms: int = 800,
) -> str:
    """`playwright-cli run-code` expects `async (page) => { ... }` returning JSON text.

    Scroll/wait run in the **page** context (not inside `evaluate`) so Facebook navigations
    do not destroy the evaluate execution context mid-flight.

    Pauses use short **browser** `setTimeout` slices with **try/catch** so Meta navigations
    mid-wait do not fail the whole step; DOM read `evaluate` is **retried** after navigation.
    """
    body = textwrap.dedent(page_evaluate_body).strip()
    inner = textwrap.indent(body, "    ")
    sleep_helper = (
        "  const _fcSleep = async (totalMs) => {\n"
        "    const step = 200;\n"
        "    for (let t = 0; t < totalMs; t += step) {\n"
        "      try {\n"
        "        await page.evaluate(\n"
        "          (ms) => new Promise((r) => globalThis.setTimeout(r, ms)),\n"
        "          Math.min(step, totalMs - t)\n"
        "        );\n"
        "      } catch (e) {\n"
        "        await page.waitForLoadState('domcontentloaded', { timeout: 8000 }).catch(() => {});\n"
        "      }\n"
        "    }\n"
        "  };\n"
    )
    scroll_block = ""
    if scroll_rounds > 0:
        sr = int(scroll_rounds)
        sp = int(scroll_pause_ms)
        scroll_block = (
            f"  for (let _fcI = 0; _fcI < {sr}; _fcI += 1) {{\n"
            "    await page.mouse.wheel(0, (page.viewportSize()?.height) || 720);\n"
            f"    await _fcSleep({sp});\n"
            "  }\n"
        )
    return (
        "async (page) => {\n"
        + sleep_helper
        + "  await page.waitForLoadState('domcontentloaded', { timeout: 45000 }).catch(() => {});\n"
        + "  await _fcSleep(500);\n"
        + scroll_block
        + "  let _fcOut;\n"
        + "  for (let _fcA = 0; _fcA < 3; _fcA += 1) {\n"
        + "    try {\n"
        + "      await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => {});\n"
        + "      _fcOut = await page.evaluate(() => {\n"
        + inner
        + "\n      });\n"
        + "      break;\n"
        + "    } catch (e) {\n"
        + "      if (_fcA === 2) throw e;\n"
        + "      await _fcSleep(600);\n"
        + "    }\n"
        + "  }\n"
        + "  return JSON.stringify(_fcOut);\n"
        + "}"
    )


class ManualLoginRequiredError(BrowserAutomationError):
    pass


@dataclass(slots=True)
class DiscoveredGroup:
    group_name: str
    group_url: str
    group_id: str | None = None


@dataclass(slots=True)
class BrowserFoundPost:
    external_id: str | None
    group_id: str
    group_name: str
    group_url: str
    post_url: str
    message: str
    author_name: str | None
    created_time: datetime | None
    raw_payload: dict[str, Any]


class PlaywrightCliRunner:
    def __init__(
        self,
        *,
        headed: bool,
        timeout_seconds: int,
        output_dir: Path,
        session_name: str | None = None,
    ) -> None:
        self._headed = headed
        self._timeout_seconds = timeout_seconds
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        # Short id: long paths under default macOS TMPDIR break @playwright/cli Unix sockets (listen EINVAL).
        self._session_name = session_name or f"p{uuid.uuid4().hex[:10]}"
        self._bootstrapped_cli_open = False
        skill_wrapper = Path.home() / ".codex" / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
        self._base_cmd = [str(skill_wrapper)] if skill_wrapper.is_file() else ["npx", "--yes", "--package", "@playwright/cli", "playwright-cli"]

    @property
    def session_name(self) -> str:
        return self._session_name

    def _goto_same_tab(self, url: str) -> None:
        """Navigate the session's existing page (avoids extra tabs from repeated ``playwright-cli open``)."""
        code = (
            "async (page) => { await page.goto("
            + json.dumps(url)
            + ", { waitUntil: 'domcontentloaded', timeout: 90000 }); return JSON.stringify('ok'); }"
        )
        self.run_code(code)

    def open(self, url: str) -> None:
        """First call uses ``playwright-cli open`` (headed bootstrap); later calls use ``page.goto`` same tab."""
        if not self._bootstrapped_cli_open:
            args = ["open", url]
            if self._headed:
                args.append("--headed")
            self._run(args)
            self._bootstrapped_cli_open = True
            return
        self._goto_same_tab(url)

    def close(self) -> None:
        try:
            self._run(["close"])
        except BrowserAutomationError:
            logger.debug("Playwright session close failed", exc_info=True)

    def snapshot(self, label: str) -> Path:
        out = self._run(["snapshot"])
        path = self._output_dir / f"{label}.txt"
        path.write_text(out, encoding="utf-8")
        return path

    def screenshot(self, label: str) -> Path:
        path = self._output_dir / f"{label}.png"
        code = (
            "async (page) => { await page.screenshot({ path: "
            + json.dumps(str(path))
            + ", fullPage: true }); return JSON.stringify('ok'); }"
        )
        self.run_code(code)
        return path

    def run_json(
        self,
        page_evaluate_body: str,
        *,
        scroll_rounds: int = 0,
        scroll_pause_ms: int = 800,
    ) -> Any:
        wrapped = _wrap_playwright_cli_run_code_json(
            page_evaluate_body=page_evaluate_body,
            scroll_rounds=scroll_rounds,
            scroll_pause_ms=scroll_pause_ms,
        )
        out = self.run_code(wrapped)
        try:
            return _parse_playwright_cli_run_code_json_payload(out)
        except BrowserAutomationError:
            raise
        except json.JSONDecodeError as exc:
            tail = out.strip()[-800:] if out.strip() else ""
            raise BrowserAutomationError(
                f"Playwright returned non-JSON output: {exc!s}. stdout tail: {tail!r}"
            ) from exc

    def run_code(self, code: str) -> str:
        return self._run(["run-code", code])

    def _playwright_child_env(self) -> dict[str, str]:
        """Env for npx/playwright-cli: avoid macOS /var/folders/... TMPDIR (often causes listen EINVAL on IPC sockets)."""
        env = os.environ.copy()
        env.setdefault("PLAYWRIGHT_CLI_SESSION", self._session_name)
        short_tmp = Path("/tmp/fc-searcher-pw")
        try:
            short_tmp.mkdir(parents=True, exist_ok=True)
            env["TMPDIR"] = str(short_tmp)
            env["TMP"] = str(short_tmp)
            env["TEMP"] = str(short_tmp)
        except OSError:
            logger.debug("Could not mkdir %s for Playwright TMPDIR", short_tmp, exc_info=True)
        return env

    def _run(self, args: list[str]) -> str:
        cmd = [*self._base_cmd, "--session", self._session_name, *args]
        env = self._playwright_child_env()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(Path.cwd()),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(self._timeout_seconds + 15, 30),
                check=False,
            )
        except FileNotFoundError as exc:
            raise BrowserAutomationError("Playwright CLI is not installed or not available on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise BrowserAutomationError(f"Playwright command timed out: {' '.join(args)}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            raise BrowserAutomationError(detail or f"Playwright command failed: {' '.join(args)}")
        return (proc.stdout or "").strip()


def parse_seed_group_urls(raw: str) -> list[DiscoveredGroup]:
    """Parse comma/newline-separated group URLs or numeric ids into `DiscoveredGroup` entries (deduped)."""
    if not (raw or "").strip():
        return []
    tokens: list[str] = []
    for line in raw.replace("\r", "").splitlines():
        for part in line.split(","):
            p = part.strip()
            if p:
                tokens.append(p)
    seen: set[str] = set()
    out: list[DiscoveredGroup] = []
    for token in tokens:
        u = token.strip()
        if not u:
            continue
        if u.isdigit():
            u = f"https://www.facebook.com/groups/{u}"
        elif not u.startswith("http"):
            continue
        u = u.split("?")[0].rstrip("/")
        gid = extract_group_id(u)
        if not gid:
            continue
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        label = f"Group {gid}" if gid.isdigit() else gid
        out.append(DiscoveredGroup(group_name=label, group_url=u, group_id=gid if gid.isdigit() else None))
    return out


def post_matches_global_message_filter(message: str | None, needle: str | None) -> bool:
    """When ``needle`` is set, post body must contain it (case-insensitive). Empty needle = no filter."""
    n = (needle or "").strip()
    if not n:
        return True
    return n.casefold() in (message or "").casefold()


_RU_MONTH_NAMES = (
    r"января|январь|февраля|февраль|марта|март|апреля|апрель|мая|май|июня|июнь|"
    r"июля|июль|августа|август|сентября|сентябрь|октября|октябрь|ноября|ноябрь|декабря|декабрь"
)
_RU_MONTH_TOKENS = [t.strip() for t in _RU_MONTH_NAMES.split("|") if t.strip()]
_RU_MONTH_WORD_TO_NUM: dict[str, int] = {}
for _i in range(0, len(_RU_MONTH_TOKENS), 2):
    _num = _i // 2 + 1
    _RU_MONTH_WORD_TO_NUM[_RU_MONTH_TOKENS[_i].lower()] = _num
    _RU_MONTH_WORD_TO_NUM[_RU_MONTH_TOKENS[_i + 1].lower()] = _num
_RU_DMY = re.compile(
    rf"(?<![0-9])(\d{{1,2}})\s+({_RU_MONTH_NAMES})\s+(\d{{4}})(?:\s*г\.?)?(?![0-9])",
    re.IGNORECASE,
)
_ISO_YMD = re.compile(r"(?<![0-9])(20\d{2})-(\d{1,2})-(\d{1,2})(?![0-9])")
_YEAR_WITH_GR = re.compile(r"(?<![0-9])(20\d{2})\s*г\.?", re.IGNORECASE)
# Facebook-style relative time in the snippet before "·" (e.g. "3 дн.", "21 ч.", "16 ч.", "1 дн.")
_RU_RELATIVE_AGE = re.compile(
    r"(?<![0-9])(\d{1,4})\s*"
    r"(?:дн\.?|дня|дней|"
    r"ч\.?|час|часа|часов|"
    r"мин\.?|минуты?|минут|"
    r"нед\.?|недели|недель)"
    r"(?=\s*[·•]|\s*$|\s+[^\d\u0400-\u04FF]|\s+[A-Za-z\u0400-\u04FF])",
    re.IGNORECASE,
)
# Day + month without year, optional "в HH:MM" (e.g. "13 апрель в 15:52", "31 март в 11:19")
_RU_DM_NO_YEAR = re.compile(
    rf"(?<![0-9])(\d{{1,2}})\s+({_RU_MONTH_NAMES})(?:\s+в\s+(\d{{1,2}}):(\d{{2}}))?(?!\s*(?:г\.?|\d{{4}}))",
    re.IGNORECASE,
)


def _reference_utc_datetime(nd: dict[str, Any]) -> datetime:
    """Instant used to resolve relative ages and missing years (scrape time or wall clock)."""
    ct = nd.get("created_time")
    if isinstance(ct, datetime):
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        return ct.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _date_from_russian_relative(head: str, ref: datetime) -> date | None:
    m = _RU_RELATIVE_AGE.search(head)
    if not m:
        return None
    n = int(m.group(1))
    if n > 999:
        return None
    span = m.group(0).lower()
    delta: timedelta | None = None
    if re.search(r"дн\.?|дня|дней", span):
        delta = timedelta(days=n)
    elif re.search(r"ч\.?|час|часа|часов", span):
        delta = timedelta(hours=n)
    elif re.search(r"мин\.?|минут", span):
        delta = timedelta(minutes=n)
    elif re.search(r"нед\.?|недели|недель", span):
        delta = timedelta(weeks=n)
    if delta is None:
        return None
    return (ref - delta).date()


def _date_from_day_month_no_year(day: int, month: int, ref: datetime) -> date | None:
    """Pick calendar year so publication date is on/before ``ref`` (Facebook-style)."""
    refd = ref.date()
    best: date | None = None
    for yr in (refd.year, refd.year - 1):
        try:
            d = date(yr, month, day)
        except ValueError:
            continue
        if d <= refd and (best is None or d > best):
            best = d
    return best


def _infer_publication_date_from_header(head: str, ref: datetime) -> date | None:
    """Parse publication date from header only (no ``created_time`` fallback)."""
    m = _RU_DMY.search(head)
    if m:
        day_s, month_word, year_s = m.group(1), m.group(2), m.group(3)
        mon = _RU_MONTH_WORD_TO_NUM.get(month_word.strip().lower())
        if mon is None:
            return None
        try:
            return date(int(year_s, 10), mon, int(day_s, 10))
        except ValueError:
            return None
    m = _ISO_YMD.search(head)
    if m:
        try:
            return date(int(m.group(1), 10), int(m.group(2), 10), int(m.group(3), 10))
        except ValueError:
            return None
    d_rel = _date_from_russian_relative(head, ref)
    if d_rel is not None:
        return d_rel
    m = _RU_DM_NO_YEAR.search(head)
    if m:
        day_s, month_word = m.group(1), m.group(2)
        mon = _RU_MONTH_WORD_TO_NUM.get(month_word.strip().lower())
        if mon is None:
            return None
        try:
            return _date_from_day_month_no_year(int(day_s, 10), mon, ref)
        except ValueError:
            return None
    m = _YEAR_WITH_GR.search(head)
    if m:
        try:
            return date(int(m.group(1), 10), 1, 1)
        except ValueError:
            return None
    return None


def _message_header_for_year_scan(message: str) -> str:
    """Use only the author/date prefix so we do not pick a year from the post body."""
    msg = message.strip()
    if not msg:
        return ""
    sep = "·"
    if sep in msg:
        return msg.split(sep, 1)[0].strip()[:700]
    return msg[:700]


def infer_publication_year_from_browser_post(nd: dict[str, Any]) -> int | None:
    """Best-effort publication year for filtering and reports.

    Prefer the **message header** (text before ``·``): Russian absolute dates, ISO, ``YYYY г.``,
    Facebook-style **relative** snippets (``3 дн.``, ``21 ч.``), and **day + month** with optional
    ``в HH:MM`` when the year is omitted (year is inferred from ``created_time`` or UTC now so the
    implied date is not in the future). If the header yields no date, fall back to ``created_time``.
    """
    msg = str(nd.get("message") or "")
    head = _message_header_for_year_scan(msg)
    ref = _reference_utc_datetime(nd)
    d = _infer_publication_date_from_header(head, ref)
    if d is not None:
        return d.year
    ct = nd.get("created_time")
    if isinstance(ct, datetime):
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        return ct.astimezone(timezone.utc).year
    return None


def infer_publication_date_from_browser_post(nd: dict[str, Any]) -> date | None:
    """Best-effort publication calendar date (UTC for ``created_time`` fallback).

    Header parsing matches Facebook Russian snippets: full DMY, ISO, relative ages (``дн.``/``ч.``/…),
    day+month with optional clock time, ``YYYY г.``. If the header has no date, use ``created_time`` date.
    """
    msg = str(nd.get("message") or "")
    head = _message_header_for_year_scan(msg)
    ref = _reference_utc_datetime(nd)
    d = _infer_publication_date_from_header(head, ref)
    if d is not None:
        return d
    ct = nd.get("created_time")
    if isinstance(ct, datetime):
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        return ct.astimezone(timezone.utc).date()
    return None


def browser_publication_cutoff_date(settings: Settings) -> date | None:
    """Minimum inclusive publication date when month is configured; else None (year-only mode)."""
    y = settings.browser_post_publication_year
    m = settings.browser_post_publication_month
    if y is None or m is None:
        return None
    d = settings.browser_post_publication_day if settings.browser_post_publication_day is not None else 1
    return date(y, m, d)


def post_publication_matches_settings_filter(nd: dict[str, Any], settings: Settings) -> bool:
    """Apply ``BROWSER_POST_PUBLICATION_*`` env: year-only equality, or from-date when month is set."""
    cutoff = browser_publication_cutoff_date(settings)
    ku = settings.browser_post_publication_keep_unknown_year
    year_f = settings.browser_post_publication_year

    if cutoff is not None:
        d = infer_publication_date_from_browser_post(nd)
        if d is not None:
            return d >= cutoff
        y = infer_publication_year_from_browser_post(nd)
        if y is None:
            return ku
        if y < cutoff.year:
            return False
        if y > cutoff.year:
            return True
        return ku

    if year_f is None:
        return True
    return post_publication_year_matches_filter(nd, year_f, keep_unknown_year=ku)


def post_publication_year_matches_filter(
    nd: dict[str, Any],
    allowed_year: int | None,
    *,
    keep_unknown_year: bool = False,
) -> bool:
    """If ``allowed_year`` is set, keep only posts whose inferred publication year equals it.

    When the year cannot be inferred, the post is dropped unless ``keep_unknown_year`` is true.
    """
    if allowed_year is None:
        return True
    inferred = infer_publication_year_from_browser_post(nd)
    if inferred is None:
        return keep_unknown_year
    return inferred == allowed_year


def merge_discovered_group_lists(
    priority: list[DiscoveredGroup],
    secondary: list[DiscoveredGroup],
    limit: int,
) -> list[DiscoveredGroup]:
    """Dedupe by canonical group URL; fill up to `limit` with `priority` first, then `secondary`."""
    seen: set[str] = set()
    merged: list[DiscoveredGroup] = []
    for g in priority + secondary:
        key = g.group_url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(g)
        if len(merged) >= limit:
            break
    return merged


def run_browser_group_search(
    settings: Settings,
    *,
    query: str | None = None,
    in_group_query: str | None = None,
    in_group_queries: Sequence[str] | None = None,
    group_limit: int | None = None,
    post_limit_per_group: int | None = None,
    seed_groups: list[DiscoveredGroup] | None = None,
    runner_factory: type[PlaywrightCliRunner] = PlaywrightCliRunner,
    global_message_contains: str | None = None,
) -> dict[str, Any]:
    search_query = (query or settings.browser_search_query or "job").strip() or "job"
    default_in_group = (
        (in_group_query or settings.browser_in_group_search_query or "").strip() or search_query
    )
    if in_group_queries is not None:
        phrases = [str(p).strip() for p in in_group_queries if str(p).strip()]
        if not phrases:
            phrases = [default_in_group]
    else:
        phrases = [default_in_group]
    in_group_kw = phrases[0]
    safe_group_limit = _coerce_limit(group_limit, settings.browser_group_scan_limit)
    safe_post_limit = _coerce_limit(post_limit_per_group, settings.browser_post_limit_per_group)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path("output") / "playwright" / timestamp
    runner = runner_factory(
        headed=not settings.browser_headless,
        timeout_seconds=settings.browser_search_timeout_seconds,
        output_dir=output_dir,
    )
    gmc = (global_message_contains or "").strip() or None
    year_f = settings.browser_post_publication_year
    cutoff = browser_publication_cutoff_date(settings)
    logger.info(
        "Starting browser search sync discover_query=%s in_group_queries=%s group_limit=%s post_limit=%s "
        "global_message_contains=%s publication_year_filter=%s publication_from_date=%s",
        search_query,
        phrases,
        safe_group_limit,
        safe_post_limit,
        gmc,
        year_f,
        cutoff.isoformat() if cutoff else None,
    )
    try:
        ensure_logged_in(runner, settings=settings)
        discovered = discover_groups(search_query, safe_group_limit, runner)
        seeds = list(seed_groups or [])
        groups = merge_discovered_group_lists(seeds, discovered, safe_group_limit)
        logger.info(
            "Browser search groups total=%s (seed=%s discovered=%s) discover_query=%s in_group_queries=%s",
            len(groups),
            len(seeds),
            len(discovered),
            search_query,
            phrases,
        )
        results_by_url: dict[str, dict[str, Any]] = {}
        for group in groups:
            key = group.group_url.rstrip("/").lower()
            results_by_url[key] = {
                "group_name": group.group_name,
                "group_id": group.group_id,
                "group_url": group.group_url,
                "posts": [],
            }
        seen_post_id_by_url: dict[str, set[str]] = defaultdict(set)
        errors: list[dict[str, Any]] = []
        found_total = 0
        for phrase in phrases:
            for group in groups:
                gkey = group.group_url.rstrip("/").lower()
                bucket = results_by_url[gkey]
                try:
                    posts = extract_group_job_posts(group, phrase, safe_post_limit, runner)
                    logger.info(
                        "Browser search group=%s phrase=%r raw_hits=%s",
                        group.group_url,
                        phrase,
                        len(posts),
                    )
                    for post in posts:
                        nd = normalize_browser_post(post, query=phrase)
                        pid = str(nd.get("id") or "")
                        if not pid:
                            continue
                        if not post_matches_global_message_filter(nd.get("message"), gmc):
                            continue
                        if not post_publication_matches_settings_filter(nd, settings):
                            logger.debug(
                                "Skipping post %s: publication date=%s year=%s cutoff=%s year_filter=%s",
                                pid,
                                infer_publication_date_from_browser_post(nd),
                                infer_publication_year_from_browser_post(nd),
                                cutoff.isoformat() if cutoff else None,
                                year_f,
                            )
                            continue
                        if pid in seen_post_id_by_url[gkey]:
                            continue
                        seen_post_id_by_url[gkey].add(pid)
                        bucket["posts"].append(nd)
                        found_total += 1
                except BrowserAutomationError as exc:
                    logger.warning(
                        "Browser extraction failed for group=%s phrase=%r: %s",
                        group.group_url,
                        phrase,
                        exc,
                    )
                    errors.append(
                        {
                            "group_url": group.group_url,
                            "group_name": group.group_name,
                            "phrase": phrase,
                            "error": str(exc),
                        }
                    )
                    try:
                        runner.snapshot(f"group-error-{_slugify(group.group_name)}")
                        runner.screenshot(f"group-error-{_slugify(group.group_name)}")
                    except BrowserAutomationError:
                        logger.debug("Failed to capture diagnostics for group error", exc_info=True)
        results = list(results_by_url.values())
        out: dict[str, Any] = {
            "ok": True,
            "query": search_query,
            "in_group_query": in_group_kw,
            "in_group_queries": phrases,
            "groups_scanned": len(groups),
            "groups": results,
            "found_posts": found_total,
            "errors": errors,
            "artifacts_dir": str(output_dir),
        }
        if gmc:
            out["global_message_contains"] = gmc
        if year_f is not None:
            out["publication_year_filter"] = year_f
        if cutoff is not None:
            out["publication_from_date"] = cutoff.isoformat()
        return out
    finally:
        runner.close()


_JS_FB_ENV_LOGIN = """async (page) => {{
  const email = {email_js};
  const password = {password_js};
  const emailSel = 'input[name="email"], input#email';
  const passSel = 'input[name="pass"], input#pass';
  try {{
    await page.waitForSelector(emailSel, {{ timeout: 12000 }});
  }} catch (e) {{
    return JSON.stringify({{ ok: false, reason: "no_form" }});
  }}
  await page.fill(emailSel, email);
  await page.fill(passSel, password);
  const buttons = ['button[name="login"]', '[data-testid="royal-login-button"]', 'button[type="submit"]'];
  for (const sel of buttons) {{
    const h = await page.$(sel);
    if (h) {{
      try {{
        await h.click();
        break;
      }} catch (e) {{}}
    }}
  }}
  try {{ await page.keyboard.press('Enter'); }} catch (e) {{}}
  for (let _w = 0; _w < 16; _w += 1) {{
    try {{
      await page.evaluate((ms) => new Promise((r) => globalThis.setTimeout(r, ms)), 500);
    }} catch (e) {{
      break;
    }}
  }}
  return JSON.stringify({{ ok: true }});
}}"""


def _run_facebook_env_login_script(runner: PlaywrightCliRunner, *, email: str, password: str) -> dict[str, Any]:
    code = _JS_FB_ENV_LOGIN.format(email_js=json.dumps(email), password_js=json.dumps(password))
    out = runner.run_code(code)
    try:
        return _parse_playwright_cli_run_code_json_payload(out)
    except json.JSONDecodeError:
        logger.warning("Could not parse Playwright output after env login attempt")
        return {"ok": False, "reason": "parse_error"}


def _try_facebook_env_credentials(runner: PlaywrightCliRunner, *, email: str, password: str) -> None:
    first = _run_facebook_env_login_script(runner, email=email, password=password)
    if first.get("reason") == "no_form":
        runner.open("https://www.facebook.com/login/")
        time.sleep(2)
        _run_facebook_env_login_script(runner, email=email, password=password)


def ensure_logged_in(runner: PlaywrightCliRunner, *, settings: Settings) -> None:
    from src.services.facebook_challenge_vision import maybe_resolve_meta_visual_challenge

    timeout_seconds = settings.browser_search_timeout_seconds
    runner.open("https://www.facebook.com/")
    runner.snapshot("facebook-home")
    if _is_logged_in(runner):
        return
    maybe_resolve_meta_visual_challenge(runner, settings, is_logged_in=lambda: _is_logged_in(runner))
    if _is_logged_in(runner):
        return
    if settings.facebook_web_credentials_configured():
        em = settings.facebook_web_login
        pw = settings.facebook_web_password
        if em is not None and pw is not None:
            logger.info(
                "FACEBOOK_WEB_LOGIN is set: attempting automated web sign-in "
                "(Meta may require 2FA, captchas, or approvals — complete those in the browser if shown)"
            )
            try:
                _try_facebook_env_credentials(runner, email=em, password=pw)
            except BrowserAutomationError as exc:
                logger.warning("Automated web login failed: %s", exc)
            try:
                runner.snapshot("facebook-after-env-login")
            except BrowserAutomationError:
                logger.debug("Snapshot after env login failed", exc_info=True)
            if _is_logged_in(runner):
                return
            maybe_resolve_meta_visual_challenge(runner, settings, is_logged_in=lambda: _is_logged_in(runner))
            if _is_logged_in(runner):
                return
    logger.info("Facebook login required; waiting for manual completion")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        maybe_resolve_meta_visual_challenge(runner, settings, is_logged_in=lambda: _is_logged_in(runner))
        time.sleep(5)
        if _is_logged_in(runner):
            runner.snapshot("facebook-after-login")
            return
    try:
        runner.screenshot("login-required-timeout")
    except BrowserAutomationError:
        logger.debug("Unable to capture login timeout screenshot", exc_info=True)
    raise ManualLoginRequiredError("manual Facebook login was not completed before timeout")


def _is_logged_in(runner: PlaywrightCliRunner) -> bool:
    payload = runner.run_json(
        """
const hasLoginForm = !!document.querySelector('input[name="email"], input[name="pass"]');
const hasAppShell = !!document.querySelector('[role="feed"], [role="navigation"], a[href*="/friends/"], a[href*="/groups/"]');
return { logged_in: !hasLoginForm && hasAppShell };
""".strip()
    )
    return bool(payload.get("logged_in"))


def discover_groups(query: str, limit: int, runner: PlaywrightCliRunner) -> list[DiscoveredGroup]:
    search_url = f"https://www.facebook.com/search/groups/?q={quote(query)}"
    runner.open(search_url)
    runner.snapshot("group-search-results")
    payload = runner.run_json(
        """
const anchors = Array.from(document.querySelectorAll('a[href*="/groups/"]'));
const seen = new Set();
const groups = [];
for (const anchor of anchors) {
  const href = anchor.href || "";
  if (!/facebook\\.com\\/groups\\//.test(href)) continue;
  if (/\\/(posts|search|members|about|media|events|files)\\b/.test(href)) continue;
  const url = href.split("?")[0].replace(/\\/$/, "");
  if (!url || seen.has(url)) continue;
  const name = (anchor.textContent || "").replace(/\\s+/g, " ").trim();
  if (!name) continue;
  seen.add(url);
  groups.push({ group_name: name, group_url: url });
}
return groups;
""".strip(),
        scroll_rounds=3,
        scroll_pause_ms=800,
    )
    groups: list[DiscoveredGroup] = []
    for item in payload[:limit]:
        url = str(item.get("group_url") or "").strip()
        name = str(item.get("group_name") or "").strip()
        if not url or not name:
            continue
        groups.append(
            DiscoveredGroup(
                group_name=name,
                group_url=url,
                group_id=extract_group_id(url),
            )
        )
    return groups


def extract_group_job_posts(
    group: DiscoveredGroup,
    keyword: str,
    limit: int,
    runner: PlaywrightCliRunner,
) -> list[BrowserFoundPost]:
    runner.open(build_group_search_url(group.group_url, keyword))
    runner.snapshot(f"group-search-{_slugify(group.group_name)}")
    payload = runner.run_json(
        """
const squeeze = value => (value || "").replace(/\\s+/g, " ").trim();
const bodyText = squeeze(document.body?.innerText || "");
if (/content isn't available|This content isn't available|join group to see/i.test(bodyText)) {
  return { inaccessible: true, posts: [] };
}
const postAnchors = Array.from(document.querySelectorAll('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid="], a[href*="multi_permalinks="]'));
const seen = new Set();
const posts = [];
for (const anchor of postAnchors) {
  const href = anchor.href || "";
  if (!href || seen.has(href)) continue;
  const article = anchor.closest('[role="article"]') || anchor.closest('div[data-pagelet]') || anchor.parentElement;
  const text = squeeze(article?.innerText || anchor.textContent || "");
  if (!text) continue;
  const timeEl = article?.querySelector('a[aria-label] time, time');
  const authorEl = article?.querySelector('h2 a, h3 a, strong a');
  seen.add(href);
  posts.push({
    post_url: href,
    message: text.slice(0, 4000),
    author_name: squeeze(authorEl?.textContent || ""),
    created_time: timeEl?.getAttribute('datetime') || "",
  });
}
return { inaccessible: false, posts };
""".strip(),
        scroll_rounds=4,
        scroll_pause_ms=900,
    )
    if payload.get("inaccessible"):
        raise BrowserAutomationError("group content is unavailable or requires membership")
    posts: list[BrowserFoundPost] = []
    for item in payload.get("posts", [])[:limit]:
        post_url = str(item.get("post_url") or "").strip()
        if not post_url:
            continue
        created_time = _parse_possible_datetime(item.get("created_time"))
        posts.append(
            BrowserFoundPost(
                external_id=extract_post_external_id(post_url),
                group_id=group.group_id or derive_group_key(group.group_url),
                group_name=group.group_name,
                group_url=group.group_url,
                post_url=post_url,
                message=str(item.get("message") or "").strip(),
                author_name=(str(item.get("author_name") or "").strip() or None),
                created_time=created_time,
                raw_payload={
                    "group": asdict(group),
                    "extracted": item,
                    "keyword": keyword,
                },
            )
        )
    return posts


def normalize_browser_post(found: BrowserFoundPost, *, query: str) -> dict[str, Any]:
    post_id = build_post_id(found)
    group_id = found.group_id or derive_group_key(found.group_url)
    return {
        "id": post_id,
        "group_id": group_id,
        "message": found.message,
        "author_id": None,
        "author_name": found.author_name,
        "created_time": found.created_time,
        "permalink_url": found.post_url,
        "raw_json": {
            "source_type": "playwright_browser",
            "query": query,
            "group_name": found.group_name,
            "group_url": found.group_url,
            "post_url": found.post_url,
            "external_id": found.external_id,
            "payload": found.raw_payload,
        },
    }


def build_group_search_url(group_url: str, keyword: str) -> str:
    return f"{group_url.rstrip('/')}/search/?q={quote(keyword)}"


def extract_group_id(group_url: str) -> str | None:
    match = _GROUP_URL_RE.search(group_url)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def derive_group_key(group_url: str) -> str:
    return f"pwgrp_{hashlib.sha256(group_url.encode('utf-8')).hexdigest()[:26]}"


def extract_post_external_id(post_url: str) -> str | None:
    normalized = post_url.strip()
    if not normalized:
        return None
    for pattern in _POST_ID_PATTERNS:
        match = pattern.search(normalized)
        if match:
            value = match.group(1).strip()
            if value:
                return value[:64]
    return None


def build_post_id(found: BrowserFoundPost) -> str:
    if found.external_id:
        return found.external_id[:64]
    digest = hashlib.sha256(found.post_url.encode("utf-8")).hexdigest()
    return f"pw_{digest[:61]}"


def _parse_possible_datetime(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw)
    except Exception:
        return None


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned or "artifact"


def _coerce_limit(value: object, default: int) -> int:
    try:
        parsed = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(1, min(parsed, 100))
