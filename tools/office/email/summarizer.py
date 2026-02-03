"""
Tool: Email Summarizer
Purpose: Generate ADHD-friendly inbox summaries

Creates concise, actionable summaries of inbox state designed for
users who get overwhelmed by email. Focuses on:
- What needs attention NOW
- What can wait
- Quick wins (easy to respond)
- Potential blockers (need info before acting)

Usage:
    python tools/office/email/summarizer.py --account-id <id>
    python tools/office/email/summarizer.py --account-id <id> --detailed
    python tools/office/email/summarizer.py --account-id <id> --priorities

Dependencies:
    - aiohttp (for API calls to providers)
"""

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office.email.reader import list_emails, load_account  # noqa: E402
from tools.office.models import Email, IntegrationLevel  # noqa: E402


# Priority keywords for classification
URGENT_KEYWORDS = [
    "urgent", "asap", "immediately", "critical", "emergency",
    "deadline", "overdue", "today", "eod", "end of day",
]

ACTION_KEYWORDS = [
    "please", "can you", "could you", "would you", "need you to",
    "action required", "response needed", "waiting for",
]

FYI_KEYWORDS = [
    "fyi", "for your information", "no action needed",
    "newsletter", "digest", "weekly", "monthly",
]


async def get_inbox_summary(
    account_id: str,
    max_emails: int = 50,
    detailed: bool = False,
) -> dict[str, Any]:
    """
    Generate an inbox summary.

    Args:
        account_id: Account ID
        max_emails: Maximum emails to analyze
        detailed: Include more detail in summary

    Returns:
        dict with summary information
    """
    # Fetch recent emails
    result = await list_emails(account_id, limit=max_emails)

    if not result.get("success"):
        return result

    emails: list[Email] = result.get("emails", [])

    if not emails:
        return {
            "success": True,
            "summary": "Your inbox is empty! Nothing to review.",
            "unread_count": 0,
            "total_analyzed": 0,
        }

    # Analyze emails
    analysis = analyze_emails(emails)

    # Generate summary
    summary = generate_summary_text(analysis, detailed)

    return {
        "success": True,
        "summary": summary,
        "analysis": analysis,
        "total_analyzed": len(emails),
    }


def analyze_emails(emails: list[Email]) -> dict[str, Any]:
    """
    Analyze a list of emails for summary generation.

    Args:
        emails: List of emails to analyze

    Returns:
        dict with analysis results
    """
    now = datetime.now()

    # Initialize categories
    unread = []
    urgent = []
    needs_action = []
    fyi_only = []
    quick_wins = []

    # Analyze each email
    for email_obj in emails:
        subject_lower = (email_obj.subject or "").lower()
        snippet_lower = (email_obj.snippet or "").lower()
        combined = f"{subject_lower} {snippet_lower}"

        # Check urgency
        is_urgent = any(kw in combined for kw in URGENT_KEYWORDS)
        needs_response = any(kw in combined for kw in ACTION_KEYWORDS)
        is_fyi = any(kw in combined for kw in FYI_KEYWORDS)

        # Quick win: short subject, no attachments, recent
        is_quick_win = (
            len(email_obj.subject or "") < 50
            and not email_obj.has_attachments
            and (now - email_obj.received_at).days < 2
        )

        # Categorize
        if not email_obj.is_read:
            unread.append(email_obj)

        if is_urgent:
            urgent.append(email_obj)
        elif needs_response and not is_fyi:
            needs_action.append(email_obj)
        elif is_fyi or not needs_response:
            fyi_only.append(email_obj)

        if is_quick_win and not email_obj.is_read:
            quick_wins.append(email_obj)

    # Group by sender domain
    sender_domains: dict[str, int] = defaultdict(int)
    for email_obj in emails:
        if email_obj.sender:
            domain = email_obj.sender.address.split("@")[-1]
            sender_domains[domain] += 1

    # Time analysis
    today = [e for e in emails if (now - e.received_at).days < 1]
    this_week = [e for e in emails if (now - e.received_at).days < 7]
    older = [e for e in emails if (now - e.received_at).days >= 7]

    return {
        "total": len(emails),
        "unread_count": len(unread),
        "unread": unread[:5],  # Top 5 for display
        "urgent_count": len(urgent),
        "urgent": urgent[:3],  # Top 3
        "needs_action_count": len(needs_action),
        "needs_action": needs_action[:5],
        "fyi_count": len(fyi_only),
        "quick_wins_count": len(quick_wins),
        "quick_wins": quick_wins[:3],
        "today_count": len(today),
        "this_week_count": len(this_week),
        "older_count": len(older),
        "top_senders": sorted(sender_domains.items(), key=lambda x: x[1], reverse=True)[:5],
    }


def generate_summary_text(analysis: dict[str, Any], detailed: bool = False) -> str:
    """
    Generate human-readable summary text.

    Args:
        analysis: Analysis results
        detailed: Include more detail

    Returns:
        Summary string
    """
    lines = []

    # Header
    lines.append("**Inbox Summary**\n")

    # Quick stats
    lines.append(f"Unread: {analysis['unread_count']} | "
                 f"Needs Action: {analysis['needs_action_count']} | "
                 f"FYI: {analysis['fyi_count']}")
    lines.append("")

    # Urgent items (always show)
    if analysis["urgent_count"] > 0:
        lines.append(f"**{analysis['urgent_count']} Urgent** (needs attention now):")
        for email_obj in analysis["urgent"]:
            sender = str(email_obj.sender) if email_obj.sender else "Unknown"
            lines.append(f"  - {email_obj.subject[:50]}... ({sender})")
        lines.append("")

    # Quick wins (ADHD-friendly)
    if analysis["quick_wins_count"] > 0:
        lines.append(f"**{analysis['quick_wins_count']} Quick Wins** (easy to handle now):")
        for email_obj in analysis["quick_wins"]:
            sender = str(email_obj.sender) if email_obj.sender else "Unknown"
            lines.append(f"  - {email_obj.subject[:50]}... ({sender})")
        lines.append("")

    # Needs action
    if detailed and analysis["needs_action_count"] > 0:
        lines.append(f"**{analysis['needs_action_count']} Need Response:**")
        for email_obj in analysis["needs_action"]:
            sender = str(email_obj.sender) if email_obj.sender else "Unknown"
            lines.append(f"  - {email_obj.subject[:50]}... ({sender})")
        lines.append("")

    # Time breakdown
    if detailed:
        lines.append("**Timeline:**")
        lines.append(f"  Today: {analysis['today_count']} | "
                     f"This Week: {analysis['this_week_count']} | "
                     f"Older: {analysis['older_count']}")
        lines.append("")

    # Top senders
    if detailed and analysis["top_senders"]:
        lines.append("**Top Senders:**")
        for domain, count in analysis["top_senders"][:3]:
            lines.append(f"  - {domain}: {count} emails")
        lines.append("")

    # ADHD-friendly recommendation
    lines.append("---")
    if analysis["urgent_count"] > 0:
        lines.append("Start with the urgent items first.")
    elif analysis["quick_wins_count"] > 0:
        lines.append("Start with a quick win to build momentum!")
    elif analysis["unread_count"] > 0:
        lines.append("Check your unread emails when you have a few minutes.")
    else:
        lines.append("All caught up!")

    return "\n".join(lines)


async def get_priority_emails(
    account_id: str,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Get the most important emails that need attention.

    ADHD-optimized: Returns ONE thing to focus on, with backups.

    Args:
        account_id: Account ID
        limit: Maximum emails to return

    Returns:
        dict with priority emails
    """
    result = await list_emails(account_id, limit=50, unread_only=True)

    if not result.get("success"):
        return result

    emails: list[Email] = result.get("emails", [])

    if not emails:
        return {
            "success": True,
            "message": "No unread emails to prioritize.",
            "primary": None,
            "alternatives": [],
        }

    # Score each email
    scored = []
    now = datetime.now()

    for email_obj in emails:
        score = 0
        subject_lower = (email_obj.subject or "").lower()
        snippet_lower = (email_obj.snippet or "").lower()
        combined = f"{subject_lower} {snippet_lower}"

        # Urgency boost
        if any(kw in combined for kw in URGENT_KEYWORDS):
            score += 50

        # Action needed boost
        if any(kw in combined for kw in ACTION_KEYWORDS):
            score += 30

        # Recency boost
        hours_old = (now - email_obj.received_at).total_seconds() / 3600
        if hours_old < 1:
            score += 20
        elif hours_old < 24:
            score += 10

        # Starred boost
        if email_obj.is_starred:
            score += 25

        # FYI penalty
        if any(kw in combined for kw in FYI_KEYWORDS):
            score -= 20

        scored.append((score, email_obj))

    # Sort by score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Get top items
    top_emails = [e for _, e in scored[:limit]]

    if not top_emails:
        return {
            "success": True,
            "message": "No priority emails found.",
            "primary": None,
            "alternatives": [],
        }

    primary = top_emails[0]

    return {
        "success": True,
        "message": "Here's what needs your attention:",
        "primary": {
            "id": primary.message_id,
            "subject": primary.subject,
            "sender": str(primary.sender) if primary.sender else "Unknown",
            "snippet": primary.snippet,
            "received": primary.received_at.isoformat(),
        },
        "alternatives": [
            {
                "id": e.message_id,
                "subject": e.subject,
                "sender": str(e.sender) if e.sender else "Unknown",
            }
            for e in top_emails[1:4]  # 3 alternatives
        ],
        "total_unread": len(emails),
    }


async def get_one_thing(account_id: str) -> dict[str, Any]:
    """
    Get THE one email to focus on right now.

    ADHD-optimized: Single focus, no overwhelm.

    Args:
        account_id: Account ID

    Returns:
        dict with one email to handle
    """
    priority_result = await get_priority_emails(account_id, limit=1)

    if not priority_result.get("success"):
        return priority_result

    primary = priority_result.get("primary")

    if not primary:
        return {
            "success": True,
            "message": "Nothing urgent in your inbox. You're caught up!",
            "email": None,
        }

    return {
        "success": True,
        "message": f"Focus on this: \"{primary['subject']}\" from {primary['sender']}",
        "email": primary,
        "total_unread": priority_result.get("total_unread", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="Email Summarizer")
    parser.add_argument("--account-id", required=True, help="Account ID")
    parser.add_argument("--detailed", action="store_true", help="Include more detail")
    parser.add_argument("--priorities", action="store_true", help="Show priority emails")
    parser.add_argument("--one-thing", action="store_true", help="Show ONE email to focus on")
    parser.add_argument("--limit", type=int, default=50, help="Emails to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.one_thing:
        result = asyncio.run(get_one_thing(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("message"))
            if result.get("email"):
                print(f"\n  From: {result['email']['sender']}")
                print(f"  Preview: {result['email']['snippet'][:100]}...")
        else:
            print(f"Error: {result.get('error')}")

    elif args.priorities:
        result = asyncio.run(get_priority_emails(args.account_id))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("message", ""))
            if result.get("primary"):
                print(f"\n**Primary:** {result['primary']['subject']}")
                print(f"  From: {result['primary']['sender']}")
            if result.get("alternatives"):
                print("\n**Also consider:**")
                for alt in result["alternatives"]:
                    print(f"  - {alt['subject'][:50]}...")
        else:
            print(f"Error: {result.get('error')}")

    else:
        result = asyncio.run(get_inbox_summary(
            args.account_id,
            max_emails=args.limit,
            detailed=args.detailed,
        ))
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        elif result.get("success"):
            print(result.get("summary"))
        else:
            print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    main()
