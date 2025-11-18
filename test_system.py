#!/usr/bin/env python3
"""
Test script for the MERCI RAYMOND report automation system.
This script tests all components individually and together.
"""

import sys
import os
from datetime import datetime, timedelta

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all modules can be imported."""
    print("🔍 Testing imports...")

    try:
        import config
        print("✅ config imported successfully")
    except Exception as e:
        print(f"❌ config import failed: {e}")
        return False

    try:
        from src.google_chat.auth import get_authenticated_service
        print("✅ Google Chat auth imported successfully")
    except Exception as e:
        print(f"❌ Google Chat auth import failed: {e}")
        return False

    try:
        from src.google_chat.client import GoogleChatClient
        print("✅ Google Chat client imported successfully")
    except Exception as e:
        print(f"❌ Google Chat client import failed: {e}")
        return False

    try:
        from src.utils.data_extractor import group_messages_by_intervention
        print("✅ Data extractor imported successfully")
    except Exception as e:
        print(f"❌ Data extractor import failed: {e}")
        return False

    try:
        from src.ai_processor.text_enhancer import TextEnhancer
        print("✅ Text enhancer imported successfully")
    except Exception as e:
        print(f"❌ Text enhancer import failed: {e}")
        return False

    try:
        from src.utils.image_handler import ImageHandler
        print("✅ Image handler imported successfully")
    except Exception as e:
        print(f"❌ Image handler import failed: {e}")
        return False

    try:
        from src.notion.client import NotionClient
        print("✅ Notion client imported successfully")
    except Exception as e:
        print(f"❌ Notion client import failed: {e}")
        return False

    try:
        from src.notion.database import NotionDatabaseManager
        print("✅ Notion database manager imported successfully")
    except Exception as e:
        print(f"❌ Notion database manager import failed: {e}")
        return False

    try:
        from src.notion.page_builder import ReportPageBuilder
        print("✅ Report page builder imported successfully")
    except Exception as e:
        print(f"❌ Report page builder import failed: {e}")
        return False

    print("✅ All imports successful!")
    return True

def test_config():
    """Test configuration loading."""
    print("\n🔍 Testing configuration...")

    try:
        import config

        # Check required environment variables
        required_vars = [
            'GOOGLE_CREDENTIALS_PATH',
            'NOTION_API_KEY',
            'NOTION_DATABASE_ID_RAPPORTS',
            'NOTION_DATABASE_ID_INTERVENTIONS',
            'OPENAI_API_KEY'
        ]

        missing_vars = []
        for var in required_vars:
            if not getattr(config, var, None):
                missing_vars.append(var)

        if missing_vars:
            print(f"❌ Missing environment variables: {missing_vars}")
            print("Please check your .env file and ensure all required variables are set.")
            return False

        print("✅ Configuration loaded successfully")
        return True

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

def test_ai_enhancement():
    """Test AI text enhancement."""
    print("\n🔍 Testing AI text enhancement...")

    try:
        from src.ai_processor.text_enhancer import TextEnhancer

        enhancer = TextEnhancer()

        # Test with sample text
        sample_text = "ras\nDésherbage\nTaille\nPalissage\nNettoyage"
        result = enhancer.enhance_intervention_text(sample_text)

        print(f"Original: {sample_text}")
        print(f"Enhanced: {result}")

        if result and len(result) > len(sample_text):
            print("✅ AI enhancement working correctly")
            return True
        else:
            print("❌ AI enhancement not working as expected")
            return False

    except Exception as e:
        print(f"❌ AI enhancement test failed: {e}")
        return False

def test_data_extraction():
    """Test data extraction utilities."""
    print("\n🔍 Testing data extraction...")

    try:
        from src.utils.data_extractor import group_messages_by_intervention, clean_text, categorize_intervention_type

        # Test with sample data
        sample_messages = [
            {
                'createTime': '2024-01-15T10:00:00Z',
                'text': 'ras',
                'author': {'name': 'Jean', 'email': 'jean@example.com'},
                'attachments': []
            },
            {
                'createTime': '2024-01-15T10:05:00Z',
                'text': 'Taille des rosiers',
                'author': {'name': 'Jean', 'email': 'jean@example.com'},
                'attachments': []
            }
        ]

        interventions = group_messages_by_intervention(sample_messages)

        print(f"Found {len(interventions)} interventions")
        for i, intervention in enumerate(interventions):
            print(f"Intervention {i+1}: {intervention.get('all_text', '')}")

        # Test text cleaning
        cleaned = clean_text("  ras  \n  Taille  ")
        print(f"Cleaned text: '{cleaned}'")

        # Test categorization
        category = categorize_intervention_type("Taille des arbustes")
        print(f"Category: {category}")

        print("✅ Data extraction working correctly")
        return True

    except Exception as e:
        print(f"❌ Data extraction test failed: {e}")
        return False

def test_notion_connection():
    """Test Notion API connection."""
    print("\n🔍 Testing Notion connection...")

    try:
        from src.notion.client import test_notion_setup

        if test_notion_setup():
            print("✅ Notion connection successful")
            return True
        else:
            print("❌ Notion connection failed")
            return False

    except Exception as e:
        print(f"❌ Notion connection test failed: {e}")
        return False

def test_url_parsing():
    """Test URL parsing utility."""
    print("\n🔍 Testing URL parsing...")

    try:
        from config import extract_space_id_from_url

        # Test different URL formats
        test_urls = [
            "https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A",
            "https://chat.google.com/room/AAAAAXFFz5A",
            "spaces/AAAAAXFFz5A",
            "AAAAAXFFz5A"
        ]

        expected = "spaces/AAAAAXFFz5A"

        for url in test_urls:
            result = extract_space_id_from_url(url)
            if result != expected:
                print(f"❌ URL parsing failed for: {url}")
                print(f"   Expected: {expected}, Got: {result}")
                return False

        print("✅ URL parsing working correctly")
        return True

    except Exception as e:
        print(f"❌ URL parsing test failed: {e}")
        return False

def test_french_properties():
    """Test French property validation."""
    print("\n🔍 Testing French properties...")

    try:
        from src.notion.database import NotionDatabaseManager, PROPERTY_NAMES

        # Check that property names are in French
        french_properties = [
            'Titre', 'Date', 'Client', 'Description', 'Commentaire Brut',
            'Responsable', 'Canal', 'Catégorie', 'Nom', 'ID Unique',
            'URL Page', 'Statut', 'Interventions', 'Date Début', 'Date Fin'
        ]

        for prop in french_properties:
            if prop not in PROPERTY_NAMES.values():
                print(f"❌ French property '{prop}' not found in mapping")
                return False

        print("✅ French properties validation successful")
        return True

    except Exception as e:
        print(f"❌ French properties test failed: {e}")
        return False

def test_three_databases():
    """Test access to all three databases."""
    print("\n🔍 Testing three databases access...")

    try:
        from src.notion.database import NotionDatabaseManager

        manager = NotionDatabaseManager()

        # Test database schema validation
        if not manager.validate_database_schemas():
            print("❌ Database schemas validation failed")
            return False

        # Test getting database stats
        stats = manager.get_database_stats()
        print(f"Database stats: {stats}")

        print("✅ Three databases access successful")
        return True

    except Exception as e:
        print(f"❌ Three databases test failed: {e}")
        return False

def test_google_chat_connection():
    """Test Google Chat API connection."""
    print("\n🔍 Testing Google Chat connection...")

    try:
        from src.google_chat.auth import test_authentication

        if test_authentication():
            print("✅ Google Chat connection successful")
            return True
        else:
            print("❌ Google Chat connection failed")
            return False

    except Exception as e:
        print(f"❌ Google Chat connection test failed: {e}")
        return False

def run_all_tests():
    """Run all tests."""
    print("🚀 Starting MERCI RAYMOND system tests...\n")

    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Data Extraction", test_data_extraction),
        ("AI Enhancement", test_ai_enhancement),
        ("URL Parsing", test_url_parsing),
        ("French Properties", test_french_properties),
        ("Three Databases", test_three_databases),
        ("Notion Connection", test_notion_connection),
        ("Google Chat Connection", test_google_chat_connection),
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running {test_name} test...")
        print('='*50)

        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False

    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)

    passed = 0
    total = len(tests)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! System is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the configuration and try again.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
