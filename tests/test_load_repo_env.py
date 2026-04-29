from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from load_repo_env import load_dotenv_file  # noqa: E402


@pytest.fixture()
def clear_facebook_keys(monkeypatch):
    for k in list(os.environ):
        if k.startswith("FACEBOOK_") or k == "FB_EXCHANGE_TOKEN":
            monkeypatch.delenv(k, raising=False)


def test_last_nonempty_value_wins_for_duplicate_key(tmp_path, monkeypatch, clear_facebook_keys):
    p = tmp_path / ".env"
    p.write_text(
        "FACEBOOK_SHORT_TOKEN=first_token_value\n"
        "FACEBOOK_SHORT_TOKEN=\n",
        encoding="utf-8",
    )
    assert load_dotenv_file(p) == p
    assert os.environ["FACEBOOK_SHORT_TOKEN"] == "first_token_value"


def test_unquoted_inline_comment_stripped(tmp_path, monkeypatch, clear_facebook_keys):
    p = tmp_path / ".env"
    p.write_text("FACEBOOK_APP_ID=999888  # app id from console\n", encoding="utf-8")
    assert load_dotenv_file(p) == p
    assert os.environ["FACEBOOK_APP_ID"] == "999888"
