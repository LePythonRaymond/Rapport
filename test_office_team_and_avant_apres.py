#!/usr/bin/env python3
"""
Test script for office team exclusion and AVANT/APRÈS image categorization.
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

def test_office_team_exclusion():
    """Test that office team members' messages are excluded from interventions."""
    print("\n=== Testing Office Team Exclusion ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    messages = [
        # Gardener message
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date,
            [{'contentType': 'image/jpeg', 'name': 'photo1.jpg'}]
        ),
        # Office team member message (should be excluded)
        create_test_message(
            "Salomé - message administratif",
            "salome@example.com", "Salomé Cremona",
            base_date + timedelta(hours=1),
            [{'contentType': 'image/jpeg', 'name': 'photo2.jpg'}]
        ),
        # Another office team member (should be excluded)
        create_test_message(
            "Luana - information bureau",
            "luana@example.com", "Luana Debusschere",
            base_date + timedelta(hours=2),
            []
        ),
        # Another gardener message
        create_test_message(
            "Désherbage terminé",
            "nicolas@example.com", "Nicolas Dupont",
            base_date + timedelta(hours=3),
            []
        )
    ]

    interventions = group_messages_by_intervention(messages)

    print(f"   Total messages: {len(messages)}")
    print(f"   Interventions created: {len(interventions)} (expected 2)")

    for i, intervention in enumerate(interventions):
        print(f"   Intervention {i+1}: {intervention['author_name']}")

    # Should only have 2 interventions (Edward and Nicolas, not Salomé or Luana)
    success = (len(interventions) == 2 and
              all(name not in ['Salomé Cremona', 'Luana Debusschere']
                  for name in [inv['author_name'] for inv in interventions]))

    print(f"\n   {'✅ PASSED' if success else '❌ FAILED'}: Office team members excluded from interventions\n")
    return success

def test_avant_apres_categorization():
    """Test that AVANT/APRÈS images are correctly categorized."""
    print("\n=== Testing AVANT/APRÈS Image Categorization ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Scenario: Regular images, then AVANT with images, then APRÈS with images
    messages = [
        # Regular message with images
        create_test_message(
            "3 mini sujet remplacé! 3 grands sujets remplacé!",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date,
            [
                {'contentType': 'image/jpeg', 'name': 'regular1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'regular2.jpg'}
            ]
        ),
        # AVANT message with images
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
        # APRÈS message with images
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
        print(f"   Total images: {len(intervention.get('images', []))}")
        print(f"   Regular images: {len(intervention.get('regular_images', []))}")
        print(f"   AVANT images: {len(intervention.get('avant_images', []))}")
        print(f"   APRÈS images: {len(intervention.get('apres_images', []))}")
        print(f"   Has AVANT/APRÈS: {intervention.get('has_avant_apres', False)}")

        # Verify counts
        success = (len(interventions) == 1 and
                  len(intervention.get('regular_images', [])) == 2 and
                  len(intervention.get('avant_images', [])) == 3 and
                  len(intervention.get('apres_images', [])) == 3 and
                  intervention.get('has_avant_apres', False))

        print(f"\n   {'✅ PASSED' if success else '❌ FAILED'}: Images correctly categorized\n")
        return success
    else:
        print(f"\n   ❌ FAILED: No intervention created\n")
        return False

def test_only_avant_apres_no_regular():
    """Test AVANT/APRÈS when there are no regular images."""
    print("\n=== Testing AVANT/APRÈS Without Regular Images ===\n")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Scenario: Only AVANT and APRÈS, no regular images
    messages = [
        # Text only
        create_test_message(
            "Remplacement effectué",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date,
            []
        ),
        # AVANT with images
        create_test_message(
            "Avant",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date + timedelta(minutes=5),
            [{'contentType': 'image/jpeg', 'name': 'avant1.jpg'}]
        ),
        # APRÈS with images
        create_test_message(
            "Après",
            "nicolas@example.com", "Nicolas Cintrat",
            base_date + timedelta(minutes=10),
            [{'contentType': 'image/jpeg', 'name': 'apres1.jpg'}]
        )
    ]

    interventions = group_messages_by_intervention(messages)

    if interventions:
        intervention = interventions[0]
        print(f"   Regular images: {len(intervention.get('regular_images', []))} (expected 0)")
        print(f"   AVANT images: {len(intervention.get('avant_images', []))} (expected 1)")
        print(f"   APRÈS images: {len(intervention.get('apres_images', []))} (expected 1)")

        success = (len(intervention.get('regular_images', [])) == 0 and
                  len(intervention.get('avant_images', [])) == 1 and
                  len(intervention.get('apres_images', [])) == 1)

        print(f"\n   {'✅ PASSED' if success else '❌ FAILED'}: Only AVANT/APRÈS, no regular images\n")
        return success
    else:
        print(f"\n   ❌ FAILED: No intervention created\n")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING OFFICE TEAM EXCLUSION & AVANT/APRÈS")
    print("=" * 60)

    try:
        test1_passed = test_office_team_exclusion()
        test2_passed = test_avant_apres_categorization()
        test3_passed = test_only_avant_apres_no_regular()

        print("\n" + "=" * 60)
        if test1_passed and test2_passed and test3_passed:
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
