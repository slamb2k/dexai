"""Office Providers — Platform-specific implementations

This package contains provider adapters for different email/calendar platforms:
- google_workspace.py: Gmail, Google Calendar
- microsoft_365.py: Outlook, Microsoft Calendar (via Graph API)
- standalone_imap.py: Generic IMAP/SMTP for Dex's own mailbox (Level 1)

All providers implement the OfficeProvider abstract base class from base.py.
"""

from tools.office.providers.base import OfficeProvider

__all__ = ["OfficeProvider"]
