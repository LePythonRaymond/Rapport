"""
Notion writers for REMPLA rows and Planning BRIEF patches.

Responsibilities:
- Build REMPLA DB properties from extracted fields and create the page.
- Find the next upcoming Planning DB row for a site (Date >= today, sorted
  ascending) and patch its BRIEF field — but only if that field is empty,
  to avoid overwriting human edits.
"""

from datetime import date
from typing import Dict, List, Optional

import config
from src.notion.client import NotionClient

from .author_resolver import NotionUserResolver
from .marker_extractor import build_rempla_title


REMPLA_PROPS = {
    "nom": "Nom",
    "site": "Site",
    "date_demande": "Date demande",
    "qui": "QUI ?",
    "vegetaux": "Végétaux à Remplacer",
    "taille": "Taille Plante",
    "lieu": "Lieu",
    "rempla_effectuee": "Rempla effectuée",
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
        self._rempla_has_lieu: Optional[bool] = None

    def _rempla_supports_lieu(self) -> bool:
        """Check once whether the 'Lieu' property exists in the REMPLA DB."""
        if self._rempla_has_lieu is not None:
            return self._rempla_has_lieu
        try:
            schema = self.client.get_database_schema(self.rempla_db_id)
            self._rempla_has_lieu = REMPLA_PROPS["lieu"] in (schema or {})
        except Exception as e:
            print(f"Could not inspect REMPLA schema ({e}); assuming no Lieu field.")
            self._rempla_has_lieu = False
        if not self._rempla_has_lieu:
            print(
                f"'{REMPLA_PROPS['lieu']}' property not found in REMPLA DB. "
                "Add it as a Rich Text property in Notion to persist lieu values."
            )
        return self._rempla_has_lieu

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
            REMPLA_PROPS["rempla_effectuee"]: {"checkbox": False},
        }

        if self._rempla_supports_lieu():
            properties[REMPLA_PROPS["lieu"]] = _rich_text_property(lieu)

        qui_user_id = self.user_resolver.resolve(author_email) if author_email else None
        if qui_user_id:
            properties[REMPLA_PROPS["qui"]] = {"people": [{"id": qui_user_id}]}
        elif author_email:
            print(
                f"No Notion user matched email '{author_email}'. "
                "'QUI ?' left empty on this REMPLA row."
            )

        try:
            response = self.client.create_page(
                parent_db_id=self.rempla_db_id,
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
    ) -> Optional[str]:
        """
        Find the next upcoming Planning row for a site and write its BRIEF field.

        Returns the patched page ID, or None if no target row was found or if
        the BRIEF field was already populated.
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
            return None

        if not results:
            print(f"No upcoming Planning row found for site {site_page_id[:8]}…")
            return None

        target = results[0]
        target_id = target.get("id")

        existing_brief = _extract_rich_text(
            target.get("properties", {}).get(PLANNING_PROPS["brief"], {})
        )
        if existing_brief.strip():
            print(
                f"Planning row {target_id[:8]}… already has a BRIEF; skipping "
                "to avoid overwriting a human edit."
            )
            return None

        try:
            self.client.update_page(
                page_id=target_id,
                properties={PLANNING_PROPS["brief"]: _rich_text_property(brief_text)},
            )
            print(f"Patched BRIEF on Planning row {target_id[:8]}…")
            return target_id
        except Exception as e:
            print(f"Failed to patch Planning BRIEF on {target_id[:8]}…: {e}")
            return None


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
