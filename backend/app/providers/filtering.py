"""Data-driven filtering of non-chat models.

Filters out embeddings, moderation, speech/audio, pure image/video generation,
rerankers, and safety classifiers so only text-generation models remain.
"""

from __future__ import annotations

import re
from typing import Any

from app.providers.base import ModelInfo

# Pattern rules for non-chat identifiers
# Category -> list of compiled regex patterns tested against model ID and label
NON_CHAT_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "embedding": [
        re.compile(r"\bembed(dings?|qa)?\b", re.IGNORECASE),
        re.compile(r"text-embedding", re.IGNORECASE),
        re.compile(r"\bbge-(small|base|large|m3|en|multilingual)", re.IGNORECASE),
        re.compile(r"\be5-(small|base|large|mistral|multilingual)", re.IGNORECASE),
        re.compile(r"\bgte-(small|base|large|qwen)", re.IGNORECASE),
        re.compile(r"sentence-transformers", re.IGNORECASE),
        re.compile(r"nomic-embed", re.IGNORECASE),
        re.compile(r"arctic-embed", re.IGNORECASE),
    ],
    "moderation_guard": [
        re.compile(r"prompt-guard", re.IGNORECASE),
        re.compile(r"llama-guard", re.IGNORECASE),
        re.compile(r"\bguard\b", re.IGNORECASE),
        re.compile(r"shieldgemma", re.IGNORECASE),
        re.compile(r"moderation", re.IGNORECASE),
        re.compile(r"wildguard", re.IGNORECASE),
        re.compile(r"safeguard", re.IGNORECASE),
    ],
    "speech_audio": [
        re.compile(r"\bwhisper\b", re.IGNORECASE),
        re.compile(r"\btts\b", re.IGNORECASE),
        re.compile(r"\bstt\b", re.IGNORECASE),
        re.compile(r"\bspeech\b", re.IGNORECASE),
        re.compile(r"\baudio\b", re.IGNORECASE),
        re.compile(r"\bbark\b", re.IGNORECASE),
        re.compile(r"seamless-m4t", re.IGNORECASE),
        re.compile(r"orpheus-(v\d+|arabic)", re.IGNORECASE),
        re.compile(r"eleven", re.IGNORECASE),
    ],
    "image_video_generation": [
        re.compile(r"\bdall-e\b", re.IGNORECASE),
        re.compile(r"stable-diffusion", re.IGNORECASE),
        re.compile(r"\bflux\b", re.IGNORECASE),
        re.compile(r"\bimagen\b", re.IGNORECASE),
        re.compile(r"\bmidjourney\b", re.IGNORECASE),
        re.compile(r"\bsdxl\b", re.IGNORECASE),
        re.compile(r"\bcanvas\b", re.IGNORECASE),
        re.compile(r"video-generation", re.IGNORECASE),
    ],
    "reranker": [
        re.compile(r"\brerank(er|ing)?\b", re.IGNORECASE),
        re.compile(r"bge-rerank", re.IGNORECASE),
        re.compile(r"cohere-rerank", re.IGNORECASE),
    ],
    "reward_classifier": [
        re.compile(r"reward-model", re.IGNORECASE),
        re.compile(r"[-_]rm[-_]", re.IGNORECASE),
        re.compile(r"\bclassifier\b", re.IGNORECASE),
        re.compile(r"\baqa\b", re.IGNORECASE),
    ],
}


def non_chat_category(
    model_id: str | ModelInfo,
    label: str = "",
    description: str = "",
    raw_meta: dict[str, Any] | None = None,
) -> str | None:
    """Return the excluded category name if model is non-chat, or None if it is a text model."""
    if isinstance(model_id, ModelInfo):
        info = model_id
        model_id = info.id
        label = info.label or ""
        description = info.description or ""
        raw_meta = getattr(info, "raw_meta", {}) or getattr(info, "pricing", {})

    meta = raw_meta or {}
    text_to_scan = f"{model_id} {label} {description}".lower()

    # 1. OpenRouter modality check (e.g. "text->image" or "image->image")
    modality = str(meta.get("architecture", {}).get("modality", "") or meta.get("modality", ""))
    if modality and "->text" not in modality and modality != "text->text":
        return "non_text_modality"

    # 2. Gemini supportedGenerationMethods check
    methods = meta.get("supportedGenerationMethods") or []
    if methods and "generateContent" not in methods:
        return "unsupported_generation_method"

    # 3. Known regex patterns
    for category, patterns in NON_CHAT_PATTERNS.items():
        for pat in patterns:
            if pat.search(text_to_scan):
                return category

    return None


def is_chat_model(
    model_id: str | ModelInfo,
    label: str = "",
    description: str = "",
    raw_meta: dict[str, Any] | None = None,
) -> bool:
    """True if model is a text generation / chat model."""
    return non_chat_category(model_id, label, description, raw_meta) is None


def filter_chat_models(
    models: list[ModelInfo],
) -> tuple[list[ModelInfo], list[tuple[ModelInfo, str]]]:
    """Partition a list of ModelInfo into (chat_models, excluded_with_reasons)."""
    chat_models: list[ModelInfo] = []
    excluded: list[tuple[ModelInfo, str]] = []

    for m in models:
        category = non_chat_category(m.id, m.label or "", m.description or "")
        if category is None:
            chat_models.append(m)
        else:
            excluded.append((m, f"Excluded non-chat model (category: {category})"))

    return chat_models, excluded
