import config
from src.notion.client import NotionClient

try:
    client = NotionClient()
    db_id = config.NOTION_DB_CLIENTS
    print(f"Querying DB ID: {db_id}")
    results = client.query_database(db_id)
    print(f"Found {len(results)} clients")
    if results:
        first_client = results[0]
        print("Properties of first client:")
        for prop_name, prop_data in first_client.get('properties', {}).items():
            print(f"  - '{prop_name}': {prop_data.get('type')}")
except Exception as e:
    print(f"Error: {e}")
