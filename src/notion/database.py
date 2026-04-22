from typing import List, Dict, Any, Optional
from datetime import datetime
from .client import NotionClient
import config

# French property mapping
PROPERTY_NAMES = {
    # Interventions (matching actual database structure)
    'intervention_titre': 'Nom',
    'intervention_date': 'Date',
    'intervention_client': 'Client',
    'intervention_description': 'Commentaire',
    'intervention_responsable': 'Responsable',
    'intervention_canal': 'Canal',
    'intervention_images': 'Images',

    # Rapports (matching actual database structure)
    'rapport_nom': 'Nom',
    'rapport_client': 'Client',
    'rapport_id': 'ID Unique',
    'rapport_url': 'URL Page',
    'rapport_statut': 'Statut',
    'rapport_interventions': 'Interventions',
    'rapport_creation': 'Date de création',

    # Clients
    'client_nom': 'Nom',
    'client_interventions': 'Interventions',
    'client_rapports': 'Rapports',
    'client_canal': 'Canal Chat',
    'client_statut': 'Statut',
    'client_contact': 'Contact',
    'client_adresse': 'Adresse'
}

class NotionDatabaseManager:
    """
    Manages database operations for Clients, Interventions, and Rapports databases.
    All operations use French property names and support relational links.
    """

    def __init__(self, notion_client: Optional[NotionClient] = None):
        """
        Initialize the database manager.

        Args:
            notion_client: NotionClient instance (creates new one if None)
        """
        self.client = notion_client or NotionClient()
        self.clients_db_id = config.NOTION_DB_CLIENTS
        self.rapports_db_id = config.NOTION_DB_RAPPORTS
        self.interventions_db_id = config.NOTION_DB_INTERVENTIONS

    # CLIENT OPERATIONS

    def add_client_to_db(self, client_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a client to the Clients database.

        Args:
            client_data: Dictionary containing client information
                - nom: Client name
                - canal_chat: Google Chat space ID
                - statut: Status (Actif/Inactif)
                - contact: Contact person
                - adresse: Site address

        Returns:
            Created page ID or None if creation fails
        """
        try:
            # Prepare properties for the database
            properties = {
                PROPERTY_NAMES['client_nom']: {
                    "title": [
                        {
                            "text": {
                                "content": client_data.get('nom', 'Nouveau Client')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['client_canal']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": client_data.get('canal_chat', '')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['client_statut']: {
                    "select": {
                        "name": client_data.get('statut', 'Actif')
                    }
                },
                PROPERTY_NAMES['client_contact']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": client_data.get('contact', '')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['client_adresse']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": client_data.get('adresse', '')
                            }
                        }
                    ]
                }
            }

            # Create the page
            response = self.client.create_page(
                parent_db_id=self.clients_db_id,
                properties=properties
            )

            print(f"✅ Added client to database: {client_data.get('nom', 'Unknown')}")
            return response['id']

        except Exception as e:
            print(f"❌ Error adding client to database: {e}")
            return None

    def get_client_by_name(self, client_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a client by name.
        Handles both plain text and page mention titles.

        Args:
            client_name: Name of the client

        Returns:
            Client data or None if not found
        """
        try:
            # Get all clients
            all_clients = self.get_all_clients()

            # Search for matching name
            for client in all_clients:
                properties = client.get('properties', {})
                nom_prop = properties.get(PROPERTY_NAMES['client_nom'], {})

                if nom_prop.get('title'):
                    title_data = nom_prop['title']
                    client_name_extracted = ''

                    # Extract name from title (handles both text and mentions)
                    for item in title_data:
                        if item.get('type') == 'text':
                            client_name_extracted += item.get('text', {}).get('content', '')
                        elif item.get('type') == 'mention':
                            client_name_extracted += item.get('plain_text', '')

                    # Match with or without trailing spaces
                    if client_name_extracted.strip() == client_name.strip():
                        return client

            return None

        except Exception as e:
            print(f"❌ Error getting client by name: {e}")
            return None

    def get_all_clients(self) -> List[Dict[str, Any]]:
        """
        Get all clients from the database.

        Returns:
            List of client pages

        Raises:
            Exception: If database query fails, re-raises with context
        """
        try:
            # Validate database ID before querying
            if not self.clients_db_id:
                raise ValueError("Clients database ID is not set or is empty")

            # Debug logging
            try:
                import streamlit as st
                if hasattr(st, 'session_state'):
                    if 'notion_debug' not in st.session_state:
                        st.session_state.notion_debug = {}
                    st.session_state.notion_debug['querying_db_id'] = self.clients_db_id[:8] + "..." if len(self.clients_db_id) > 8 else self.clients_db_id
            except (ImportError, AttributeError):
                pass

            results = self.client.query_database(self.clients_db_id)
            return results

        except Exception as e:
            # Log full error details
            error_msg = f"Error getting all clients from database '{self.clients_db_id[:8] if self.clients_db_id else 'None'}...': {str(e)}"

            # Try to display in Streamlit if available
            try:
                import streamlit as st
                st.error(f"❌ {error_msg}")
            except (ImportError, AttributeError):
                print(f"❌ {error_msg}")

            # Re-raise to allow caller to handle
            raise Exception(error_msg) from e

    def get_all_clients_mapping(self) -> Dict[str, str]:
        """
        Get client name to chat space ID mapping.

        Returns:
            Dictionary mapping client names to space IDs

        Raises:
            Exception: If database query or processing fails, re-raises with context
        """
        try:
            clients = self.get_all_clients()
            mapping = {}

            # Debug: Log number of clients found
            try:
                import streamlit as st
                if hasattr(st, 'session_state'):
                    if 'notion_debug' not in st.session_state:
                        st.session_state.notion_debug = {}
                    st.session_state.notion_debug['clients_found'] = len(clients)
            except (ImportError, AttributeError):
                pass

            for client in clients:
                try:
                    properties = client.get('properties', {})
                    nom_prop = properties.get(PROPERTY_NAMES['client_nom'], {})
                    canal_prop = properties.get(PROPERTY_NAMES['client_canal'], {})

                    if nom_prop.get('title') and canal_prop.get('rich_text'):
                        # Extract client name from title property (handle complex structure)
                        title_data = nom_prop['title']
                        client_name = ''

                        # Handle both text and mention types in title
                        for item in title_data:
                            if item.get('type') == 'text':
                                client_name += item.get('text', {}).get('content', '')
                            elif item.get('type') == 'mention':
                                client_name += item.get('plain_text', '')

                        # Extract canal chat from rich_text
                        canal_chat = canal_prop['rich_text'][0].get('text', {}).get('content', '')

                        if client_name and canal_chat:
                            mapping[client_name] = canal_chat
                except Exception as client_error:
                    # Log but continue processing other clients
                    try:
                        import streamlit as st
                        st.warning(f"⚠️ Error processing client entry: {str(client_error)}")
                    except (ImportError, AttributeError):
                        print(f"⚠️ Error processing client entry: {str(client_error)}")

            if not mapping:
                # No clients found - this might be expected if database is empty
                try:
                    import streamlit as st
                    st.info(f"ℹ️ No clients found in database. Database ID: {self.clients_db_id[:8] if self.clients_db_id else 'None'}...")
                except (ImportError, AttributeError):
                    print(f"ℹ️ No clients found in database. Database ID: {self.clients_db_id[:8] if self.clients_db_id else 'None'}...")

            return mapping

        except Exception as e:
            # Re-raise to allow caller to handle
            error_msg = f"Error getting clients mapping: {str(e)}"
            try:
                import streamlit as st
                st.error(f"❌ {error_msg}")
            except (ImportError, AttributeError):
                print(f"❌ {error_msg}")
            raise Exception(error_msg) from e

    def update_client_chat_space(self, client_name: str, space_id: str) -> bool:
        """
        Update a client's chat space ID.

        Args:
            client_name: Name of the client
            space_id: New chat space ID

        Returns:
            True if successful, False otherwise
        """
        try:
            client = self.get_client_by_name(client_name)
            if not client:
                print(f"❌ Client '{client_name}' not found")
                return False

            properties = {
                PROPERTY_NAMES['client_canal']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": space_id
                            }
                        }
                    ]
                }
            }

            self.client.update_page(client['id'], properties)
            print(f"✅ Updated client '{client_name}' chat space to '{space_id}'")
            return True

        except Exception as e:
            print(f"❌ Error updating client chat space: {e}")
            return False

    # INTERVENTION OPERATIONS

    def add_intervention_to_db(self, intervention_data: Dict[str, Any]) -> Optional[str]:
        """
        Add an intervention to the Interventions database.

        Args:
            intervention_data: Dictionary containing intervention information
                - titre: Intervention title
                - date: Intervention date
                - client_name: Client name (will be converted to relation)
                - description: AI-enhanced description
                - commentaire_brut: Original raw text
                - responsable: Person in charge
                - canal: Source chat channel
                - categorie: Intervention category
                - images: List of image URLs

        Returns:
            Created page ID or None if creation fails
        """
        try:
            # Get client ID for relation
            client = self.get_client_by_name(intervention_data.get('client_name', ''))
            if not client:
                print(f"❌ Client '{intervention_data.get('client_name')}' not found")
                return None

            # Prepare properties for the database
            properties = {
                PROPERTY_NAMES['intervention_titre']: {
                    "title": [
                        {
                            "text": {
                                "content": intervention_data.get('titre', 'Intervention de maintenance')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['intervention_date']: {
                    "date": {
                        "start": intervention_data.get('date', datetime.now().isoformat())
                    }
                },
                PROPERTY_NAMES['intervention_client']: {
                    "relation": [
                        {
                            "id": client['id']
                        }
                    ]
                },
                PROPERTY_NAMES['intervention_description']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": intervention_data.get('description', '')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['intervention_responsable']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": intervention_data.get('responsable', 'Unknown')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['intervention_canal']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": intervention_data.get('canal', '')
                            }
                        }
                    ]
                }
            }

            # Create the page
            response = self.client.create_page(
                parent_db_id=self.interventions_db_id,
                properties=properties
            )

            # Add images if available
            if intervention_data.get('images'):
                # Extract download URIs from image dictionaries
                image_urls = []
                for img in intervention_data['images']:
                    if isinstance(img, dict) and img.get('downloadUri'):
                        image_urls.append(img['downloadUri'])
                    elif isinstance(img, str):
                        image_urls.append(img)

                if image_urls:
                    self._add_images_to_page(response['id'], image_urls)

            print(f"✅ Added intervention to database: {intervention_data.get('titre', 'Unknown')}")
            return response['id']

        except Exception as e:
            print(f"❌ Error adding intervention to database: {e}")
            return None

    def get_interventions_for_client(self, client_name: str, start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Get interventions for a specific client within a date range.

        Args:
            client_name: Name of the client
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of intervention pages
        """
        try:
            # Get client ID first
            client = self.get_client_by_name(client_name)
            if not client:
                return []

            # Build filter conditions
            filter_conditions = {
                "property": PROPERTY_NAMES['intervention_client'],
                "relation": {
                    "contains": client['id']
                }
            }

            # Add date filters if provided
            if start_date or end_date:
                date_filter = {
                    "property": PROPERTY_NAMES['intervention_date'],
                    "date": {}
                }

                if start_date:
                    date_filter["date"]["after"] = start_date.isoformat()
                if end_date:
                    date_filter["date"]["before"] = end_date.isoformat()

                # Combine filters
                filter_conditions = {
                    "and": [filter_conditions, date_filter]
                }

            # Query the database
            results = self.client.query_database(
                database_id=self.interventions_db_id,
                filter_conditions=filter_conditions
            )

            return results

        except Exception as e:
            print(f"❌ Error getting interventions for client: {e}")
            return []

    # REPORT OPERATIONS

    def add_report_to_db(self, report_data: Dict[str, Any]) -> Optional[str]:
        """
        Add a report to the Rapports database.

        Args:
            report_data: Dictionary containing report information
                - nom: Report title
                - client_name: Client name (will be converted to relation)
                - id_unique: Unique report ID
                - url_page: Report page URL
                - statut: Report status
                - date_debut: Start date
                - date_fin: End date

        Returns:
            Created page ID or None if creation fails
        """
        try:
            # Get client ID for relation
            client = self.get_client_by_name(report_data.get('client_name', ''))
            if not client:
                print(f"❌ Client '{report_data.get('client_name')}' not found")
                return None

            # Prepare properties for the database
            properties = {
                PROPERTY_NAMES['rapport_nom']: {
                    "title": [
                        {
                            "text": {
                                "content": report_data.get('nom', f"Rapport {report_data.get('client_name', 'Unknown')}")
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['rapport_client']: {
                    "relation": [
                        {
                            "id": client['id']
                        }
                    ]
                },
                PROPERTY_NAMES['rapport_id']: {
                    "rich_text": [
                        {
                            "text": {
                                "content": report_data.get('id_unique', '')
                            }
                        }
                    ]
                },
                PROPERTY_NAMES['rapport_url']: {
                    "url": report_data.get('url_page', '')
                },
                PROPERTY_NAMES['rapport_statut']: {
                    "select": {
                        "name": report_data.get('statut', 'Brouillon')
                    }
                }
            }

            # Create the page
            response = self.client.create_page(
                parent_db_id=self.rapports_db_id,
                properties=properties
            )

            print(f"✅ Added report to database: {report_data.get('nom', 'Unknown')}")
            return response['id']

        except Exception as e:
            print(f"❌ Error adding report to database: {e}")
            return None

    def get_reports_for_client(self, client_name: str) -> List[Dict[str, Any]]:
        """
        Get all reports for a specific client.

        Args:
            client_name: Name of the client

        Returns:
            List of report pages
        """
        try:
            # Get client ID first
            client = self.get_client_by_name(client_name)
            if not client:
                return []

            filter_conditions = {
                "property": PROPERTY_NAMES['rapport_client'],
                "relation": {
                    "contains": client['id']
                }
            }

            results = self.client.query_database(
                database_id=self.rapports_db_id,
                filter_conditions=filter_conditions
            )

            return results

        except Exception as e:
            print(f"❌ Error getting reports for client: {e}")
            return []

    # RELATION LINKING OPERATIONS

    def link_interventions_to_report(self, report_id: str, intervention_ids: List[str]) -> bool:
        """
        Link interventions to a report.

        Args:
            report_id: ID of the report page
            intervention_ids: List of intervention page IDs

        Returns:
            True if successful, False otherwise
        """
        try:
            properties = {
                PROPERTY_NAMES['rapport_interventions']: {
                    "relation": [{"id": iid} for iid in intervention_ids]
                }
            }

            self.client.update_page(report_id, properties)
            print(f"✅ Linked {len(intervention_ids)} interventions to report")
            return True

        except Exception as e:
            print(f"❌ Error linking interventions to report: {e}")
            return False

    def link_report_to_client(self, report_id: str, client_id: str) -> bool:
        """
        Link a report to a client.

        Args:
            report_id: ID of the report page
            client_id: ID of the client page

        Returns:
            True if successful, False otherwise
        """
        try:
            properties = {
                PROPERTY_NAMES['rapport_client']: {
                    "relation": [{"id": client_id}]
                }
            }

            self.client.update_page(report_id, properties)
            print(f"✅ Linked report to client")
            return True

        except Exception as e:
            print(f"❌ Error linking report to client: {e}")
            return False

    def link_intervention_to_client(self, intervention_id: str, client_id: str) -> bool:
        """
        Link an intervention to a client.

        Args:
            intervention_id: ID of the intervention page
            client_id: ID of the client page

        Returns:
            True if successful, False otherwise
        """
        try:
            properties = {
                PROPERTY_NAMES['intervention_client']: {
                    "relation": [{"id": client_id}]
                }
            }

            self.client.update_page(intervention_id, properties)
            print(f"✅ Linked intervention to client")
            return True

        except Exception as e:
            print(f"❌ Error linking intervention to client: {e}")
            return False

    # UTILITY METHODS

    def _add_images_to_page(self, page_id: str, images: List[str]) -> bool:
        """
        Add images to a Notion page.

        Args:
            page_id: ID of the page
            images: List of image URLs

        Returns:
            True if successful, False otherwise
        """
        try:
            blocks = []

            for i, image_url in enumerate(images):
                # Create image block
                image_block = self.client.create_image_block(
                    image_url=image_url,
                    caption=f"Photo {i + 1}" if len(images) > 1 else None
                )
                blocks.append(image_block)

            # Append blocks to the page
            if blocks:
                self.client.append_blocks(page_id, blocks)
                print(f"✅ Added {len(blocks)} images to page")
                return True

            return False

        except Exception as e:
            print(f"❌ Error adding images to page: {e}")
            return False

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the databases.

        Returns:
            Dictionary with database statistics
        """
        try:
            stats = {}

            # Get interventions count
            interventions = self.client.query_database(self.interventions_db_id)
            stats['interventions_count'] = len(interventions)

            # Get reports count
            reports = self.client.query_database(self.rapports_db_id)
            stats['reports_count'] = len(reports)

            # Get clients count
            clients = self.client.query_database(self.clients_db_id)
            stats['clients_count'] = len(clients)

            # Get unique clients
            client_names = set()
            for client in clients:
                nom_prop = client.get('properties', {}).get(PROPERTY_NAMES['client_nom'], {})
                if nom_prop.get('title'):
                    client_name = nom_prop['title'][0].get('text', {}).get('content', '')
                    if client_name:
                        client_names.add(client_name)

            stats['unique_clients'] = len(client_names)
            stats['clients'] = list(client_names)

            return stats

        except Exception as e:
            print(f"❌ Error getting database stats: {e}")
            return {}

    def validate_database_schemas(self) -> bool:
        """
        Validate that the databases have the required French properties.

        Returns:
            True if schemas are valid, False otherwise
        """
        try:
            # Check Clients database
            clients_schema = self.client.get_database_schema(self.clients_db_id)
            required_client_props = [
                PROPERTY_NAMES['client_nom'],
                PROPERTY_NAMES['client_canal'],
                PROPERTY_NAMES['client_statut']
            ]

            for prop in required_client_props:
                if prop not in clients_schema:
                    print(f"❌ Missing property '{prop}' in Clients database")
                    return False

            # Check Interventions database
            interventions_schema = self.client.get_database_schema(self.interventions_db_id)
            required_intervention_props = [
                PROPERTY_NAMES['intervention_titre'],
                PROPERTY_NAMES['intervention_date'],
                PROPERTY_NAMES['intervention_client'],
                PROPERTY_NAMES['intervention_description']
            ]

            for prop in required_intervention_props:
                if prop not in interventions_schema:
                    print(f"❌ Missing property '{prop}' in Interventions database")
                    return False

            # Check Rapports database
            rapports_schema = self.client.get_database_schema(self.rapports_db_id)
            required_rapport_props = [
                PROPERTY_NAMES['rapport_nom'],
                PROPERTY_NAMES['rapport_client'],
                PROPERTY_NAMES['rapport_id']
            ]

            for prop in required_rapport_props:
                if prop not in rapports_schema:
                    print(f"❌ Missing property '{prop}' in Rapports database")
                    return False

            print("✅ Database schemas are valid")
            return True

        except Exception as e:
            print(f"❌ Error validating database schemas: {e}")
            return False

# Convenience functions
def create_database_manager() -> NotionDatabaseManager:
    """
    Create a database manager with default configuration.

    Returns:
        Configured NotionDatabaseManager instance
    """
    return NotionDatabaseManager()

def test_database_operations() -> bool:
    """
    Test database operations.

    Returns:
        True if all operations work, False otherwise
    """
    try:
        manager = create_database_manager()

        # Validate schemas
        if not manager.validate_database_schemas():
            return False

        # Get stats
        stats = manager.get_database_stats()
        print(f"Database stats: {stats}")

        print("✅ Database operations test successful!")
        return True

    except Exception as e:
        print(f"❌ Database operations test failed: {e}")
        return False

if __name__ == "__main__":
    # Test database operations
    test_database_operations()
