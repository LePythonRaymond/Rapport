"""Notion-side progress detection for bulk report generation.

Uses the Rapports DB as the source of truth for which clients already have a
report for the current month/year. Survives Streamlit Cloud container restarts
(unlike the local `batch_progress.json`).
"""
from datetime import datetime, timedelta
from typing import Iterable, Optional, Set


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


def get_completed_clients_for_run(
    db_manager,
    page_builder,
    available_clients: Iterable[str],
    report_date: Optional[datetime] = None,
) -> Set[str]:
    """Query the Rapports DB and return the set of client names that already
    have a report for the same month/year a bulk run would produce now.

    Args:
        db_manager: NotionDatabaseManager instance.
        page_builder: ReportPageBuilder instance (used to compute the expected
            title per client so the check matches the writer's naming scheme).
        available_clients: Iterable of client names to test.
        report_date: Reference date (defaults to now). Mirrors what
            `create_report_page` passes when its own `report_date` arg is None.

    Returns:
        Set of client names already done. On query failure returns an empty
        set so the bulk run can proceed (better to redo a few than to refuse).
    """
    report_date = report_date or datetime.now()
    label = title_month_year_label(report_date)

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
        print(f"⚠️ Could not query existing Rapports for completion check: {e}")
        return set()

    existing_titles: Set[str] = set()
    for page in existing_pages:
        title_arr = (page.get("properties", {}) or {}).get("Nom", {}).get("title", []) or []
        title = "".join(t.get("plain_text", "") for t in title_arr).strip()
        if title:
            existing_titles.add(title)

    completed: Set[str] = set()
    for client_name in available_clients:
        expected = page_builder._generate_report_title(client_name, report_date)
        if expected in existing_titles:
            completed.add(client_name)
    return completed
