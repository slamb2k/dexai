"""
Tool: Office Provider Base
Purpose: Abstract base class for office platform providers

Defines the common interface that all office providers must implement.
This allows the rest of the system to work with any provider interchangeably.

Usage:
    from tools.office.providers.base import OfficeProvider
    from tools.office.providers.google_workspace import GoogleWorkspaceProvider

    provider = GoogleWorkspaceProvider(account)
    emails = await provider.get_emails(limit=10)
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from tools.office.models import CalendarEvent, Email, IntegrationLevel, OfficeAccount


class OfficeProvider(ABC):
    """
    Abstract base class for office platform providers.

    Subclasses implement platform-specific logic for Google Workspace,
    Microsoft 365, and standalone IMAP/SMTP.
    """

    def __init__(self, account: OfficeAccount):
        """
        Initialize provider with an office account.

        Args:
            account: Office account with credentials and configuration
        """
        self.account = account

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'google', 'microsoft', 'standalone')."""
        pass

    @property
    def integration_level(self) -> IntegrationLevel:
        """Return the current integration level."""
        return self.account.integration_level

    @abstractmethod
    async def authenticate(self) -> dict[str, Any]:
        """
        Verify authentication and refresh tokens if needed.

        Returns:
            dict with success status and any error messages
        """
        pass

    @abstractmethod
    async def get_user_info(self) -> dict[str, Any]:
        """
        Get information about the authenticated user.

        Returns:
            dict with email, name, and other user details
        """
        pass

    # =========================================================================
    # Email Operations (Level 2+)
    # =========================================================================

    @abstractmethod
    async def get_emails(
        self,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get emails from inbox.

        Args:
            query: Search query (provider-specific syntax)
            limit: Maximum number of emails to return
            offset: Number of emails to skip
            unread_only: Return only unread emails
            labels: Filter by labels/folders

        Returns:
            dict with list of Email objects and pagination info
        """
        pass

    @abstractmethod
    async def get_email(self, message_id: str) -> dict[str, Any]:
        """
        Get a single email by ID.

        Args:
            message_id: Provider-specific message ID

        Returns:
            dict with Email object or error
        """
        pass

    @abstractmethod
    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """
        Get all emails in a thread/conversation.

        Args:
            thread_id: Provider-specific thread ID

        Returns:
            dict with list of Email objects in thread
        """
        pass

    async def get_inbox_summary(
        self,
        max_emails: int = 50,
    ) -> dict[str, Any]:
        """
        Get a summary of the inbox state.

        Default implementation that providers can override.

        Args:
            max_emails: Max emails to analyze for summary

        Returns:
            dict with unread_count, important emails, categories
        """
        result = await self.get_emails(limit=max_emails)
        if not result.get("success"):
            return result

        emails: list[Email] = result.get("emails", [])

        # Calculate summary stats
        unread = [e for e in emails if not e.is_read]
        starred = [e for e in emails if e.is_starred]

        # Group by sender domain
        sender_counts: dict[str, int] = {}
        for email in emails:
            if email.sender:
                domain = email.sender.address.split("@")[-1]
                sender_counts[domain] = sender_counts.get(domain, 0) + 1

        return {
            "success": True,
            "total_analyzed": len(emails),
            "unread_count": len(unread),
            "starred_count": len(starred),
            "top_senders": sorted(
                sender_counts.items(), key=lambda x: x[1], reverse=True
            )[:5],
            "recent_unread": [
                {"subject": e.subject, "sender": str(e.sender), "received": e.received_at.isoformat()}
                for e in unread[:5]
            ],
        }

    # =========================================================================
    # Calendar Operations (Level 2+)
    # =========================================================================

    @abstractmethod
    async def get_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> dict[str, Any]:
        """
        Get calendar events in a date range.

        Args:
            start_date: Start of range (default: now)
            end_date: End of range (default: 7 days from now)
            calendar_id: Calendar to query
            max_results: Maximum events to return

        Returns:
            dict with list of CalendarEvent objects
        """
        pass

    @abstractmethod
    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """
        Get a single calendar event.

        Args:
            event_id: Provider-specific event ID
            calendar_id: Calendar containing the event

        Returns:
            dict with CalendarEvent object or error
        """
        pass

    async def get_availability(
        self,
        start_date: datetime,
        end_date: datetime,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """
        Get free/busy availability for a time range.

        Default implementation that providers can override.

        Args:
            start_date: Start of range
            end_date: End of range
            calendar_id: Calendar to check

        Returns:
            dict with busy_periods and free_periods
        """
        result = await self.get_events(
            start_date=start_date,
            end_date=end_date,
            calendar_id=calendar_id,
        )

        if not result.get("success"):
            return result

        events: list[CalendarEvent] = result.get("events", [])

        # Get busy periods
        busy_periods = []
        for event in events:
            if event.busy_status == "free":
                continue
            busy_periods.append({
                "start": event.start_time.isoformat(),
                "end": event.end_time.isoformat(),
                "title": event.title,
            })

        return {
            "success": True,
            "busy_periods": busy_periods,
            "busy_count": len(busy_periods),
        }

    async def get_today_schedule(self) -> dict[str, Any]:
        """
        Get today's calendar events.

        Returns:
            dict with today's events
        """
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        result = await self.get_events(start_date=start, end_date=end)

        if result.get("success"):
            result["date"] = start.date().isoformat()

        return result

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
        """
        Create an email draft.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body (plain text or HTML)
            cc: CC recipients
            bcc: BCC recipients
            reply_to_message_id: Message ID if this is a reply

        Returns:
            dict with draft_id or error
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {
                "success": False,
                "error": f"Draft creation requires Level 3+, current level: {self.integration_level.value}",
            }
        return {"success": False, "error": "Not implemented by provider"}

    async def update_draft(
        self,
        draft_id: str,
        to: list[str] | None = None,
        subject: str | None = None,
        body: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing draft.

        Args:
            draft_id: ID of draft to update
            to: New recipients (if updating)
            subject: New subject (if updating)
            body: New body (if updating)
            cc: New CC (if updating)
            bcc: New BCC (if updating)

        Returns:
            dict with success status
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {
                "success": False,
                "error": f"Draft operations require Level 3+",
            }
        return {"success": False, "error": "Not implemented by provider"}

    async def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """
        Delete a draft.

        Args:
            draft_id: ID of draft to delete

        Returns:
            dict with success status
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}
        return {"success": False, "error": "Not implemented by provider"}

    async def get_drafts(self, limit: int = 20) -> dict[str, Any]:
        """
        Get list of draft emails.

        Args:
            limit: Maximum drafts to return

        Returns:
            dict with list of draft emails
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Draft operations require Level 3+"}
        return {"success": False, "error": "Not implemented by provider"}

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
        """
        Send an email.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            reply_to_message_id: Message ID if this is a reply

        Returns:
            dict with sent message_id or error
        """
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {
                "success": False,
                "error": f"Sending email requires Level 4+, current level: {self.integration_level.value}",
            }
        return {"success": False, "error": "Not implemented by provider"}

    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        """
        Send an existing draft.

        Args:
            draft_id: ID of draft to send

        Returns:
            dict with sent message_id or error
        """
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Sending requires Level 4+"}
        return {"success": False, "error": "Not implemented by provider"}

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
        """
        Create a calendar event.

        Args:
            title: Event title
            start_time: Event start
            end_time: Event end
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            calendar_id: Calendar to create event in

        Returns:
            dict with event_id or error
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {
                "success": False,
                "error": f"Creating events requires Level 3+",
            }
        return {"success": False, "error": "Not implemented by provider"}

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
        """
        Update a calendar event.

        Args:
            event_id: Event to update
            title: New title (if updating)
            start_time: New start (if updating)
            end_time: New end (if updating)
            description: New description (if updating)
            location: New location (if updating)
            attendees: New attendees (if updating)
            calendar_id: Calendar containing event

        Returns:
            dict with success status
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Updating events requires Level 3+"}
        return {"success": False, "error": "Not implemented by provider"}

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """
        Delete a calendar event.

        Args:
            event_id: Event to delete
            calendar_id: Calendar containing event

        Returns:
            dict with success status
        """
        if self.integration_level < IntegrationLevel.MANAGED_PROXY:
            return {"success": False, "error": "Deleting events requires Level 4+"}
        return {"success": False, "error": "Not implemented by provider"}

    async def respond_to_event(
        self,
        event_id: str,
        response: str,  # 'accepted', 'declined', 'tentative'
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """
        Respond to a calendar event invitation.

        Args:
            event_id: Event to respond to
            response: Response type
            calendar_id: Calendar containing event

        Returns:
            dict with success status
        """
        if self.integration_level < IntegrationLevel.COLLABORATIVE:
            return {"success": False, "error": "Responding to events requires Level 3+"}
        return {"success": False, "error": "Not implemented by provider"}

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def can_perform(self, operation: str) -> bool:
        """
        Check if the current integration level allows an operation.

        Args:
            operation: Operation name ('read_email', 'create_draft', 'send_email', etc.)

        Returns:
            True if operation is allowed
        """
        operation_levels = {
            "read_email": IntegrationLevel.READ_ONLY,
            "read_calendar": IntegrationLevel.READ_ONLY,
            "get_inbox_summary": IntegrationLevel.READ_ONLY,
            "create_draft": IntegrationLevel.COLLABORATIVE,
            "update_draft": IntegrationLevel.COLLABORATIVE,
            "delete_draft": IntegrationLevel.COLLABORATIVE,
            "create_event": IntegrationLevel.COLLABORATIVE,
            "update_event": IntegrationLevel.COLLABORATIVE,
            "respond_to_event": IntegrationLevel.COLLABORATIVE,
            "send_email": IntegrationLevel.MANAGED_PROXY,
            "send_draft": IntegrationLevel.MANAGED_PROXY,
            "delete_event": IntegrationLevel.MANAGED_PROXY,
            "delete_email": IntegrationLevel.MANAGED_PROXY,
        }

        required = operation_levels.get(operation, IntegrationLevel.READ_ONLY)
        return self.integration_level >= required
