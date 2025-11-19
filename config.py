import os
import json
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

# AI Model settings
AI_MODEL = "gpt-4.1-mini"
AI_TEMPERATURE = 0.3

# Report assets
REPORT_COVER_IMAGE_PATH = "Image_Rapport.jpeg"
REPORT_ICON_IMAGE_PATH = "/Users/taddeocarpinelli/Desktop/MERCI RAYMOND/Rapport_2/logo_MR_copie.webp"

# Office team members to exclude from gardener lists
OFFICE_TEAM_MEMBERS = ["Salomé Cremona", "Luana Debusschere","salome cremona","luana debusschere"]

# Timezone configuration
PARIS_TIMEZONE = "Europe/Paris"

# Message filtering patterns
OFF_MARKERS_PATTERN = r'\(?\s*\boff\b\s*\)?'  # Case-insensitive regex for (OFF), off, (off), etc. with word boundaries
AVANT_MARKERS_PATTERN = r'\b(avant|AVANT|Avant)\b'
APRES_MARKERS_PATTERN = r'\b(après|apres|APRÈS|APRES|Apres|Après)\b'
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
