#!/usr/bin/env python3
"""
Test script for the new Notion File Upload API implementation.
Tests both single and multiple image uploads.
"""

import sys
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO

# Import our modules
from src.notion.client import NotionClient
from src.utils.image_handler import ImageHandler
from src.google_chat.client import GoogleChatClient, get_messages_for_client
from src.utils.data_extractor import group_messages_by_intervention
from src.notion.database import NotionDatabaseManager
import config

def create_test_image(width=800, height=600, color=(100, 150, 200)) -> bytes:
    """Create a test image as bytes."""
    img = Image.new('RGB', (width, height), color=color)

    # Add some text to make it identifiable
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)

    # Draw some shapes to make it more realistic
    draw.rectangle([50, 50, width-50, height-50], outline=(255, 255, 255), width=5)
    draw.ellipse([width//4, height//4, 3*width//4, 3*height//4], fill=(200, 100, 150))

    # Convert to bytes
    output = BytesIO()
    img.save(output, format='JPEG', quality=85)
    return output.getvalue()

def test_single_image_upload():
    """Test uploading a single image using the new API."""
    print("\n" + "="*60)
    print("TEST 1: Single Image Upload via Notion File Upload API")
    print("="*60 + "\n")

    try:
        # Create Notion client
        notion_client = NotionClient()
        print("✅ Notion client initialized")

        # Create image handler
        image_handler = ImageHandler(notion_client=notion_client)
        print("✅ Image handler initialized")

        # Create a test image
        print("\n📸 Creating test image...")
        test_image_bytes = create_test_image(1200, 1600, color=(50, 100, 200))
        print(f"✅ Created test image: {len(test_image_bytes)} bytes")

        # Upload the image
        print("\n📤 Uploading image to Notion...")
        notion_url = image_handler.upload_image_to_notion(
            test_image_bytes,
            filename="test_upload_single.jpg"
        )

        if notion_url:
            print(f"\n✅ SUCCESS! Image uploaded to Notion")
            print(f"   URL: {notion_url[:80]}...")
            print(f"\n   This URL is now hosted by Notion and can be used in image blocks!")
            return True
        else:
            print("\n❌ FAILED: No URL returned from upload")
            return False

    except Exception as e:
        print(f"\n❌ ERROR during single image upload test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_images_from_google_chat():
    """Test the complete pipeline: Google Chat → Process → Upload to Notion."""
    print("\n" + "="*60)
    print("TEST 2: Multiple Images from Google Chat")
    print("="*60 + "\n")

    try:
        # Load clients from Notion
        print("📋 Loading clients from Notion...")
        config.load_clients_from_notion()
        available_clients = list(config.CLIENT_CHAT_MAPPING.keys())

        if not available_clients:
            print("❌ No clients found in Notion database")
            return False

        print(f"✅ Found {len(available_clients)} clients")
        print(f"   Available: {', '.join(available_clients)}")

        # Use the first client for testing
        test_client = available_clients[0]
        print(f"\n🎯 Testing with client: {test_client}")

        # Get recent messages (last 7 days)
        print("\n📥 Fetching recent messages from Google Chat...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        messages = get_messages_for_client(test_client, start_date, end_date)
        print(f"✅ Retrieved {len(messages)} messages")

        if not messages:
            print("⚠️  No messages found for this client in the last 7 days")
            return False

        # Group into interventions
        print("\n🔄 Grouping messages into interventions...")
        interventions = group_messages_by_intervention(messages)
        print(f"✅ Grouped into {len(interventions)} interventions")

        # Count images
        total_images = sum(len(intervention.get('images', [])) for intervention in interventions)
        print(f"📸 Found {total_images} total images in interventions")

        if total_images == 0:
            print("⚠️  No images found in messages")
            return False

        # Process images
        print(f"\n📤 Processing and uploading {total_images} images to Notion...")

        # Initialize components
        chat_client = GoogleChatClient()
        notion_client = NotionClient()
        db_manager = NotionDatabaseManager()
        image_handler = ImageHandler(chat_client.service, notion_client)

        space_id = config.CLIENT_CHAT_MAPPING[test_client]

        # Process images for each intervention
        uploaded_count = 0
        failed_count = 0

        for i, intervention in enumerate(interventions):
            print(f"\n  Intervention {i+1}/{len(interventions)}:")

            if not intervention.get('images'):
                print("    (no images)")
                continue

            notion_urls = []
            for img_info in intervention.get('images', []):
                try:
                    # Download from Google Chat
                    image_bytes = image_handler.download_image_from_chat(img_info, space_id)
                    if not image_bytes:
                        print(f"    ❌ Failed to download: {img_info.get('name', 'unknown')}")
                        failed_count += 1
                        continue

                    # Upload to Notion
                    filename = img_info.get('name', f"image_{uploaded_count}")
                    notion_url = image_handler.upload_image_to_notion(image_bytes, filename)

                    if notion_url:
                        notion_urls.append(notion_url)
                        uploaded_count += 1
                        print(f"    ✅ Uploaded: {filename}")
                    else:
                        print(f"    ❌ Failed to upload: {filename}")
                        failed_count += 1

                except Exception as e:
                    print(f"    ❌ Error processing image: {e}")
                    failed_count += 1

            # Store the Notion URLs in the intervention
            intervention['notion_images'] = notion_urls

        print(f"\n" + "="*60)
        print(f"RESULTS:")
        print(f"  ✅ Successfully uploaded: {uploaded_count} images")
        print(f"  ❌ Failed: {failed_count} images")
        print("="*60)

        if uploaded_count > 0:
            print("\n✅ SUCCESS! Multiple images uploaded successfully")
            print("   These images are now hosted by Notion and ready to use!")
            return True
        else:
            print("\n❌ FAILED: No images were uploaded")
            return False

    except Exception as e:
        print(f"\n❌ ERROR during multiple images test: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("NOTION FILE UPLOAD API - TEST SUITE")
    print("="*60)

    results = {}

    # Test 1: Single image upload
    results['single_upload'] = test_single_image_upload()

    # Test 2: Multiple images from Google Chat
    results['multiple_uploads'] = test_multiple_images_from_google_chat()

    # Summary
    print("\n" + "="*60)
    print("TEST SUITE SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe new Notion File Upload API implementation is working correctly.")
        print("You can now proceed with creating report pages with multiple images.")
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("\nPlease review the errors above and fix any issues before proceeding.")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

