import os
import json
from dotenv import load_dotenv

load_dotenv()

def _get_secret(key: str) -> str:
    """
    Get a secret value from Streamlit secrets or environment variables.
    Tries st.secrets first (Streamlit Cloud), then falls back to os.getenv() (local development).

    Args:
        key: The secret key to retrieve

    Returns:
        The secret value or None if not found
    """
    try:
        # Try to import streamlit and access secrets (works in Streamlit Cloud)
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                # Access secrets like a dictionary
                if key in st.secrets:
                    return st.secrets[key]
            except (AttributeError, RuntimeError, KeyError, TypeError):
                # st.secrets exists but key not found or not accessible, continue to fallback
                pass
    except (ImportError, AttributeError, RuntimeError):
        # Not in Streamlit context or streamlit not available, fall back to os.getenv
        pass

    # Fallback to environment variables (for local development)
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
    # Check if credentials JSON is provided as secret (Streamlit Cloud) or env var
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
    credentials_path = _get_secret("GOOGLE_CREDENTIALS_PATH") or "credentials.json"
    if os.path.exists(credentials_path):
        return credentials_path

    # If neither exists, return None (will raise error in auth.py)
    return None

GOOGLE_CREDENTIALS_PATH = _setup_google_credentials()

def _format_database_id(db_id: str) -> str:
    """
    Format Notion database ID for API calls.
    Removes dashes from database IDs as required by Notion API.

    Args:
        db_id: Database ID (with or without dashes)

    Returns:
        Database ID without dashes for API calls
    """
    if not db_id:
        return ""
    return db_id.replace('-', '')

# Notion Database IDs (with automatic dash removal)
# Uses st.secrets in Streamlit Cloud, falls back to os.getenv() for local development
NOTION_DB_CLIENTS = _format_database_id(_get_secret("NOTION_DATABASE_ID_CLIENTS"))
NOTION_DB_RAPPORTS = _format_database_id(_get_secret("NOTION_DATABASE_ID_RAPPORTS"))
NOTION_DB_INTERVENTIONS = _format_database_id(_get_secret("NOTION_DATABASE_ID_INTERVENTIONS"))

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
    # Check required environment variables first
    if not NOTION_API_KEY:
        raise ValueError(
            "NOTION_API_KEY environment variable is not set. "
            "Please set it in Streamlit Cloud secrets or your .env file."
        )

    if not NOTION_DB_CLIENTS:
        raise ValueError(
            "NOTION_DATABASE_ID_CLIENTS environment variable is not set. "
            "Please set it in Streamlit Cloud secrets or your .env file."
        )

    try:
        from src.notion.database import NotionDatabaseManager
        db_manager = NotionDatabaseManager()
        global CLIENT_CHAT_MAPPING
        CLIENT_CHAT_MAPPING = db_manager.get_all_clients_mapping()
        return CLIENT_CHAT_MAPPING
    except ValueError as e:
        # Re-raise ValueError (from environment variable checks)
        raise
    except Exception as e:
        error_msg = f"Could not load clients from Notion: {e}"
        print(f"Warning: {error_msg}")
        raise RuntimeError(error_msg) from e
