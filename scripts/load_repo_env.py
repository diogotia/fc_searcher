"""Load project-root `.env` into `os.environ` (supports `export KEY=`, quoted values).

When you run `python3 scripts/…`, Python puts `scripts/` on `sys.path`, so other scripts
can `from load_repo_env import load_dotenv_file`.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

_VAR = re.compile(
    r"^(?:export\s+)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$",
    re.IGNORECASE,
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    # Unquoted: strip trailing ` # comment` (common when copying from examples)
    value = re.sub(r"\s+#.*$", "", value).strip()
    return value


def load_dotenv_file(path: Path | None = None) -> Path | None:
    """Parse `.env` and set `os.environ`. Returns path if read.

    For each key, if the file contains several assignments, the **last non-empty** value
    wins. That way a real ``FACEBOOK_SHORT_TOKEN=EAAG...`` is not wiped by a later empty
    ``FACEBOOK_SHORT_TOKEN=`` line (often left over from ``.env.example``).
    """
    path = path or project_root() / ".env"
    if not path.is_file():
        return None
    pairs: list[tuple[str, str]] = []
    # utf-8-sig strips a UTF-8 BOM so the first key is not "\ufeffFACEBOOK_..."
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip().replace("\r", "")
        if not line or line.startswith("#"):
            continue
        m = _VAR.match(line)
        if not m:
            continue
        key = m.group(1)
        value = _parse_value(m.group(2))
        pairs.append((key, value))

    buckets: defaultdict[str, list[str]] = defaultdict(list)
    for key, value in pairs:
        buckets[key].append(value)
    for key, values in buckets.items():
        if key in os.environ:
            # Respect variables already set for this process (e.g. ``REPORTS_DIR=./reports`` on the
            # command line before ``load_dotenv_file()``), same as python-dotenv ``override=False``.
            continue
        nonempty = [v for v in values if v.strip()]
        os.environ[key] = nonempty[-1] if nonempty else values[-1]
    return path
