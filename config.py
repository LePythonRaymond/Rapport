import os
import re
import json
import unicodedata
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# Cache for secrets to avoid repeated lookups
_secrets_cache: dict = {}

def _get_secret(key: str) -> Optional[str]:
    """
    Get a secret value, checking Streamlit secrets first (for Streamlit Cloud),
    then falling back to environment variables (for local development).

    This function accesses secrets lazily - only when called within the Streamlit
    runtime context, not at module import time.

    Args:
        key: The secret key to retrieve

    Returns:
        The secret value, or None if not found
    """
    # Check cache first
    if key in _secrets_cache:
        return _secrets_cache[key]

    # Try to access Streamlit secrets (for Streamlit Cloud)
    # This only works when called within Streamlit runtime context
    try:
        import streamlit as st
        # Access st.secrets directly - it's available within Streamlit context
        if hasattr(st, 'secrets') and st.secrets is not None:
            try:
                # Access secret using top-level key (matches .streamlit/secrets.toml structure)
                if key in st.secrets:
                    value = st.secrets[key]
                    _secrets_cache[key] = value
                    return value
            except (KeyError, AttributeError, TypeError):
                # Secret not found in st.secrets, continue to fallback
                pass
            except Exception as e:
                # Handle any other error when accessing secrets
                # (e.g., StreamlitSecretNotFoundError or no secrets.toml file in local dev)
                pass
    except (ImportError, AttributeError, RuntimeError):
        # Streamlit not available or not in Streamlit context
        # This is normal when running outside Streamlit (e.g., tests, scripts)
        pass

    # Fallback to environment variable (for local development)
    value = os.getenv(key)
    if value:
        _secrets_cache[key] = value
    return value

# API Keys - Using lazy getter functions
def get_notion_api_key() -> Optional[str]:
    """Get Notion API key (lazy loaded)."""
    return _get_secret("NOTION_API_KEY")

def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key (lazy loaded)."""
    return _get_secret("OPENAI_API_KEY")

def get_gemini_api_key() -> Optional[str]:
    """Get Gemini API key for Google AI (lazy loaded). Prefers GEMINI_API_KEY, fallback to GOOGLE_API_KEY."""
    return _get_secret("GEMINI_API_KEY") or _get_secret("GOOGLE_API_KEY")

# Module-level properties for backward compatibility
# These are accessed lazily via __getattr__
def __getattr__(name: str):
    """
    Lazy attribute access for secrets and configuration.
    Allows backward compatibility with config.NOTION_API_KEY syntax.
    """
    # API Keys
    if name == "NOTION_API_KEY":
        return get_notion_api_key()
    elif name == "OPENAI_API_KEY":
        return get_openai_api_key()
    elif name == "GEMINI_API_KEY":
        return get_gemini_api_key()

    # Google Credentials
    elif name == "GOOGLE_CREDENTIALS_PATH":
        return get_google_credentials_path()

    # Database IDs
    elif name == "NOTION_DB_CLIENTS":
        return get_notion_db_clients()
    elif name == "NOTION_DB_RAPPORTS":
        return get_notion_db_rapports()
    elif name == "NOTION_DB_INTERVENTIONS":
        return get_notion_db_interventions()
    elif name == "NOTION_DB_REMPLA":
        return get_notion_db_rempla()
    elif name == "NOTION_DB_PLANNING":
        return get_notion_db_planning()
    elif name == "NOTION_DB_TEAM":
        return get_notion_db_team()

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# Google OAuth Credentials handling
# For Streamlit Cloud: Store credentials.json content in GOOGLE_CREDENTIALS_JSON secret
# For local: Use GOOGLE_CREDENTIALS_PATH pointing to credentials.json file
_google_credentials_path_cache: Optional[str] = None

def _setup_google_credentials() -> Optional[str]:
    """
    Setup Google credentials file from environment variable or file path.
    Supports both local development (file path) and Streamlit Cloud (JSON content).
    This function is called lazily when GOOGLE_CREDENTIALS_PATH is accessed.
    """
    global _google_credentials_path_cache

    # Return cached value if available
    if _google_credentials_path_cache is not None:
        return _google_credentials_path_cache

    # Check if credentials JSON is provided (Streamlit Cloud secrets or env var)
    credentials_json = _get_secret("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        # Write credentials to a temporary file
        credentials_path = "credentials.json"
        try:
            # Parse to validate JSON, then write
            json.loads(credentials_json)  # Validate JSON
            with open(credentials_path, 'w') as f:
                f.write(credentials_json)
            _google_credentials_path_cache = credentials_path
            return credentials_path
        except json.JSONDecodeError:
            raise ValueError("GOOGLE_CREDENTIALS_JSON is not valid JSON")

    # Fallback to file path (local development)
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    if os.path.exists(credentials_path):
        _google_credentials_path_cache = credentials_path
        return credentials_path

    # If neither exists, return None (will raise error in auth.py)
    _google_credentials_path_cache = None
    return None

def get_google_credentials_path() -> Optional[str]:
    """Get Google credentials path (lazy loaded)."""
    return _setup_google_credentials()

def _format_database_id(db_id: str) -> str:
    """
    Format Notion database ID for API calls.
    Removes dashes, quotes, and whitespace from database IDs as required by Notion API.

    Args:
        db_id: Database ID (with or without dashes, may include quotes/whitespace)

    Returns:
        Database ID without dashes, quotes, or whitespace for API calls
    """
    if not db_id:
        return ""
    # Convert to string, strip whitespace and quotes, then remove dashes
    db_id = str(db_id).strip().strip('"').strip("'")
    return db_id.replace('-', '')

# Notion Database IDs (hardcoded defaults with override via secrets/env vars)
# Hardcoded default values (can be overridden by secrets or environment variables)
NOTION_DB_CLIENTS_DEFAULT = "285d9278-02d7-809d-bf44-d2112b6fcad0"
NOTION_DB_RAPPORTS_DEFAULT = "293d9278-02d7-801c-a1b3-cf6d7dbadf84"
NOTION_DB_INTERVENTIONS_DEFAULT = "286d9278-02d7-8097-8539-fa6f88aa0ecf"
NOTION_DB_REMPLA_DEFAULT = "349d9278-02d7-80ec-ada9-000b9afab73a"
NOTION_DB_PLANNING_DEFAULT = "342d9278-02d7-8016-9336-000b5f9f3f81"
NOTION_DB_TEAM_DEFAULT = "342d9278-02d7-80bb-a655-000b70f28756"

# Cache for database IDs
_db_ids_cache: dict = {}

def _get_database_id(key: str, default: str) -> str:
    """
    Get a database ID from secrets/env vars, with fallback to default.
    Lazy loaded - only accessed when needed.
    """
    if key in _db_ids_cache:
        return _db_ids_cache[key]

    secret_value = _get_secret(key)
    db_id = _format_database_id(str(secret_value or default))
    _db_ids_cache[key] = db_id
    return db_id

def get_notion_db_clients() -> str:
    """Get Clients database ID (lazy loaded)."""
    return _get_database_id("NOTION_DATABASE_ID_CLIENTS", NOTION_DB_CLIENTS_DEFAULT)

def get_notion_db_rapports() -> str:
    """Get Rapports database ID (lazy loaded)."""
    return _get_database_id("NOTION_DATABASE_ID_RAPPORTS", NOTION_DB_RAPPORTS_DEFAULT)

def get_notion_db_interventions() -> str:
    """Get Interventions database ID (lazy loaded)."""
    return _get_database_id("NOTION_DATABASE_ID_INTERVENTIONS", NOTION_DB_INTERVENTIONS_DEFAULT)

def get_notion_db_rempla() -> str:
    """Get SUIVI REMPLA database ID (lazy loaded)."""
    return _get_database_id("NOTION_DATABASE_ID_REMPLA", NOTION_DB_REMPLA_DEFAULT)

def get_notion_db_planning() -> str:
    """Get Planning database ID (lazy loaded)."""
    return _get_database_id("NOTION_DATABASE_ID_PLANNING", NOTION_DB_PLANNING_DEFAULT)

def get_notion_db_team() -> str:
    """Get Team / maintenance team database ID (lazy loaded).

    DB columns expected: `Nom` (title), `email` (rich_text), `Sous-Groupe`
    (multi_select with `INT` / `EXT` / `BUREAU`). `BUREAU` flags office members.
    """
    return _get_database_id("NOTION_DATABASE_ID_TEAM", NOTION_DB_TEAM_DEFAULT)

# AI Model settings (Gemini 3.1 Flash-Lite — GA)
AI_MODEL = "gemini-3.1-flash-lite"
AI_TEMPERATURE = 1

# Report assets (paths relative to project root unless absolute)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_COVER_IMAGE_PATH = "Image_Rapport.jpeg"
# Directory containing multiple cover images; one is chosen at random per report. If missing, REPORT_COVER_IMAGE_PATH is used.
REPORT_COVER_IMAGE_DIR = "report_covers"
REPORT_ICON_IMAGE_PATH = "logo_MR_copie.webp"

# Office team / maintenance directory.
#
# Source of truth: Notion DB `NOTION_DATABASE_ID_TEAM` (rows tagged `BUREAU` in
# the `Sous-Groupe` multi-select are office). Loaded into `_TEAM_CACHE` at
# startup via `load_team_members_from_notion()`.
#
# `OFFICE_TEAM_MEMBERS` below is an emergency fallback used only when the cache
# is empty (tests, cold start, Notion unreachable). Keep it lean — Notion is
# the source of truth in production.
OFFICE_TEAM_MEMBERS = [
    "Salomé Cremona",
    "Salome Cremona",
    "Luana Debusschere",
    "Diane De Magnitot",
    "Vincent Dasilva",
    "Vincent Da Silva",
    "Taddeo Carpinelli",
]

# Sous-Groupe value that flags an office row in the Team DB.
TEAM_OFFICE_GROUP_NAME = "BUREAU"

# Property names in the Team DB. Override here if you rename columns in Notion.
TEAM_PROP_NAME = "Nom"
TEAM_PROP_EMAIL = "email"
TEAM_PROP_GROUP = "Sous-Groupe"


def normalize_display_name_for_office_match(name: str) -> str:
    """Aggressive normalization for office-name matching.

    Strips accents, removes all whitespace, lowercases. Lets directory variants
    like `Vincent Da Silva` / `Vincent Dasilva` and `Salomé Crémona` /
    `Salome Cremona` match the same canonical form.
    """
    if not name or not str(name).strip():
        return ""
    s = unicodedata.normalize("NFKD", str(name).strip())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return "".join(s.split()).lower()


def _normalize_email(email: str) -> str:
    """Strip + lowercase. Empty string for falsy input or non-email strings."""
    if not email:
        return ""
    e = str(email).strip().lower()
    if "@" not in e:
        return ""
    return e


# Team cache populated by load_team_members_from_notion().
# Shape: {"office_emails": set[str], "office_names": set[str],
#         "all_by_email": dict[str, dict], "loaded": bool}
_TEAM_CACHE: dict = {
    "office_emails": set(),
    "office_names": set(),
    "all_by_email": {},
    "loaded": False,
}


def _office_emails() -> set:
    """Normalized emails of office members (from Notion cache)."""
    return _TEAM_CACHE["office_emails"]


def _office_names_normalized() -> set:
    """Normalized office display names. Cache first, fallback to constant."""
    if _TEAM_CACHE["loaded"] and _TEAM_CACHE["office_names"]:
        return _TEAM_CACHE["office_names"]
    return {normalize_display_name_for_office_match(n) for n in OFFICE_TEAM_MEMBERS}


def is_office_team_email(email: str) -> bool:
    """True if email is in the Notion-loaded office set. Email-only path (primary)."""
    e = _normalize_email(email)
    if not e:
        return False
    return e in _office_emails()


def is_office_team_display_name(display_name: str) -> bool:
    """True if display name matches an office member.

    Uses Notion-loaded names when the cache is populated; otherwise falls back
    to the `OFFICE_TEAM_MEMBERS` constant. Matching is whitespace + accent +
    case insensitive (see `normalize_display_name_for_office_match`).
    """
    n = normalize_display_name_for_office_match(display_name)
    if not n:
        return False
    return n in _office_names_normalized()


def is_office_team_author(email: str = "", display_name: str = "") -> bool:
    """Email-first office check with name fallback.

    Use whenever both fields are available (e.g. `message.author`). For
    @mentions where only a name exists, call `is_office_team_display_name`.
    """
    if is_office_team_email(email):
        return True
    return is_office_team_display_name(display_name)

# Timezone configuration
PARIS_TIMEZONE = "Europe/Paris"

# Message filtering patterns
OFF_MARKERS_PATTERN = r'\(?\s*\boff\b\s*\)?'  # Case-insensitive regex for (OFF), off, (off), etc. with word boundaries
# ON caveat (French): bare word "on" is the pronoun. We match either:
#   - Parenthesized marker, any casing: (ON) (on) (oN) …
#   - Or bare ON in capitals only (not "on", not "oN").
ON_MARKERS_PATTERN = r'(?:\(\s*(?i:on)\s*\)|\bON\b)'
AVANT_MARKERS_PATTERN = r'\b(avant|before)\b'  # Case-insensitive, handles French "avant" and English "before"
APRES_MARKERS_PATTERN = r'\b(après|apres|after)\b'  # Case-insensitive, handles French "après/apres" and English "after"
# Standalone combined marker: "Avant/après", "before|after", etc. (single message + one wide collage image)
COMBINED_AVANT_APRES_PATTERN = re.compile(
    r'^\s*(?:avant\s*[/\\|]\s*(?:après|apres|arpès)|before\s*[/\\|]\s*after)\s*[:\-!.\s]*$',
    re.IGNORECASE,
)
# Minimum width/height ratio to treat a composite-marker image as side-by-side before/after
COMPOSITE_MIN_ASPECT_RATIO = 1.35
DATE_PATTERN = r'\b(\d{1,2})/(\d{1,2})\b'  # DD/MM format

# Utility Functions
def extract_space_id_from_url(chat_url: str) -> str:
    """
    Extract space ID from various Google Chat URL formats.

    Supported formats:
    - https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A
    - https://chat.google.com/room/AAAAAXFFz5A
    - spaces/AAAAAXFFz5A
    - AAAAAXFFz5A

    Returns: spaces/XXXXXX format
    """
    if not chat_url:
        return ""

    # Already in correct format
    if chat_url.startswith("spaces/"):
        return chat_url

    # Extract from Gmail chat URL
    if "#chat/space/" in chat_url:
        space_id = chat_url.split("#chat/space/")[1].split("?")[0].split("/")[0]
        return f"spaces/{space_id}"

    # Extract from Google Chat room URL
    if "/room/" in chat_url:
        space_id = chat_url.split("/room/")[1].split("?")[0].split("/")[0]
        return f"spaces/{space_id}"

    # Assume it's just the space ID
    return f"spaces/{chat_url}"

# Client-to-Chat Space mapping (dynamically loaded)
CLIENT_CHAT_MAPPING = {}

def load_team_members_from_notion() -> dict:
    """Load the maintenance team directory from the Notion Team DB into the cache.

    Reads `TEAM_PROP_NAME` (title), `TEAM_PROP_EMAIL` (rich_text or email),
    and `TEAM_PROP_GROUP` (multi_select). Rows tagged with
    `TEAM_OFFICE_GROUP_NAME` (`BUREAU`) feed the office sets.

    Should be called once at startup (Streamlit + scanner). Idempotent:
    repopulates the cache on every call. Returns a snapshot of the cache
    (mostly useful for tests / debugging).

    Failures are logged and re-raised so the caller can surface them in the UI.
    """
    try:
        from src.notion.client import NotionClient

        client = NotionClient()
        db_id = get_notion_db_team()
        rows = client.query_database(db_id)

        office_emails: set = set()
        office_names: set = set()
        all_by_email: dict = {}

        for row in rows:
            props = row.get("properties", {}) or {}

            title_arr = (props.get(TEAM_PROP_NAME, {}) or {}).get("title", []) or []
            name = "".join(t.get("plain_text", "") for t in title_arr).strip()

            email_prop = props.get(TEAM_PROP_EMAIL, {}) or {}
            if "email" in email_prop:
                raw_email = email_prop.get("email") or ""
            else:
                rt = email_prop.get("rich_text", []) or []
                raw_email = "".join(t.get("plain_text", "") for t in rt).strip()
            email = _normalize_email(raw_email)

            group_arr = (props.get(TEAM_PROP_GROUP, {}) or {}).get("multi_select", []) or []
            groups = [(o.get("name") or "").strip().upper() for o in group_arr]
            is_office = TEAM_OFFICE_GROUP_NAME.upper() in groups

            if email:
                all_by_email[email] = {"name": name, "email": email, "groups": groups}

            if is_office:
                if email:
                    office_emails.add(email)
                if name:
                    office_names.add(normalize_display_name_for_office_match(name))

        _TEAM_CACHE["office_emails"] = office_emails
        _TEAM_CACHE["office_names"] = office_names
        _TEAM_CACHE["all_by_email"] = all_by_email
        _TEAM_CACHE["loaded"] = True

        print(
            f"👥 Team loaded from Notion: {len(all_by_email)} members, "
            f"{len(office_emails)} office emails, {len(office_names)} office names"
        )
        return {
            "office_emails": set(office_emails),
            "office_names": set(office_names),
            "all_by_email": dict(all_by_email),
            "loaded": True,
        }
    except Exception as e:
        import traceback
        error_details = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        raise Exception(f"Could not load team members from Notion: {error_details}") from e


def load_clients_from_notion():
    """
    Dynamically load client-to-chat mappings from Clients Notion DB.
    This should be called on application startup.

    Raises exceptions instead of silently returning empty dict to allow
    proper error handling in the calling code.
    """
    try:
        from src.notion.database import NotionDatabaseManager

        # Debug: Check if we can access secrets
        try:
            import streamlit as st
            api_key = get_notion_api_key()
            db_id = get_notion_db_clients()

            # Log debug info (without exposing sensitive data)
            if hasattr(st, 'session_state'):
                if 'notion_debug' not in st.session_state:
                    st.session_state.notion_debug = {}
                st.session_state.notion_debug['api_key_present'] = api_key is not None and len(api_key) > 0
                st.session_state.notion_debug['db_id'] = db_id[:8] + "..." if db_id else "None"
        except (ImportError, AttributeError):
            # Not in Streamlit context, skip debug logging
            pass

        db_manager = NotionDatabaseManager()
        global CLIENT_CHAT_MAPPING
        CLIENT_CHAT_MAPPING = db_manager.get_all_clients_mapping()
        return CLIENT_CHAT_MAPPING
    except Exception as e:
        # Re-raise the exception so it can be handled by the caller
        # This allows main.py to display the error in Streamlit UI
        import traceback
        error_details = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        raise Exception(f"Could not load clients from Notion: {error_details}") from e
