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
import logging
import os
import sys
import traceback
from datetime import datetime


def _silence_streamlit_noise() -> None:
    """
    The scanner imports modules that also live in our Streamlit app, so
    `streamlit` gets transitively imported. When we run outside `streamlit
    run`, Streamlit emits "missing ScriptRunContext!" warnings and tries to
    read a secrets.toml. None of that is actionable here — mute it before
    any downstream imports pull Streamlit in.
    """
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_GLOBAL_DISABLE_WATCHDOG_WARNING", "true")
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
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    started_at = datetime.now()

    print(f"=== Scanner run started at {started_at.isoformat(timespec='seconds')} ===")

    try:
        scanner = ChannelScanner(
            state_file_path=args.state_file,
            cold_start_lookback_hours=args.cold_start_hours,
        )
        counters = scanner.run()
    except Exception as e:
        print(f"FATAL: scanner aborted: {e}")
        traceback.print_exc()
        return 1

    finished_at = datetime.now()
    duration_s = (finished_at - started_at).total_seconds()

    print("\n=== Scanner run summary ===")
    for key, value in counters.items():
        print(f"  {key}: {value}")
    print(f"  duration_s: {duration_s:.1f}")
    print(f"=== Scanner run finished at {finished_at.isoformat(timespec='seconds')} ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
