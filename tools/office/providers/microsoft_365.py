"""
Tool: Microsoft 365 Provider
Purpose: Outlook and Microsoft Calendar integration via Microsoft Graph API

Implements the OfficeProvider interface for Microsoft 365.
Supports all integration levels (2-5) for Outlook Mail and Calendar.

Usage:
    from tools.office.providers.microsoft_365 import Microsoft365Provider

    provider = Microsoft365Provider(account)
    emails = await provider.get_emails(limit=10)
    events = await provider.get_events()

Dependencies:
    - aiohttp (pip install aiohttp)
"""

import base64
from datetime import datetime, timedelta
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


# Microsoft Graph API endpoints
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


class Microsoft365Provider(OfficeProvider):
    """
    Microsoft 365 provider for Outlook and Microsoft Calendar.

    Implements read operations for Level 2, draft operations for Level 3,
    send operations for Level 4, and autonomous operations for Level 5.
    """

    @property
    def provider_name(self) -> str:
        return "microsoft"

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

        if resp.status in (200, 201):
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
        """Verify authentication by making a test API call.

        Uses proactive token refresh to avoid mid-operation expiry.
        """
        if not self.account.access_token:
            return {"success": False, "error": "No access token"}

        # Proactive refresh: check expiry *before* making the API call
        from tools.office.oauth_manager import get_valid_access_token

        refreshed = await get_valid_access_token("microsoft", self.account.id)
        if refreshed:
            self.account.access_token = refreshed
        elif self.account.is_token_expired():
            # Fallback: reactive refresh if proactive refresh returned None
            if self.account.refresh_token:
                from tools.office.oauth_manager import refresh_access_token

                result = await refresh_access_token("microsoft", self.account.refresh_token)
                if result.get("success"):
                    self.account.access_token = result["access_token"]
                    if result.get("refresh_token"):
                        self.account.refresh_token = result["refresh_token"]
                    expires_in = result.get("expires_in", 3600)
                    self.account.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                else:
                    return {"success": False, "error": "Token refresh failed"}
            else:
                return {"success": False, "error": "Token expired and no refresh token"}

        result = await self.get_user_info()
        if result.get("success"):
            return {"success": True, "email": result.get("email")}
        return result

    async def get_user_info(self) -> dict[str, Any]:
        """Get information about the authenticated user."""
        url = f"{GRAPH_API_BASE}/me"
        result = await self._make_request("GET", url)

        if result.get("success"):
            data = result.get("data", {})
            return {
                "success": True,
                "email": data.get("mail") or data.get("userPrincipalName"),
                "name": data.get("displayName"),
                "id": data.get("id"),
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
        """Get emails from Outlook."""
        url = f"{GRAPH_API_BASE}/me/messages"

        params = {
            "$top": limit,
            "$skip": offset,
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,bodyPreview,"
                       "receivedDateTime,isRead,flag,hasAttachments,body",
        }

        # Build filter
        filters = []
        if unread_only:
            filters.append("isRead eq false")
        if query:
            # Microsoft uses $search for full-text search
            params["$search"] = f'"{query}"'

        if filters:
            params["$filter"] = " and ".join(filters)

        result = await self._make_request("GET", url, params=params)

        if not result.get("success"):
            return result

        messages = result.get("data", {}).get("value", [])
        emails = [self._parse_outlook_message(m) for m in messages]

        return {
            "success": True,
            "emails": emails,
            "total": len(emails),
        }

    async def get_email(self, message_id: str) -> dict[str, Any]:
        """Get a single email by ID."""
        url = f"{GRAPH_API_BASE}/me/messages/{message_id}"
        params = {"$select": "id,conversationId,subject,from,toRecipients,ccRecipients,"
                             "bccRecipients,bodyPreview,receivedDateTime,isRead,flag,"
                             "hasAttachments,body"}

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        email_obj = self._parse_outlook_message(result.get("data", {}))
        return {"success": True, "email": email_obj}

    def _parse_outlook_message(self, data: dict) -> Email:
        """Parse Outlook message into Email object."""
        # Parse sender
        from_data = data.get("from", {}).get("emailAddress", {})
        sender = EmailAddress(
            address=from_data.get("address", ""),
            name=from_data.get("name"),
        ) if from_data else None

        # Parse recipients
        to_list = [
            EmailAddress(
                address=r.get("emailAddress", {}).get("address", ""),
                name=r.get("emailAddress", {}).get("name"),
            )
            for r in data.get("toRecipients", [])
        ]

        cc_list = [
            EmailAddress(
                address=r.get("emailAddress", {}).get("address", ""),
                name=r.get("emailAddress", {}).get("name"),
            )
            for r in data.get("ccRecipients", [])
        ]

        # Parse date
        received_str = data.get("receivedDateTime", "")
        try:
            received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
        except Exception:
            received_at = datetime.now()

        # Get body
        body_data = data.get("body", {})
        body_text = body_data.get("content") if body_data.get("contentType") == "text" else None
        body_html = body_data.get("content") if body_data.get("contentType") == "html" else None

        # Starred = flagged in Outlook
        is_starred = data.get("flag", {}).get("flagStatus") == "flagged"

        return Email(
            id=Email.generate_id(),
            account_id=self.account.id,
            message_id=data.get("id", ""),
            thread_id=data.get("conversationId"),
            subject=data.get("subject", ""),
            sender=sender,
            to=to_list,
            cc=cc_list,
            snippet=data.get("bodyPreview", ""),
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            labels=[],  # Outlook uses folders, not labels
            is_read=data.get("isRead", False),
            is_starred=is_starred,
            has_attachments=data.get("hasAttachments", False),
            provider="microsoft",
            raw_data=data,
        )

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Get all emails in a conversation."""
        url = f"{GRAPH_API_BASE}/me/messages"
        params = {
            "$filter": f"conversationId eq '{thread_id}'",
            "$orderby": "receivedDateTime asc",
        }

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        messages = result.get("data", {}).get("value", [])
        emails = [self._parse_outlook_message(m) for m in messages]

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

        # Use calendarView for expanded recurring events
        url = f"{GRAPH_API_BASE}/me/calendarView"
        params = {
            "startDateTime": start_date.isoformat() + "Z",
            "endDateTime": end_date.isoformat() + "Z",
            "$top": max_results,
            "$orderby": "start/dateTime",
        }

        result = await self._make_request("GET", url, params=params)

        if not result.get("success"):
            return result

        items = result.get("data", {}).get("value", [])
        events = [self._parse_calendar_event(item) for item in items]

        return {"success": True, "events": events, "total": len(events)}

    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """Get a single calendar event."""
        url = f"{GRAPH_API_BASE}/me/events/{event_id}"
        result = await self._make_request("GET", url)

        if not result.get("success"):
            return result

        event = self._parse_calendar_event(result.get("data", {}))
        return {"success": True, "event": event}

    def _parse_calendar_event(self, data: dict) -> CalendarEvent:
        """Parse Outlook calendar event into CalendarEvent object."""
        # Parse start/end times
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        all_day = data.get("isAllDay", False)

        start_str = start_data.get("dateTime", "")
        end_str = end_data.get("dateTime", "")

        try:
            start_time = datetime.fromisoformat(start_str)
            end_time = datetime.fromisoformat(end_str)
        except Exception:
            start_time = datetime.now()
            end_time = datetime.now()

        # Parse organizer
        org_data = data.get("organizer", {}).get("emailAddress", {})
        organizer = Attendee(
            email=org_data.get("address", ""),
            name=org_data.get("name"),
            is_organizer=True,
            status="accepted",
        ) if org_data else None

        # Parse attendees
        attendees = []
        for att in data.get("attendees", []):
            email_addr = att.get("emailAddress", {})
            # Map response status
            status_map = {
                "none": "needsAction",
                "accepted": "accepted",
                "declined": "declined",
                "tentativelyAccepted": "tentative",
            }
            attendees.append(Attendee(
                email=email_addr.get("address", ""),
                name=email_addr.get("name"),
                status=status_map.get(att.get("status", {}).get("response", "none"), "needsAction"),
                is_optional=att.get("type") == "optional",
            ))

        # Determine if it's a meeting
        is_meeting = data.get("isMeeting", False) or len(attendees) > 0

        # Get meeting link
        meeting_link = None
        if data.get("onlineMeeting"):
            meeting_link = data.get("onlineMeeting", {}).get("joinUrl")

        return CalendarEvent(
            id=CalendarEvent.generate_id(),
            account_id=self.account.id,
            event_id=data.get("id", ""),
            calendar_id="primary",
            title=data.get("subject", ""),
            description=data.get("bodyPreview", ""),
            location=data.get("location", {}).get("displayName", ""),
            start_time=start_time,
            end_time=end_time,
            all_day=all_day,
            timezone=start_data.get("timeZone", "UTC"),
            is_recurring=data.get("type") == "seriesMaster" or "recurrence" in data,
            recurrence_rule=None,  # Would need to convert from Graph format
            organizer=organizer,
            attendees=attendees,
            status=data.get("showAs", "busy"),  # busy, free, tentative, etc.
            visibility="default",
            is_meeting=is_meeting,
            meeting_link=meeting_link,
            provider="microsoft",
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
        """Create an email draft in Outlook."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft creation requires Level 3+"}

        data = {
            "subject": subject,
            "body": {
                "contentType": "text",
                "content": body,
            },
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }

        if cc:
            data["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]
        if bcc:
            data["bccRecipients"] = [{"emailAddress": {"address": a}} for a in bcc]

        url = f"{GRAPH_API_BASE}/me/messages"
        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            draft_id = result.get("data", {}).get("id")
            return {"success": True, "draft_id": draft_id}
        return result

    async def get_drafts(self, limit: int = 20) -> dict[str, Any]:
        """Get list of draft emails."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}

        url = f"{GRAPH_API_BASE}/me/mailFolders/drafts/messages"
        params = {"$top": limit}

        result = await self._make_request("GET", url, params=params)
        if not result.get("success"):
            return result

        drafts = result.get("data", {}).get("value", [])
        return {"success": True, "drafts": drafts, "total": len(drafts)}

    async def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """Delete a draft."""
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}

        url = f"{GRAPH_API_BASE}/me/messages/{draft_id}"
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
        """Send an email via Outlook."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Sending email requires Level 4+"}

        data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "text",
                    "content": body,
                },
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            },
            "saveToSentItems": True,
        }

        if cc:
            data["message"]["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]
        if bcc:
            data["message"]["bccRecipients"] = [{"emailAddress": {"address": a}} for a in bcc]

        url = f"{GRAPH_API_BASE}/me/sendMail"
        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            return {"success": True, "message": "Email sent"}
        return result

    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Send an existing draft."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Sending requires Level 4+"}

        url = f"{GRAPH_API_BASE}/me/messages/{draft_id}/send"
        return await self._make_request("POST", url)

    async def move_to_deleted(self, message_id: str) -> dict[str, Any]:
        """Move an email to the deletedItems folder."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Moving to deleted requires Level 4+"}

        url = f"{GRAPH_API_BASE}/me/messages/{message_id}/move"
        data = {"destinationId": "deleteditems"}

        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            new_id = result.get("data", {}).get("id")
            return {"success": True, "message_id": new_id}
        return result

    async def delete_email(self, message_id: str) -> dict[str, Any]:
        """Permanently delete an email via Graph API DELETE."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Deleting email requires Level 4+"}

        url = f"{GRAPH_API_BASE}/me/messages/{message_id}"
        return await self._make_request("DELETE", url)

    async def archive_email(self, message_id: str) -> dict[str, Any]:
        """Move an email to the archive folder."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Archiving email requires Level 4+"}

        url = f"{GRAPH_API_BASE}/me/messages/{message_id}/move"
        data = {"destinationId": "archive"}

        result = await self._make_request("POST", url, data=data)

        if result.get("success"):
            new_id = result.get("data", {}).get("id")
            return {"success": True, "message_id": new_id}
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
            "subject": title,
            "body": {
                "contentType": "text",
                "content": description,
            },
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            },
        }

        if location:
            data["location"] = {"displayName": location}

        if attendees:
            data["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"}
                for a in attendees
            ]

        url = f"{GRAPH_API_BASE}/me/events"
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

        data = {}
        if title is not None:
            data["subject"] = title
        if description is not None:
            data["body"] = {"contentType": "text", "content": description}
        if location is not None:
            data["location"] = {"displayName": location}
        if start_time is not None:
            data["start"] = {"dateTime": start_time.isoformat(), "timeZone": "UTC"}
        if end_time is not None:
            data["end"] = {"dateTime": end_time.isoformat(), "timeZone": "UTC"}
        if attendees is not None:
            data["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"}
                for a in attendees
            ]

        url = f"{GRAPH_API_BASE}/me/events/{event_id}"
        return await self._make_request("PATCH", url, data=data)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """Delete a calendar event."""
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Deleting events requires Level 4+"}

        url = f"{GRAPH_API_BASE}/me/events/{event_id}"
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

        # Map response to Graph API endpoints
        response_endpoints = {
            "accepted": "accept",
            "declined": "decline",
            "tentative": "tentativelyAccept",
        }

        if response not in response_endpoints:
            return {"success": False, "error": f"Invalid response: {response}"}

        url = f"{GRAPH_API_BASE}/me/events/{event_id}/{response_endpoints[response]}"
        data = {"sendResponse": True}

        return await self._make_request("POST", url, data=data)
