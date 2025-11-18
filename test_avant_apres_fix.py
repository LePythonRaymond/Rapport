#!/usr/bin/env python3
"""
Test script to verify that "avant" in regular text doesn't trigger AVANT section.
"""

from datetime import datetime, timezone, timedelta
import pytz
from src.utils.data_extractor import group_messages_by_intervention

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

def test_avant_in_sentence_not_marker():
    """Test that 'avant' in a regular sentence doesn't trigger AVANT section."""
    print("\n=== Testing 'avant' in Regular Text ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # This matches the user's scenario
    messages = [
        # Regular message with "avant" in a sentence (NOT a marker)
        create_test_message(
            "3 mini sujet remplacé! 3 grands sujets remplacé! Attendre 1/2 semaines avant de les arroser",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date,
            [
                {'contentType': 'image/jpeg', 'name': 'regular1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'regular2.jpg'}
            ]
        ),
        # Actual AVANT marker message
        create_test_message(
            "Avant",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date + timedelta(minutes=5),
            [
                {'contentType': 'image/jpeg', 'name': 'avant1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant2.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant3.jpg'}
            ]
        ),
        # APRÈS marker message
        create_test_message(
            "Après",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date + timedelta(minutes=10),
            [
                {'contentType': 'image/jpeg', 'name': 'apres1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'apres2.jpg'},
                {'contentType': 'image/jpeg', 'name': 'apres3.jpg'}
            ]
        )
    ]

    interventions = group_messages_by_intervention(messages)

    print(f"   Total messages: {len(messages)}")
    print(f"   Interventions: {len(interventions)} (expected 1)")

    if interventions:
        intervention = interventions[0]
        regular_count = len(intervention.get('regular_images', []))
        avant_count = len(intervention.get('avant_images', []))
        apres_count = len(intervention.get('apres_images', []))

        print(f"   Regular images: {regular_count} (expected 2)")
        print(f"   AVANT images: {avant_count} (expected 3)")
        print(f"   APRÈS images: {apres_count} (expected 3)")
        print(f"   Has AVANT/APRÈS: {intervention.get('has_avant_apres', False)}")

        # List image names for debugging
        print(f"\n   Regular image names: {[img.get('name') for img in intervention.get('regular_images', [])]}")
        print(f"   AVANT image names: {[img.get('name') for img in intervention.get('avant_images', [])]}")
        print(f"   APRÈS image names: {[img.get('name') for img in intervention.get('apres_images', [])]}")

        # Verify the "avant de les arroser" text is included in regular_text
        regular_text = intervention.get('all_text', '')
        has_sentence_text = 'avant de les arroser' in regular_text.lower()
        print(f"   Regular text contains 'avant de les arroser': {has_sentence_text}")

        # Verify counts
        success = (len(interventions) == 1 and
                  regular_count == 2 and
                  avant_count == 3 and
                  apres_count == 3 and
                  intervention.get('has_avant_apres', False) and
                  has_sentence_text)

        print(f"\n   {'✅ PASSED' if success else '❌ FAILED'}: Images correctly categorized and text preserved\n")
        return success
    else:
        print(f"\n   ❌ FAILED: No intervention created\n")
        return False

def test_pure_avant_marker():
    """Test various forms of pure AVANT/APRÈS markers."""
    print("\n=== Testing Pure Marker Detection ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    test_cases = [
        ("Avant", True, "bare marker"),
        ("AVANT", True, "uppercase"),
        ("Avant:", True, "with colon"),
        ("Avant !", True, "with exclamation"),
        ("avant", True, "lowercase"),
        ("Avant de faire X", False, "in sentence"),
        ("Il faut le faire avant", False, "at end of sentence"),
        ("Attendre avant de continuer", False, "middle of sentence"),
    ]

    all_passed = True
    for marker_text, should_detect, description in test_cases:
        messages = [
            create_test_message(
                "Regular text",
                "nicolas@example.com", "Nicolas Cintrat",
                base_date,
                [{'contentType': 'image/jpeg', 'name': 'regular1.jpg'}]
            ),
            create_test_message(
                marker_text,
                "nicolas@example.com", "Nicolas Cintrat",
                base_date + timedelta(minutes=5),
                [{'contentType': 'image/jpeg', 'name': 'avant1.jpg'}]
            )
        ]

        interventions = group_messages_by_intervention(messages)
        if interventions:
            has_avant_apres = interventions[0].get('has_avant_apres', False)
            passed = (has_avant_apres == should_detect)
            status = '✅' if passed else '❌'
            print(f"   {status} '{marker_text}' ({description}): detected={has_avant_apres}, expected={should_detect}")
            all_passed = all_passed and passed
        else:
            print(f"   ❌ No intervention for '{marker_text}'")
            all_passed = False

    print(f"\n   {'✅ ALL PASSED' if all_passed else '❌ SOME FAILED'}\n")
    return all_passed

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING AVANT/APRÈS MARKER DETECTION FIX")
    print("=" * 60)

    try:
        test1_passed = test_avant_in_sentence_not_marker()
        test2_passed = test_pure_avant_marker()

        print("\n" + "=" * 60)
        if test1_passed and test2_passed:
            print("✅ All tests PASSED!")
        else:
            print("❌ Some tests FAILED!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
