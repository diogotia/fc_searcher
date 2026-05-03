"""Specialized in-group search phrases (VK/Facebook-style tags) for construction / repair niche.

Used by ``scripts/run_browser_search_parent_then_construction_tags.py`` as **additional**
``in_group_query`` passes after the parent job-search flow.
"""

from __future__ import annotations

from typing import TypedDict


class ConstructionHashtag(TypedDict):
    tag: str
    label_en: str


SPECIALIZED_CONSTRUCTION_TAGS: list[ConstructionHashtag] = [
    {"tag": "#рабочий_строительства", "label_en": "Construction worker"},
    {"tag": "#строитель", "label_en": "Builder"},
    {"tag": "#плотник", "label_en": "Carpenter"},
    {"tag": "#столяр", "label_en": "Joiner"},
]


def tag_strings() -> list[str]:
    return [entry["tag"] for entry in SPECIALIZED_CONSTRUCTION_TAGS]


def tag_to_in_group_search(tag: str) -> str:
    """Facebook group search works better with words than raw hashtags: ``#a_b`` → ``a b``."""
    t = (tag or "").strip().lstrip("#").replace("_", " ").strip()
    return t


def merge_parent_in_group_with_additional(parent: str, additional_phrase: str) -> str:
    """Combine main in-group phrase with a niche phrase for ``/groups/.../search/?q=`` (one string, space-separated).

    Avoids duplicating the parent when ``additional`` already contains it. If ``parent`` is empty,
    returns ``additional_phrase`` only.
    """
    p = (parent or "").strip()
    a = (additional_phrase or "").strip()
    if not p:
        return a
    if not a:
        return p
    pl, al = p.casefold(), a.casefold()
    if pl in al:
        return a
    if al in pl:
        return p
    return f"{p} {a}"
