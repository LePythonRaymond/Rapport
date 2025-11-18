from typing import List, Dict, Any, Optional
from notion_client import Client
import config
import requests

class NotionClient:
    """
    Wrapper for Notion API client with additional functionality for report generation.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Notion client.

        Args:
            api_key: Notion API key (defaults to config.NOTION_API_KEY)
        """
        self.api_key = api_key or config.NOTION_API_KEY
        if not self.api_key:
            raise ValueError("Notion API key not found in environment variables")

        self.client = Client(auth=self.api_key)

    def _format_database_id(self, db_id: str) -> str:
        """
        Format database ID for Notion API calls.
        Removes dashes from database IDs as required by Notion API.

        Args:
            db_id: Database ID (with or without dashes)

        Returns:
            Database ID without dashes for API calls
        """
        if not db_id:
            return ""
        return db_id.replace('-', '')

    def create_page(self, parent_db_id: str, properties: Dict[str, Any],
                   children: Optional[List[Dict[str, Any]]] = None,
                   cover: Optional[str] = None, icon: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new page in a Notion database.

        Args:
            parent_db_id: ID of the parent database
            properties: Page properties
            children: Optional list of child blocks
            cover: Optional cover image URL or file_upload_id
            icon: Optional icon image URL or file_upload_id

        Returns:
            Created page information
        """
        try:
            page_data = {
                "parent": {"database_id": self._format_database_id(parent_db_id)},
                "properties": properties
            }

            if children:
                page_data["children"] = children

            # Add cover if provided
            if cover:
                if cover.startswith("notion://file_upload/"):
                    file_upload_id = cover.replace("notion://file_upload/", "")
                    page_data["cover"] = {
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id}
                    }
                else:
                    page_data["cover"] = {
                        "type": "external",
                        "external": {"url": cover}
                    }

            # Add icon if provided
            if icon:
                if icon.startswith("notion://file_upload/"):
                    file_upload_id = icon.replace("notion://file_upload/", "")
                    page_data["icon"] = {
                        "type": "file_upload",
                        "file_upload": {"id": file_upload_id}
                    }
                else:
                    page_data["icon"] = {
                        "type": "external",
                        "external": {"url": icon}
                    }

            response = self.client.pages.create(**page_data)
            return response

        except Exception as e:
            print(f"Error creating Notion page: {e}")
            raise

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing Notion page.

        Args:
            page_id: ID of the page to update
            properties: Properties to update

        Returns:
            Updated page information
        """
        try:
            response = self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            return response

        except Exception as e:
            print(f"Error updating Notion page: {e}")
            raise

    def append_blocks(self, page_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Append blocks to an existing Notion page.

        Args:
            page_id: ID of the page
            children: List of blocks to append

        Returns:
            Response from Notion API
        """
        try:
            response = self.client.blocks.children.append(
                block_id=page_id,
                children=children
            )
            return response

        except Exception as e:
            print(f"Error appending blocks to Notion page: {e}")
            raise

    def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Get a Notion page by ID.

        Args:
            page_id: ID of the page

        Returns:
            Page information
        """
        try:
            response = self.client.pages.retrieve(page_id=page_id)
            return response

        except Exception as e:
            print(f"Error getting Notion page: {e}")
            raise

    def get_database(self, database_id: str) -> Dict[str, Any]:
        """
        Get a Notion database by ID.

        Args:
            database_id: ID of the database

        Returns:
            Database information
        """
        try:
            response = self.client.databases.retrieve(database_id=self._format_database_id(database_id))
            return response

        except Exception as e:
            print(f"Error getting Notion database: {e}")
            raise

    def query_database(self, database_id: str, filter_conditions: Optional[Dict[str, Any]] = None,
                      sorts: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Query a Notion database.

        Args:
            database_id: ID of the database
            filter_conditions: Optional filter conditions
            sorts: Optional sort conditions

        Returns:
            List of pages from the database
        """
        try:
            query_params = {"database_id": self._format_database_id(database_id)}

            if filter_conditions:
                query_params["filter"] = filter_conditions

            if sorts:
                query_params["sorts"] = sorts

            response = self.client.databases.query(**query_params)
            return response.get("results", [])

        except Exception as e:
            print(f"Error querying Notion database: {e}")
            return []

    def create_heading_block(self, text: str, level: int = 1) -> Dict[str, Any]:
        """
        Create a heading block.

        Args:
            text: Heading text
            level: Heading level (1-3)

        Returns:
            Heading block dictionary
        """
        heading_type = f"heading_{level}"

        return {
            "type": heading_type,
            heading_type: {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": text}
                    }
                ]
            }
        }

    def create_text_block(self, text: str, bold: bool = False, italic: bool = False) -> Dict[str, Any]:
        """
        Create a text block.

        Args:
            text: Text content
            bold: Whether text is bold
            italic: Whether text is italic

        Returns:
            Text block dictionary
        """
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {
                            "bold": bold,
                            "italic": italic,
                            "strikethrough": False,
                            "underline": False,
                            "code": False,
                            "color": "default"
                        }
                    }
                ]
            }
        }

    def create_text_block_from_rich_text(self, rich_text: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a text block from a rich text array.

        Args:
            rich_text: List of rich text dictionaries

        Returns:
            Text block dictionary
        """
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": rich_text
            }
        }

    def create_bullet_list_block(self, items: List[str]) -> List[Dict[str, Any]]:
        """
        Create bullet list blocks.

        Args:
            items: List of items

        Returns:
            List of bullet list block dictionaries
        """
        blocks = []

        for item in items:
            block = {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": item}
                        }
                    ]
                }
            }
            blocks.append(block)

        return blocks

    def create_image_block(self, image_url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """
        Create an image block.

        Supports both external URLs and Notion file_upload references.

        Args:
            image_url: URL of the image or notion://file_upload/{id} reference
            caption: Optional caption

        Returns:
            Image block dictionary
        """
        # Check if this is a file_upload reference
        if image_url.startswith("notion://file_upload/"):
            file_upload_id = image_url.replace("notion://file_upload/", "")
            block = {
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {"id": file_upload_id}
                }
            }
        else:
            # Regular external URL
            block = {
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": image_url}
                }
            }

        if caption:
            block["image"]["caption"] = [
                {
                    "type": "text",
                    "text": {"content": caption}
                }
            ]

        return block

    def create_divider_block(self) -> Dict[str, Any]:
        """
        Create a divider block.

        Returns:
            Divider block dictionary
        """
        return {"type": "divider", "divider": {}}

    def create_quote_block(self, text: str, rich_text: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Create a quote block.

        Args:
            text: Quote text (used if rich_text not provided)
            rich_text: Optional rich text array for multi-line content (overrides text if provided)

        Returns:
            Quote block dictionary
        """
        if rich_text is not None:
            quote_rich_text = rich_text
        else:
            # Handle multi-line text by splitting on \n
            lines = text.split('\n')
            quote_rich_text = []
            for i, line in enumerate(lines):
                if i > 0:
                    # Add line break (text content with newline)
                    quote_rich_text.append({
                        "type": "text",
                        "text": {"content": "\n"}
                    })
                quote_rich_text.append({
                    "type": "text",
                    "text": {"content": line}
                })

        return {
            "type": "quote",
            "quote": {
                "rich_text": quote_rich_text
            }
        }

    def create_callout_block(self, text: Optional[str] = None, icon: str = "💡",
                            rich_text: Optional[List[Dict[str, Any]]] = None,
                            color: str = "default", children: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Create a callout block.

        Args:
            text: Callout text (used if rich_text not provided)
            icon: Icon emoji
            rich_text: Optional rich text array (overrides text if provided)
            color: Background color ("default", "gray_background", "green_background", etc.)
            children: Optional list of child blocks (e.g., bullet lists)

        Returns:
            Callout block dictionary
        """
        # Use rich_text if provided, otherwise convert text to rich_text
        if rich_text is not None:
            callout_rich_text = rich_text
        elif text:
            callout_rich_text = [
                {
                    "type": "text",
                    "text": {"content": text}
                }
            ]
        else:
            callout_rich_text = []

        block = {
            "type": "callout",
            "callout": {
                "rich_text": callout_rich_text,
                "icon": {
                    "type": "emoji",
                    "emoji": icon
                }
            }
        }

        # Add color if specified (and not default)
        if color != "default":
            block["callout"]["color"] = color

        # Add children if provided
        if children:
            block["callout"]["children"] = children

        return block

    def upload_local_file_for_asset(self, file_path: str) -> Optional[str]:
        """
        Upload a local file to Notion for use as page asset (cover/icon).

        Args:
            file_path: Path to local file

        Returns:
            Notion file_upload reference (notion://file_upload/{id}) or None if failed
        """
        try:
            import os
            from pathlib import Path

            # Check if file exists
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}")
                return None

            # Read file
            with open(file_path, 'rb') as f:
                file_bytes = f.read()

            # Determine content type
            file_ext = Path(file_path).suffix.lower()
            content_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.gif': 'image/gif'
            }
            content_type = content_types.get(file_ext, 'application/octet-stream')

            # Get filename
            filename = os.path.basename(file_path)

            # Create file upload
            upload_info = self.create_file_upload(filename, len(file_bytes))
            if not upload_info:
                return None

            upload_url = upload_info.get('upload_url')
            file_upload_id = upload_info.get('id')

            if not upload_url or not file_upload_id:
                print(f"❌ Missing upload URL or file upload ID: {upload_info}")
                return None

            # Send file
            if not self.send_file_to_upload(upload_url, file_bytes, content_type):
                return None

            # Return file_upload reference
            return f"notion://file_upload/{file_upload_id}"

        except Exception as e:
            print(f"❌ Error uploading local file: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_column_list_block(self, columns: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Create a column list block with multiple columns.

        Args:
            columns: List of column contents, where each item is a list of blocks for that column

        Returns:
            Column list block dictionary
        """
        column_blocks = []
        for column_children in columns:
            column_blocks.append(self.create_column_block(column_children))

        return {
            "type": "column_list",
            "column_list": {
                "children": column_blocks
            }
        }

    def create_column_block(self, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a single column block.

        Args:
            children: List of blocks to place in the column

        Returns:
            Column block dictionary
        """
        return {
            "type": "column",
            "column": {
                "children": children
            }
        }

    def create_heading_3_rich_text(self, text: str) -> Dict[str, Any]:
        """
        Create rich text entry formatted as H3 heading (bold text).

        Args:
            text: Heading text

        Returns:
            Rich text dictionary with bold annotation
        """
        return {
            "type": "text",
            "text": {"content": text},
            "annotations": {
                "bold": True,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "code": False,
                "color": "default"
            }
        }

    def create_rich_text_with_annotations(self, text: str, bold: bool = False,
                                         italic: bool = False) -> List[Dict[str, Any]]:
        """
        Create rich text array with annotations.

        Args:
            text: Text content
            bold: Whether text is bold
            italic: Whether text is italic

        Returns:
            List of rich text dictionaries
        """
        return [
            {
                "type": "text",
                "text": {"content": text},
                "annotations": {
                    "bold": bold,
                    "italic": italic,
                    "strikethrough": False,
                    "underline": False,
                    "code": False,
                    "color": "default"
                }
            }
        ]

    def convert_markdown_bold_to_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Convert markdown-style bold (**text**) to Notion rich text with bold annotations.

        Args:
            text: Text with potential markdown bold markers

        Returns:
            List of rich text dictionaries
        """
        import re
        rich_text = []
        parts = re.split(r'(\*\*[^*]+\*\*)', text)

        for part in parts:
            if not part:
                continue
            if part.startswith('**') and part.endswith('**'):
                # Bold text
                bold_text = part[2:-2]  # Remove ** markers
                rich_text.append({
                    "type": "text",
                    "text": {"content": bold_text},
                    "annotations": {
                        "bold": True,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    }
                })
            else:
                # Regular text
                rich_text.append({
                    "type": "text",
                    "text": {"content": part},
                    "annotations": {
                        "bold": False,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    }
                })

        return rich_text if rich_text else [{
            "type": "text",
            "text": {"content": text},
            "annotations": {
                "bold": False,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "code": False,
                "color": "default"
            }
        }]

    def test_connection(self) -> bool:
        """
        Test the Notion API connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Try to get user info
            response = self.client.users.me()
            print("✅ Notion API connection successful!")
            print(f"Connected as: {response.get('name', 'Unknown')}")
            return True

        except Exception as e:
            print(f"❌ Notion API connection failed: {e}")
            return False

    def create_file_upload(self, filename: str, file_size: int) -> Optional[Dict[str, Any]]:
        """
        Create a file upload and get upload URL.
        Step 1 of Notion's File Upload API.

        Args:
            filename: Name of the file to upload
            file_size: Size of the file in bytes

        Returns:
            Dictionary with upload_url, file_upload_id, and expiration_time, or None if failed
        """
        try:
            url = "https://api.notion.com/v1/file_uploads"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            payload = {
                "name": filename,
                "file_size": file_size
            }

            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()

            result = response.json()
            print(f"✅ Created file upload for {filename} (ID: {result.get('id', 'unknown')[:8]}...)")

            return result

        except Exception as e:
            print(f"❌ Error creating file upload: {e}")
            return None

    def send_file_to_upload(self, upload_url: str, file_bytes: bytes, content_type: str = "image/jpeg") -> bool:
        """
        Send file bytes to the upload URL.
        Step 2 of Notion's File Upload API.

        The upload_url is a Notion endpoint (/send) where we POST the file as multipart/form-data.

        Args:
            upload_url: The upload URL from create_file_upload (Notion /send endpoint)
            file_bytes: The file content as bytes
            content_type: MIME type of the file

        Returns:
            True if successful, False otherwise
        """
        try:
            # POST the file as multipart/form-data to Notion's /send endpoint
            # The file must be sent with the field name 'file'
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": "2022-06-28"
            }

            # Create multipart/form-data with the file
            files = {
                'file': ('image.jpg', file_bytes, content_type)
            }

            response = requests.post(upload_url, files=files, headers=headers)

            if response.status_code in [200, 201, 204]:
                print(f"✅ Successfully uploaded file ({len(file_bytes)} bytes)")
                return True
            else:
                print(f"❌ Upload failed with status {response.status_code}: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Error uploading file: {e}")
            import traceback
            traceback.print_exc()
            return False

    def complete_file_upload(self, file_upload_id: str) -> Optional[Dict[str, Any]]:
        """
        Complete the file upload and get the permanent Notion-hosted URL.
        Step 3 of Notion's File Upload API.

        Args:
            file_upload_id: The file upload ID from create_file_upload

        Returns:
            File object with permanent URL, or None if failed
        """
        try:
            url = f"https://api.notion.com/v1/file_uploads/{file_upload_id}/complete"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": "2022-06-28"
            }

            response = requests.post(url, headers=headers)

            # Print detailed error if it fails
            if response.status_code != 200:
                print(f"❌ Complete failed with status {response.status_code}: {response.text}")
                return None

            result = response.json()
            file_url = result.get("file", {}).get("url", "")

            if file_url:
                print(f"✅ File upload completed! Notion URL: {file_url[:50]}...")
            else:
                print(f"⚠️ File upload completed but no URL returned. Response: {result}")

            return result

        except Exception as e:
            print(f"❌ Error completing file upload: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_database_schema(self, database_id: str) -> Dict[str, Any]:
        """
        Get the schema of a database.

        Args:
            database_id: ID of the database

        Returns:
            Database schema information
        """
        try:
            database = self.get_database(database_id)
            return database.get("properties", {})

        except Exception as e:
            print(f"Error getting database schema: {e}")
            return {}

    def search_pages(self, query: str = "", filter_conditions: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for pages in Notion.

        Args:
            query: Search query
            filter_conditions: Optional filter conditions

        Returns:
            List of matching pages
        """
        try:
            search_params = {"query": query}

            if filter_conditions:
                search_params["filter"] = filter_conditions

            response = self.client.search(**search_params)
            return response.get("results", [])

        except Exception as e:
            print(f"Error searching Notion pages: {e}")
            return []

    def create_relation_property(self, page_ids: List[str]) -> Dict[str, Any]:
        """
        Create a relation property for linking pages.

        Args:
            page_ids: List of page IDs to link

        Returns:
            Relation property dictionary
        """
        return {
            "relation": [{"id": page_id} for page_id in page_ids]
        }

    def get_page_id_by_property(self, database_id: str, property_name: str, value: str) -> Optional[str]:
        """
        Get a page ID by searching for a specific property value.

        Args:
            database_id: ID of the database to search
            property_name: Name of the property to search
            value: Value to search for

        Returns:
            Page ID if found, None otherwise
        """
        try:
            filter_conditions = {
                "property": property_name,
                "rich_text": {
                    "equals": value
                }
            }

            results = self.query_database(
                database_id=database_id,
                filter_conditions=filter_conditions
            )

            return results[0]['id'] if results else None

        except Exception as e:
            print(f"Error getting page ID by property: {e}")
            return None

# Convenience functions
def create_notion_client() -> NotionClient:
    """
    Create a Notion client with default configuration.

    Returns:
        Configured NotionClient instance
    """
    return NotionClient()

def test_notion_setup() -> bool:
    """
    Test the complete Notion setup.

    Returns:
        True if setup is working, False otherwise
    """
    try:
        client = create_notion_client()

        # Test connection
        if not client.test_connection():
            return False

        # Test database access
        if config.NOTION_DB_RAPPORTS:
            schema = client.get_database_schema(config.NOTION_DB_RAPPORTS)
            if not schema:
                print("❌ Cannot access Rapports database")
                return False

        if config.NOTION_DB_INTERVENTIONS:
            schema = client.get_database_schema(config.NOTION_DB_INTERVENTIONS)
            if not schema:
                print("❌ Cannot access Interventions database")
                return False

        print("✅ Notion setup is working correctly!")
        return True

    except Exception as e:
        print(f"❌ Notion setup test failed: {e}")
        return False

if __name__ == "__main__":
    # Test the Notion client
    test_notion_setup()
