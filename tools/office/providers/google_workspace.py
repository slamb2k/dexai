"""
Tool: Google Workspace Provider
Purpose: Gmail and Google Calendar integration via Google APIs

Implements the OfficeProvider interface for Google Workspace.
Supports all integration levels (2-5) for Gmail and Google Calendar.

Usage:
    from tools.office.providers.google_workspace import GoogleWorkspaceProvider

    provider = GoogleWorkspaceProvider(account)
    emails = await provider.get_emails(limit=10)
    events = await provider.get_events()

Dependencies:
    - aiohttp (pip install aiohttp)
    - google-auth (pip install google-auth) [optional, for service accounts]
"""

import base64
import email.utils
import json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

from tools.office.models import (
    Attendee,
    CalendarEvent,
    Email,
    EmailAddress,
    IntegrationLevel,
    OfficeAccount,
)
from tools.office.providers.base import OfficeProvider


# Google API endpoints
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class GoogleWorkspaceProvider(OfficeProvider):
    """
    Google Workspace provider for Gmail and Google Calendar.

    Implements read operations for Level 2, draft operations for Level 3,
    send operations for Level 4, and autonomous operations for Level 5.
    """

    @property
    def provider_name(self) -> str:
        return "google"

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {self.account.access_token}",
            "Content-Type": "application/json",
        }

    async def _make_request(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method
            url: Full API URL
            data: Request body (for POST/PUT)
            params: Query parameters

        Returns:
            dict with response data or error
        """
        try:
            import aiohttp
        except ImportError:
            return {"success": False, "error": "aiohttp not installed"}

        headers = self._get_headers()

        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=params) as resp:
                        return await self._handle_response(resp)
                elif method == "POST":
                    async with session.post(url, headers=headers, json=data, params=params) as resp:
                        return await self._handle_response(resp)
                elif method == "PUT":
                    async with session.put(url, headers=headers, json=data, params=params) as resp:
                        return await self._handle_response(resp)
                elif method == "PATCH":
                    async with session.patch(url, headers=headers, json=data, params=params) as resp:
                        return await self._handle_response(resp)
                elif method == "DELETE":
                    async with session.delete(url, headers=headers, params=params) as resp:
                        return await self._handle_response(resp)
                else:
                    return {"success": False, "error": f"Unknown method: {method}"}

        except Exception as e:
            return {"success": False, "error": f"Request failed: {e!s}"}

    async def _handle_response(self, resp) -> dict[str, Any]:
        """Handle API response."""
        if resp.status == 204:
            return {"success": True}

        try:
            data = await resp.json()
        except Exception:
            data = {}

        if resp.status == 200:
            return {"success": True, "data": data}
        elif resp.status == 401:
            return {"success": False, "error": "Authentication failed - token may be expired"}
        elif resp.status == 403:
            return {"success": False, "error": "Permission denied - insufficient scopes"}
        elif resp.status == 404:
            return {"success": False, "error": "Resource not found"}
        else:
            error_msg = data.get("error", {}).get("message", f"HTTP {resp.status}")
            return {"success": False, "error": error_msg}

    async def authenticate(self) -> dict[str, Any]:
        """Verify authentication by making a test API call."""
        if not self.account.access_token:
            return {"success": False, "error": "No access token"}

        # Check if token is expired
        if self.account.is_token_expired():
            # Try to refresh
            if self.account.refresh_token:
                from tools.office.oauth_manager import refresh_access_token

                result = await refresh_access_token("google", self.account.refresh_token)
                if result.get("success"):
                    self.account.access_token = result["access_token"]
                    # Update expiry
                    expires_in = result.get("expires_in", 3600)
                    self.account.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                else:
                    return {"success": False, "error": "Token refresh failed"}
            else:
                return {"success": False, "error": "Token expired and no refresh token"}

        # Verify with a simple API call
        result = await self.get_user_info()
        if result.get("success"):
            return {"success": True, "email": result.get("email")}
        return result

    async def get_user_info(self) -> dict[str, Any]:
        """Get information about the authenticated user."""
        result = await self._make_request("GET", USERINFO_URL)
        if result.get("success"):
            data = result.get("data", {})
            return {
                "success": True,
                "email": data.get("email"),
                "name": data.get("name"),
                "picture": data.get("picture"),
            }
        return result

    # =========================================================================
    # Email Operations
    # =========================================================================

    async def get_emails(
        self,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get emails from Gmail."""
        # Build query
        q_parts = []
        if query:
            q_parts.append(query)
        if unread_only:
            q_parts.append("is:unread")
        if labels:
            for label in labels:
                q_parts.append(f"label:{label}")

        params = {
            "maxResults": limit,
            "q": " ".join(q_parts) if q_parts else None,
        }
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}

        url = f"{GMAIL_API_BASE}/users/me/messages"
        result = await self._make_request("GET", url, params=params)

        if not result.get("success"):
            return result

        messages = result.get("data", {}).get("messages", [])
        emails = []

        # Fetch full message details for each
        for msg_info in messages:
            msg_result = await self.get_email(msg_info["id"])
            if msg_result.get("success"):
                emails.append(msg_result["email"])

        return {
            "success": True,
            "emails": emails,
            "total": len(emails),
            "next_page_token": result.get("data", {}).get("nextPageToken"),
        }

    async def get_email(self, message_id: str) -> dict[str, Any]:
        """Get a single email by ID."""
        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}"
        params = {"format": "full"}

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        data = result.get("data", {})
        email_obj = self._parse_gmail_message(data)

        return {"success": True, "email": email_obj}

    def _parse_gmail_message(self, data: dict) -> Email:
        """Parse Gmail API message into Email object."""
        headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}

        # Parse sender
        sender_raw = headers.get("from", "")
        sender = EmailAddress.from_string(sender_raw) if sender_raw else None

        # Parse recipients
        to_raw = headers.get("to", "")
        to_list = [EmailAddress.from_string(a.strip()) for a in to_raw.split(",") if a.strip()]

        cc_raw = headers.get("cc", "")
        cc_list = [EmailAddress.from_string(a.strip()) for a in cc_raw.split(",") if a.strip()]

        # Parse date
        date_raw = headers.get("date", "")
        try:
            received_at = datetime(*email.utils.parsedate(date_raw)[:6]) if date_raw else datetime.now()
        except Exception:
            received_at = datetime.now()

        # Get snippet and labels
        snippet = data.get("snippet", "")
        labels = data.get("labelIds", [])

        # Determine read/starred status
        is_read = "UNREAD" not in labels
        is_starred = "STARRED" in labels

        # Get body
        body_text = self._extract_body(data.get("payload", {}), "text/plain")
        body_html = self._extract_body(data.get("payload", {}), "text/html")

        return Email(
            id=Email.generate_id(),
            account_id=self.account.id,
            message_id=data.get("id", ""),
            thread_id=data.get("threadId"),
            subject=headers.get("subject", ""),
            sender=sender,
            to=to_list,
            cc=cc_list,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            labels=labels,
            is_read=is_read,
            is_starred=is_starred,
            has_attachments=len(data.get("payload", {}).get("parts", [])) > 1,
            provider="google",
            raw_data=data,
        )

    def _extract_body(self, payload: dict, mime_type: str) -> str | None:
        """Extract email body of specified MIME type."""
        if payload.get("mimeType") == mime_type:
            body_data = payload.get("body", {}).get("data")
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")

        # Check parts
        for part in payload.get("parts", []):
            result = self._extract_body(part, mime_type)
            if result:
                return result

        return None

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Get all emails in a thread."""
        url = f"{GMAIL_API_BASE}/users/me/threads/{thread_id}"
        params = {"format": "full"}

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        messages = result.get("data", {}).get("messages", [])
        emails = [self._parse_gmail_message(m) for m in messages]

        return {"success": True, "emails": emails, "thread_id": thread_id}

    # =========================================================================
    # Calendar Operations
    # =========================================================================

    async def get_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Get calendar events in a date range."""
        if not start_date:
            start_date = datetime.now()
        if not end_date:
            end_date = start_date + timedelta(days=7)

        params = {
            "timeMin": start_date.isoformat() + "Z",
            "timeMax": end_date.isoformat() + "Z",
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }

        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events"
        result = await self._make_request("GET", url, params=params)

        if not result.get("success"):
            return result

        items = result.get("data", {}).get("items", [])
        events = [self._parse_calendar_event(item) for item in items]

        return {"success": True, "events": events, "total": len(events)}

    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """Get a single calendar event."""
        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        result = await self._make_request("GET", url)

        if not result.get("success"):
            return result

        event = self._parse_calendar_event(result.get("data", {}))
        return {"success": True, "event": event}

    def _parse_calendar_event(self, data: dict) -> CalendarEvent:
        """Parse Google Calendar event into CalendarEvent object."""
        # Parse start/end times
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        all_day = "date" in start_data

        if all_day:
            start_time = datetime.fromisoformat(start_data.get("date", ""))
            end_time = datetime.fromisoformat(end_data.get("date", ""))
        else:
            start_str = start_data.get("dateTime", "")
            end_str = end_data.get("dateTime", "")
            # Handle timezone offset
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

        # Parse organizer
        org_data = data.get("organizer", {})
        organizer = Attendee(
            email=org_data.get("email", ""),
            name=org_data.get("displayName"),
            is_organizer=True,
            status="accepted",
        ) if org_data else None

        # Parse attendees
        attendees = []
        for att in data.get("attendees", []):
            attendees.append(Attendee(
                email=att.get("email", ""),
                name=att.get("displayName"),
                status=att.get("responseStatus", "needsAction"),
                is_optional=att.get("optional", False),
            ))

        return CalendarEvent(
            id=CalendarEvent.generate_id(),
            account_id=self.account.id,
            event_id=data.get("id", ""),
            calendar_id=data.get("calendarId", "primary"),
            title=data.get("summary", ""),
            description=data.get("description", ""),
            location=data.get("location", ""),
            start_time=start_time,
            end_time=end_time,
            all_day=all_day,
            timezone=start_data.get("timeZone", "UTC"),
            is_recurring="recurrence" in data,
            recurrence_rule=data.get("recurrence", [None])[0] if data.get("recurrence") else None,
            organizer=organizer,
            attendees=attendees,
            status=data.get("status", "confirmed"),
            visibility=data.get("visibility", "default"),
            is_meeting=len(attendees) > 0,
            meeting_link=data.get("hangoutLink"),
            provider="google",
            raw_data=data,
        )

    # =========================================================================
    # Draft Operations (Level 3+)
    # =========================================================================

    async def create_draft(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an email draft in Gmail."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft creation requires Level 3+"}

        # Build message
        message = MIMEText(body)
        message["to"] = ", ".join(to)
        message["subject"] = subject
        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        # Encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        data = {"message": {"raw": raw}}
        if reply_to_message_id:
            data["message"]["threadId"] = reply_to_message_id

        url = f"{GMAIL_API_BASE}/users/me/drafts"
        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            draft_id = result.get("data", {}).get("id")
            return {"success": True, "draft_id": draft_id}
        return result

    async def get_drafts(self, limit: int = 20) -> dict[str, Any]:
        """Get list of draft emails."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}

        url = f"{GMAIL_API_BASE}/users/me/drafts"
        params = {"maxResults": limit}

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        drafts = result.get("data", {}).get("drafts", [])
        return {"success": True, "drafts": drafts, "total": len(drafts)}

    async def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """Delete a draft."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}

        url = f"{GMAIL_API_BASE}/users/me/drafts/{draft_id}"
        return await self._make_request("DELETE", url)

    # =========================================================================
    # Send Operations (Level 4+)
    # =========================================================================

    async def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an email via Gmail."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Sending email requires Level 4+"}

        # Build message
        message = MIMEText(body)
        message["to"] = ", ".join(to)
        message["subject"] = subject
        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        # Encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        data = {"raw": raw}
        if reply_to_message_id:
            data["threadId"] = reply_to_message_id

        url = f"{GMAIL_API_BASE}/users/me/messages/send"
        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            message_id = result.get("data", {}).get("id")
            return {"success": True, "message_id": message_id}
        return result

    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Send an existing draft."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Sending requires Level 4+"}

        url = f"{GMAIL_API_BASE}/users/me/drafts/send"
        data = {"id": draft_id}

        result = await self._make_request("POST", url, data=data)
        if result.get("success"):
            message_id = result.get("data", {}).get("id")
            return {"success": True, "message_id": message_id}
        return result

    async def trash_email(self, message_id: str) -> dict[str, Any]:
        """Move an email to trash via Gmail API messages.trash()."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Trashing email requires Level 4+"}

        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}/trash"
        result = await self._make_request("POST", url)

        if result.get("success"):
            return {"success": True, "message_id": message_id}
        return result

    async def delete_email(self, message_id: str) -> dict[str, Any]:
        """Permanently delete an email via Gmail API messages.delete()."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Deleting email requires Level 4+"}

        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}"
        return await self._make_request("DELETE", url)

    async def archive_email(self, message_id: str) -> dict[str, Any]:
        """Archive an email by removing the INBOX label."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Archiving email requires Level 4+"}

        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}/modify"
        data = {"removeLabelIds": ["INBOX"]}

        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            return {"success": True, "message_id": message_id}
        return result

    # =========================================================================
    # Calendar Write Operations (Level 3+)
    # =========================================================================

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create a calendar event."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Creating events requires Level 3+"}

        data = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        }

        if attendees:
            data["attendees"] = [{"email": a} for a in attendees]

        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events"
        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            event_id = result.get("data", {}).get("id")
            return {"success": True, "event_id": event_id}
        return result

    async def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Update a calendar event."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Updating events requires Level 3+"}

        # Get existing event first
        existing = await self.get_event(event_id, calendar_id)
        if not existing.get("success"):
            return existing

        # Build update data
        data = {}
        if title is not None:
            data["summary"] = title
        if description is not None:
            data["description"] = description
        if location is not None:
            data["location"] = location
        if start_time is not None:
            data["start"] = {"dateTime": start_time.isoformat(), "timeZone": "UTC"}
        if end_time is not None:
            data["end"] = {"dateTime": end_time.isoformat(), "timeZone": "UTC"}
        if attendees is not None:
            data["attendees"] = [{"email": a} for a in attendees]

        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        return await self._make_request("PATCH", url, data=data)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """Delete a calendar event."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Deleting events requires Level 4+"}

        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        return await self._make_request("DELETE", url)

    async def respond_to_event(
        self,
        event_id: str,
        response: str,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Respond to a calendar event invitation."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Responding to events requires Level 3+"}

        # Map response to Google API format
        response_map = {
            "accepted": "accepted",
            "declined": "declined",
            "tentative": "tentative",
        }

        if response not in response_map:
            return {"success": False, "error": f"Invalid response: {response}"}

        # Get event and update attendee status
        # This is a simplified implementation - full implementation would
        # find the current user's attendee entry and update it
        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        data = {"attendees": [{"email": self.account.email_address, "responseStatus": response_map[response]}]}

        return await self._make_request("PATCH", url, data=data)
