#!/usr/bin/env python3
"""
Test script for @mention extraction in intervention messages.
"""

from datetime import datetime, timezone
from src.utils.data_extractor import extract_mentions_from_text, extract_team_members

def test_mention_extraction():
    """Test extracting @mentions from message text."""
    print("\n=== Testing @Mention Extraction ===\n")

    test_cases = [
        # (input_text, expected_mentions)
        ("En binôme avec @Alice MARTIN", ["Alice MARTIN"]),
        ("Travail avec @Jean-Pierre DUPONT", ["Jean-Pierre DUPONT"]),
        ("@Marie Louise BERNARD et @Paul LECLERC ont fait le travail", ["Marie Louise BERNARD", "Paul LECLERC"]),
        ("Pas de mention dans ce texte", []),
        ("Email test@example.com ne doit pas être capturé", []),
        ("@Edward CAREY a fait la taille", ["Edward CAREY"]),
    ]

    all_passed = True

    for text, expected_mentions in test_cases:
        result = extract_mentions_from_text(text)
        passed = result == expected_mentions

        status = "✅" if passed else "❌"
        print(f"{status} Text: '{text}'")
        print(f"   Expected: {expected_mentions}")
        print(f"   Got:      {result}")

        if not passed:
            all_passed = False
            print("   FAILED!")
        print()

    return all_passed

def test_team_member_extraction_with_mentions():
    """Test that team members include both authors and mentioned people."""
    print("\n=== Testing Team Member Extraction with Mentions ===\n")

    # Create test messages
    messages = [
        {
            'author': {
                'name': 'Edward Carey',
                'email': 'edward@example.com'
            },
            'text': 'Pas d\'accès aujourd\'hui à R+11 (réunion).. Donc à faire lors du prochain passage.',
            'createTime': datetime.now(timezone.utc).isoformat()
        },
        {
            'author': {
                'name': 'Edward Carey',
                'email': 'edward@example.com'
            },
            'text': 'En binôme avec @Alice MARTIN',
            'createTime': datetime.now(timezone.utc).isoformat()
        }
    ]

    team_members = extract_team_members(messages)

    print(f"Extracted {len(team_members)} team member(s):\n")
    for member in team_members:
        print(f"  - {member['name']}" + (f" ({member['email']})" if member['email'] else " (mentioned)"))

    # Check that we have both Edward (author) and Alice (mentioned)
    names = [member['name'] for member in team_members]

    has_edward = any('Edward' in name and 'Carey' in name for name in names)
    has_alice = any('Alice' in name and 'Martin' in name for name in names)

    print(f"\n✅ Found Edward Carey (author): {has_edward}")
    print(f"✅ Found Alice Martin (mentioned): {has_alice}")

    success = has_edward and has_alice and len(team_members) == 2

    if success:
        print("\n✅ Team member extraction with mentions test PASSED!")
    else:
        print("\n❌ Team member extraction with mentions test FAILED!")

    return success

def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING @MENTION EXTRACTION")
    print("=" * 60)

    try:
        test1_passed = test_mention_extraction()
        test2_passed = test_team_member_extraction_with_mentions()

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
