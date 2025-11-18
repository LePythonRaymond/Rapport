from typing import Dict, Optional, List
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from .auth import get_credentials


def format_name(name: str) -> str:
    """
    Format a full name with proper capitalization.
    Capitalizes the first letter of each word (first name, last name, etc.).

    Examples:
        "edward carey" -> "Edward Carey"
        "JOHN DOE" -> "John Doe"
        "marie-pierre DUPONT" -> "Marie-pierre Dupont"
        "jean-marc MARTIN" -> "Jean-marc Martin"

    Args:
        name: Full name string

    Returns:
        Formatted name with proper capitalization
    """
    if not name or not name.strip():
        return name

    # Split by spaces and capitalize each word
    words = name.strip().split()
    formatted_words = []

    for word in words:
        if not word:
            continue
        # Capitalize first letter, lowercase the rest
        formatted_word = word[0].upper() + word[1:].lower() if len(word) > 1 else word[0].upper()
        formatted_words.append(formatted_word)

    return ' '.join(formatted_words)


class PeopleResolver:
    """
    Resolves Google Chat user IDs (users/{id}) to actual display names using the People API.
    Includes caching to minimize API calls.
    """

    def __init__(self):
        """
        Initialize the People API service and cache.
        """
        try:
            self.service = build('people', 'v1', credentials=get_credentials())
            self.cache = {}  # {user_id: {name, email, cached_at}}
            self.cache_ttl = timedelta(hours=24)
            print("✅ People API resolver initialized")
        except Exception as e:
            print(f"⚠️ Failed to initialize People API: {e}")
            self.service = None
            self.cache = {}

    def resolve_user_id(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Resolve a Google Chat user ID to a display name and email.

        Args:
            user_id: User resource name (e.g., "users/123456")

        Returns:
            Dict with 'name' and 'email' keys, or None if resolution fails
        """
        if not self.service:
            print(f"⚠️ People API not available, cannot resolve {user_id}")
            return None

        # Check cache first
        if user_id in self.cache:
            cached = self.cache[user_id]
            if datetime.now() - cached.get('cached_at', datetime.min) < self.cache_ttl:
                print(f"💾 Cache hit for {user_id}: {cached.get('name', 'Unknown')}")
                return cached

        # Extract numeric ID from "users/123456"
        if not user_id.startswith('users/'):
            print(f"⚠️ Invalid user ID format: {user_id}")
            return None

        numeric_id = user_id.split('/')[-1]

        try:
            print(f"🔍 Resolving user via People API: {user_id}")

            # Call People API
            person = self.service.people().get(
                resourceName=f'people/{numeric_id}',
                personFields='names,emailAddresses'
            ).execute()

            # Extract name and email
            names = person.get('names', [])
            emails = person.get('emailAddresses', [])

            name = names[0].get('displayName') if names else None
            email = emails[0].get('value') if emails else None

            if not name:
                print(f"⚠️ No displayName found for {user_id}")
                return None

            # Format the name with proper capitalization
            formatted_name = format_name(name)

            result = {
                'name': formatted_name,
                'email': email,
                'cached_at': datetime.now()
            }

            # Cache result
            self.cache[user_id] = result
            print(f"✅ Resolved user from People API: {formatted_name} ({email})")

            return result

        except Exception as e:
            print(f"⚠️ Failed to resolve user {user_id}: {e}")
            # Cache the failure to avoid repeated API calls for unresolvable users
            self.cache[user_id] = {
                'name': None,
                'email': None,
                'cached_at': datetime.now()
            }
            return None

    def batch_resolve(self, user_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Resolve multiple user IDs in a single batch request.

        Args:
            user_ids: List of user resource names

        Returns:
            Dict mapping user_id to {name, email}
        """
        if not self.service:
            print(f"⚠️ People API not available, cannot batch resolve")
            return {}

        # Filter out already cached IDs
        uncached_ids = []
        results = {}

        for user_id in user_ids:
            if user_id in self.cache:
                cached = self.cache[user_id]
                if datetime.now() - cached.get('cached_at', datetime.min) < self.cache_ttl:
                    results[user_id] = cached
                    continue
            uncached_ids.append(user_id)

        if not uncached_ids:
            print(f"💾 All {len(user_ids)} users found in cache")
            return results

        print(f"🔍 Batch resolving {len(uncached_ids)} users via People API")

        # Convert to People API resource names
        resource_names = [f"people/{uid.split('/')[-1]}" for uid in uncached_ids if uid.startswith('users/')]

        if not resource_names:
            return results

        try:
            # Batch get from People API
            response = self.service.people().getBatchGet(
                resourceNames=resource_names,
                personFields='names,emailAddresses'
            ).execute()

            # Process responses
            for i, person_response in enumerate(response.get('responses', [])):
                user_id = uncached_ids[i]
                person = person_response.get('person', {})

                names = person.get('names', [])
                emails = person.get('emailAddresses', [])

                name = names[0].get('displayName') if names else None
                email = emails[0].get('value') if emails else None

                if name:
                    # Format the name with proper capitalization
                    formatted_name = format_name(name)
                    result = {
                        'name': formatted_name,
                        'email': email,
                        'cached_at': datetime.now()
                    }
                    self.cache[user_id] = result
                    results[user_id] = result
                    print(f"✅ Batch resolved: {formatted_name}")

            print(f"✅ Batch resolved {len(results) - len([r for r in results.values() if 'cached_at' in r])} new users")

        except Exception as e:
            print(f"⚠️ Batch resolution failed: {e}")

        return results

    def clear_cache(self):
        """Clear the name resolution cache."""
        self.cache.clear()
        print("🗑️ People API cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about the cache."""
        total = len(self.cache)
        expired = sum(1 for v in self.cache.values()
                     if datetime.now() - v.get('cached_at', datetime.min) >= self.cache_ttl)
        return {
            'total': total,
            'active': total - expired,
            'expired': expired
        }
