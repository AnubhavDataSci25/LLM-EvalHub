"""Shared text normalisation.

Both the deterministic evaluators and the lexical embedder tokenise text, and
they must agree: if the metric layer treats "refund" and "refunds" as the same
term but the retriever does not, retrieval quality and the retrieval *metrics*
disagree with each other. Keeping one implementation here prevents that drift.
"""

from __future__ import annotations

import re

WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

STOPWORDS = frozenset(
    """a an the is are was were be been being of to in on for with and or as at by from
    that this these those it its was do does did not no but if then than so such can could
    will would shall should may might must have has had i you he she they we our your their
    what which who whom when where why how""".split()
)


def stem(token: str) -> str:
    """Very light suffix stripping so `refund` and `refunds` match.

    Deliberately not a full Porter stemmer: predictability matters more than
    linguistic completeness for a deterministic metric.
    """
    for suffix in ("ies", "ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            base = token[: -len(suffix)]
            return base + "y" if suffix == "ies" else base
    return token


def tokenize(text: str | None, *, drop_stopwords: bool = True, apply_stem: bool = True) -> list[str]:
    tokens = WORD_RE.findall((text or "").lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return [stem(t) for t in tokens] if apply_stem else tokens


def token_set(text: str | None, *, drop_stopwords: bool = True) -> set[str]:
    return set(tokenize(text, drop_stopwords=drop_stopwords))


def split_sentences(text: str | None) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text or "") if s.strip()]
