"""
Resolve Google Chat author emails to Notion user IDs.

The 'QUI ?' Person property in the REMPLA DB requires a Notion user ID
(a user present in the workspace). We build an email -> user_id index once
per run by paginating GET /v1/users, and look up authors as needed.
"""

from typing import Dict, List, Optional

import requests


class NotionUserResolver:
    """
    Lightweight resolver that maps lowercased emails to Notion user IDs.

    Uses the public Notion Users API (GET /v1/users) which the integration
    can access as long as it has been added to the workspace. Case-insensitive
    email matching; bot users are skipped.
    """

    USERS_ENDPOINT = "https://api.notion.com/v1/users"
    NOTION_API_VERSION = "2022-06-28"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Notion API key is required for NotionUserResolver")
        self.api_key = api_key
        self._email_to_id: Optional[Dict[str, str]] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.NOTION_API_VERSION,
        }

    def _fetch_all_users(self) -> List[Dict]:
        users: List[Dict] = []
        start_cursor: Optional[str] = None

        while True:
            params: Dict[str, str] = {"page_size": "100"}
            if start_cursor:
                params["start_cursor"] = start_cursor

            response = requests.get(
                self.USERS_ENDPOINT,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            users.extend(data.get("results", []))

            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")
            if not start_cursor:
                break

        return users

    def _build_index(self) -> Dict[str, str]:
        """Build a lowercased email -> user_id map, skipping bots."""
        email_to_id: Dict[str, str] = {}

        try:
            users = self._fetch_all_users()
        except Exception as e:
            print(f"Could not fetch Notion users for email resolution: {e}")
            return email_to_id

        for user in users:
            if user.get("type") != "person":
                continue
            person = user.get("person") or {}
            email = person.get("email")
            user_id = user.get("id")
            if email and user_id:
                email_to_id[email.strip().lower()] = user_id

        print(f"Indexed {len(email_to_id)} Notion users by email")
        return email_to_id

    def resolve(self, email: Optional[str]) -> Optional[str]:
        """
        Return the Notion user ID for a given email, or None if no match.

        Lazily builds the email index on first use, then reuses it for the
        lifetime of the resolver (one scanner run).
        """
        if not email:
            return None

        normalized = email.strip().lower()
        if "@" not in normalized:
            return None

        if self._email_to_id is None:
            self._email_to_id = self._build_index()

        return self._email_to_id.get(normalized)
