"""Opt-in Anthropic vision assist for Meta post-login visual security puzzles (e.g. match icon to cup).

This does not bypass Meta protections; it may fail or violate terms if misused. Off by default.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from anthropic import Anthropic

from src.config import Settings
from src.config_anthropic import get_anthropic_settings

logger = logging.getLogger(__name__)

_MAX_RIGHT_CLICKS = 24
_VISION_ROUNDS = 8


class PlaywrightChallengeRunner(Protocol):
    def screenshot(self, label: str) -> Path: ...
    def run_code(self, code: str) -> str: ...


def _parse_pw_stdout(stdout: str) -> Any:
    from src.services.browser_search import _parse_playwright_cli_run_code_json_payload

    return _parse_playwright_cli_run_code_json_payload(stdout)


def _meta_challenge_detected(runner: PlaywrightChallengeRunner) -> bool:
    code = r"""
async (page) => {
  await page.waitForLoadState('domcontentloaded', { timeout: 15000 }).catch(() => {});
  const url = (page.url() || "").toLowerCase();
  const text = ((document.body && document.body.innerText) || "").slice(0, 16000).toLowerCase();
  const challenge =
    url.includes("two_step_verification") ||
    url.includes("checkpoint") ||
    (/\bsubmit\b/.test(text) &&
      (/icon for|fullest cup|match the icon|arrows to match|use the arrows|security check|pick the/i.test(
        text
      ) ||
        (/cup/.test(text) && /icon/.test(text))));
  return JSON.stringify({ challenge, url: page.url() });
}
""".strip()
    try:
        out = _parse_pw_stdout(runner.run_code(code))
        if isinstance(out, dict):
            return bool(out.get("challenge"))
    except Exception:
        logger.debug("Meta challenge detection failed", exc_info=True)
    return False


def _press_arrow_right(runner: PlaywrightChallengeRunner, n: int) -> None:
    if n <= 0:
        return
    safe = min(int(n), _MAX_RIGHT_CLICKS)
    code = (
        "async (page) => {\n"
        f"  for (let i = 0; i < {safe}; i++) {{\n"
        "    try { await page.keyboard.press('ArrowRight'); } catch (e) {}\n"
        "    try {\n"
        "      await page.evaluate((ms) => new Promise((r) => globalThis.setTimeout(r, ms)), 380);\n"
        "    } catch (e) {}\n"
        "  }\n"
        "  return JSON.stringify({ ok: true, n: "
        + str(safe)
        + " });\n"
        "}"
    )
    try:
        runner.run_code(code)
    except Exception as exc:
        logger.warning("ArrowRight presses failed: %s", exc)


def _click_challenge_submit(runner: PlaywrightChallengeRunner) -> None:
    code = r"""
async (page) => {
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim().toLowerCase();
  const candidates = Array.from(document.querySelectorAll('button, [role="button"]'));
  let picked = candidates.find((b) => norm(b.textContent) === "submit");
  if (!picked) {
    picked = candidates.find((b) => /^submit\b/i.test((b.textContent || "").trim()));
  }
  if (!picked) {
    picked = candidates.find((b) => /submit/i.test(b.getAttribute("aria-label") || ""));
  }
  if (picked) {
    try {
      await picked.click({ timeout: 5000 });
    } catch (e) {}
  }
  return JSON.stringify({ clicked: !!picked });
}
""".strip()
    try:
        runner.run_code(code)
    except Exception as exc:
        logger.warning("Challenge Submit click failed: %s", exc)


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start : end + 1])


def _vision_plan_challenge(screenshot_path: Path) -> dict[str, Any]:
    ai = get_anthropic_settings()
    if not ai.anthropic_api_key:
        return {"right_arrow_clicks": 0, "submit": False}
    client = Anthropic(api_key=ai.anthropic_api_key)
    b64 = base64.standard_b64encode(screenshot_path.read_bytes()).decode("ascii")
    prompt = """You are helping resolve a Meta/Facebook browser security puzzle shown in the screenshot.

Typical layout: instruction text at the top; a reference icon on the left; a larger scene on the right with objects (e.g. cups) and small icons; left/right arrow controls to rotate which icon is aligned with which object; a blue "Submit" button.

Read the instruction exactly (e.g. match the left icon to the cup with the most liquid). The RIGHT arrow usually rotates assignments clockwise — choose how many times (0–24) to press the RIGHT arrow so the target icon from the left sits on the correct object per the instruction, BEFORE pressing Submit.

Return ONLY a JSON object (no markdown), shape:
{"right_arrow_clicks": <int 0-24>, "submit": <true if the puzzle looks correctly aligned and Submit should be pressed, else false>}

If this screenshot is not that puzzle, return {"right_arrow_clicks": 0, "submit": false}."""

    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            },
        },
        {"type": "text", "text": prompt},
    ]
    response = client.messages.create(
        model=ai.claude_model,
        max_tokens=256,
        messages=[{"role": "user", "content": content}],
    )
    parts: list[str] = []
    for block in response.content:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    raw = "\n".join(parts) if parts else ""
    parsed = _extract_json_object(raw)
    clicks = int(parsed.get("right_arrow_clicks") or 0)
    parsed["right_arrow_clicks"] = max(0, min(_MAX_RIGHT_CLICKS, clicks))
    parsed["submit"] = bool(parsed.get("submit"))
    return parsed


def maybe_resolve_meta_visual_challenge(
    runner: PlaywrightChallengeRunner,
    settings: Settings,
    *,
    is_logged_in: Callable[[], bool],
) -> None:
    """If a Meta visual challenge is visible and env allows, screenshot → vision → ArrowRight × N → optional Submit."""
    if not settings.enable_browser_meta_challenge_vision:
        return
    if not get_anthropic_settings().anthropic_api_key:
        logger.debug("Meta challenge vision skipped: no ANTHROPIC_API_KEY")
        return

    for round_idx in range(_VISION_ROUNDS):
        if is_logged_in():
            return
        if not _meta_challenge_detected(runner):
            return
        try:
            shot = runner.screenshot(f"meta-challenge-r{round_idx}")
        except Exception as exc:
            logger.warning("Challenge screenshot failed: %s", exc)
            return
        try:
            plan = _vision_plan_challenge(shot)
        except Exception as exc:
            logger.warning("Vision plan for Meta challenge failed: %s", exc)
            return
        n = int(plan.get("right_arrow_clicks") or 0)
        do_submit = bool(plan.get("submit"))
        logger.info(
            "Meta challenge vision round=%s right_arrow_clicks=%s submit=%s",
            round_idx + 1,
            n,
            do_submit,
        )
        _press_arrow_right(runner, n)
        time.sleep(0.4)
        if do_submit:
            _click_challenge_submit(runner)
            time.sleep(2.0)
        else:
            time.sleep(0.8)

        if not _meta_challenge_detected(runner):
            return
