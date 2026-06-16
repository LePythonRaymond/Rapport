"""
Notion writers for REMPLA rows and Planning BRIEF patches.

Responsibilities:
- Build REMPLA DB properties from extracted fields and create the page.
  The writer is schema-aware: any property declared in REMPLA_PROPS that
  doesn't exist in the actual Notion data source is silently dropped with
  a one-time warning, so a renamed/removed column never fails the row.
  The optional "Exposition (EXT)" select is matched case-insensitively to
  an existing option (or a new option is created if none matches).
- Find the next few upcoming Planning DB rows for a site (Date >= today,
  sorted ascending) and APPEND to each one's BRIEF field, preserving any
  existing content with a clear dated separator. Identical retries are
  deduped per row.
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

# A BRIEF is propagated to the next N upcoming passages (Planning rows), not
# just the immediate next one, so the team sees it across the coming visits.
BRIEF_TARGET_PASSAGES = 3


REMPLA_PROPS = {
    "nom": "Nom",
    "site": "Site",
    "date_demande": "Date demande",
    "qui": "QUI ?",
    "vegetaux": "Végétaux à Remplacer",
    "taille": "Taille Plante",
    "lieu": "Lieu",
    "exposition": "Exposition (EXT)",
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

    def _resolve_select_option(self, prop_name: str, value: str) -> Optional[str]:
        """
        Map a free-typed select value to the schema's canonical option.

        Returns the existing option name on a case-insensitive match; if no
        option matches, returns the trimmed raw value so Notion creates a new
        option (info isn't lost). Returns None for an empty value so callers
        can skip the property entirely.
        """
        value = (value or "").strip()
        if not value:
            return None

        schema = self._rempla_schema()
        prop = schema.get(prop_name) if schema else None
        if prop and prop.get("type") == "select":
            options = (prop.get("select") or {}).get("options") or []
            for opt in options:
                if (opt.get("name") or "").strip().lower() == value.lower():
                    return opt.get("name")
        return value

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
            fields: Dict with 'plante', 'taille', 'lieu', 'exposition', 'raw'
                from the extractor.
        """
        plante = fields.get("plante", "") or ""
        taille = fields.get("taille", "") or ""
        lieu = fields.get("lieu", "") or ""
        exposition = fields.get("exposition", "") or ""
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

        # Optional outdoor exposure (select). Only set when present; map to an
        # existing option case-insensitively, else create a new one.
        expo_option = self._resolve_select_option(
            REMPLA_PROPS["exposition"], exposition
        )
        if expo_option:
            properties[REMPLA_PROPS["exposition"]] = {"select": {"name": expo_option}}

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
            expo_log = f", exposition='{expo_option}'" if expo_option else ""
            print(
                f"Created REMPLA row {page_id} "
                f"(plante='{plante}', lieu='{lieu}'{expo_log})"
            )
            return page_id
        except Exception as e:
            print(f"Failed to create REMPLA row: {e}")
            return None

    # -------- BRIEF / Planning --------

    def patch_next_planning_briefs(
        self,
        site_page_id: str,
        brief_text: str,
        max_passages: int = BRIEF_TARGET_PASSAGES,
    ) -> List[str]:
        """
        Write/append the BRIEF to the next ``max_passages`` upcoming Planning
        rows for a site (Date >= today, soonest first).

        Per target row:
        - Empty BRIEF field → the new text is written directly ('written').
        - Field already contains the new text (substring match, whitespace and
          case normalised) → no-op ('duplicate'). Handles re-sent messages
          and re-runs after a partial failure without double-appending.
        - Otherwise the text is appended after a dated separator so prior
          content (auto-written or hand-edited) is preserved ('appended').

        Returns a list with one status per processed row, each one of
        'written' / 'appended' / 'duplicate' / 'error'. Special cases:
        - ``['no_target']`` if the site has no upcoming Planning row.
        - ``['error']`` if the Planning query itself failed.
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
            print(f"Failed to query Planning DB for next interventions: {e}")
            return ["error"]

        if not results:
            print(f"No upcoming Planning row found for site {site_page_id[:8]}…")
            return ["no_target"]

        statuses: List[str] = []
        for target in results[:max_passages]:
            statuses.append(self._patch_one_planning_brief(target, brief_text))
        return statuses

    def _patch_one_planning_brief(self, target: Dict, brief_text: str) -> str:
        """Write/append a BRIEF to a single Planning row. See callers for the
        status vocabulary ('written' / 'appended' / 'duplicate' / 'error')."""
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
            merged = f"{existing_brief.rstrip()}{joiner}{brief_text.lstrip()}"
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
