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
        # Try to access the secret
        token_b64 = None
        try:
            if hasattr(st, 'secrets'):
                # Check if key exists
                if 'GOOGLE_TOKEN_PICKLE_B64' in st.secrets:
                    token_b64 = st.secrets['GOOGLE_TOKEN_PICKLE_B64']
                    print(f"✅ Found GOOGLE_TOKEN_PICKLE_B64 in secrets (length: {len(token_b64) if token_b64 else 0})")
                else:
                    print("⚠️ GOOGLE_TOKEN_PICKLE_B64 not found in st.secrets")
                    # Try to list available keys for debugging
                    try:
                        available_keys = list(st.secrets.keys()) if hasattr(st.secrets, 'keys') else []
                        print(f"Available secret keys: {available_keys[:10]}...")  # Show first 10
                    except:
                        pass
        except Exception as secret_error:
            print(f"Error accessing st.secrets: {secret_error}")

        if token_b64:
            try:
                # Decode base64 and unpickle
                token_bytes = base64.b64decode(token_b64)
                creds = pickle.loads(token_bytes)
                print("✅ Successfully decoded and loaded token from Streamlit secrets")
                return creds
            except Exception as decode_error:
                print(f"❌ Error decoding token from secrets: {decode_error}")
                import traceback
                traceback.print_exc()
                try:
                    import streamlit as st
                    st.error(f"Error loading Google token from secrets: {decode_error}")
                except:
                    pass
                return None
        else:
            print("⚠️ GOOGLE_TOKEN_PICKLE_B64 is None or empty")
    except Exception as e:
        print(f"Could not load token from secrets: {e}")
        import traceback
        traceback.print_exc()
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

            # In headless environments (Streamlit Cloud), we can't use browser flow
            if _is_headless_environment():
                # Check if token should have been loaded from secrets
                try:
                    import streamlit as st
                    st.error("🔐 **Google Authentication Token Not Found**")
                    st.markdown("""
                    **The Google OAuth token was not found in Streamlit secrets.**

                    **To fix this:**

                    1. **Verify** that `GOOGLE_TOKEN_PICKLE_B64` is set in your Streamlit Cloud secrets
                    2. **Check** that the base64 string is complete and correct
                    3. **Re-authenticate locally** if needed and regenerate the token

                    **Note:** In Streamlit Cloud, you cannot authenticate interactively.
                    You must provide the token via secrets.
                    """)
                    raise Exception(
                        "Google authentication token not found in Streamlit secrets. "
                        "Please add GOOGLE_TOKEN_PICKLE_B64 to your Streamlit Cloud secrets. "
                        "Authenticate locally first to generate the token, then add it to secrets."
                    )
                except ImportError:
                    # Not in Streamlit, raise the original error
                    raise Exception(
                        "Cannot authenticate in headless environment. "
                        "Please provide GOOGLE_TOKEN_PICKLE_B64 in secrets or authenticate locally first."
                    )
            else:
                # Local development: use browser flow
                try:
                    creds = flow.run_local_server(port=0)
                except Exception as browser_error:
                    # If browser flow fails, provide helpful error
                    if "could not locate runnable browser" in str(browser_error).lower():
                        raise Exception(
                            "Browser not available for OAuth. "
                            "Please ensure you have a browser installed, or provide GOOGLE_TOKEN_PICKLE_B64 in secrets."
                        ) from browser_error
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

            # In headless environments (Streamlit Cloud), we can't use browser flow
            if _is_headless_environment():
                # Check if token should have been loaded from secrets
                try:
                    import streamlit as st
                    st.error("🔐 **Google Authentication Token Not Found**")
                    st.markdown("""
                    **The Google OAuth token was not found in Streamlit secrets.**

                    **To fix this:**

                    1. **Verify** that `GOOGLE_TOKEN_PICKLE_B64` is set in your Streamlit Cloud secrets
                    2. **Check** that the base64 string is complete and correct
                    3. **Re-authenticate locally** if needed and regenerate the token

                    **Note:** In Streamlit Cloud, you cannot authenticate interactively.
                    You must provide the token via secrets.
                    """)
                    raise Exception(
                        "Google authentication token not found in Streamlit secrets. "
                        "Please add GOOGLE_TOKEN_PICKLE_B64 to your Streamlit Cloud secrets. "
                        "Authenticate locally first to generate the token, then add it to secrets."
                    )
                except ImportError:
                    # Not in Streamlit, raise the original error
                    raise Exception(
                        "Cannot authenticate in headless environment. "
                        "Please provide GOOGLE_TOKEN_PICKLE_B64 in secrets or authenticate locally first."
                    )
            else:
                # Local development: use browser flow
                try:
                    creds = flow.run_local_server(port=0)
                except Exception as browser_error:
                    # If browser flow fails, provide helpful error
                    if "could not locate runnable browser" in str(browser_error).lower():
                        raise Exception(
                            "Browser not available for OAuth. "
                            "Please ensure you have a browser installed, or provide GOOGLE_TOKEN_PICKLE_B64 in secrets."
                        ) from browser_error
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
