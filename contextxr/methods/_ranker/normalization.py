"""Minimal normalization helpers for the context facet ranker.

Ported from the paper's research code (context_facet_ranker); logic unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List


_WHITESPACE_RE = re.compile(r"\s+")
_SLASH_RE = re.compile(r"\s*/\s*")


def normalize_label(value: object) -> str:
    """Normalize labels conservatively: lowercase, trim, collapse spaces."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.strip().lower()
    text = _WHITESPACE_RE.sub(" ", text)
    text = _SLASH_RE.sub(" / ", text)
    return text


def clean_display_label(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.strip()
    text = _WHITESPACE_RE.sub(" ", text)
    text = _SLASH_RE.sub(" / ", text)
    return text


def normalize_column_name(value: object) -> str:
    text = clean_display_label(value).lower()
    text = text.replace("-", "_").replace(" ", "_")
    return text


def capability_name(value: object) -> str:
    raw = normalize_label(value)
    if not raw:
        return ""
    if "." in raw and " " not in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


def split_multi_value_field(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        raw = str(value).strip()
        if not raw:
            return []
        separator = "|"
        if "|" not in raw and ";" in raw:
            separator = ";"
        elif "|" not in raw and ";" not in raw and "," in raw:
            separator = ","
        items = [part.strip() for part in raw.split(separator)]
    out: List[str] = []
    seen = set()
    for item in items:
        normalized = normalize_label(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def dedupe_preserve(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
