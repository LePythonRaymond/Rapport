"""
Marker detection and field extraction for (REMPLA) and (BRIEF) messages.

Detection is fast and regex-based. A single message may carry BOTH a
``(REMPLA)`` and a ``(BRIEF)`` marker — they are processed independently and
each "owns" the text from its own marker tag up to (but not including) the
next marker tag (or end of message). Field extraction for REMPLA tries a
structured parse first (plante / taille / lieu separated by `/` or `,`),
and falls back to Gemini for free-form or multi-plant messages.
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

# (REMPLA) and (BRIEF) — strict markers: parentheses are MANDATORY so casual
# mentions like "remplacement à prévoir" or "briefing demain" never trigger.
# The marker is case-insensitive and tolerates whitespace inside the parens
# (e.g. "( REMPLA )"), but the parentheses themselves are required.
REMPLA_PATTERN = re.compile(r"\(\s*REMPLA\s*\)", re.IGNORECASE)
BRIEF_PATTERN = re.compile(r"\(\s*BRIEF\s*\)", re.IGNORECASE)


class MarkerType(str, Enum):
    """Marker type detected in a message."""

    REMPLA = "rempla"
    BRIEF = "brief"
    NONE = "none"


@dataclass(frozen=True)
class MarkerSpan:
    """One marker occurrence in a message + the payload that belongs to it.

    ``payload`` is the text from immediately after the marker tag up to (but
    not including) the start of the next marker tag — or end of message if
    this is the last marker. The payload is already stripped of surrounding
    punctuation/whitespace so callers can pass it straight to the extractors.
    """

    marker: MarkerType
    payload: str


def detect_marker(text: str) -> MarkerType:
    """
    Detect whether a message contains a REMPLA or BRIEF marker.

    Backwards-compatible single-marker check: returns the FIRST marker found
    in chronological order. Prefer ``detect_markers`` (plural) when you need
    to handle messages that carry both.

    Returns:
        MarkerType.REMPLA, MarkerType.BRIEF, or MarkerType.NONE.
    """
    spans = detect_markers(text)
    if not spans:
        return MarkerType.NONE
    return spans[0].marker


def detect_markers(text: str) -> List[MarkerSpan]:
    """
    Find every (REMPLA) / (BRIEF) marker in the message in chronological
    order, with each span's ``payload`` bounded by the start of the next
    marker (of any type) or end of message.

    Only the FIRST occurrence of each marker type is returned: a single
    chat message that contains two ``(REMPLA)`` tags is treated as one
    REMPLA whose payload covers everything up to the next marker. Multi-
    plant cases are intentionally consolidated by the AI fallback inside
    ``extract_rempla_fields`` rather than by emitting two REMPLA spans.

    Returns an empty list if no markers are present.
    """
    if not text:
        return []

    # All occurrences (incl. duplicates of the same type) drive boundary
    # calculation so a duplicate (REMPLA) still cuts the previous payload.
    candidates: List[Tuple[int, int, MarkerType]] = []
    for m in REMPLA_PATTERN.finditer(text):
        candidates.append((m.start(), m.end(), MarkerType.REMPLA))
    for m in BRIEF_PATTERN.finditer(text):
        candidates.append((m.start(), m.end(), MarkerType.BRIEF))

    if not candidates:
        return []

    candidates.sort(key=lambda c: c[0])
    all_starts = [c[0] for c in candidates]

    spans: List[MarkerSpan] = []
    seen_types: set = set()
    for start, end, mtype in candidates:
        if mtype in seen_types:
            continue
        seen_types.add(mtype)

        # Boundary = first start strictly after `start` across ALL candidates
        next_starts = [s for s in all_starts if s > start]
        boundary = next_starts[0] if next_starts else len(text)
        payload = text[end:boundary].strip(" :-\n\t").strip()
        spans.append(MarkerSpan(marker=mtype, payload=payload))

    return spans


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
    payload: str,
    text_enhancer=None,
) -> Dict[str, str]:
    """
    Extract REMPLA fields (plante, taille, lieu) from a payload.

    The ``payload`` is the text segment that belongs to the (REMPLA) marker
    — typically obtained from a ``MarkerSpan`` returned by
    ``detect_markers``. Pass the bounded segment, NOT the whole message,
    so a trailing ``(BRIEF) ...`` block isn't bleed into the REMPLA fields.

    Strategy:
    1. Try a structured parse of 'plante / taille / lieu' (or commas).
    2. If structured parse fails AND a text_enhancer is provided, call Gemini
       to consolidate into a single row (handles multi-plant messages and
       free-form text).
    3. Otherwise, return the raw payload in 'plante' and leave the others empty.

    Returns:
        Dict with keys 'plante', 'taille', 'lieu', 'raw' (always present,
        possibly empty strings).
    """
    payload = (payload or "").strip()

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


def extract_brief_content(payload: str) -> str:
    """
    Return the BRIEF content (the payload that belongs to the (BRIEF)
    marker, as bounded by ``detect_markers``).

    BRIEF is open-format — we just trim whitespace and pass through. The
    caller is responsible for slicing out the BRIEF segment so that, if
    the same message also has a (REMPLA) tag, the REMPLA part doesn't
    end up duplicated in the planning brief.
    """
    if not payload:
        return ""
    return payload.strip()


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
