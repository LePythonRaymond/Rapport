"""
Entry point for the REMPLA & BRIEF channel scanner.

=== What this does ===
Scans every Google Chat channel from the Sites Notion DB for messages that
contain (REMPLA) or (BRIEF) markers. For each detected message:
- (REMPLA) -> creates a new row in the REMPLA Notion DB (plante / taille /
  lieu, linked to the site, author resolved to a Notion Person).
- (BRIEF)  -> patches the next upcoming Planning row for that site with the
  full message text (only if that row's BRIEF field is currently empty).

Deduplication is persisted in scanner_state.json (processed message IDs +
last scan timestamp per channel), so running this every hour is safe.

=== VPS deployment (Hostinger) ===
Prerequisites on the VPS:
- Python 3.10+ and a virtualenv with requirements.txt installed.
- credentials.json and a valid token.pickle (or GOOGLE_TOKEN_PICKLE_B64 env
  var for headless environments) — same auth as the main app.
- .env with NOTION_API_KEY, GEMINI_API_KEY, plus (optional, already defaulted)
  NOTION_DATABASE_ID_CLIENTS / REMPLA / PLANNING.
- Manual Notion step: add a 'Lieu' Rich Text property to the REMPLA DB.
  Without it, the scanner still writes every other field and just skips Lieu
  (logged at startup).

Cron entry (every hour on the hour, with log rotation via logrotate):

    0 * * * * cd /srv/merci-raymond-scanner \
        && /srv/merci-raymond-scanner/venv/bin/python run_scanner.py \
        >> /var/log/merci-raymond-scanner/scanner.log 2>&1

Example logrotate config at /etc/logrotate.d/merci-raymond-scanner:

    /var/log/merci-raymond-scanner/scanner.log {
        weekly
        rotate 8
        compress
        missingok
        notifempty
        copytruncate
    }

=== CLI ===

    python run_scanner.py [--state-file PATH] [--cold-start-hours N]

Exit codes:
    0 — scan completed (even if some sites/messages errored individually)
    1 — fatal failure (couldn't initialize, lost connectivity, etc.)
"""

import argparse
import contextlib
import io
import logging
import os
import sys
import traceback
from datetime import datetime


def _silence_streamlit_noise() -> None:
    """
    The scanner imports modules that also live in our Streamlit app, so
    `streamlit` gets transitively imported. When we run outside `streamlit
    run`, Streamlit emits:
      - a CORS/XSRF config-conflict warning on import
      - "missing ScriptRunContext!" log warnings when code accesses
        st.session_state
      - noisy "No secrets found" messages from our own auth helpers trying
        to read st.secrets

    We mute everything before any downstream import pulls Streamlit in:
      1. Env vars are read by Streamlit at import time, so they must be set
         FIRST (override CORS/XSRF to silence the config warning, mute the
         logger, hide usage prompts).
      2. Set the Streamlit logger levels as a belt-and-braces in case the
         env var doesn't propagate.
      3. Flip our custom SCANNER_SKIP_STREAMLIT flag so auth.py /
         notion/client.py skip their Streamlit-only code paths cleanly.
    """
    streamlit_env = {
        "STREAMLIT_SERVER_HEADLESS": "true",
        "STREAMLIT_SERVER_ENABLE_CORS": "true",
        "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION": "true",
        "STREAMLIT_LOGGER_LEVEL": "error",
        "STREAMLIT_GLOBAL_DISABLE_WATCHDOG_WARNING": "true",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        # Our own gate — respected by src/google_chat/auth.py and
        # src/notion/client.py so they don't touch st.secrets /
        # st.session_state outside a Streamlit runtime.
        "SCANNER_SKIP_STREAMLIT": "1",
    }
    for key, value in streamlit_env.items():
        os.environ.setdefault(key, value)

    for logger_name in (
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
        "streamlit.runtime.caching",
        "streamlit.config",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


_silence_streamlit_noise()

# Streamlit reads .streamlit/config.toml on import and only validates it the
# first time a config option is actually read. Config reads happen lazily
# inside our scanner deps (notion-client, people resolver, etc.), which is
# why env vars, logger levels, and even an eager `import streamlit` don't
# always catch the CORS/XSRF conflict warning — the validator fires only
# when a real option lookup happens. We therefore:
#   1. eagerly import streamlit under redirect_stderr, and
#   2. eagerly trigger a config read under the same redirect so the
#      validator runs and prints the warning into our sink, not the log.
# After that, streamlit's module-level state caches the config so later
# lazy imports never re-trigger the validator.
# Unhandled exceptions still propagate — redirect_stderr only captures
# text written to sys.stderr, not raised exceptions.
_import_noise = io.StringIO()
with contextlib.redirect_stderr(_import_noise):
    try:
        import streamlit  # noqa: F401
        try:
            from streamlit import config as _st_config
            _st_config.get_option("server.headless")
        except Exception:
            pass
    except ImportError:
        pass  # Streamlit isn't a scanner dependency; nothing to silence.
    from src.scanner.channel_scanner import ChannelScanner  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Google Chat channels for (REMPLA) and (BRIEF) markers."
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to the JSON state file (default: scanner_state.json in CWD).",
    )
    parser.add_argument(
        "--cold-start-hours",
        type=int,
        default=24,
        help=(
            "When a channel has no prior state, look this many hours back on "
            "the very first scan of that channel (default: 24)."
        ),
    )
    parser.add_argument(
        "--site-filter",
        default=None,
        help=(
            "Case-insensitive substring; only sites whose name OR space_id "
            "contains this string are scanned. Use for fast iteration on a "
            "single channel, e.g. --site-filter 'TEST(TAD)'."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    started_at = datetime.now()

    print(f"=== Scanner run started at {started_at.isoformat(timespec='seconds')} ===")

    try:
        scanner = ChannelScanner(
            state_file_path=args.state_file,
            cold_start_lookback_hours=args.cold_start_hours,
            site_filter=args.site_filter,
        )
        result = scanner.run()
    except Exception as e:
        print(f"FATAL: scanner aborted: {e}")
        traceback.print_exc()
        return 1

    counters = result.get("counters", {})
    forbidden = result.get("forbidden", [])

    finished_at = datetime.now()
    duration_s = (finished_at - started_at).total_seconds()

    print("\n=== Scanner run summary ===")
    for key, value in counters.items():
        print(f"  {key}: {value}")
    print(f"  duration_s: {duration_s:.1f}")

    # 403 summary: one line per channel the OAuth user can't read. Easier
    # to triage than digging through inline 403s in the per-site logs.
    if forbidden:
        print(f"\n=== 403 (no access) — {len(forbidden)} channel(s) ===")
        for entry in forbidden:
            print(f"  • {entry['space_id']} — {entry['name']}")
        print(
            "  (Add the OAuth user to these spaces in Google Chat, or clear "
            "their 'Canal Chat' field in Notion to silence them.)"
        )

    print(f"=== Scanner run finished at {finished_at.isoformat(timespec='seconds')} ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
