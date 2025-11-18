#!/usr/bin/env python3
"""
Migration script to convert existing data to the new French 3-database architecture.
This script helps migrate from the old 2-database system to the new 3-database system.
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def migrate_clients():
    """
    Create sample clients in the Clients database.
    This should be run after setting up the three databases in Notion.
    """
    print("🔄 Creating sample clients...")

    try:
        from src.notion.database import NotionDatabaseManager

        db_manager = NotionDatabaseManager()

        # Sample clients with their Google Chat URLs
        sample_clients = [
            {
                'nom': 'Site ABC - Résidence',
                'canal_chat': 'https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A',
                'statut': 'Actif',
                'contact': 'Jean Dupont',
                'adresse': '123 Rue de la Paix, Paris 75001'
            },
            {
                'nom': 'Site XYZ - Bureau',
                'canal_chat': 'https://mail.google.com/chat/u/0/#chat/space/BBBBBBBBBB',
                'statut': 'Actif',
                'contact': 'Marie Martin',
                'adresse': '456 Avenue des Champs, Paris 75008'
            },
            {
                'nom': 'Site DEF - Parc',
                'canal_chat': 'https://mail.google.com/chat/u/0/#chat/space/CCCCCCCCCC',
                'statut': 'Actif',
                'contact': 'Pierre Durand',
                'adresse': '789 Boulevard Saint-Germain, Paris 75006'
            }
        ]

        created_clients = []
        for client_data in sample_clients:
            client_id = db_manager.add_client_to_db(client_data)
            if client_id:
                created_clients.append(client_data['nom'])
                print(f"✅ Created client: {client_data['nom']}")
            else:
                print(f"❌ Failed to create client: {client_data['nom']}")

        print(f"✅ Migration completed: {len(created_clients)} clients created")
        return created_clients

    except Exception as e:
        print(f"❌ Error during client migration: {e}")
        return []

def test_url_extraction():
    """
    Test the URL extraction utility with sample URLs.
    """
    print("🔄 Testing URL extraction...")

    try:
        from config import extract_space_id_from_url

        test_cases = [
            {
                'input': 'https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A',
                'expected': 'spaces/AAAAAXFFz5A'
            },
            {
                'input': 'https://chat.google.com/room/BBBBBBBBBB',
                'expected': 'spaces/BBBBBBBBBB'
            },
            {
                'input': 'spaces/CCCCCCCCCC',
                'expected': 'spaces/CCCCCCCCCC'
            },
            {
                'input': 'DDDDDDDDDD',
                'expected': 'spaces/DDDDDDDDDD'
            }
        ]

        all_passed = True
        for case in test_cases:
            result = extract_space_id_from_url(case['input'])
            if result == case['expected']:
                print(f"✅ {case['input']} → {result}")
            else:
                print(f"❌ {case['input']} → {result} (expected {case['expected']})")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Error testing URL extraction: {e}")
        return False

def validate_database_schemas():
    """
    Validate that all three databases have the correct French properties.
    """
    print("🔄 Validating database schemas...")

    try:
        from src.notion.database import NotionDatabaseManager

        db_manager = NotionDatabaseManager()

        if db_manager.validate_database_schemas():
            print("✅ All database schemas are valid")
            return True
        else:
            print("❌ Database schema validation failed")
            return False

    except Exception as e:
        print(f"❌ Error validating schemas: {e}")
        return False

def test_client_loading():
    """
    Test loading clients from the Notion database.
    """
    print("🔄 Testing client loading...")

    try:
        from src.notion.database import NotionDatabaseManager
        import config

        db_manager = NotionDatabaseManager()

        # Test getting all clients
        clients = db_manager.get_all_clients()
        print(f"Found {len(clients)} clients in database")

        # Test getting client mapping
        mapping = db_manager.get_all_clients_mapping()
        print(f"Client mapping: {mapping}")

        # Test dynamic loading
        config.load_clients_from_notion()
        print(f"Dynamic loading result: {len(config.CLIENT_CHAT_MAPPING)} clients loaded")

        return True

    except Exception as e:
        print(f"❌ Error testing client loading: {e}")
        return False

def create_sample_intervention():
    """
    Create a sample intervention to test the new French properties.
    """
    print("🔄 Creating sample intervention...")

    try:
        from src.notion.database import NotionDatabaseManager

        db_manager = NotionDatabaseManager()

        # Get first client for testing
        clients = db_manager.get_all_clients()
        if not clients:
            print("❌ No clients found. Please run client migration first.")
            return False

        client_name = clients[0].get('properties', {}).get('Nom', {}).get('title', [{}])[0].get('text', {}).get('content', '')
        if not client_name:
            print("❌ Could not extract client name")
            return False

        # Create sample intervention
        intervention_data = {
            'titre': 'Test Intervention - Taille des rosiers',
            'date': datetime.now().isoformat(),
            'client_name': client_name,
            'description': 'Taille de formation effectuée sur les rosiers du jardin principal. Les plantes ont été taillées selon les bonnes pratiques horticoles.',
            'commentaire_brut': 'ras\nTaille rosiers\nNettoyage',
            'responsable': 'Jean Dupont',
            'canal': f'Chat {client_name}',
            'categorie': 'Taille',
            'images': []
        }

        intervention_id = db_manager.add_intervention_to_db(intervention_data)
        if intervention_id:
            print(f"✅ Created sample intervention: {intervention_id}")
            return True
        else:
            print("❌ Failed to create sample intervention")
            return False

    except Exception as e:
        print(f"❌ Error creating sample intervention: {e}")
        return False

def create_sample_report():
    """
    Create a sample report to test the new French properties.
    """
    print("🔄 Creating sample report...")

    try:
        from src.notion.database import NotionDatabaseManager
        import uuid

        db_manager = NotionDatabaseManager()

        # Get first client for testing
        clients = db_manager.get_all_clients()
        if not clients:
            print("❌ No clients found. Please run client migration first.")
            return False

        client_name = clients[0].get('properties', {}).get('Nom', {}).get('title', [{}])[0].get('text', {}).get('content', '')
        if not client_name:
            print("❌ Could not extract client name")
            return False

        # Create sample report
        report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"
        report_data = {
            'nom': f'Rapport Test - {client_name}',
            'client_name': client_name,
            'id_unique': report_id,
            'url_page': f'https://notion.so/test-{report_id}',
            'statut': 'Brouillon',
            'date_debut': datetime.now().isoformat(),
            'date_fin': datetime.now().isoformat()
        }

        report_page_id = db_manager.add_report_to_db(report_data)
        if report_page_id:
            print(f"✅ Created sample report: {report_page_id}")
            return True
        else:
            print("❌ Failed to create sample report")
            return False

    except Exception as e:
        print(f"❌ Error creating sample report: {e}")
        return False

def run_migration():
    """
    Run the complete migration process.
    """
    print("🚀 Starting MERCI RAYMOND migration to French 3-database architecture...\n")

    steps = [
        ("URL Extraction Test", test_url_extraction),
        ("Database Schema Validation", validate_database_schemas),
        ("Client Migration", migrate_clients),
        ("Client Loading Test", test_client_loading),
        ("Sample Intervention", create_sample_intervention),
        ("Sample Report", create_sample_report)
    ]

    results = {}

    for step_name, step_func in steps:
        print(f"\n{'='*50}")
        print(f"Running {step_name}...")
        print('='*50)

        try:
            result = step_func()
            results[step_name] = result
        except Exception as e:
            print(f"❌ {step_name} failed: {e}")
            results[step_name] = False

    # Summary
    print(f"\n{'='*50}")
    print("MIGRATION SUMMARY")
    print('='*50)

    passed = 0
    total = len(steps)

    for step_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{step_name}: {status}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{total} steps passed")

    if passed == total:
        print("🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Verify the three databases in Notion have the correct French properties")
        print("2. Add your real clients to the Clients database")
        print("3. Test the system with: python test_system.py")
        print("4. Run the main application: streamlit run main.py")
        return True
    else:
        print("⚠️  Some migration steps failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
