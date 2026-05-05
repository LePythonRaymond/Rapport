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
from typing import Dict, List, Optional, Set, Tuple

import config
from src.google_chat.client import GoogleChatClient, format_date_for_api
from src.notion.client import NotionClient

from .author_resolver import NotionUserResolver
from .marker_extractor import (
    MarkerSpan,
    MarkerType,
    detect_markers,
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

# Sites DB property names. The Clients DB title property is "Nom"; we keep
# these constants local to the scanner so they stay decoupled from
# src.notion.database.PROPERTY_NAMES (which target Interventions/Rapports).
SITES_TITLE_PROP = "Nom"
SITES_CANAL_PROP = "Canal Chat"
SITES_INT_EXT_PROP = "INT EXT ?"


class ChannelScanner:
    """Coordinates site loading, chat scanning, marker detection, and writes."""

    def __init__(
        self,
        state_file_path: Optional[str] = None,
        cold_start_lookback_hours: int = COLD_START_LOOKBACK_HOURS_DEFAULT,
        site_filter: Optional[str] = None,
    ):
        self.state_file_path = state_file_path or STATE_FILE_DEFAULT
        self.cold_start_lookback_hours = cold_start_lookback_hours
        # Case-insensitive substring match against site name OR space_id.
        # Used by the --site-filter CLI flag to scope a run to one channel
        # (e.g. "TEST(TAD)") for fast iteration without touching state files.
        self.site_filter = (site_filter or "").strip().lower() or None

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
        """
        Load scanner state, migrating older schemas in place.

        Schema today:
            {
                "last_scan_per_channel": {space_id: iso_ts, ...},
                "processed_markers": {msg_id: ["rempla", "brief"], ...},
            }

        Pre-multi-marker schema had ``processed_message_ids: List[str]``
        (one entry per fully-processed message). We migrate by treating
        each legacy id as having BOTH markers handled — the conservative
        choice that prevents accidental duplicate writes after upgrade.
        """
        empty: Dict = {"last_scan_per_channel": {}, "processed_markers": {}}
        if not os.path.exists(self.state_file_path):
            return empty
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Failed to read {self.state_file_path} ({e}); starting fresh.")
            return empty

        data.setdefault("last_scan_per_channel", {})

        if "processed_markers" not in data:
            legacy_ids = data.get("processed_message_ids") or []
            data["processed_markers"] = {
                mid: [MarkerType.REMPLA.value, MarkerType.BRIEF.value]
                for mid in legacy_ids
            }
        # Drop the legacy key so we don't keep re-migrating from a stale list.
        data.pop("processed_message_ids", None)
        return data

    def _save_state(self, state: Dict) -> None:
        processed = state.get("processed_markers") or {}
        if len(processed) > MAX_PROCESSED_IDS:
            # Soft cap — keep the alphabetically-last N. Message IDs are
            # opaque, so this isn't truly LRU, but it bounds growth and
            # the cap is generous enough that real recent traffic survives.
            keep_keys = sorted(processed.keys())[-MAX_PROCESSED_IDS:]
            state["processed_markers"] = {k: processed[k] for k in keep_keys}

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
        site row that has a valid Canal Chat URL.

        Guarantees:
        - Rows without a Canal Chat URL, with a malformed URL (e.g. "N/A"),
          or that don't resolve to a proper "spaces/<id>" are dropped.
        - If multiple Notion rows point at the same Google Chat space, only
          the first one is kept so the same channel isn't scanned twice.
        """
        sites: List[Dict[str, str]] = []
        seen_space_ids: set = set()
        skipped_invalid = 0
        skipped_duplicate = 0

        try:
            results = self.notion_client.query_database(config.get_notion_db_clients())
        except Exception as e:
            print(f"Could not load Sites DB: {e}")
            return sites

        for page in results:
            props = page.get("properties", {}) or {}
            page_id = page.get("id")

            name = _extract_title(props.get(SITES_TITLE_PROP, {}))
            canal_url = _extract_rich_text_or_url(props.get(SITES_CANAL_PROP, {}))
            int_ext = _extract_select(props.get(SITES_INT_EXT_PROP, {}))

            if not page_id or not canal_url:
                continue

            # Fast-reject obvious placeholders typed by hand into the field.
            if canal_url.strip().upper() in _CANAL_PLACEHOLDERS:
                skipped_invalid += 1
                continue

            # Let config.extract_space_id_from_url handle the URL shapes
            # (Gmail chat link, chat.google.com/room link, raw 'spaces/...',
            # or a bare token) and then validate only the resulting space id.
            space_id = config.extract_space_id_from_url(canal_url)
            if not _is_well_formed_space_id(space_id):
                skipped_invalid += 1
                continue

            if space_id in seen_space_ids:
                skipped_duplicate += 1
                continue
            seen_space_ids.add(space_id)

            sites.append(
                {
                    "page_id": page_id,
                    "name": name or "(sans nom)",
                    "channel_url": canal_url,
                    "space_id": space_id,
                    "int_ext": int_ext or "",
                }
            )

        print(
            f"Loaded {len(sites)} sites with chat channels from Sites DB "
            f"(skipped {skipped_invalid} invalid, {skipped_duplicate} duplicates)"
        )

        if self.site_filter:
            needle = self.site_filter
            before = len(sites)
            sites = [
                s
                for s in sites
                if needle in s["name"].lower() or needle in s["space_id"].lower()
            ]
            print(
                f"--site-filter '{self.site_filter}' kept {len(sites)}/{before} site(s)"
            )
            for s in sites:
                print(f"  • {s['name']} ({s['space_id']})")

        return sites

    # -------- Core scan loop --------

    def run(self) -> Dict:
        """Execute one full scan pass. Returns counters + 403 list for logging."""
        counters = {
            "sites_scanned": 0,
            "messages_seen": 0,
            "rempla_created": 0,
            # Granular BRIEF outcomes — accurate per-write accounting so the
            # summary reflects what actually changed in Notion (vs. the old
            # `brief_patched` which lumped writes, skips and no-ops together).
            "brief_written": 0,        # empty target → first write
            "brief_appended": 0,       # non-empty target → appended after separator
            "brief_duplicate": 0,      # exact text already present, no-op
            "brief_no_target": 0,      # no upcoming Planning row exists
            "skipped_already_processed": 0,
            "permission_denied": 0,
            "errors": 0,
        }
        # Channels the OAuth user can't read. These are NOT data-loss errors —
        # the user simply isn't a member of the space — so we track them
        # separately from `errors` and surface a one-line summary at the end
        # of the run so it's easy to triage.
        forbidden: List[Dict[str, str]] = []

        state = self._load_state()
        processed_markers: Dict[str, List[str]] = dict(
            state.get("processed_markers") or {}
        )
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
                    raise_on_error=True,
                )
            except Exception as e:
                if _is_permission_denied(e):
                    counters["permission_denied"] += 1
                    forbidden.append({"name": site["name"], "space_id": space_id})
                    print(f"  ↳ 403 (no access): {site_label}")
                else:
                    print(f"Chat fetch failed for {site_label}: {e}")
                    counters["errors"] += 1
                continue

            counters["messages_seen"] += len(messages)

            # Only shout about channels that actually have new activity so
            # the log is easy to skim across 100+ quiet sites.
            if messages:
                print(f"  {len(messages)} new message(s) in window")

            # Process in chronological order so the cursor-advance logic below
            # is deterministic even if the API returns newest-first.
            messages_sorted = sorted(
                messages, key=lambda m: m.get("createTime") or ""
            )

            latest_seen_iso = start_iso
            earliest_failure_iso: Optional[str] = None

            for message in messages_sorted:
                msg_id = message.get("id")
                msg_time = message.get("createTime") or now_iso

                if not msg_id:
                    # No stable id → can't dedup, so don't advance the cursor
                    # past it either; safest to skip without side effects.
                    continue

                already_handled = set(processed_markers.get(msg_id, []))

                outcomes = self._handle_message(site, message, already_handled)

                if outcomes is None:
                    # No marker at all → safe to advance the cursor.
                    if msg_time > latest_seen_iso:
                        latest_seen_iso = msg_time
                    continue

                if not outcomes:
                    # Markers present but every one was already handled in a
                    # prior run. Advance the cursor — there's nothing left.
                    counters["skipped_already_processed"] += 1
                    if msg_time > latest_seen_iso:
                        latest_seen_iso = msg_time
                    continue

                any_failure = False
                for marker_value, status in outcomes:
                    if status == "rempla":
                        counters["rempla_created"] += 1
                        already_handled.add(marker_value)
                    elif status == "brief_written":
                        counters["brief_written"] += 1
                        already_handled.add(marker_value)
                    elif status == "brief_appended":
                        counters["brief_appended"] += 1
                        already_handled.add(marker_value)
                    elif status == "brief_duplicate":
                        counters["brief_duplicate"] += 1
                        already_handled.add(marker_value)
                    elif status == "brief_no_target":
                        counters["brief_no_target"] += 1
                        already_handled.add(marker_value)
                    elif status == "brief":
                        # Empty BRIEF payload — handled (avoid retry loop)
                        # but no counter to increment.
                        already_handled.add(marker_value)
                    elif status == "error":
                        counters["errors"] += 1
                        any_failure = True

                if already_handled:
                    processed_markers[msg_id] = sorted(already_handled)

                if any_failure:
                    # Clamp the cursor just before this message so the failed
                    # marker(s) get a retry next run. Successful markers on
                    # this same message are recorded in processed_markers and
                    # will be skipped on retry, so we won't double-write.
                    if earliest_failure_iso is None or msg_time < earliest_failure_iso:
                        earliest_failure_iso = msg_time
                elif msg_time > latest_seen_iso:
                    latest_seen_iso = msg_time

            # If any marker write failed, don't let the cursor advance past
            # the failed message — otherwise it would silently drop off the
            # next query window and never be retried.
            if earliest_failure_iso is not None:
                clamped = _iso_minus_one_second(earliest_failure_iso)
                if clamped < latest_seen_iso:
                    latest_seen_iso = clamped

            state.setdefault("last_scan_per_channel", {})[space_id] = latest_seen_iso

        state["processed_markers"] = processed_markers
        self._save_state(state)

        return {"counters": counters, "forbidden": forbidden}

    def _handle_message(
        self,
        site: Dict[str, str],
        message: Dict,
        already_handled: Set[str],
    ) -> Optional[List[Tuple[str, str]]]:
        """
        Dispatch every (REMPLA) / (BRIEF) span in a message, skipping any
        marker types that were already processed for this message in a
        prior run.

        Returns:
            None  → the message has no markers at all.
            []    → markers exist but all were already processed.
            [(marker_value, status), ...] otherwise, where status is one of
            'rempla', 'brief', or 'error'. Order matches the order spans
            appear in the message.
        """
        text = message.get("text", "") or ""
        spans = detect_markers(text)
        if not spans:
            return None

        new_spans = [s for s in spans if s.marker.value not in already_handled]
        if not new_spans:
            return []

        msg_id = message.get("id", "?")
        msg_time = message.get("createTime", "")
        author = message.get("author") or {}
        author_email = author.get("email") if "@" in (author.get("email") or "") else None

        outcomes: List[Tuple[str, str]] = []

        for span in new_spans:
            if span.marker == MarkerType.REMPLA:
                outcomes.append(
                    (
                        span.marker.value,
                        self._process_rempla_span(
                            site, msg_id, msg_time, author_email, span
                        ),
                    )
                )
            elif span.marker == MarkerType.BRIEF:
                outcomes.append(
                    (
                        span.marker.value,
                        self._process_brief_span(site, msg_id, span),
                    )
                )

        return outcomes

    def _process_rempla_span(
        self,
        site: Dict[str, str],
        msg_id: str,
        msg_time: str,
        author_email: Optional[str],
        span: MarkerSpan,
    ) -> str:
        enhancer = self._get_text_enhancer()
        fields = extract_rempla_fields(
            span.payload,
            text_enhancer=enhancer if enhancer else None,
        )
        created = self.writer.create_rempla_row(
            site_page_id=site["page_id"],
            message_text=span.payload,
            message_timestamp_iso=msg_time,
            author_email=author_email,
            fields=fields,
        )
        if created:
            print(f"  → REMPLA row created for message {msg_id[-12:]}")
            return "rempla"
        print(f"  → REMPLA write failed for message {msg_id[-12:]}")
        return "error"

    def _process_brief_span(
        self,
        site: Dict[str, str],
        msg_id: str,
        span: MarkerSpan,
    ) -> str:
        """
        Translate the writer's per-call status into a scanner-loop outcome.

        Mapping:
          writer 'written'   → 'brief_written'   (counts + dedup)
          writer 'appended'  → 'brief_appended'  (counts + dedup)
          writer 'duplicate' → 'brief_duplicate' (counts + dedup, no Notion change)
          writer 'no_target' → 'brief_no_target' (counts + dedup, avoid retry loop)
          writer 'error'     → 'error'           (no dedup → retried next run)
          empty payload      → 'brief'           (handled, no counter)
        """
        brief_text = extract_brief_content(span.payload)
        if not brief_text:
            return "brief"

        status = self.writer.patch_next_planning_brief(
            site_page_id=site["page_id"],
            brief_text=brief_text,
        )

        short_id = msg_id[-12:]
        if status == "written":
            print(f"  → BRIEF written for message {short_id}")
            return "brief_written"
        if status == "appended":
            print(f"  → BRIEF appended for message {short_id}")
            return "brief_appended"
        if status == "duplicate":
            print(f"  → BRIEF already present, skipped for message {short_id}")
            return "brief_duplicate"
        if status == "no_target":
            print(f"  → no upcoming Planning row for message {short_id}")
            return "brief_no_target"
        # status == "error"
        print(f"  → BRIEF write failed for message {short_id}")
        return "error"


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


def _iso_minus_one_second(iso_str: str) -> str:
    """
    Subtract one second from an ISO-8601 timestamp and return it in the API
    format. Accepts both 'Z' and '+HH:MM' suffixes. Falls back to the
    original string if parsing fails, so we never drop a valid cursor.
    """
    try:
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return format_date_for_api(dt - timedelta(seconds=1))
    except Exception:
        return iso_str


_CANAL_PLACEHOLDERS = {"", "N/A", "NA", "TBD", "-", "/", "NONE", "NULL", "X", "?"}


def _is_permission_denied(exc: BaseException) -> bool:
    """
    Detect a Google Chat 403 from either an `HttpError` (preferred) or by
    inspecting the stringified exception (defensive fallback so we don't
    take a hard dep on googleapiclient here).
    """
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status == 403:
        return True
    return "HttpError 403" in str(exc) or "Permission denied" in str(exc)


def _is_well_formed_space_id(space_id: str) -> bool:
    """
    A valid Google Chat space id is exactly 'spaces/<token>' where <token>
    has no slashes and isn't a placeholder like 'N/A'. This matches the API
    pattern '^spaces/[^/]+$'.
    """
    if not space_id or not space_id.startswith("spaces/"):
        return False
    token = space_id[len("spaces/"):]
    if not token or "/" in token:
        return False
    if token.strip().upper() in {"N", "NA", "N/A", "TBD", "-"}:
        return False
    return True
