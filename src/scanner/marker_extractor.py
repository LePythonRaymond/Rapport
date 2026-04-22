"""
Marker detection and field extraction for (REMPLA) and (BRIEF) messages.

Detection is fast and regex-based. Field extraction for REMPLA tries a
structured parse first (plante / taille / lieu separated by `/` or `,`), and
falls back to Gemini for free-form or multi-plant messages.
"""

import json
import re
from enum import Enum
from typing import Dict, Optional, Tuple

# (REMPLA) and (BRIEF) — tolerant of parentheses, case, surrounding whitespace.
# Requires word boundary-like behavior so we don't match "remplacement" inside a longer word.
REMPLA_PATTERN = re.compile(r"\(?\s*REMPLA\s*\)?", re.IGNORECASE)
BRIEF_PATTERN = re.compile(r"\(?\s*BRIEF\s*\)?", re.IGNORECASE)


class MarkerType(str, Enum):
    """Marker type detected in a message."""

    REMPLA = "rempla"
    BRIEF = "brief"
    NONE = "none"


def detect_marker(text: str) -> MarkerType:
    """
    Detect whether a message contains a REMPLA or BRIEF marker.

    REMPLA takes precedence over BRIEF if both are present (rare case, but
    REMPLA is the more specific/actionable marker).

    Args:
        text: The message text to scan.

    Returns:
        MarkerType.REMPLA, MarkerType.BRIEF, or MarkerType.NONE.
    """
    if not text:
        return MarkerType.NONE

    if REMPLA_PATTERN.search(text):
        return MarkerType.REMPLA
    if BRIEF_PATTERN.search(text):
        return MarkerType.BRIEF
    return MarkerType.NONE


def _text_after_marker(text: str, pattern: re.Pattern) -> str:
    """Return everything after the first marker match, stripped."""
    match = pattern.search(text)
    if not match:
        return text.strip()
    return text[match.end():].strip(" :-\n\t").strip()


def _try_structured_parse(payload: str) -> Optional[Tuple[str, str, str]]:
    """
    Try parsing 'plante / taille / lieu' (or comma-separated) from the raw
    payload after the (REMPLA) marker.

    Returns (plante, taille, lieu) if exactly 3 clean fields are found,
    otherwise None (caller should fall back to AI).
    """
    if not payload:
        return None

    # Prefer slash separator if present, otherwise comma
    if "/" in payload:
        parts = [p.strip() for p in payload.split("/") if p.strip()]
    elif "," in payload:
        parts = [p.strip() for p in payload.split(",") if p.strip()]
    else:
        return None

    if len(parts) != 3:
        return None

    plante, taille, lieu = parts
    # Sanity check: none of the parts should be abnormally long (likely a
    # stray sentence rather than a short field)
    if any(len(p) > 120 for p in (plante, taille, lieu)):
        return None

    return plante, taille, lieu


def extract_rempla_fields(
    message_text: str,
    text_enhancer=None,
) -> Dict[str, str]:
    """
    Extract REMPLA fields (plante, taille, lieu) from a message.

    Strategy:
    1. Try a structured parse of 'plante / taille / lieu' (or commas).
    2. If structured parse fails AND a text_enhancer is provided, call Gemini
       to consolidate into a single row (handles multi-plant messages and
       free-form text).
    3. Otherwise, return the raw payload in 'plante' and leave the others empty.

    Args:
        message_text: The raw Google Chat message text.
        text_enhancer: Optional TextEnhancer instance for AI fallback.

    Returns:
        Dict with keys 'plante', 'taille', 'lieu', 'raw' (always present,
        possibly empty strings).
    """
    payload = _text_after_marker(message_text, REMPLA_PATTERN)

    result = {
        "plante": "",
        "taille": "",
        "lieu": "",
        "raw": payload,
    }

    structured = _try_structured_parse(payload)
    if structured is not None:
        result["plante"], result["taille"], result["lieu"] = structured
        return result

    # Fallback to AI extraction if available
    if text_enhancer is not None and payload:
        ai_fields = _extract_rempla_with_ai(payload, text_enhancer)
        if ai_fields:
            result.update(ai_fields)
            return result

    # Last resort: put everything in "plante" so nothing is lost
    result["plante"] = payload
    return result


def _extract_rempla_with_ai(payload: str, text_enhancer) -> Optional[Dict[str, str]]:
    """
    Use Gemini to extract plante / taille / lieu from a free-form REMPLA payload.

    Consolidates multi-plant messages into a single "Végétaux à Remplacer"
    string (e.g. "3 Monstera + 1 Fougère").

    Args:
        payload: Text after the (REMPLA) marker.
        text_enhancer: TextEnhancer instance (for its .llm attribute).

    Returns:
        Dict with 'plante', 'taille', 'lieu' keys, or None on failure.
    """
    prompt = (
        "Extract REMPLA fields from a French gardening-team chat message. "
        "Return only a JSON object with exactly these keys: plante, taille, lieu. "
        "If a field is missing, set its value to an empty string. "
        "For multiple plants, consolidate them into the plante field "
        '(e.g. "3 Monstera + 1 Fougère"). '
        "Do not include any markdown, explanation, or surrounding text.\n\n"
        f"Message: {payload}\n\n"
        "JSON:"
    )

    try:
        response = text_enhancer.llm.invoke(prompt)
        content = getattr(response, "content", str(response))
        return _parse_json_object(content)
    except Exception as e:
        print(f"Gemini REMPLA extraction failed: {e}")
        return None


def _parse_json_object(raw: str) -> Optional[Dict[str, str]]:
    """Extract the first JSON object from an LLM response; tolerate code fences."""
    if not raw:
        return None

    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    return {
        "plante": str(parsed.get("plante") or "").strip(),
        "taille": str(parsed.get("taille") or "").strip(),
        "lieu": str(parsed.get("lieu") or "").strip(),
    }


def extract_brief_content(message_text: str) -> str:
    """
    Return the BRIEF content, which is the full original message text.

    Per spec, BRIEF is open-format and we preserve everything the author wrote.
    We don't strip the marker itself because it can be useful context for
    whoever reads the brief later.

    Args:
        message_text: The raw Google Chat message text.

    Returns:
        Cleaned message text (trimmed), or empty string.
    """
    if not message_text:
        return ""
    return message_text.strip()


def build_rempla_title(
    plante: str,
    lieu: str,
    raw_payload: str,
    max_len: int = 80,
) -> str:
    """
    Build a concise title for the REMPLA row's "Nom" field.

    Prefers 'Rempla {plante} - {lieu}' when both are known; falls back to a
    truncated raw payload otherwise.
    """
    plante = (plante or "").strip()
    lieu = (lieu or "").strip()

    if plante and lieu:
        title = f"Rempla {plante} - {lieu}"
    elif plante:
        title = f"Rempla {plante}"
    elif raw_payload:
        title = f"Rempla {raw_payload.strip()}"
    else:
        title = "Rempla"

    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    return title
