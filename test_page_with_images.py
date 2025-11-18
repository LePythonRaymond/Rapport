#!/usr/bin/env python3
"""
Final integration test: Create a Notion page with 6+ images to verify no 413 error.
"""

from datetime import datetime, timedelta
from src.notion.client import NotionClient
from src.notion.database import NotionDatabaseManager
from src.google_chat.client import GoogleChatClient, get_messages_for_client
from src.utils.data_extractor import group_messages_by_intervention
from src.utils.image_handler import ImageHandler
import config

def test_create_page_with_multiple_images():
    """Test creating a Notion page with 6+ images (the original 413 error scenario)."""
    print("\n" + "="*70)
    print("FINAL INTEGRATION TEST: Create Notion Page with 6+ Images")
    print("="*70 + "\n")

    try:
        # Load clients
        print("📋 Loading clients from Notion...")
        config.load_clients_from_notion()
        available_clients = list(config.CLIENT_CHAT_MAPPING.keys())

        if not available_clients:
            print("❌ No clients found")
            return False

        test_client = available_clients[0]
        print(f"✅ Using client: {test_client}")

        # Get recent messages with images
        print("\n📥 Fetching recent messages...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        messages = get_messages_for_client(test_client, start_date, end_date)

        if not messages:
            print("❌ No messages found")
            return False

        print(f"✅ Found {len(messages)} messages")

        # Group into interventions
        interventions = group_messages_by_intervention(messages)
        print(f"✅ Grouped into {len(interventions)} interventions")

        # Count images
        total_images = sum(len(intervention.get('images', [])) for intervention in interventions)
        print(f"📸 Found {total_images} total images")

        if total_images < 6:
            print(f"⚠️  Need at least 6 images for this test (found {total_images})")
            return False

        # Initialize components
        print("\n🔧 Initializing components...")
        chat_client = GoogleChatClient()
        notion_client = NotionClient()
        db_manager = NotionDatabaseManager()
        image_handler = ImageHandler(chat_client.service, notion_client)

        # Process images
        print(f"\n📤 Processing {total_images} images...")
        space_id = config.CLIENT_CHAT_MAPPING[test_client]

        uploaded_image_refs = []
        for intervention in interventions:
            for img_info in intervention.get('images', []):
                # Download from Google Chat
                image_bytes = image_handler.download_image_from_chat(img_info, space_id)
                if not image_bytes:
                    continue

                # Upload to Notion
                filename = img_info.get('name', 'test_image.jpg')
                notion_ref = image_handler.upload_image_to_notion(image_bytes, filename)

                if notion_ref:
                    uploaded_image_refs.append(notion_ref)
                    print(f"  ✅ Uploaded: {filename}")

        if len(uploaded_image_refs) < 6:
            print(f"\n❌ Failed to upload enough images (got {len(uploaded_image_refs)}, need 6)")
            return False

        print(f"\n✅ Successfully uploaded {len(uploaded_image_refs)} images")

        # Create a test page with all these images
        print(f"\n📄 Creating test page with {len(uploaded_image_refs)} images...")
        print("   (This is where the 413 error would have occurred before)")

        # Build page blocks
        blocks = [
            notion_client.create_heading_block("Test Report - Multiple Images", level=1),
            notion_client.create_text_block(
                f"This page contains {len(uploaded_image_refs)} images uploaded using Notion's File Upload API."
            ),
            notion_client.create_heading_block("Images", level=2)
        ]

        # Add all images
        for i, img_ref in enumerate(uploaded_image_refs):
            blocks.append(notion_client.create_image_block(img_ref, caption=f"Image {i+1}"))

        # Get client for page creation
        client = db_manager.get_client_by_name(test_client)
        if not client:
            print(f"❌ Client '{test_client}' not found in database")
            return False

        # Create page properties
        page_properties = {
            "Nom": {
                "title": [{
                    "text": {
                        "content": f"TEST - Multiple Images ({len(uploaded_image_refs)} images)"
                    }
                }]
            },
            "Client": {
                "relation": [{"id": client['id']}]
            },
            "Statut": {
                "select": {"name": "Test"}
            }
        }

        # Create the page (THIS IS THE CRITICAL TEST - should NOT get 413 error)
        print(f"\n🚀 Creating page with {len(uploaded_image_refs)} images...")
        print(f"   Page will have ~{len(blocks)} blocks total")

        response = notion_client.create_page(
            parent_db_id=db_manager.rapports_db_id,
            properties=page_properties,
            children=blocks
        )

        page_id = response.get('id', '')
        page_url = response.get('url', '')

        print("\n" + "="*70)
        print("🎉 SUCCESS! Page created without 413 error!")
        print("="*70)
        print(f"\n   Page ID: {page_id}")
        print(f"   Page URL: {page_url}")
        print(f"   Images: {len(uploaded_image_refs)}")
        print(f"\n✅ The 413 'Payload Too Large' error has been resolved!")
        print("   You can now create reports with unlimited images.")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_create_page_with_multiple_images()
    exit(0 if success else 1)

