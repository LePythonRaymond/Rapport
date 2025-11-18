from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from .auth import get_authenticated_service
from .people_resolver import PeopleResolver, format_name

class GoogleChatClient:
    """
    Client for interacting with Google Chat API to fetch messages and attachments.
    """

    def __init__(self):
        self.service = get_authenticated_service()
        # Initialize People API resolver for user name resolution
        try:
            self.people_resolver = PeopleResolver()
        except Exception as e:
            print(f"⚠️ Could not initialize People API resolver: {e}")
            self.people_resolver = None

    def get_messages_for_space(self, space_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        Fetch messages from a Google Chat space within the specified date range.

        Args:
            space_id: The Google Chat space ID (e.g., "spaces/AAAA...")
            start_date: Start date in ISO format (e.g., "2024-01-01T00:00:00Z")
            end_date: End date in ISO format (e.g., "2024-01-31T23:59:59Z")

        Returns:
            List of message dictionaries with text, author, timestamp, and attachments
        """
        messages = []
        page_token = None

        # Build filter for date range only if dates are provided
        # Google Chat API requires RFC 3339 format with double quotes
        # Use > and < operators as shown in documentation examples
        filter_query = None
        if start_date and end_date:
            filter_query = f'createTime > "{start_date}" AND createTime < "{end_date}"'
        elif start_date:
            filter_query = f'createTime > "{start_date}"'
        elif end_date:
            filter_query = f'createTime < "{end_date}"'

        try:
            while True:
                # Request messages with pagination
                request_params = {
                    'parent': space_id,
                    'pageSize': 100
                }

                # Add filter only if we have one
                if filter_query:
                    request_params['filter'] = filter_query

                if page_token:
                    request_params['pageToken'] = page_token

                request = self.service.spaces().messages().list(**request_params)

                response = request.execute()

                # Process messages
                for message in response.get('messages', []):
                    processed_message = self._process_message(message)
                    if processed_message:
                        messages.append(processed_message)

                # Check for more pages
                page_token = response.get('nextPageToken')
                if not page_token:
                    break

        except Exception as e:
            print(f"Error fetching messages from {space_id}: {e}")
            return []

        # Sort messages by creation time (oldest first)
        messages.sort(key=lambda x: x['createTime'])
        return messages

    def _process_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a raw Google Chat message into our standardized format.

        Args:
            message: Raw message from Google Chat API

        Returns:
            Processed message dictionary or None if message should be skipped
        """
        try:
            # Extract basic message info
            message_id = message.get('name', '')
            create_time = message.get('createTime', '')
            text = message.get('text', '')

            # Skip only messages with no text AND no attachments
            # (Images often come with minimal or no text)
            # Note: Google Chat API uses 'attachment' (singular), not 'attachments'
            if not text.strip() and not message.get('attachment'):
                return None

            # Extract author info with improved fallback logic
            author_info = message.get('sender', {})

            # Debug: Log sender structure for troubleshooting
            if not author_info:
                print(f"⚠️ No sender info found in message: {message.get('name', 'unknown_id')}")

            # Try multiple strategies to extract author name
            author_name = 'Unknown'
            author_email = ''

            # Strategy 1: Try displayName (primary method)
            if author_info.get('displayName'):
                author_name = format_name(author_info.get('displayName'))
                print(f"✅ Extracted author name from displayName: {author_name}")
            else:
                # Strategy 2: Try to extract from sender.name (might be email or resource name)
                sender_name = author_info.get('name', '')
                if sender_name:
                    # Check if it's an email address
                    if '@' in sender_name:
                        # Extract name from email (part before @)
                        email_parts = sender_name.split('@')[0]
                        # Try to format it (e.g., "edward.carey" -> "Edward Carey")
                        formatted_name = email_parts.replace('.', ' ').replace('_', ' ').title()
                        author_name = format_name(formatted_name)
                        author_email = sender_name
                        print(f"✅ Extracted author name from email: {author_name} (from {sender_name})")
                    elif sender_name.startswith('users/'):
                        # It's a resource name, try to resolve via People API
                        print(f"🔍 Sender name is a resource name: {sender_name}, attempting People API resolution")
                        author_email = sender_name

                        # Try to resolve via People API
                        if self.people_resolver:
                            resolved = self.people_resolver.resolve_user_id(sender_name)
                            if resolved and resolved.get('name'):
                                # Name is already formatted by PeopleResolver
                                author_name = resolved['name']
                                if resolved.get('email'):
                                    author_email = resolved['email']
                                print(f"✅ Resolved user from People API: {author_name}")
                            else:
                                # People API resolution failed, use fallback
                                parts = sender_name.split('/')
                                if len(parts) > 1:
                                    resource_id = parts[-1]
                                    author_name = f"User {resource_id[:8]}"  # Fallback with partial ID
                                print(f"⚠️ Could not resolve {sender_name} via People API, using fallback: {author_name}")
                        else:
                            # No People API resolver available
                            parts = sender_name.split('/')
                            if len(parts) > 1:
                                resource_id = parts[-1]
                                author_name = f"User {resource_id[:8]}"  # Fallback with partial ID
                            print(f"⚠️ People API resolver not available, using fallback: {author_name}")
                    else:
                        # Unknown format, use as-is
                        author_name = sender_name
                        author_email = sender_name
                        print(f"⚠️ Using sender.name directly: {author_name}")

            # If we still don't have an email, try to get it from author_info
            if not author_email:
                author_email = author_info.get('name', '')

            # Final fallback: ensure we have something
            if not author_name or author_name == 'Unknown':
                print(f"⚠️ Could not extract author name, using fallback. Sender structure: {author_info}")

            # Extract attachments (Google Chat API uses 'attachment' singular, not 'attachments')
            attachments = []
            attachment_list = message.get('attachment', [])  # Fixed: use 'attachment' not 'attachments'

            for attachment in attachment_list:
                if attachment.get('attachmentDataRef'):
                    attachment_info = {
                        'name': attachment.get('contentName', attachment.get('name', '')),  # Use contentName for actual filename
                        'contentType': attachment.get('contentType', ''),
                        'downloadUri': attachment.get('downloadUri', ''),  # Use direct downloadUri
                        'attachmentDataRef': attachment.get('attachmentDataRef', {})
                    }
                    attachments.append(attachment_info)
                    print(f"📎 Captured attachment: {attachment_info['name']} ({attachment_info['contentType']})")

            if attachments:
                print(f"✅ Message has {len(attachments)} attachments")

            # Build processed message
            processed = {
                'id': message_id,
                'createTime': create_time,
                'text': text,
                'author': {
                    'name': author_name,
                    'email': author_email
                },
                'attachments': attachments,
                'raw_message': message  # Keep original for debugging
            }

            return processed

        except Exception as e:
            print(f"Error processing message: {e}")
            return None

    def get_space_info(self, space_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific space.

        Args:
            space_id: The Google Chat space ID

        Returns:
            Space information dictionary or None if not found
        """
        try:
            space = self.service.spaces().get(name=space_id).execute()
            return {
                'name': space.get('name', ''),
                'displayName': space.get('displayName', ''),
                'spaceType': space.get('spaceType', ''),
                'spaceDetails': space.get('spaceDetails', {})
            }
        except Exception as e:
            print(f"Error getting space info for {space_id}: {e}")
            return None

    def list_accessible_spaces(self) -> List[Dict[str, Any]]:
        """
        List all spaces accessible to the authenticated user.

        Returns:
            List of space information dictionaries
        """
        try:
            response = self.service.spaces().list().execute()
            spaces = []

            for space in response.get('spaces', []):
                space_info = {
                    'name': space.get('name', ''),
                    'displayName': space.get('displayName', ''),
                    'spaceType': space.get('spaceType', ''),
                    'spaceDetails': space.get('spaceDetails', {})
                }
                spaces.append(space_info)

            return spaces

        except Exception as e:
            print(f"Error listing spaces: {e}")
            return []

    def download_attachment(self, space_id: str, attachment_name: str) -> Optional[bytes]:
        """
        Download an attachment from a Google Chat space.

        Args:
            space_id: The Google Chat space ID
            attachment_name: The attachment resource name

        Returns:
            Attachment content as bytes or None if download fails
        """
        try:
            # Use the media download method
            request = self.service.media().download_media(
                resourceName=attachment_name
            )

            # Execute the request and get the content
            content = request.execute()
            return content

        except Exception as e:
            print(f"Error downloading attachment {attachment_name}: {e}")
            return None

def format_date_for_api(date_obj: datetime) -> str:
    """
    Format a datetime object for Google Chat API filter.
    Google Chat API expects RFC 3339 format with timezone: YYYY-MM-DDTHH:MM:SS+00:00

    Args:
        date_obj: Python datetime object

    Returns:
        RFC 3339 format string for API with timezone
    """
    if date_obj.tzinfo is None:
        date_obj = date_obj.replace(tzinfo=timezone.utc)

    # Format as RFC 3339 with timezone (YYYY-MM-DDTHH:MM:SS+00:00)
    return date_obj.strftime('%Y-%m-%dT%H:%M:%S+00:00')

def get_messages_for_client(client_name: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Convenience function to get messages for a specific client.

    Args:
        client_name: Name of the client (must be in CLIENT_CHAT_MAPPING)
        start_date: Start date for message filtering
        end_date: End date for message filtering

    Returns:
        List of processed messages
    """
    import config

    if client_name not in config.CLIENT_CHAT_MAPPING:
        print(f"Client '{client_name}' not found in CLIENT_CHAT_MAPPING")
        return []

    raw_space_id = config.CLIENT_CHAT_MAPPING[client_name]
    # Convert the URL to proper space ID format for Google Chat API
    space_id = config.extract_space_id_from_url(raw_space_id)
    start_date_str = format_date_for_api(start_date)
    end_date_str = format_date_for_api(end_date)

    client = GoogleChatClient()
    return client.get_messages_for_space(space_id, start_date_str, end_date_str)

if __name__ == "__main__":
    # Test the client
    client = GoogleChatClient()
    spaces = client.list_accessible_spaces()
    print(f"Found {len(spaces)} accessible spaces:")
    for space in spaces:
        print(f"- {space['displayName']} ({space['name']})")
