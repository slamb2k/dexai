"""
Contact Processor for Multi-Modal Messaging (Phase 15d)

Handles vCard parsing and contact data extraction:
- Telegram contact format (dict with phone_number, first_name, last_name)
- vCard 3.0 and 4.0 format parsing (RFC 6350)
- Extracts: name, phone, email, organization, title

No external dependencies required -- uses regex for vCard parsing.

Usage:
    from tools.channels.media.contact_processor import get_contact_processor

    processor = get_contact_processor()
    result = await processor.process_contact(contact_data)
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)


class ContactProcessor:
    """
    Process contact data from messaging channels.

    Phase 15d: Parses contact information from multiple input formats
    including Telegram/Discord contact dicts and vCard (3.0/4.0) strings.
    """

    def __init__(self) -> None:
        """Initialize contact processor."""
        pass

    async def process_contact(
        self, contact_data: dict[str, Any] | str
    ) -> dict[str, Any]:
        """
        Parse contact info from a dict or vCard string.

        Accepts either a dict (e.g., from Telegram contact sharing) or a
        raw vCard string and normalizes it into a consistent output format.

        Args:
            contact_data: Either a dict with contact fields (Telegram format)
                or a vCard string (RFC 6350).

        Returns:
            Dict with keys: success, name, phone, email, organization,
            title, raw.
        """
        try:
            if isinstance(contact_data, dict):
                return self._process_dict_contact(contact_data)
            elif isinstance(contact_data, str):
                return self.parse_vcard(contact_data)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported contact data type: {type(contact_data).__name__}",
                    "raw": str(contact_data),
                }
        except Exception as e:
            logger.error(f"Contact processing failed: {e}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)[:200]}",
                "raw": str(contact_data)[:500],
            }

    def _process_dict_contact(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Process a contact dict (e.g., from Telegram).

        Handles Telegram contact format with keys like phone_number,
        first_name, last_name, and optional vcard field.

        Args:
            data: Contact dict from a messaging platform.

        Returns:
            Normalized contact result dict.
        """
        # If the dict contains a vcard field, parse that too
        vcard_str = data.get("vcard", "")
        vcard_data: dict[str, Any] = {}
        if vcard_str:
            vcard_data = self.parse_vcard(vcard_str)

        # Build name from available fields
        first_name = data.get("first_name", "")
        last_name = data.get("last_name", "")
        name_parts = [p for p in [first_name, last_name] if p]
        name = " ".join(name_parts) if name_parts else vcard_data.get("name", "")

        # Phone number
        phone = data.get("phone_number", "") or vcard_data.get("phone", "")

        # Email (not typically in Telegram contacts, but may be in vcard)
        email = data.get("email", "") or vcard_data.get("email", "")

        # Organization and title from vcard if available
        organization = data.get("organization", "") or vcard_data.get(
            "organization", ""
        )
        title = data.get("title", "") or vcard_data.get("title", "")

        logger.info(f"Processed dict contact: {name or 'unnamed'}")

        return {
            "success": True,
            "name": name,
            "phone": phone,
            "email": email,
            "organization": organization,
            "title": title,
            "raw": data,
        }

    def parse_vcard(self, vcard_text: str) -> dict[str, Any]:
        """
        Parse a vCard format string (VERSION 3.0 and 4.0).

        Extracts name, phone, email, organization, and title fields
        using regex. Handles folded lines (continuation lines starting
        with whitespace) per the vCard specification.

        Args:
            vcard_text: Raw vCard string content.

        Returns:
            Dict with keys: success, name, phone, email, organization,
            title, raw.
        """
        if not vcard_text or not vcard_text.strip():
            return {
                "success": False,
                "error": "Empty vCard data",
                "raw": "",
            }

        # Unfold continuation lines (lines starting with space/tab are
        # continuations of the previous line per RFC 6350)
        unfolded = re.sub(r"\r?\n[ \t]", "", vcard_text)

        # Normalize line endings
        lines = unfolded.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        name = ""
        phone = ""
        email = ""
        organization = ""
        title = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse property: handle parameters (e.g., TEL;TYPE=CELL:+1234)
            # Split on first colon to get property and value
            colon_idx = line.find(":")
            if colon_idx < 0:
                continue

            prop_part = line[:colon_idx].upper()
            value = line[colon_idx + 1:].strip()

            # Extract the base property name (before any parameters)
            prop_name = prop_part.split(";")[0]

            # FN (Formatted Name) - preferred over N
            if prop_name == "FN" and value:
                name = value

            # N (Structured Name) - fallback if FN not found
            elif prop_name == "N" and not name:
                # N format: LastName;FirstName;MiddleName;Prefix;Suffix
                parts = value.split(";")
                name_parts = []
                if len(parts) >= 2 and parts[1]:
                    name_parts.append(parts[1])  # First name
                if len(parts) >= 1 and parts[0]:
                    name_parts.append(parts[0])  # Last name
                if name_parts:
                    name = " ".join(name_parts)

            # TEL (Phone) - take the first one found
            elif prop_name == "TEL" and not phone:
                # Remove tel: URI prefix if present
                phone = re.sub(r"^tel:", "", value, flags=re.IGNORECASE)

            # EMAIL
            elif prop_name == "EMAIL" and not email:
                email = value

            # ORG (Organization)
            elif prop_name == "ORG" and not organization:
                # ORG may contain sub-parts separated by semicolons
                organization = value.replace(";", ", ").strip(", ")

            # TITLE
            elif prop_name == "TITLE" and not title:
                title = value

        if not any([name, phone, email, organization, title]):
            logger.warning("vCard parsed but no recognized fields found")
            return {
                "success": False,
                "error": "No recognized fields in vCard",
                "raw": vcard_text[:500],
            }

        logger.info(f"Parsed vCard contact: {name or 'unnamed'}")

        return {
            "success": True,
            "name": name,
            "phone": phone,
            "email": email,
            "organization": organization,
            "title": title,
            "raw": vcard_text,
        }


# =============================================================================
# Singleton Factory
# =============================================================================

_instance: ContactProcessor | None = None


def get_contact_processor() -> ContactProcessor:
    """
    Get or create the global ContactProcessor instance.

    Returns:
        The singleton ContactProcessor instance.
    """
    global _instance
    if _instance is None:
        _instance = ContactProcessor()
    return _instance
