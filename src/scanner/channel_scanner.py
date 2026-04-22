"""
Channel scanner — orchestrates the end-to-end REMPLA/BRIEF detection loop.

Responsibilities:
- Load all sites from the Sites DB (page_id, name, channel_url, space_id).
- For each site, fetch Google Chat messages newer than the last scan.
- Detect (REMPLA) / (BRIEF) markers.
- Skip messages already processed (dedup via message ID set in state).
- Write REMPLA rows and patch Planning BRIEF fields.
- Persist updated state (last_scan_per_channel + processed_message_ids).
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

import config
from src.google_chat.client import GoogleChatClient, format_date_for_api
from src.notion.client import NotionClient
from src.notion.database import PROPERTY_NAMES

from .author_resolver import NotionUserResolver
from .marker_extractor import (
    MarkerType,
    detect_marker,
    extract_brief_content,
    extract_rempla_fields,
)
from .notion_writer import ScannerNotionWriter


STATE_FILE_DEFAULT = "scanner_state.json"
# How far back to look on first run (or when a channel has no prior state)
COLD_START_LOOKBACK_HOURS_DEFAULT = 24
# Cap the size of processed_message_ids to avoid unbounded growth. We only
# need enough history to cover the API query window we'll ever ask for.
MAX_PROCESSED_IDS = 10000


class ChannelScanner:
    """Coordinates site loading, chat scanning, marker detection, and writes."""

    def __init__(
        self,
        state_file_path: Optional[str] = None,
        cold_start_lookback_hours: int = COLD_START_LOOKBACK_HOURS_DEFAULT,
    ):
        self.state_file_path = state_file_path or STATE_FILE_DEFAULT
        self.cold_start_lookback_hours = cold_start_lookback_hours

        self.notion_client = NotionClient()
        self.chat_client = GoogleChatClient()
        self.user_resolver = NotionUserResolver(self.notion_client.api_key)
        self.writer = ScannerNotionWriter(
            notion_client=self.notion_client,
            user_resolver=self.user_resolver,
        )

        self._text_enhancer = None  # Lazy — only if/when we need AI fallback

    def _get_text_enhancer(self):
        """Lazy-load the Gemini enhancer so a missing AI key doesn't crash startup."""
        if self._text_enhancer is not None:
            return self._text_enhancer
        try:
            from src.ai_processor.text_enhancer import TextEnhancer

            self._text_enhancer = TextEnhancer()
        except Exception as e:
            print(f"Gemini enhancer unavailable; regex-only REMPLA parsing. ({e})")
            self._text_enhancer = False
        return self._text_enhancer

    # -------- State persistence --------

    def _load_state(self) -> Dict:
        if not os.path.exists(self.state_file_path):
            return {"last_scan_per_channel": {}, "processed_message_ids": []}
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("last_scan_per_channel", {})
            data.setdefault("processed_message_ids", [])
            return data
        except Exception as e:
            print(f"Failed to read {self.state_file_path} ({e}); starting fresh.")
            return {"last_scan_per_channel": {}, "processed_message_ids": []}

    def _save_state(self, state: Dict) -> None:
        processed = state.get("processed_message_ids", [])
        if len(processed) > MAX_PROCESSED_IDS:
            state["processed_message_ids"] = processed[-MAX_PROCESSED_IDS:]

        tmp_path = self.state_file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.state_file_path)
        except Exception as e:
            print(f"Failed to persist scanner state: {e}")

    # -------- Sites loading --------

    def load_sites(self) -> List[Dict[str, str]]:
        """
        Return [{page_id, name, channel_url, space_id, int_ext}] for every
        site row that has a Canal Chat URL.
        """
        sites: List[Dict[str, str]] = []

        try:
            results = self.notion_client.query_database(config.get_notion_db_clients())
        except Exception as e:
            print(f"Could not load Sites DB: {e}")
            return sites

        name_prop = PROPERTY_NAMES["client_nom"]
        canal_prop = PROPERTY_NAMES["client_canal"]

        for page in results:
            props = page.get("properties", {}) or {}
            page_id = page.get("id")

            name = _extract_title(props.get(name_prop, {}))
            canal_url = _extract_rich_text_or_url(props.get(canal_prop, {}))
            int_ext = _extract_select(props.get("INT EXT ?", {}))

            if not page_id or not canal_url:
                continue

            space_id = config.extract_space_id_from_url(canal_url)
            if not space_id:
                continue

            sites.append(
                {
                    "page_id": page_id,
                    "name": name or "(sans nom)",
                    "channel_url": canal_url,
                    "space_id": space_id,
                    "int_ext": int_ext or "",
                }
            )

        print(f"Loaded {len(sites)} sites with chat channels from Sites DB")
        return sites

    # -------- Core scan loop --------

    def run(self) -> Dict[str, int]:
        """Execute one full scan pass. Returns counters for logging."""
        counters = {
            "sites_scanned": 0,
            "messages_seen": 0,
            "rempla_created": 0,
            "brief_patched": 0,
            "skipped_already_processed": 0,
            "errors": 0,
        }

        state = self._load_state()
        processed_ids: Set[str] = set(state.get("processed_message_ids", []))
        now_iso = _now_utc_iso()

        sites = self.load_sites()

        for site in sites:
            counters["sites_scanned"] += 1
            space_id = site["space_id"]
            site_label = f"{site['name']} ({space_id})"

            start_iso = state.get("last_scan_per_channel", {}).get(space_id)
            if not start_iso:
                start_iso = _hours_ago_iso(self.cold_start_lookback_hours)

            print(f"\n=== Scanning {site_label} from {start_iso} ===")

            try:
                messages = self.chat_client.get_messages_for_space(
                    space_id=space_id,
                    start_date=start_iso,
                    end_date=now_iso,
                )
            except Exception as e:
                print(f"Chat fetch failed for {site_label}: {e}")
                counters["errors"] += 1
                continue

            counters["messages_seen"] += len(messages)

            latest_seen_iso = start_iso
            for message in messages:
                msg_id = message.get("id")
                msg_time = message.get("createTime") or now_iso

                if msg_time > latest_seen_iso:
                    latest_seen_iso = msg_time

                if not msg_id:
                    continue

                if msg_id in processed_ids:
                    counters["skipped_already_processed"] += 1
                    continue

                handled = self._handle_message(site, message)
                if handled is None:
                    continue  # Not a marker message

                if handled == "rempla":
                    counters["rempla_created"] += 1
                    processed_ids.add(msg_id)
                elif handled == "brief":
                    counters["brief_patched"] += 1
                    processed_ids.add(msg_id)
                elif handled == "error":
                    counters["errors"] += 1
                    # Do NOT mark as processed — we'll retry on next run

            state.setdefault("last_scan_per_channel", {})[space_id] = latest_seen_iso

        state["processed_message_ids"] = sorted(processed_ids)
        self._save_state(state)

        return counters

    def _handle_message(
        self, site: Dict[str, str], message: Dict
    ) -> Optional[str]:
        """
        Dispatch a single message to the correct writer.

        Returns one of: 'rempla', 'brief', 'error', or None (no marker).
        """
        text = message.get("text", "") or ""
        marker = detect_marker(text)
        if marker == MarkerType.NONE:
            return None

        msg_id = message.get("id", "?")
        msg_time = message.get("createTime", "")
        author = message.get("author") or {}
        author_email = author.get("email") if "@" in (author.get("email") or "") else None

        if marker == MarkerType.REMPLA:
            enhancer = self._get_text_enhancer()
            fields = extract_rempla_fields(
                text,
                text_enhancer=enhancer if enhancer else None,
            )
            created = self.writer.create_rempla_row(
                site_page_id=site["page_id"],
                message_text=text,
                message_timestamp_iso=msg_time,
                author_email=author_email,
                fields=fields,
            )
            if created:
                print(f"  → REMPLA row created for message {msg_id[-12:]}")
                return "rempla"
            print(f"  → REMPLA write failed for message {msg_id[-12:]}")
            return "error"

        if marker == MarkerType.BRIEF:
            brief_text = extract_brief_content(text)
            if not brief_text:
                return None
            patched = self.writer.patch_next_planning_brief(
                site_page_id=site["page_id"],
                brief_text=brief_text,
            )
            if patched:
                print(f"  → BRIEF patched for message {msg_id[-12:]}")
                return "brief"
            # No target found OR BRIEF already filled — treat as handled so
            # we don't retry forever on the same message.
            return "brief"

        return None


# -------- Helpers --------


def _now_utc_iso() -> str:
    return format_date_for_api(datetime.now(tz=timezone.utc))


def _hours_ago_iso(hours: int) -> str:
    return format_date_for_api(datetime.now(tz=timezone.utc) - timedelta(hours=hours))


def _extract_title(prop: Dict) -> str:
    if not prop:
        return ""
    parts: List[str] = []
    for item in prop.get("title") or []:
        if item.get("type") == "text":
            parts.append(item.get("text", {}).get("content", ""))
        elif item.get("type") == "mention":
            parts.append(item.get("plain_text", ""))
        else:
            parts.append(item.get("plain_text", ""))
    return "".join(parts).strip()


def _extract_rich_text_or_url(prop: Dict) -> str:
    """
    Sites DB 'Canal Chat' is rich_text in some workspaces and URL in others —
    handle both so we don't silently drop rows.
    """
    if not prop:
        return ""

    url_val = prop.get("url")
    if url_val:
        return str(url_val).strip()

    items = prop.get("rich_text") or []
    if items:
        return "".join(
            item.get("text", {}).get("content", "") or item.get("plain_text", "")
            for item in items
        ).strip()

    return ""


def _extract_select(prop: Dict) -> str:
    if not prop:
        return ""
    sel = prop.get("select")
    if not sel:
        return ""
    return str(sel.get("name") or "").strip()
