#!/usr/bin/env python3
"""
Test script for handling image-only messages in interventions.
"""

from datetime import datetime, timezone, timedelta
import pytz
from src.utils.data_extractor import group_messages_by_intervention, extract_images_from_message

def create_test_message(text: str, author_email: str, author_name: str,
                       create_time: datetime, attachments: list = None) -> dict:
    """Helper to create a test message."""
    return {
        'text': text,
        'author': {
            'email': author_email,
            'name': author_name
        },
        'createTime': create_time.isoformat(),
        'attachments': attachments or []
    }

def test_image_only_messages():
    """Test that image-only messages are captured in interventions."""
    print("\n=== Testing Image-Only Messages ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Scenario 1: Image only, then text later
    print("📋 Scenario 1: Image-only message, then text")
    messages_scenario1 = [
        create_test_message(
            "",  # No text, only images
            "edward@example.com", "Edward Carey",
            base_date,
            [
                {'contentType': 'image/jpeg', 'name': 'photo1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'photo2.jpg'}
            ]
        ),
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=30),
            []
        )
    ]

    interventions1 = group_messages_by_intervention(messages_scenario1)
    print(f"   Messages: {len(messages_scenario1)}")
    print(f"   Interventions: {len(interventions1)}")
    if interventions1:
        print(f"   Images in intervention: {len(interventions1[0]['images'])}")
        print(f"   Text in intervention: '{interventions1[0]['all_text']}'")

    success1 = (len(interventions1) == 1 and
                len(interventions1[0]['images']) == 2 and
                interventions1[0]['all_text'].strip() != '')
    print(f"   {'✅ PASSED' if success1 else '❌ FAILED'}: Images and text grouped together\n")

    # Scenario 2: Text with images attached
    print("📋 Scenario 2: Text with images attached")
    messages_scenario2 = [
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date,
            [
                {'contentType': 'image/jpeg', 'name': 'photo1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'photo2.jpg'}
            ]
        )
    ]

    interventions2 = group_messages_by_intervention(messages_scenario2)
    print(f"   Messages: {len(messages_scenario2)}")
    print(f"   Interventions: {len(interventions2)}")
    if interventions2:
        print(f"   Images in intervention: {len(interventions2[0]['images'])}")
        print(f"   Text in intervention: '{interventions2[0]['all_text']}'")

    success2 = (len(interventions2) == 1 and
                len(interventions2[0]['images']) == 2 and
                interventions2[0]['all_text'].strip() != '')
    print(f"   {'✅ PASSED' if success2 else '❌ FAILED'}: Text and images captured\n")

    # Scenario 3: Text, then images later
    print("📋 Scenario 3: Text, then images in later message")
    messages_scenario3 = [
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date,
            []
        ),
        create_test_message(
            "",  # No text, only images
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=30),
            [
                {'contentType': 'image/jpeg', 'name': 'photo1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'photo2.jpg'}
            ]
        )
    ]

    interventions3 = group_messages_by_intervention(messages_scenario3)
    print(f"   Messages: {len(messages_scenario3)}")
    print(f"   Interventions: {len(interventions3)}")
    if interventions3:
        print(f"   Images in intervention: {len(interventions3[0]['images'])}")
        print(f"   Text in intervention: '{interventions3[0]['all_text']}'")

    success3 = (len(interventions3) == 1 and
                len(interventions3[0]['images']) == 2 and
                interventions3[0]['all_text'].strip() != '')
    print(f"   {'✅ PASSED' if success3 else '❌ FAILED'}: Text and images grouped together\n")

    # Scenario 4: Multiple image-only messages
    print("📋 Scenario 4: Multiple image-only messages")
    messages_scenario4 = [
        create_test_message(
            "",  # No text
            "edward@example.com", "Edward Carey",
            base_date,
            [{'contentType': 'image/jpeg', 'name': 'photo1.jpg'}]
        ),
        create_test_message(
            "",  # No text
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=10),
            [{'contentType': 'image/jpeg', 'name': 'photo2.jpg'}]
        ),
        create_test_message(
            "Voilà les photos",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=20),
            []
        )
    ]

    interventions4 = group_messages_by_intervention(messages_scenario4)
    print(f"   Messages: {len(messages_scenario4)}")
    print(f"   Interventions: {len(interventions4)}")
    if interventions4:
        print(f"   Images in intervention: {len(interventions4[0]['images'])}")
        print(f"   Text in intervention: '{interventions4[0]['all_text']}'")

    success4 = (len(interventions4) == 1 and
                len(interventions4[0]['images']) == 2 and
                interventions4[0]['all_text'].strip() != '')
    print(f"   {'✅ PASSED' if success4 else '❌ FAILED'}: Multiple images grouped with text\n")

    return success1 and success2 and success3 and success4

def test_extract_images():
    """Test that extract_images_from_message works correctly."""
    print("\n=== Testing Image Extraction ===\n")

    # Message with images
    message_with_images = {
        'text': 'Some text',
        'attachments': [
            {'contentType': 'image/jpeg', 'name': 'photo1.jpg'},
            {'contentType': 'image/png', 'name': 'photo2.png'},
            {'contentType': 'application/pdf', 'name': 'doc.pdf'}  # Should be ignored
        ]
    }

    images = extract_images_from_message(message_with_images)
    print(f"   Message with 2 images + 1 PDF")
    print(f"   Extracted {len(images)} image(s) (expected 2)")

    success = len(images) == 2
    print(f"   {'✅ PASSED' if success else '❌ FAILED'}: Only images extracted, PDF ignored\n")

    return success

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING IMAGE-ONLY MESSAGES")
    print("=" * 60)

    try:
        test1_passed = test_extract_images()
        test2_passed = test_image_only_messages()

        print("\n" + "=" * 60)
        if test1_passed and test2_passed:
            print("✅ All tests PASSED!")
            print("Image-only messages are now properly captured!")
        else:
            print("❌ Some tests FAILED!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
