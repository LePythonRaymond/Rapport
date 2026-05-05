"""
REMPLA & BRIEF Channel Scanner.

Scans Google Chat channels from the Sites DB on a schedule, detects (REMPLA)
and (BRIEF) markers, and writes structured data back to Notion:
- REMPLA DB: one row per detected (REMPLA) message with plante / taille / lieu
- Planning DB: patches the next upcoming intervention's BRIEF field with the content
"""

from .marker_extractor import (
    MarkerSpan,
    MarkerType,
    detect_marker,
    detect_markers,
    extract_rempla_fields,
    extract_brief_content,
)
from .author_resolver import NotionUserResolver
from .notion_writer import ScannerNotionWriter
from .channel_scanner import ChannelScanner

__all__ = [
    "MarkerSpan",
    "MarkerType",
    "detect_marker",
    "detect_markers",
    "extract_rempla_fields",
    "extract_brief_content",
    "NotionUserResolver",
    "ScannerNotionWriter",
    "ChannelScanner",
]
