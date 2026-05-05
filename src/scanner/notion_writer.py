"""
Notion writers for REMPLA rows and Planning BRIEF patches.

Responsibilities:
- Build REMPLA DB properties from extracted fields and create the page.
  The writer is schema-aware: any property declared in REMPLA_PROPS that
  doesn't exist in the actual Notion data source is silently dropped with
  a one-time warning, so a renamed/removed column never fails the row.
- Find the next upcoming Planning DB row for a site (Date >= today, sorted
  ascending) and APPEND to its BRIEF field, preserving any existing
  content with a clear visual separator (and the addition's date for
  traceability). Identical retries are deduped.
"""

from datetime import date
from typing import Any, Dict, List, Optional

import config
from src.notion.client import NotionClient

from .author_resolver import NotionUserResolver
from .marker_extractor import build_rempla_title

# Visual separator inserted between successive BRIEF chunks. The date prefix
# makes it clear when each addition was made and lets readers scan the
# accumulated history without having to cross-reference the chat.
BRIEF_JOIN_TEMPLATE = "\n\n— [{label}] :\n"


REMPLA_PROPS = {
    "nom": "Nom",
    "site": "Site",
    "date_demande": "Date demande",
    "qui": "QUI ?",
    "vegetaux": "Végétaux à Remplacer",
    "taille": "Taille Plante",
    "lieu": "Lieu",
    "rempla_effectuee": "Effectuée",
}

PLANNING_PROPS = {
    "site": "Site",
    "date": "Date",
    "brief": "BRIEF",
}


class ScannerNotionWriter:
    """Writes REMPLA rows and patches Planning BRIEF fields in Notion."""

    def __init__(
        self,
        notion_client: Optional[NotionClient] = None,
        user_resolver: Optional[NotionUserResolver] = None,
    ):
        self.client = notion_client or NotionClient()
        self.user_resolver = user_resolver or NotionUserResolver(self.client.api_key)
        self.rempla_db_id = config.get_notion_db_rempla()
        self.planning_db_id = config.get_notion_db_planning()
        # Cached schema (Notion property name → property definition) for the
        # REMPLA DB, fetched on first write via the 2025-09-03 data_source
        # endpoint. Used to drop properties that no longer exist (renamed
        # or removed in Notion) so a single missing column doesn't fail
        # the whole row.
        self._rempla_schema_cache: Optional[Dict[str, Any]] = None
        # Property names we've already warned about being absent from the
        # schema, so the cron log doesn't repeat the same warning per row.
        self._missing_props_warned: set = set()

    def _rempla_schema(self) -> Dict[str, Any]:
        """Lazy/cached fetch of the REMPLA DB's data_source property schema."""
        if self._rempla_schema_cache is not None:
            return self._rempla_schema_cache
        try:
            self._rempla_schema_cache = (
                self.client.get_data_source_schema(self.rempla_db_id) or {}
            )
        except Exception as e:
            print(
                f"Could not fetch REMPLA schema ({e}); writes will not be "
                "filtered against the schema this run."
            )
            self._rempla_schema_cache = {}
        return self._rempla_schema_cache

    def _filter_to_existing_props(self, properties: Dict) -> Dict:
        """
        Drop any property whose name isn't in the REMPLA schema.

        If the schema lookup failed (empty cache), we pass everything
        through unchanged and let the API decide — losing one row is
        better than silently dropping all of them due to a transient
        schema fetch error.
        """
        schema = self._rempla_schema()
        if not schema:
            return properties

        kept: Dict = {}
        for key, value in properties.items():
            if key in schema:
                kept[key] = value
                continue
            if key not in self._missing_props_warned:
                self._missing_props_warned.add(key)
                print(
                    f"⚠️ '{key}' is not a property of the REMPLA DB; values "
                    "for it will be dropped until you add it back in Notion."
                )
        return kept

    # -------- REMPLA --------

    def create_rempla_row(
        self,
        site_page_id: str,
        message_text: str,
        message_timestamp_iso: str,
        author_email: Optional[str],
        fields: Dict[str, str],
    ) -> Optional[str]:
        """
        Create a new REMPLA row. Returns the created page ID or None on failure.

        Args:
            site_page_id: Notion page ID of the Site row to relate to.
            message_text: Raw message text (used as a fallback title).
            message_timestamp_iso: ISO-8601 timestamp of the chat message.
            author_email: Email of the chat author (may be None).
            fields: Dict with 'plante', 'taille', 'lieu', 'raw' from extractor.
        """
        plante = fields.get("plante", "") or ""
        taille = fields.get("taille", "") or ""
        lieu = fields.get("lieu", "") or ""
        raw_payload = fields.get("raw", "") or message_text

        properties: Dict = {
            REMPLA_PROPS["nom"]: _title_property(
                build_rempla_title(plante, lieu, raw_payload)
            ),
            REMPLA_PROPS["site"]: {"relation": [{"id": site_page_id}]},
            REMPLA_PROPS["date_demande"]: {
                "date": {"start": _iso_to_date_string(message_timestamp_iso)}
            },
            REMPLA_PROPS["vegetaux"]: _rich_text_property(plante),
            REMPLA_PROPS["taille"]: _rich_text_property(taille),
            REMPLA_PROPS["lieu"]: _rich_text_property(lieu),
            REMPLA_PROPS["rempla_effectuee"]: {"checkbox": False},
        }

        qui_user_id = self.user_resolver.resolve(author_email) if author_email else None
        if qui_user_id:
            properties[REMPLA_PROPS["qui"]] = {"people": [{"id": qui_user_id}]}
        elif author_email:
            print(
                f"No Notion user matched email '{author_email}'. "
                "'QUI ?' left empty on this REMPLA row."
            )

        # Schema-aware: drop anything not actually in the Notion DB so a
        # renamed/removed column (e.g. "Rempla effectuée" being deleted)
        # never fails the row.
        properties = self._filter_to_existing_props(properties)

        try:
            # Notion's 2025-09-03 API requires pages created in a database to
            # use a data_source_id parent. The notion-client SDK's
            # pages.create() still posts a legacy database_id parent, which
            # returns 404 for databases that have been migrated. Use the
            # direct REST path instead.
            response = self.client.create_page_in_data_source(
                database_id=self.rempla_db_id,
                properties=properties,
            )
            page_id = response.get("id")
            print(f"Created REMPLA row {page_id} (plante='{plante}', lieu='{lieu}')")
            return page_id
        except Exception as e:
            print(f"Failed to create REMPLA row: {e}")
            return None

    # -------- BRIEF / Planning --------

    def patch_next_planning_brief(
        self,
        site_page_id: str,
        brief_text: str,
    ) -> str:
        """
        Find the next upcoming Planning row for a site and write/append BRIEF.

        Behavior:
        - If the BRIEF field is empty, the new text is written directly.
        - If the BRIEF field already contains the new text (substring match,
          whitespace and case normalised), no-op — useful when the same
          (BRIEF) message gets re-sent because the author wasn't sure the
          first one landed.
        - Otherwise the new text is appended after a dated visual separator
          so prior content (auto-written or hand-edited) is preserved and
          the addition history stays readable.

        Returns one of:
          - 'written'   : empty target → wrote new BRIEF
          - 'appended'  : non-empty target → appended after separator
          - 'duplicate' : new text already present, no-op
          - 'no_target' : no upcoming Planning row exists for this site
          - 'error'     : Notion API call failed
        """
        today_iso = date.today().isoformat()

        filter_conditions = {
            "and": [
                {
                    "property": PLANNING_PROPS["site"],
                    "relation": {"contains": site_page_id},
                },
                {
                    "property": PLANNING_PROPS["date"],
                    "date": {"on_or_after": today_iso},
                },
            ]
        }
        sorts = [{"property": PLANNING_PROPS["date"], "direction": "ascending"}]

        try:
            results: List[Dict] = self.client.query_database(
                database_id=self.planning_db_id,
                filter_conditions=filter_conditions,
                sorts=sorts,
            )
        except Exception as e:
            print(f"Failed to query Planning DB for next intervention: {e}")
            return "error"

        if not results:
            print(f"No upcoming Planning row found for site {site_page_id[:8]}…")
            return "no_target"

        target = results[0]
        target_id = target.get("id")

        existing_brief = _extract_rich_text(
            target.get("properties", {}).get(PLANNING_PROPS["brief"], {})
        )

        if _is_brief_duplicate(existing_brief, brief_text):
            print(
                f"BRIEF content already present on Planning row "
                f"{target_id[:8]}…; skipping to avoid duplicate."
            )
            return "duplicate"

        if existing_brief.strip():
            label = date.today().strftime("%d/%m")
            joiner = BRIEF_JOIN_TEMPLATE.format(label=label)
            merged = (
                f"{existing_brief.rstrip()}{joiner}{brief_text.lstrip()}"
            )
            outcome = "appended"
        else:
            merged = brief_text
            outcome = "written"

        try:
            self.client.update_page(
                page_id=target_id,
                properties={PLANNING_PROPS["brief"]: _rich_text_property(merged)},
            )
            verb = "Appended to" if outcome == "appended" else "Wrote"
            print(f"{verb} BRIEF on Planning row {target_id[:8]}…")
            return outcome
        except Exception as e:
            print(f"Failed to patch Planning BRIEF on {target_id[:8]}…: {e}")
            return "error"


# -------- Property helpers --------


def _title_property(text: str) -> Dict:
    return {"title": [{"type": "text", "text": {"content": text or ""}}]}


def _rich_text_property(text: str) -> Dict:
    """
    Build a rich_text property. Notion hard-caps each rich_text segment at
    2000 characters, so we chunk long content to avoid 400 errors.
    """
    if not text:
        return {"rich_text": []}

    MAX = 2000
    segments = [text[i : i + MAX] for i in range(0, len(text), MAX)]
    return {
        "rich_text": [
            {"type": "text", "text": {"content": seg}} for seg in segments
        ]
    }


def _iso_to_date_string(iso_timestamp: str) -> str:
    """Keep full ISO-8601 for Notion date.start; it accepts date or datetime."""
    if not iso_timestamp:
        return date.today().isoformat()
    return iso_timestamp


def _extract_rich_text(prop: Dict) -> str:
    """Concatenate the plain_text content of a rich_text property."""
    if not prop:
        return ""
    items = prop.get("rich_text") or []
    return "".join(item.get("plain_text", "") for item in items)


def _normalise_for_compare(text: str) -> str:
    """Collapse whitespace and lowercase for substring-equality checks."""
    return " ".join((text or "").lower().split())


def _is_brief_duplicate(existing: str, new: str) -> bool:
    """
    True iff ``new`` is already substring-included in ``existing``, comparing
    after whitespace collapse and case-fold. An empty ``new`` is treated as
    a duplicate (nothing to add).
    """
    new_n = _normalise_for_compare(new)
    if not new_n:
        return True
    existing_n = _normalise_for_compare(existing)
    return new_n in existing_n
