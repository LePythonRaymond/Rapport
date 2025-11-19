import os
import json
from dotenv import load_dotenv

load_dotenv()

def _get_secret(key: str) -> str:
    """
    Get a secret value, checking Streamlit secrets first (for Streamlit Cloud),
    then falling back to environment variables (for local development).

    Args:
        key: The secret key to retrieve

    Returns:
        The secret value, or None if not found
    """
    # Try to access Streamlit secrets (for Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                if key in st.secrets:
                    return st.secrets[key]
            except Exception:
                # Handle StreamlitSecretNotFoundError or any other error
                # when accessing secrets (e.g., no secrets.toml file in local dev)
                pass
    except (ImportError, AttributeError, RuntimeError):
        # Streamlit not available or not in Streamlit context
        pass

    # Fallback to environment variable (for local development)
    return os.getenv(key)

# API Keys
NOTION_API_KEY = _get_secret("NOTION_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")

# Google OAuth Credentials handling
# For Streamlit Cloud: Store credentials.json content in GOOGLE_CREDENTIALS_JSON secret
# For local: Use GOOGLE_CREDENTIALS_PATH pointing to credentials.json file
def _setup_google_credentials():
    """
    Setup Google credentials file from environment variable or file path.
    Supports both local development (file path) and Streamlit Cloud (JSON content).
    """
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
            return credentials_path
        except json.JSONDecodeError:
            raise ValueError("GOOGLE_CREDENTIALS_JSON is not valid JSON")

    # Fallback to file path (local development)
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    if os.path.exists(credentials_path):
        return credentials_path

    # If neither exists, return None (will raise error in auth.py)
    return None

GOOGLE_CREDENTIALS_PATH = _setup_google_credentials()

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
NOTION_DB_CLIENTS_DEFAULT ="285d9278-02d7-809d-bf44-d2112b6fcad0"
NOTION_DB_RAPPORTS_DEFAULT ="293d9278-02d7-801c-a1b3-cf6d7dbadf84"
NOTION_DB_INTERVENTIONS_DEFAULT ="286d9278-02d7-8097-8539-fa6f88aa0ecf"

# Get database IDs from secrets/env vars, fallback to hardcoded defaults
# Ensure we convert to string and handle None values
NOTION_DB_CLIENTS = _format_database_id(
    str(_get_secret("NOTION_DATABASE_ID_CLIENTS") or NOTION_DB_CLIENTS_DEFAULT)
)
NOTION_DB_RAPPORTS = _format_database_id(
    str(_get_secret("NOTION_DATABASE_ID_RAPPORTS") or NOTION_DB_RAPPORTS_DEFAULT)
)
NOTION_DB_INTERVENTIONS = _format_database_id(
    str(_get_secret("NOTION_DATABASE_ID_INTERVENTIONS") or NOTION_DB_INTERVENTIONS_DEFAULT)
)

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
    """
    try:
        from src.notion.database import NotionDatabaseManager
        db_manager = NotionDatabaseManager()
        global CLIENT_CHAT_MAPPING
        CLIENT_CHAT_MAPPING = db_manager.get_all_clients_mapping()
        return CLIENT_CHAT_MAPPING
    except Exception as e:
        print(f"Warning: Could not load clients from Notion: {e}")
        return {}
