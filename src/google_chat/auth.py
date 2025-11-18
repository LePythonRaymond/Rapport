import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

# Scopes required for Google Chat API and People API
SCOPES = [
    'https://www.googleapis.com/auth/chat.spaces.readonly',
    'https://www.googleapis.com/auth/chat.messages.readonly',
    'https://www.googleapis.com/auth/chat.messages',  # For attachments
    'https://www.googleapis.com/auth/directory.readonly'  # For People API to resolve user names
]

# Token file to store credentials
TOKEN_FILE = 'token.pickle'

def get_authenticated_service():
    """
    Authenticate with Google Chat API and return the service object.
    Handles OAuth flow and token refresh automatically.
    """
    creds = None

    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None

        if not creds:
            if not config.GOOGLE_CREDENTIALS_PATH or not os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials file not found at {config.GOOGLE_CREDENTIALS_PATH}. "
                    "Please ensure credentials.json is in the project root."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                config.GOOGLE_CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    # Build and return the Chat API service
    service = build('chat', 'v1', credentials=creds)
    return service

def get_credentials():
    """
    Get authenticated credentials for Google APIs.
    Used by services that need raw credentials (like PeopleResolver).

    Returns:
        Credentials object with proper scopes
    """
    creds = None

    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None

        if not creds:
            if not config.GOOGLE_CREDENTIALS_PATH or not os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Google credentials file not found at {config.GOOGLE_CREDENTIALS_PATH}. "
                    "Please ensure credentials.json is in the project root."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                config.GOOGLE_CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return creds

def revoke_credentials():
    """
    Revoke stored credentials and delete token file.
    Useful for testing or if credentials become corrupted.
    """
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

        if creds and creds.token:
            try:
                creds.revoke(Request())
            except Exception as e:
                print(f"Error revoking credentials: {e}")

        os.remove(TOKEN_FILE)
        print("Credentials revoked and token file deleted.")

def test_authentication():
    """
    Test the authentication by making a simple API call.
    Returns True if successful, False otherwise.
    """
    try:
        service = get_authenticated_service()
        # Try to list spaces to test authentication
        result = service.spaces().list().execute()
        print("✅ Google Chat API authentication successful!")
        print(f"Found {len(result.get('spaces', []))} accessible spaces.")
        return True
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False

if __name__ == "__main__":
    # Test authentication when run directly
    test_authentication()
