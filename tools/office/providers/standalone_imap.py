"""
Tool: Standalone IMAP Provider
Purpose: IMAP/SMTP provider for Dex's own mailbox (Level 1)

Provides email access via standard IMAP/SMTP protocols for Level 1 integration,
where Dex has its own email address separate from the user's.

Usage:
    from tools.office.providers.standalone_imap import StandaloneImapProvider

    provider = StandaloneImapProvider(account)
    emails = await provider.get_emails(limit=10)

Dependencies:
    - aiohttp is NOT required (uses stdlib imaplib/smtplib)

Note:
    Calendar operations are not supported for standalone IMAP.
    Use a CalDAV server if calendar integration is needed for Level 1.
"""

import email
import email.utils
import imaplib
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from tools.office.models import (
    CalendarEvent,
    Email,
    EmailAddress,
    IntegrationLevel,
    OfficeAccount,
)
from tools.office.providers.base import OfficeProvider


class StandaloneImapProvider(OfficeProvider):
    """
    Standalone IMAP/SMTP provider for Level 1 integration.

    In Level 1, Dex has its own email address. This provider connects
    to that mailbox via IMAP for reading and SMTP for sending.

    This is useful for:
    - Users who want maximum privacy (user forwards emails to Dex)
    - Organizations that want a dedicated assistant mailbox
    - Testing without OAuth setup
    """

    def __init__(self, account: OfficeAccount):
        """
        Initialize provider.

        Account should have these fields in raw_data:
        - imap_host: IMAP server hostname
        - imap_port: IMAP port (default 993)
        - smtp_host: SMTP server hostname
        - smtp_port: SMTP port (default 587)
        - username: Login username (usually email address)
        - password: Login password or app password
        """
        super().__init__(account)
        self._imap: imaplib.IMAP4_SSL | None = None
        self._config = account.raw_data if hasattr(account, "raw_data") else {}

    @property
    def provider_name(self) -> str:
        return "standalone"

    def _get_imap_config(self) -> dict[str, Any]:
        """Get IMAP configuration from account."""
        return {
            "host": self._config.get("imap_host", ""),
            "port": self._config.get("imap_port", 993),
            "username": self._config.get("username", self.account.email_address),
            "password": self._config.get("password", self.account.access_token),
        }

    def _get_smtp_config(self) -> dict[str, Any]:
        """Get SMTP configuration from account."""
        return {
            "host": self._config.get("smtp_host", ""),
            "port": self._config.get("smtp_port", 587),
            "username": self._config.get("username", self.account.email_address),
            "password": self._config.get("password", self.account.access_token),
        }

    def _connect_imap(self) -> dict[str, Any]:
        """Establish IMAP connection."""
        config = self._get_imap_config()

        if not config["host"]:
            return {"success": False, "error": "IMAP host not configured"}

        try:
            self._imap = imaplib.IMAP4_SSL(config["host"], config["port"])
            self._imap.login(config["username"], config["password"])
            return {"success": True}
        except imaplib.IMAP4.error as e:
            return {"success": False, "error": f"IMAP authentication failed: {e!s}"}
        except Exception as e:
            return {"success": False, "error": f"IMAP connection failed: {e!s}"}

    def _disconnect_imap(self):
        """Close IMAP connection."""
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    async def authenticate(self) -> dict[str, Any]:
        """Verify IMAP connection works."""
        result = self._connect_imap()
        if result.get("success"):
            self._disconnect_imap()
        return result

    async def get_user_info(self) -> dict[str, Any]:
        """Get configured email address."""
        return {
            "success": True,
            "email": self.account.email_address,
            "name": "Dex Assistant",
            "provider": "standalone",
        }

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
        """Get emails from IMAP mailbox."""
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            # Select inbox
            self._imap.select("INBOX")

            # Build search criteria
            criteria = []
            if unread_only:
                criteria.append("UNSEEN")
            if query:
                # IMAP search is limited - search subject and from
                criteria.append(f'OR SUBJECT "{query}" FROM "{query}"')

            search_criteria = " ".join(criteria) if criteria else "ALL"

            # Search for messages
            _, message_nums = self._imap.search(None, search_criteria)
            message_ids = message_nums[0].split()

            # Reverse to get newest first, apply offset and limit
            message_ids = list(reversed(message_ids))
            message_ids = message_ids[offset:offset + limit]

            emails = []
            for msg_id in message_ids:
                email_result = await self._fetch_email(msg_id.decode())
                if email_result.get("success"):
                    emails.append(email_result["email"])

            return {
                "success": True,
                "emails": emails,
                "total": len(emails),
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to fetch emails: {e!s}"}
        finally:
            self._disconnect_imap()

    async def _fetch_email(self, msg_id: str) -> dict[str, Any]:
        """Fetch a single email by IMAP message ID."""
        try:
            _, msg_data = self._imap.fetch(msg_id, "(RFC822 FLAGS)")

            if not msg_data or not msg_data[0]:
                return {"success": False, "error": "Message not found"}

            raw_email = msg_data[0][1]
            flags = msg_data[0][0] if len(msg_data[0]) > 0 else b""

            msg = email.message_from_bytes(raw_email)

            # Parse email
            email_obj = self._parse_email_message(msg, msg_id, flags)

            return {"success": True, "email": email_obj}

        except Exception as e:
            return {"success": False, "error": f"Failed to fetch email: {e!s}"}

    def _parse_email_message(
        self,
        msg: email.message.Message,
        msg_id: str,
        flags: bytes,
    ) -> Email:
        """Parse email.message.Message into Email object."""
        # Parse sender
        from_header = msg.get("From", "")
        sender = EmailAddress.from_string(from_header) if from_header else None

        # Parse recipients
        to_header = msg.get("To", "")
        to_list = [
            EmailAddress.from_string(a.strip())
            for a in to_header.split(",")
            if a.strip()
        ]

        cc_header = msg.get("Cc", "")
        cc_list = [
            EmailAddress.from_string(a.strip())
            for a in cc_header.split(",")
            if a.strip()
        ]

        # Parse date
        date_header = msg.get("Date", "")
        try:
            parsed_date = email.utils.parsedate_to_datetime(date_header)
            received_at = parsed_date.replace(tzinfo=None)
        except Exception:
            received_at = datetime.now()

        # Get body
        body_text = None
        body_html = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and not body_text:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode("utf-8", errors="ignore")
                elif content_type == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_html = payload.decode("utf-8", errors="ignore")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                if msg.get_content_type() == "text/html":
                    body_html = payload.decode("utf-8", errors="ignore")
                else:
                    body_text = payload.decode("utf-8", errors="ignore")

        # Determine flags
        flags_str = flags.decode() if isinstance(flags, bytes) else str(flags)
        is_read = "\\Seen" in flags_str
        is_starred = "\\Flagged" in flags_str

        # Create snippet
        snippet = ""
        if body_text:
            snippet = body_text[:200].replace("\n", " ").strip()
        elif body_html:
            # Basic HTML strip for snippet
            import re
            clean = re.sub(r"<[^>]+>", "", body_html)
            snippet = clean[:200].replace("\n", " ").strip()

        return Email(
            id=Email.generate_id(),
            account_id=self.account.id,
            message_id=msg_id,
            thread_id=msg.get("References", "").split()[0] if msg.get("References") else None,
            subject=msg.get("Subject", ""),
            sender=sender,
            to=to_list,
            cc=cc_list,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            labels=[],
            is_read=is_read,
            is_starred=is_starred,
            has_attachments=any(
                part.get_content_disposition() == "attachment"
                for part in msg.walk()
            ) if msg.is_multipart() else False,
            provider="standalone",
        )

    async def get_email(self, message_id: str) -> dict[str, Any]:
        """Get a single email by ID."""
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            self._imap.select("INBOX")
            result = await self._fetch_email(message_id)
            return result
        finally:
            self._disconnect_imap()

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """
        Get all emails in a thread.

        Note: IMAP thread support is limited. This searches for messages
        with matching References header.
        """
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            self._imap.select("INBOX")

            # Search by References header (imperfect but common approach)
            _, message_nums = self._imap.search(None, f'HEADER References "{thread_id}"')
            message_ids = message_nums[0].split()

            emails = []
            for msg_id in message_ids:
                result = await self._fetch_email(msg_id.decode())
                if result.get("success"):
                    emails.append(result["email"])

            return {"success": True, "emails": emails, "thread_id": thread_id}

        except Exception as e:
            return {"success": False, "error": f"Failed to fetch thread: {e!s}"}
        finally:
            self._disconnect_imap()

    # =========================================================================
    # Calendar Operations (Not Supported)
    # =========================================================================

    async def get_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        calendar_id: str = "primary",
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Calendar not supported for standalone IMAP."""
        return {
            "success": False,
            "error": "Calendar operations not supported for standalone IMAP. "
                     "Consider using CalDAV or upgrading to Level 2 with Google/Microsoft.",
        }

    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        """Calendar not supported for standalone IMAP."""
        return {"success": False, "error": "Calendar not supported for standalone IMAP"}

    # =========================================================================
    # Send Operations (Dex's Own Identity)
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
        Send an email from Dex's own address via SMTP.

        Note: For Level 1, this sends from Dex's identity, not the user's.
        This is allowed at any integration level since it's Dex's own account.
        """
        config = self._get_smtp_config()

        if not config["host"]:
            return {"success": False, "error": "SMTP host not configured"}

        try:
            # Build message
            msg = MIMEMultipart()
            msg["From"] = self.account.email_address
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = ", ".join(cc)

            msg.attach(MIMEText(body, "plain"))

            # Connect and send
            with smtplib.SMTP(config["host"], config["port"]) as server:
                server.starttls()
                server.login(config["username"], config["password"])

                # Build recipient list
                all_recipients = list(to)
                if cc:
                    all_recipients.extend(cc)
                if bcc:
                    all_recipients.extend(bcc)

                server.sendmail(
                    self.account.email_address,
                    all_recipients,
                    msg.as_string(),
                )

            return {
                "success": True,
                "message": "Email sent from Dex's address",
                "from": self.account.email_address,
            }

        except smtplib.SMTPAuthenticationError:
            return {"success": False, "error": "SMTP authentication failed"}
        except Exception as e:
            return {"success": False, "error": f"Failed to send email: {e!s}"}

    # =========================================================================
    # Draft/Write Operations (Limited for Standalone)
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
        Create a draft in the IMAP Drafts folder.

        Note: For Level 1, drafts are in Dex's mailbox, not user's.
        """
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            # Build message
            msg = MIMEMultipart()
            msg["From"] = self.account.email_address
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            if cc:
                msg["Cc"] = ", ".join(cc)

            msg.attach(MIMEText(body, "plain"))

            # Append to Drafts folder
            self._imap.append(
                "Drafts",
                "\\Draft",
                None,
                msg.as_bytes(),
            )

            return {
                "success": True,
                "message": "Draft created in Dex's Drafts folder",
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to create draft: {e!s}"}
        finally:
            self._disconnect_imap()

    async def get_drafts(self, limit: int = 20) -> dict[str, Any]:
        """Get drafts from Dex's Drafts folder."""
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            # Select Drafts folder
            status, _ = self._imap.select("Drafts")
            if status != "OK":
                return {"success": True, "drafts": [], "total": 0}

            _, message_nums = self._imap.search(None, "ALL")
            message_ids = message_nums[0].split()[-limit:]  # Last N

            drafts = []
            for msg_id in reversed(message_ids):
                result = await self._fetch_email(msg_id.decode())
                if result.get("success"):
                    draft = result["email"]
                    draft.is_draft = True
                    drafts.append(draft)

            return {"success": True, "drafts": drafts, "total": len(drafts)}

        except Exception as e:
            return {"success": False, "error": f"Failed to get drafts: {e!s}"}
        finally:
            self._disconnect_imap()

    async def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """Delete a draft from Dex's Drafts folder."""
        conn_result = self._connect_imap()
        if not conn_result.get("success"):
            return conn_result

        try:
            self._imap.select("Drafts")
            self._imap.store(draft_id, "+FLAGS", "\\Deleted")
            self._imap.expunge()

            return {"success": True, "message": "Draft deleted"}

        except Exception as e:
            return {"success": False, "error": f"Failed to delete draft: {e!s}"}
        finally:
            self._disconnect_imap()
