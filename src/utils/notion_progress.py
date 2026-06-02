"""Notion-side progress detection for bulk report generation.

Uses the Rapports DB as the source of truth for which clients already have a
report for the current month/year. Survives Streamlit Cloud container restarts
(unlike the local `batch_progress.json`).

Matching strategy
-----------------
1. Scope: filter Rapports rows whose title contains "<MoisFr> <YYYY>" — the
   same label `ReportPageBuilder._generate_report_title` writes into the title.
2. Identity: within that scope, match by the **Client relation** (page ID),
   not by title text. The title is lossy because `_generate_report_title`
   strips the `(INT)` / `(EXT)` tags and the numeric suffix — INT and EXT
   variants of the same site collapse to the same title, but they ARE
   separate rows in the Clients DB (different page IDs) and the team
   generates a separate report for each. Relation-based matching keeps them
   distinct.
"""
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional, Set


FRENCH_MONTHS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
}


def title_month_year_label(report_date: datetime) -> str:
    """Return the "<MoisFr> <YYYY>" label that ReportPageBuilder._generate_report_title
    would put in a report title for the given report_date.

    Mirrors the day>15 / day<=15 rule in page_builder.py so this stays in sync.
    """
    if report_date.day > 15:
        month_date = report_date
    else:
        month_date = report_date.replace(day=1) - timedelta(days=1)
    month_fr = FRENCH_MONTHS.get(month_date.month, month_date.strftime("%B"))
    return f"{month_fr} {month_date.year}"


def _extract_title_text(title_array) -> str:
    """Mirror the title-extraction logic in NotionDatabaseManager.get_all_clients_mapping
    so we resolve names the same way (text + mention types)."""
    out = ""
    for item in title_array or []:
        if item.get("type") == "text":
            out += item.get("text", {}).get("content", "")
        elif item.get("type") == "mention":
            out += item.get("plain_text", "")
        else:
            out += item.get("plain_text", "")
    return out.strip()


def get_completed_clients_for_run(
    db_manager,
    available_clients: Iterable[str],
    report_date: Optional[datetime] = None,
) -> Set[str]:
    """Return set of client names from `available_clients` that already have a
    Rapport for the current month/year (label derived from `report_date`).

    Matches each existing Rapport by its `Client` relation (page ID), so
    INT/EXT variants of the same site stay distinct.

    Args:
        db_manager: NotionDatabaseManager instance.
        available_clients: Iterable of client names to check.
        report_date: Reference date (defaults to now), mirrors what
            `create_report_page` uses when its own arg is None.

    Returns:
        Set of client names already done. On any query failure returns
        an empty set so the bulk run can still proceed (better to redo a
        few than to refuse).
    """
    report_date = report_date or datetime.now()
    label = title_month_year_label(report_date)

    # Step 1 — Build name → page_id map from the Clients DB. We need the
    # reverse direction (page_id → name) to interpret the `Client` relation
    # on each Rapport row.
    try:
        clients_pages = db_manager.get_all_clients()
    except Exception as e:
        print(f"⚠️ Could not load Clients DB for completion check: {e}")
        return set()

    # Import here to avoid a circular import at module-load time.
    from src.notion.database import PROPERTY_NAMES
    name_prop = PROPERTY_NAMES["client_nom"]  # "Nom"

    name_by_id: Dict[str, str] = {}
    for page in clients_pages:
        pid = page.get("id", "")
        title_arr = (page.get("properties", {}) or {}).get(name_prop, {}).get("title", []) or []
        nm = _extract_title_text(title_arr)
        if pid and nm:
            name_by_id[pid] = nm

    # Step 2 — Query Rapports filtered to titles containing "<MoisFr> <YYYY>".
    # This scopes us to the current period without leaking April or June rows.
    filter_conditions = {
        "property": "Nom",
        "title": {"contains": label},
    }
    try:
        existing_pages = db_manager.client.query_database(
            db_manager.rapports_db_id,
            filter_conditions=filter_conditions,
        )
    except Exception as e:
        print(f"⚠️ Could not query Rapports DB for completion check: {e}")
        return set()

    # Step 3 — Collect the Client relation page IDs from each Rapport.
    done_client_ids: Set[str] = set()
    for page in existing_pages:
        relation = (page.get("properties", {}) or {}).get("Client", {}).get("relation", []) or []
        for ref in relation:
            rid = ref.get("id", "")
            if rid:
                done_client_ids.add(rid)

    # Step 4 — Map page IDs back to names, intersected with `available_clients`.
    available_set = set(available_clients)
    completed: Set[str] = set()
    for cid in done_client_ids:
        nm = name_by_id.get(cid)
        if nm and nm in available_set:
            completed.add(nm)
    return completed
