import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
NOTION_DB_CLIENTS = _format_database_id(os.getenv("NOTION_DATABASE_ID_CLIENTS"))
NOTION_DB_RAPPORTS = _format_database_id(os.getenv("NOTION_DATABASE_ID_RAPPORTS"))
NOTION_DB_INTERVENTIONS = _format_database_id(os.getenv("NOTION_DATABASE_ID_INTERVENTIONS"))

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
