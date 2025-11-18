#!/usr/bin/env python3
"""
Test script to verify People API integration and user name resolution.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from google_chat.people_resolver import PeopleResolver
from google_chat.client import GoogleChatClient
from google_chat.auth import get_credentials

def test_credentials():
    """Test that credentials have the correct scopes."""
    print("=" * 60)
    print("Testing Credentials and Scopes")
    print("=" * 60)

    try:
        creds = get_credentials()
        print(f"✅ Credentials obtained successfully")
        print(f"Token valid: {creds.valid}")
        print(f"Has refresh token: {bool(creds.refresh_token)}")

        # Check scopes
        if hasattr(creds, 'scopes'):
            print(f"\nGranted scopes:")
            for scope in creds.scopes:
                print(f"  - {scope}")

            # Check if we have the People API scope
            people_scope = 'https://www.googleapis.com/auth/directory.readonly'
            if people_scope in creds.scopes:
                print(f"\n✅ People API scope is present!")
            else:
                print(f"\n⚠️ People API scope is MISSING!")
                print(f"   Required: {people_scope}")
                print(f"\n   You need to delete token.pickle and re-authenticate.")
        else:
            print("\n⚠️ Cannot check scopes (credentials object doesn't expose them)")

        return True
    except Exception as e:
        print(f"❌ Error getting credentials: {e}")
        return False

def test_people_resolver():
    """Test the People API resolver."""
    print("\n" + "=" * 60)
    print("Testing People API Resolver")
    print("=" * 60)

    try:
        resolver = PeopleResolver()
        print("✅ PeopleResolver initialized")

        # Test with a mock user ID (this will fail but we can see the error)
        test_user_id = "users/123456789"
        print(f"\nTesting resolution of: {test_user_id}")
        result = resolver.resolve_user_id(test_user_id)

        if result:
            print(f"✅ Resolved: {result.get('name')} ({result.get('email')})")
        else:
            print(f"⚠️ Could not resolve (this is expected if user doesn't exist)")

        # Show cache stats
        stats = resolver.get_cache_stats()
        print(f"\nCache stats: {stats}")

        return True
    except Exception as e:
        print(f"❌ Error initializing PeopleResolver: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_client():
    """Test the Google Chat client with People API integration."""
    print("\n" + "=" * 60)
    print("Testing Google Chat Client Integration")
    print("=" * 60)

    try:
        client = GoogleChatClient()
        print("✅ GoogleChatClient initialized")

        if client.people_resolver:
            print("✅ People API resolver is available in ChatClient")

            # Show cache stats
            stats = client.people_resolver.get_cache_stats()
            print(f"Cache stats: {stats}")
        else:
            print("⚠️ People API resolver is NOT available in ChatClient")

        return True
    except Exception as e:
        print(f"❌ Error initializing GoogleChatClient: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n🧪 PEOPLE API INTEGRATION TEST SUITE\n")

    results = []

    # Test 1: Credentials
    results.append(("Credentials", test_credentials()))

    # Test 2: People Resolver
    results.append(("People Resolver", test_people_resolver()))

    # Test 3: Chat Client Integration
    results.append(("Chat Client Integration", test_chat_client()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)

    if not all_passed:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        print("\nIf People API scope is missing, run:")
        print("  rm token.pickle")
        print("  python test_people_api.py")
        return 1
    else:
        print("\n✅ All tests passed!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
