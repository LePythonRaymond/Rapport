"""
Offline regression tests for the two REMPLA/BRIEF scanner features added
2026-06-16 (see Resume.md "Session append (2026-06-16)"):

  Feature 1 — REMPLA "Exposition (EXT)": optional 4th slash/comma field
              (plante / taille / lieu / exposition), mapped to a Notion
              select (match-or-create), written whenever present.

  Feature 2 — BRIEF → next 3 upcoming Planning passages, one status per row,
              append-with-dated-separator + substring dedup per row, and the
              scanner fan-out that records a marker as handled only if NONE
              of its rows errored.

Everything here runs fully offline: no Google Chat, no Notion, no Gemini.
Notion/People are replaced with in-memory fakes so we exercise the real
production code paths (extractor, writer, scanner orchestration) without I/O.

Run:  venv/bin/python test_scanner_features.py
"""

import sys
import traceback
from datetime import date

from src.scanner.marker_extractor import (
    MarkerType,
    detect_markers,
    _try_structured_parse,
    extract_rempla_fields,
    _parse_json_object,
    build_rempla_title,
)
from src.scanner.notion_writer import (
    ScannerNotionWriter,
    REMPLA_PROPS,
    PLANNING_PROPS,
    BRIEF_TARGET_PASSAGES,
    BRIEF_JOIN_TEMPLATE,
)
from src.scanner.channel_scanner import ChannelScanner, _BRIEF_STATUS_MAP


# --------------------------------------------------------------------------
# Tiny test harness (no pytest dependency required)
# --------------------------------------------------------------------------

_PASSED = 0
_FAILED = 0


def check(cond, msg):
    global _PASSED, _FAILED
    if cond:
        _PASSED += 1
        print(f"  ✅ {msg}")
    else:
        _FAILED += 1
        print(f"  ❌ FAIL: {msg}")


def section(title):
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


def _planning_row(page_id, brief_text=""):
    """A minimal Notion Planning page with a BRIEF rich_text property."""
    rich = [{"plain_text": brief_text}] if brief_text else []
    return {"id": page_id, "properties": {PLANNING_PROPS["brief"]: {"rich_text": rich}}}


REMPLA_SCHEMA = {
    REMPLA_PROPS["nom"]: {"type": "title"},
    REMPLA_PROPS["site"]: {"type": "relation"},
    REMPLA_PROPS["date_demande"]: {"type": "date"},
    REMPLA_PROPS["qui"]: {"type": "people"},
    REMPLA_PROPS["vegetaux"]: {"type": "rich_text"},
    REMPLA_PROPS["taille"]: {"type": "rich_text"},
    REMPLA_PROPS["lieu"]: {"type": "rich_text"},
    REMPLA_PROPS["exposition"]: {
        "type": "select",
        "select": {"options": [{"name": "Plein soleil"}, {"name": "Mi-ombre"}]},
    },
    REMPLA_PROPS["rempla_effectuee"]: {"type": "checkbox"},
}


class FakeNotionClient:
    def __init__(self, schema=None, query_results=None):
        self.api_key = "fake-key"
        self._schema = schema if schema is not None else {}
        self._query_results = query_results if query_results is not None else []
        self.created_pages = []
        self.updated_pages = []
        self.query_calls = []
        self.raise_on_query = False
        self.raise_on_create = False
        self.update_fail_ids = set()  # page_ids that should raise on update_page

    def get_data_source_schema(self, database_id):
        return self._schema

    def create_page_in_data_source(self, database_id, properties, **kwargs):
        if self.raise_on_create:
            raise RuntimeError("simulated create failure")
        self.created_pages.append({"database_id": database_id, "properties": properties})
        return {"id": "created-rempla-id"}

    def query_database(self, database_id, filter_conditions=None, sorts=None):
        self.query_calls.append(
            {"database_id": database_id, "filter": filter_conditions, "sorts": sorts}
        )
        if self.raise_on_query:
            raise RuntimeError("simulated query failure")
        return list(self._query_results)

    def update_page(self, page_id, properties):
        if page_id in self.update_fail_ids:
            raise RuntimeError(f"simulated update failure for {page_id}")
        self.updated_pages.append({"page_id": page_id, "properties": properties})
        return {"id": page_id}


class FakeResolver:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def resolve(self, email):
        return self.mapping.get(email)


def make_writer(schema=None, query_results=None, resolver=None):
    client = FakeNotionClient(schema=schema, query_results=query_results)
    writer = ScannerNotionWriter(
        notion_client=client, user_resolver=resolver or FakeResolver()
    )
    return writer, client


def _select_name(properties):
    """Pull the chosen select option name out of a built REMPLA properties dict."""
    prop = properties.get(REMPLA_PROPS["exposition"])
    if not prop:
        return None
    return (prop.get("select") or {}).get("name")


def _rich_text_value(properties, prop_name):
    items = (properties.get(prop_name) or {}).get("rich_text") or []
    return "".join(i.get("text", {}).get("content", "") for i in items)


# --------------------------------------------------------------------------
# FEATURE 1 — REMPLA Exposition (EXT)
# --------------------------------------------------------------------------


def test_structured_parse_exposition():
    section("F1: _try_structured_parse — 3 vs 4 fields (exposition)")

    # 3 fields → exposition empty
    r = _try_structured_parse("Monstera / 1m20 / Hall d'entrée")
    check(r is not None and len(r) == 4, "3-field parse returns a 4-tuple")
    check(r == ("Monstera", "1m20", "Hall d'entrée", ""), f"3 fields, exposition empty -> {r}")

    # 4 fields → exposition set
    r = _try_structured_parse("Ficus / 2m / Terrasse / plein soleil")
    check(r == ("Ficus", "2m", "Terrasse", "plein soleil"), f"4 fields, exposition captured -> {r}")

    # comma separator, 4 fields
    r = _try_structured_parse("Olivier, 1m50, Patio, mi-ombre")
    check(r == ("Olivier", "1m50", "Patio", "mi-ombre"), f"comma-separated 4 fields -> {r}")

    # 2 fields → None (fall back to AI / raw)
    check(_try_structured_parse("Monstera / 1m20") is None, "2 fields -> None")

    # 5 fields → None
    check(_try_structured_parse("a / b / c / d / e") is None, "5 fields -> None")

    # overly-long field → None (looks like a sentence)
    long = "x" * 130
    check(_try_structured_parse(f"{long} / b / c / d") is None, "abnormally long field -> None")


def test_extract_rempla_fields_shape():
    section("F1: extract_rempla_fields — dict always has 'exposition'")

    f = extract_rempla_fields("Ficus / 2m / Terrasse / plein soleil")
    check(set(f.keys()) == {"plante", "taille", "lieu", "exposition", "raw"},
          f"keys present: {sorted(f.keys())}")
    check(f["exposition"] == "plein soleil", f"exposition parsed = {f['exposition']!r}")

    f3 = extract_rempla_fields("Ficus / 2m / Terrasse")
    check(f3["exposition"] == "", "3-field message -> exposition empty string")

    # No AI enhancer, unparseable → raw goes to plante, exposition empty (no crash)
    f_raw = extract_rempla_fields("remplacer le gros ficus du fond", text_enhancer=None)
    check(f_raw["exposition"] == "" and f_raw["plante"], "free-form w/o AI -> exposition empty, plante=raw")


def test_ai_json_parser_exposition():
    section("F1: _parse_json_object — AI fallback returns 'exposition'")

    parsed = _parse_json_object(
        '```json\n{"plante": "3 Monstera", "taille": "1m", "lieu": "Hall", '
        '"exposition": "mi-ombre"}\n```'
    )
    check(parsed is not None, "fenced JSON parses")
    check(parsed and parsed.get("exposition") == "mi-ombre", f"exposition extracted -> {parsed}")

    # Missing exposition key in AI output → empty string, not KeyError
    parsed2 = _parse_json_object('{"plante": "Ficus", "taille": "", "lieu": "X"}')
    check(parsed2 is not None and parsed2.get("exposition") == "", "missing exposition key -> ''")


def test_resolve_select_option():
    section("F1: _resolve_select_option — match-or-create")

    writer, _ = make_writer(schema=REMPLA_SCHEMA)

    # Case-insensitive match to an existing option returns the canonical name
    check(
        writer._resolve_select_option(REMPLA_PROPS["exposition"], "plein soleil") == "Plein soleil",
        "case-insensitive match -> canonical 'Plein soleil'",
    )
    check(
        writer._resolve_select_option(REMPLA_PROPS["exposition"], "MI-OMBRE") == "Mi-ombre",
        "uppercase input matches 'Mi-ombre'",
    )
    # Unknown value -> returned as-is (Notion will create the option)
    check(
        writer._resolve_select_option(REMPLA_PROPS["exposition"], "ombre totale") == "ombre totale",
        "unknown value -> returned for create",
    )
    # Whitespace trimmed
    check(
        writer._resolve_select_option(REMPLA_PROPS["exposition"], "  plein soleil  ") == "Plein soleil",
        "surrounding whitespace trimmed before match",
    )
    # Empty -> None (caller skips the property)
    check(writer._resolve_select_option(REMPLA_PROPS["exposition"], "") is None, "empty -> None")
    check(writer._resolve_select_option(REMPLA_PROPS["exposition"], "   ") is None, "whitespace-only -> None")


def test_create_rempla_row_exposition_present():
    section("F1: create_rempla_row — exposition select written when present")

    writer, client = make_writer(schema=REMPLA_SCHEMA)
    fields = {
        "plante": "Ficus",
        "taille": "2m",
        "lieu": "Terrasse",
        "exposition": "plein soleil",
        "raw": "Ficus / 2m / Terrasse / plein soleil",
    }
    page_id = writer.create_rempla_row(
        site_page_id="site-123",
        message_text=fields["raw"],
        message_timestamp_iso="2026-06-16T09:00:00Z",
        author_email=None,
        fields=fields,
    )
    check(page_id == "created-rempla-id", "row created (page id returned)")
    check(len(client.created_pages) == 1, "exactly one create call")
    props = client.created_pages[0]["properties"]
    check(_select_name(props) == "Plein soleil", f"exposition select = {_select_name(props)!r} (canonicalised)")
    check(_rich_text_value(props, REMPLA_PROPS["vegetaux"]) == "Ficus", "végétaux rich_text = plante")
    check(_rich_text_value(props, REMPLA_PROPS["lieu"]) == "Terrasse", "lieu rich_text written")
    check(props.get(REMPLA_PROPS["rempla_effectuee"]) == {"checkbox": False}, "Effectuée defaults to False")


def test_create_rempla_row_exposition_absent():
    section("F1: create_rempla_row — no exposition -> property omitted")

    writer, client = make_writer(schema=REMPLA_SCHEMA)
    fields = {"plante": "Olivier", "taille": "1m", "lieu": "Patio", "exposition": "", "raw": "x"}
    writer.create_rempla_row("site-1", "x", "2026-06-16T09:00:00Z", None, fields)
    props = client.created_pages[0]["properties"]
    check(REMPLA_PROPS["exposition"] not in props, "Exposition (EXT) key absent when no value")


def test_create_rempla_row_exposition_dropped_when_column_missing():
    section("F1: create_rempla_row — exposition dropped if column not in schema")

    # Schema WITHOUT the Exposition column -> schema filter should drop it
    schema_no_expo = {k: v for k, v in REMPLA_SCHEMA.items() if k != REMPLA_PROPS["exposition"]}
    writer, client = make_writer(schema=schema_no_expo)
    fields = {"plante": "Ficus", "taille": "2m", "lieu": "T", "exposition": "plein soleil", "raw": "x"}
    page_id = writer.create_rempla_row("site-1", "x", "2026-06-16T09:00:00Z", None, fields)
    check(page_id == "created-rempla-id", "row still created despite missing column")
    props = client.created_pages[0]["properties"]
    check(REMPLA_PROPS["exposition"] not in props, "missing column -> exposition silently dropped (row not failed)")


# --------------------------------------------------------------------------
# FEATURE 2 — BRIEF → next 3 passages
# --------------------------------------------------------------------------


def test_brief_fans_out_to_three_rows():
    section("F2: patch_next_planning_briefs — writes to next 3 empty rows")

    rows = [_planning_row(f"plan-{i}") for i in range(5)]  # 5 upcoming, all empty
    writer, client = make_writer(query_results=rows)
    statuses = writer.patch_next_planning_briefs("site-1", "Tailler la haie")
    check(statuses == ["written", "written", "written"], f"3 statuses, all 'written' -> {statuses}")
    check(len(client.updated_pages) == 3, "exactly 3 Planning rows updated (not 5, not 1)")
    updated_ids = [u["page_id"] for u in client.updated_pages]
    check(updated_ids == ["plan-0", "plan-1", "plan-2"], f"the 3 soonest rows -> {updated_ids}")
    # Query used the right filter/sort
    q = client.query_calls[0]
    check(q["sorts"] == [{"property": PLANNING_PROPS["date"], "direction": "ascending"}],
          "query sorted by Date ascending")
    today = date.today().isoformat()
    has_date_filter = any(
        c.get("date", {}).get("on_or_after") == today for c in q["filter"]["and"]
    )
    check(has_date_filter, "query filters Date on_or_after today")


def test_brief_fewer_than_three():
    section("F2: patch_next_planning_briefs — fewer rows than target")

    rows = [_planning_row("only-1")]
    writer, client = make_writer(query_results=rows)
    statuses = writer.patch_next_planning_briefs("site-1", "Arroser")
    check(statuses == ["written"], f"single upcoming row -> single status {statuses}")
    check(len(client.updated_pages) == 1, "one update")


def test_brief_no_target():
    section("F2: patch_next_planning_briefs — no upcoming row")

    writer, client = make_writer(query_results=[])
    statuses = writer.patch_next_planning_briefs("site-1", "Quelque chose")
    check(statuses == ["no_target"], f"empty result -> ['no_target'] ({statuses})")
    check(len(client.updated_pages) == 0, "nothing updated")


def test_brief_query_error():
    section("F2: patch_next_planning_briefs — query failure")

    writer, client = make_writer(query_results=[])
    client.raise_on_query = True
    statuses = writer.patch_next_planning_briefs("site-1", "X")
    check(statuses == ["error"], f"query exception -> ['error'] ({statuses})")


def test_brief_append_and_dedup_per_row():
    section("F2: per-row write / append / duplicate")

    today_label = date.today().strftime("%d/%m")
    rows = [
        _planning_row("empty-row"),                          # -> written
        _planning_row("has-other", "Ancien brief existant"), # -> appended
        _planning_row("has-same", "Tailler la haie"),        # -> duplicate (substring)
    ]
    writer, client = make_writer(query_results=rows)
    statuses = writer.patch_next_planning_briefs("site-1", "Tailler la haie")
    check(statuses == ["written", "appended", "duplicate"], f"mixed per-row statuses -> {statuses}")

    # Only the empty + the append-target rows are actually updated; duplicate is a no-op
    updated_ids = [u["page_id"] for u in client.updated_pages]
    check("has-same" not in updated_ids, "duplicate row NOT updated (no-op)")
    check(set(updated_ids) == {"empty-row", "has-other"}, f"only written+appended updated -> {updated_ids}")

    # The appended row should contain a dated separator and preserve old text
    appended = next(u for u in client.updated_pages if u["page_id"] == "has-other")
    merged = _rich_text_value(appended["properties"], PLANNING_PROPS["brief"])
    check("Ancien brief existant" in merged, "appended row preserves existing text")
    check("Tailler la haie" in merged, "appended row contains new text")
    check(f"[{today_label}]" in merged, f"appended row has dated separator [{today_label}]")


def test_brief_partial_failure_returns_error_status():
    section("F2: per-row error surfaces as 'error' status")

    rows = [_planning_row("ok-row"), _planning_row("bad-row")]
    writer, client = make_writer(query_results=rows)
    client.update_fail_ids = {"bad-row"}
    statuses = writer.patch_next_planning_briefs("site-1", "Nettoyer")
    check(statuses == ["written", "error"], f"one ok, one failed -> {statuses}")


# --------------------------------------------------------------------------
# FEATURE 2 — scanner fan-out / dedup orchestration
# --------------------------------------------------------------------------


def _bare_scanner(writer):
    """Build a ChannelScanner without running its network-touching __init__."""
    scanner = object.__new__(ChannelScanner)
    scanner.writer = writer
    scanner._text_enhancer = False  # disable AI fallback in REMPLA parsing
    return scanner


def test_brief_status_map_complete():
    section("F2: _BRIEF_STATUS_MAP covers every writer status")
    expected = {"written", "appended", "duplicate", "no_target", "error"}
    check(set(_BRIEF_STATUS_MAP.keys()) == expected, f"map keys = {sorted(_BRIEF_STATUS_MAP)}")
    check(_BRIEF_STATUS_MAP["error"] == "error", "writer 'error' maps to scanner 'error'")


def test_process_brief_span_maps_list():
    section("F2: _process_brief_span returns a LIST of mapped statuses")

    rows = [_planning_row("a"), _planning_row("b", "old"), _planning_row("c", "Brief Y")]
    writer, _ = make_writer(query_results=rows)
    scanner = _bare_scanner(writer)

    spans = detect_markers("(BRIEF) Brief Y")
    check(len(spans) == 1 and spans[0].marker == MarkerType.BRIEF, "single BRIEF span detected")

    statuses = scanner._process_brief_span({"page_id": "site-1"}, "msg-123456789012", spans[0])
    check(statuses == ["brief_written", "brief_appended", "brief_duplicate"],
          f"mapped to brief_* list -> {statuses}")


def test_handle_message_both_markers():
    section("F2: _handle_message — one message with REMPLA + BRIEF")

    # REMPLA needs a schema-aware writer; reuse same writer for both (it also
    # serves Planning). Provide both a schema and planning query results.
    client = FakeNotionClient(schema=REMPLA_SCHEMA, query_results=[_planning_row("p1")])
    writer = ScannerNotionWriter(notion_client=client, user_resolver=FakeResolver())
    scanner = _bare_scanner(writer)

    msg = {
        "id": "msg-abcdef123456",
        "createTime": "2026-06-16T08:00:00Z",
        "author": {"email": "someone@example.com"},
        "text": "(REMPLA) Ficus / 2m / Terrasse / plein soleil (BRIEF) Penser à la clé",
    }
    outcomes = scanner._handle_message({"page_id": "site-1"}, msg, already_handled=set())
    check(outcomes is not None and len(outcomes) == 2, f"two markers handled -> {len(outcomes) if outcomes else 0}")
    markers = [mv for mv, _ in outcomes]
    check(markers == ["rempla", "brief"], f"order rempla then brief -> {markers}")
    rempla_statuses = dict(outcomes)["rempla"]
    brief_statuses = dict(outcomes)["brief"]
    check(rempla_statuses == ["rempla"], f"rempla status list -> {rempla_statuses}")
    check(brief_statuses == ["brief_written"], f"brief status list -> {brief_statuses}")
    # REMPLA payload must NOT bleed the (BRIEF) text into the plant fields
    expo = _select_name(client.created_pages[0]["properties"])
    check(expo == "Plein soleil", f"REMPLA exposition correctly bounded -> {expo}")


def test_handle_message_dedup_skips_processed_marker():
    section("F2: _handle_message — already-processed marker is skipped")

    client = FakeNotionClient(schema=REMPLA_SCHEMA, query_results=[_planning_row("p1")])
    writer = ScannerNotionWriter(notion_client=client, user_resolver=FakeResolver())
    scanner = _bare_scanner(writer)
    msg = {
        "id": "msg-x",
        "createTime": "2026-06-16T08:00:00Z",
        "author": {},
        "text": "(REMPLA) Ficus / 2m / Terrasse (BRIEF) note",
    }
    # rempla already handled -> only brief should be processed
    outcomes = scanner._handle_message({"page_id": "s1"}, msg, already_handled={"rempla"})
    markers = [mv for mv, _ in outcomes]
    check(markers == ["brief"], f"only unprocessed marker handled -> {markers}")
    check(len(client.created_pages) == 0, "no REMPLA row re-created for already-handled marker")


def test_handle_message_no_marker():
    section("F2: _handle_message — no marker -> None")
    writer, _ = make_writer()
    scanner = _bare_scanner(writer)
    out = scanner._handle_message({"page_id": "s"}, {"id": "m", "text": "juste un message normal"}, set())
    check(out is None, "plain message returns None")


def test_run_loop_partial_failure_does_not_mark_handled():
    section("F2: run-loop accounting — partial BRIEF failure retries whole marker")

    # Simulate the inner accounting block of run() the way the scanner does it,
    # to prove a marker with ANY 'error' row is NOT added to already_handled.
    outcomes = [("brief", ["brief_written", "error", "brief_duplicate"])]
    already_handled = set()
    any_failure = False
    counters = {"brief_written": 0, "brief_duplicate": 0, "errors": 0}
    for marker_value, statuses in outcomes:
        marker_errored = False
        for status in statuses:
            if status == "brief_written":
                counters["brief_written"] += 1
            elif status == "brief_duplicate":
                counters["brief_duplicate"] += 1
            elif status == "error":
                counters["errors"] += 1
                marker_errored = True
        if marker_errored:
            any_failure = True
        else:
            already_handled.add(marker_value)

    check(any_failure is True, "any_failure set when a row errored")
    check("brief" not in already_handled, "marker NOT recorded as handled on partial failure (will retry)")
    check(counters["brief_written"] == 1 and counters["brief_duplicate"] == 1,
          "successful rows still counted")
    check(counters["errors"] == 1, "error row counted once")


def test_run_loop_all_success_marks_handled():
    section("F2: run-loop accounting — all-success marks marker handled")
    outcomes = [("brief", ["brief_written", "brief_appended", "brief_duplicate"])]
    already_handled = set()
    any_failure = False
    for marker_value, statuses in outcomes:
        marker_errored = any(s == "error" for s in statuses)
        if marker_errored:
            any_failure = True
        else:
            already_handled.add(marker_value)
    check(not any_failure and "brief" in already_handled, "no error -> marker recorded handled")


# --------------------------------------------------------------------------
# FEATURE 2 — REAL run() end-to-end (state file, cursor clamp, retry)
# --------------------------------------------------------------------------


class FakeChatClient:
    """Returns a fixed message list for any space; records calls."""

    def __init__(self, messages):
        self._messages = messages
        self.calls = []

    def get_messages_for_space(self, space_id, start_date, end_date, raise_on_error=False):
        self.calls.append({"space_id": space_id, "start": start_date, "end": end_date})
        return list(self._messages)


def _run_scanner(writer, messages, state_file):
    """Build a ChannelScanner bypassing network __init__, with stubbed
    site-loading + chat client, and execute the REAL run() loop."""
    scanner = object.__new__(ChannelScanner)
    scanner.state_file_path = state_file
    scanner.cold_start_lookback_hours = 24
    scanner.site_filter = None
    scanner.writer = writer
    scanner._text_enhancer = False
    scanner.chat_client = FakeChatClient(messages)
    scanner.load_sites = lambda: [
        {
            "page_id": "site-1",
            "name": "TEST(TAD)",
            "channel_url": "spaces/AAA",
            "space_id": "spaces/AAA",
            "int_ext": "",
        }
    ]
    return scanner


def test_run_end_to_end_brief_success():
    section("F2 e2e: run() — BRIEF to 3 rows, state records marker handled")
    import json
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)  # start with no state file

    rows = [_planning_row(f"p{i}") for i in range(3)]
    writer, client = make_writer(query_results=rows)
    msg = {
        "id": "msg-success-1",
        "createTime": "2026-06-16T08:00:00Z",
        "author": {},
        "text": "(BRIEF) Penser à tailler",
    }
    scanner = _run_scanner(writer, [msg], tmp.name)
    result = scanner.run()
    counters = result["counters"]

    check(counters["brief_written"] == 3, f"brief_written == 3 -> {counters['brief_written']}")
    check(counters["errors"] == 0, f"no errors -> {counters['errors']}")
    check(len(client.updated_pages) == 3, "3 Planning rows updated")

    with open(tmp.name) as f:
        state = json.load(f)
    check(state["processed_markers"].get("msg-success-1") == ["brief"],
          f"marker recorded handled -> {state['processed_markers'].get('msg-success-1')}")
    # Cursor advanced to (or past) the message time
    cursor = state["last_scan_per_channel"].get("spaces/AAA", "")
    check(cursor >= "2026-06-16T08:00:00", f"cursor advanced past message -> {cursor}")
    os.unlink(tmp.name)


def test_run_end_to_end_partial_failure_then_retry():
    section("F2 e2e: run() — partial failure clamps cursor & retries without double-write")
    import json
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    os.unlink(tmp.name)

    # 3 upcoming rows; the middle one fails on update.
    rows = [_planning_row("ok-1"), _planning_row("bad-2"), _planning_row("ok-3")]
    writer, client = make_writer(query_results=rows)
    client.update_fail_ids = {"bad-2"}

    msg = {
        "id": "msg-partial-1",
        "createTime": "2026-06-16T08:00:00Z",
        "author": {},
        "text": "(BRIEF) Mission importante",
    }
    scanner = _run_scanner(writer, [msg], tmp.name)
    result = scanner.run()
    counters = result["counters"]

    check(counters["brief_written"] == 2, f"2 rows written -> {counters['brief_written']}")
    check(counters["errors"] == 1, f"1 error -> {counters['errors']}")

    with open(tmp.name) as f:
        state = json.load(f)
    # Marker must NOT be recorded as handled (so it retries)
    check("msg-partial-1" not in state.get("processed_markers", {}),
          "failed marker NOT in processed_markers (will retry)")
    # Cursor clamped strictly before the message so the retry window includes it
    cursor = state["last_scan_per_channel"].get("spaces/AAA", "")
    check(cursor < "2026-06-16T08:00:00", f"cursor clamped before message -> {cursor}")

    # --- Second run (retry): the good rows now already contain the text and
    # must be deduped; only the previously-failing row should change. ---
    client.update_fail_ids = set()  # the transient failure is gone now
    # Reflect the first run's writes into the query results so dedup can see them
    rows_after = [
        _planning_row("ok-1", "Mission importante"),
        _planning_row("bad-2"),  # still empty — it failed last time
        _planning_row("ok-3", "Mission importante"),
    ]
    client._query_results = rows_after
    client.updated_pages.clear()

    result2 = scanner.run()
    c2 = result2["counters"]
    check(c2["brief_duplicate"] == 2, f"2 rows dedup-skipped on retry -> {c2['brief_duplicate']}")
    check(c2["brief_written"] == 1, f"only the failed row written on retry -> {c2['brief_written']}")
    updated_ids = [u["page_id"] for u in client.updated_pages]
    check(updated_ids == ["bad-2"], f"only previously-failed row updated on retry -> {updated_ids}")

    with open(tmp.name) as f:
        state2 = json.load(f)
    check(state2["processed_markers"].get("msg-partial-1") == ["brief"],
          "marker now recorded handled after successful retry")
    os.unlink(tmp.name)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def main():
    tests = [
        # Feature 1
        test_structured_parse_exposition,
        test_extract_rempla_fields_shape,
        test_ai_json_parser_exposition,
        test_resolve_select_option,
        test_create_rempla_row_exposition_present,
        test_create_rempla_row_exposition_absent,
        test_create_rempla_row_exposition_dropped_when_column_missing,
        # Feature 2 — writer
        test_brief_fans_out_to_three_rows,
        test_brief_fewer_than_three,
        test_brief_no_target,
        test_brief_query_error,
        test_brief_append_and_dedup_per_row,
        test_brief_partial_failure_returns_error_status,
        # Feature 2 — scanner orchestration
        test_brief_status_map_complete,
        test_process_brief_span_maps_list,
        test_handle_message_both_markers,
        test_handle_message_dedup_skips_processed_marker,
        test_handle_message_no_marker,
        test_run_loop_partial_failure_does_not_mark_handled,
        test_run_loop_all_success_marks_handled,
        # Feature 2 — real run() end-to-end
        test_run_end_to_end_brief_success,
        test_run_end_to_end_partial_failure_then_retry,
    ]
    for t in tests:
        try:
            t()
        except Exception:
            global _FAILED
            _FAILED += 1
            print(f"  ❌ EXCEPTION in {t.__name__}:")
            traceback.print_exc()

    print(f"\n{'='*48}")
    print(f"  RESULTS: {_PASSED} passed, {_FAILED} failed")
    print(f"{'='*48}")
    return 1 if _FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
