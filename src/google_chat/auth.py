import os
import pickle
import base64
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

def _is_headless_environment():
    """
    Check if we're running in a headless environment (no browser available).
    This is true for Streamlit Cloud, Docker containers, etc.
    """
    # Check for common headless environment indicators
    if os.getenv('STREAMLIT_SERVER_HEADLESS') == 'true':
        return True
    if os.getenv('CI') == 'true':
        return True
    if not _has_browser_available():
        return True
    return False

def _has_browser_available():
    """
    Check if a browser is available in the environment.
    """
    try:
        import webbrowser
        # Try to get a browser - if it fails, we're headless
        browser = webbrowser.get()
        return browser is not None
    except Exception:
        return False

def _load_token_from_secrets():
    """
    Load token from Streamlit secrets (base64 encoded).
    Returns Credentials object or None if not found.
    """
    try:
        import streamlit as st
        token_b64 = _get_secret("GOOGLE_TOKEN_PICKLE_B64")
        if token_b64:
            # Decode base64 and unpickle
            token_bytes = base64.b64decode(token_b64)
            creds = pickle.loads(token_bytes)
            return creds
    except Exception as e:
        print(f"Could not load token from secrets: {e}")
    return None

def _get_secret(key: str):
    """
    Get a secret from Streamlit secrets or environment variables.
    """
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except (ImportError, AttributeError, KeyError):
        pass
    # Fallback to environment variable
    return os.getenv(key)

def get_authenticated_service():
    """
    Authenticate with Google Chat API and return the service object.
    Handles OAuth flow and token refresh automatically.
    """
    creds = None

    # Try loading from Streamlit secrets first (for Streamlit Cloud)
    creds = _load_token_from_secrets()

    # Fallback to file if not in secrets
    if not creds and os.path.exists(TOKEN_FILE):
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

            # Use console flow for headless environments (Streamlit Cloud)
            if _is_headless_environment():
                # In headless environments, we can't use browser flow
                # Try console flow which prints URL to console
                try:
                    creds = flow.run_console()
                except Exception as console_error:
                    # If console flow also fails, provide helpful error message
                    try:
                        import streamlit as st
                        st.error("🔐 **Google Authentication Required for Streamlit Cloud**")
                        st.markdown("""
                        **To use Google Chat API in Streamlit Cloud, you need to authenticate first:**

                        1. **Run the app locally** and authenticate (this will create `token.pickle`)
                        2. **Upload `token.pickle`** to your Streamlit Cloud app's file system
                        3. **Or** add the token as a secret in Streamlit Cloud settings

                        **Alternative:** You can authenticate locally and then the token will work in both environments.
                        """)
                        raise Exception(
                            "Google authentication requires browser access. "
                            "Please authenticate locally first to generate token.pickle, "
                            "then upload it to Streamlit Cloud."
                        ) from console_error
                    except ImportError:
                        # Not in Streamlit, raise the original error
                        raise Exception(
                            "Cannot authenticate in headless environment. "
                            "Please run authentication locally first."
                        ) from console_error
            else:
                # Local development: use browser flow
                try:
                    creds = flow.run_local_server(port=0)
                except Exception as browser_error:
                    # If browser flow fails, try console as fallback
                    if "could not locate runnable browser" in str(browser_error).lower():
                        print("⚠️ Browser not available, using console flow instead...")
                        creds = flow.run_console()
                    else:
                        raise

        # Save credentials for next run (only if we have file system access)
        # In Streamlit Cloud, we don't save to file since we use secrets
        if not _is_headless_environment() or os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Could not save token to file: {e}")

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

    # Try loading from Streamlit secrets first (for Streamlit Cloud)
    creds = _load_token_from_secrets()

    # Fallback to file if not in secrets
    if not creds and os.path.exists(TOKEN_FILE):
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

            # Use console flow for headless environments (Streamlit Cloud)
            if _is_headless_environment():
                # In headless environments, we can't use browser flow
                # Try console flow which prints URL to console
                try:
                    creds = flow.run_console()
                except Exception as console_error:
                    # If console flow also fails, provide helpful error message
                    try:
                        import streamlit as st
                        st.error("🔐 **Google Authentication Required for Streamlit Cloud**")
                        st.markdown("""
                        **To use Google Chat API in Streamlit Cloud, you need to authenticate first:**

                        1. **Run the app locally** and authenticate (this will create `token.pickle`)
                        2. **Upload `token.pickle`** to your Streamlit Cloud app's file system
                        3. **Or** add the token as a secret in Streamlit Cloud settings

                        **Alternative:** You can authenticate locally and then the token will work in both environments.
                        """)
                        raise Exception(
                            "Google authentication requires browser access. "
                            "Please authenticate locally first to generate token.pickle, "
                            "then upload it to Streamlit Cloud."
                        ) from console_error
                    except ImportError:
                        # Not in Streamlit, raise the original error
                        raise Exception(
                            "Cannot authenticate in headless environment. "
                            "Please run authentication locally first."
                        ) from console_error
            else:
                # Local development: use browser flow
                try:
                    creds = flow.run_local_server(port=0)
                except Exception as browser_error:
                    # If browser flow fails, try console as fallback
                    if "could not locate runnable browser" in str(browser_error).lower():
                        print("⚠️ Browser not available, using console flow instead...")
                        creds = flow.run_console()
                    else:
                        raise

        # Save credentials for next run (only if we have file system access)
        # In Streamlit Cloud, we don't save to file since we use secrets
        if not _is_headless_environment() or os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
            except Exception as e:
                print(f"Could not save token to file: {e}")

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
