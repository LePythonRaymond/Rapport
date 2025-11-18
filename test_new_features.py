#!/usr/bin/env python3
"""
Test script for new intervention grouping and filtering features.
Tests OFF rule filtering, AVANT/APRÈS detection, date extraction, and same-day grouping.
"""

import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import pytz

# Import the functions we want to test
from src.utils.data_extractor import (
    split_message_text_at_off,
    apply_off_rule_filtering,
    extract_date_from_text,
    detect_avant_apres_sections,
    group_messages_by_intervention,
    extract_date_from_message
)
import config

def create_test_message(text: str, author_email: str, author_name: str,
                       create_time: datetime, attachments: List[Dict] = None) -> Dict[str, Any]:
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

def test_off_rule_splitting():
    """Test the split_message_text_at_off function."""
    print("\n=== Testing OFF Rule Text Splitting ===")

    test_cases = [
        ("Normal text with no marker", "Normal text with no marker", False),
        ("Some text (OFF) private stuff", "Some text", True),
        ("Text with off in middle", "Text with", True),
        ("(off) everything is private", "", True),
        ("OFF at the start", "", True),
    ]

    for input_text, expected_text, expected_has_off in test_cases:
        result_text, has_off = split_message_text_at_off(input_text)
        success = result_text == expected_text and has_off == expected_has_off
        status = "✅" if success else "❌"
        print(f"{status} Input: '{input_text[:50]}...'")
        print(f"   Expected: ('{expected_text}', {expected_has_off})")
        print(f"   Got:      ('{result_text}', {has_off})")
        if not success:
            print("   FAILED!")

def test_date_extraction():
    """Test the extract_date_from_text function."""
    print("\n=== Testing Date Extraction ===")

    test_cases = [
        ("Intervention du 06/12 effectuée", 6, 12, True),
        ("Le 1/3 nous avons fait le désherbage", 1, 3, True),
        ("Taille effectuée le 25/11", 25, 11, True),
        ("No date in this text", None, None, False),
        ("Invalid date 45/99", None, None, False),
    ]

    for text, expected_day, expected_month, expected_found in test_cases:
        day, month, found = extract_date_from_text(text)
        success = day == expected_day and month == expected_month and found == expected_found
        status = "✅" if success else "❌"
        print(f"{status} Text: '{text[:50]}...'")
        print(f"   Expected: ({expected_day}, {expected_month}, {expected_found})")
        print(f"   Got:      ({day}, {month}, {found})")
        if not success:
            print("   FAILED!")

def test_avant_apres_detection():
    """Test the detect_avant_apres_sections function."""
    print("\n=== Testing AVANT/APRÈS Detection ===")

    # Test case 1: Messages with AVANT and APRÈS markers
    messages = [
        {
            'text': 'Voici le travail effectué',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'regular1.jpg'}
            ]
        },
        {
            'text': 'AVANT la taille',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'avant1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant2.jpg'}
            ]
        },
        {
            'text': 'APRÈS la taille',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'apres1.jpg'}
            ]
        }
    ]

    result = detect_avant_apres_sections(messages)
    print(f"Has avant/après: {result['has_avant_apres']}")
    print(f"Regular images: {len(result['regular_images'])} (expected 1)")
    print(f"Avant images: {len(result['avant_images'])} (expected 2)")
    print(f"Après images: {len(result['apres_images'])} (expected 1)")

    success = (result['has_avant_apres'] and
              len(result['regular_images']) == 1 and
              len(result['avant_images']) == 2 and
              len(result['apres_images']) == 1)

    status = "✅" if success else "❌"
    print(f"{status} AVANT/APRÈS detection test")

def test_same_day_grouping():
    """Test same-day + same-author grouping with interrupted messages."""
    print("\n=== Testing Same-Day Grouping (with interruptions) ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create messages from same author on same day at different times
    # with another author's message in between
    messages = [
        create_test_message(
            "Message at 9am", "edward@example.com", "Edward Carey",
            base_date
        ),
        create_test_message(
            "Nicolas message", "nicolas@example.com", "Nicolas Dupont",
            base_date + timedelta(hours=1)
        ),
        create_test_message(
            "Message at 2pm", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=5)
        ),
        create_test_message(
            "Message at 5pm", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=8)
        ),
        # Same author, next day
        create_test_message(
            "Edward next day", "edward@example.com", "Edward Carey",
            base_date + timedelta(days=1)
        ),
    ]

    interventions = group_messages_by_intervention(messages)

    print(f"Total messages: {len(messages)}")
    print(f"Grouped into {len(interventions)} interventions (expected 3)")

    for i, intervention in enumerate(interventions):
        print(f"  Intervention {i+1}: {intervention['author_name']} - {len(intervention['messages'])} messages")
        for j, msg in enumerate(intervention['messages']):
            msg_time = extract_date_from_message(msg)
            print(f"    Message {j+1}: {msg_time.strftime('%H:%M') if msg_time else 'unknown'} - '{msg.get('text', '')[:50]}'")

    # Should have 3 interventions:
    # 1. Edward (all 3 messages on day 1: 9am, 2pm, 5pm) - merged together despite Nicolas's interruption
    # 2. Nicolas (1 message on day 1)
    # 3. Edward (1 message on day 2)
    success = len(interventions) == 3
    if success:
        # Verify Edward's day 1 intervention has all 3 messages
        edward_day1 = None
        for intervention in interventions:
            if (intervention['author_name'] == 'Edward Carey' and
                intervention['intervention_day'] == base_date.date()):
                edward_day1 = intervention
                break
        if edward_day1:
            success = len(edward_day1['messages']) == 3
            print(f"  ✅ Edward's day 1 intervention correctly has 3 messages")
        else:
            success = False
            print(f"  ❌ Could not find Edward's day 1 intervention")

    status = "✅" if success else "❌"
    print(f"{status} Same-day grouping test (with interruptions)")

def test_off_rule_filtering():
    """Test OFF rule filtering across messages."""
    print("\n=== Testing OFF Rule Filtering ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create messages with OFF markers
    messages = [
        create_test_message(
            "First message is fine", "edward@example.com", "Edward Carey",
            base_date
        ),
        create_test_message(
            "Second message also fine", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=1)
        ),
        create_test_message(
            "This message has (OFF) in it and more text after",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=2)
        ),
        create_test_message(
            "This should be excluded", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=3)
        ),
        # Different author, same day - should not be affected
        create_test_message(
            "Nicolas message", "nicolas@example.com", "Nicolas Dupont",
            base_date + timedelta(hours=2, minutes=30)
        ),
    ]

    filtered = apply_off_rule_filtering(messages)

    print(f"Original messages: {len(messages)}")
    print(f"After filtering: {len(filtered)} (expected 4)")

    for msg in filtered:
        print(f"  - {msg['author']['name']}: '{msg['text'][:50]}...'")

    # Should have 4 messages:
    # 1. Edward's first message
    # 2. Edward's second message
    # 3. Edward's third message (split at OFF to keep only "This message has")
    # 4. Nicolas's message (not affected)
    # Edward's 4th message should be excluded
    expected_count = 4
    success = len(filtered) == expected_count
    status = "✅" if success else "❌"
    print(f"{status} OFF rule filtering test")

def test_full_pipeline():
    """Test the full pipeline integration."""
    print("\n=== Testing Full Pipeline Integration ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create realistic test messages
    messages = [
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date,
            [{'contentType': 'image/jpeg', 'name': 'before.jpg'}]
        ),
        create_test_message(
            "AVANT les travaux",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=30),
            [
                {'contentType': 'image/jpeg', 'name': 'avant1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant2.jpg'}
            ]
        ),
        create_test_message(
            "APRÈS les travaux",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=1),
            [
                {'contentType': 'image/jpeg', 'name': 'apres1.jpg'}
            ]
        ),
        create_test_message(
            "Tout est terminé (OFF) informations privées",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=2)
        ),
    ]

    # Apply full pipeline
    filtered = apply_off_rule_filtering(messages)
    interventions = group_messages_by_intervention(filtered)

    print(f"Original messages: {len(messages)}")
    print(f"After OFF filtering: {len(filtered)}")
    print(f"Interventions: {len(interventions)}")

    if interventions:
        intervention = interventions[0]
        print(f"\nIntervention details:")
        print(f"  Author: {intervention['author_name']}")
        print(f"  Messages: {len(intervention['messages'])}")
        print(f"  Has AVANT/APRÈS: {intervention.get('has_avant_apres', False)}")
        print(f"  Intervention date: {intervention.get('intervention_date')}")
        print(f"  Date source: {intervention.get('date_source')}")

        if intervention.get('has_avant_apres'):
            print(f"  Regular images: {len(intervention.get('regular_images', []))}")
            print(f"  AVANT images: {len(intervention.get('avant_images', []))}")
            print(f"  APRÈS images: {len(intervention.get('apres_images', []))}")

    success = (len(interventions) == 1 and
              interventions[0].get('has_avant_apres') == True and
              interventions[0].get('date_source') == 'extracted')

    status = "✅" if success else "❌"
    print(f"\n{status} Full pipeline test")

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING NEW INTERVENTION GROUPING FEATURES")
    print("=" * 60)

    try:
        test_off_rule_splitting()
        test_date_extraction()
        test_avant_apres_detection()
        test_same_day_grouping()
        test_off_rule_filtering()
        test_full_pipeline()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
