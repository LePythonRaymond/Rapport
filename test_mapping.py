import config
from src.notion.database import NotionDatabaseManager

try:
    db_manager = NotionDatabaseManager()
    mapping = db_manager.get_all_clients_mapping()
    print(f"Successfully mapped {len(mapping)} clients.")
    if mapping:
        print("Sample mappings:")
        for k, v in list(mapping.items())[:5]:
            print(f"  {k} -> {v}")
except Exception as e:
    print(f"Error: {e}")
