"""
Tool: ADHD Response Formatter
Purpose: Apply brevity rules, strip preamble, and enforce one-thing mode for ADHD users

ADHD brains have specific communication needs:
1. Short is better - long responses lose attention
2. No filler - preamble like "Sure!" is noise
3. One thing at a time - lists of 5 things = zero things
4. Depth on demand - "more" unlocks expanded response

This formatter transforms any AI response into ADHD-friendly output.

Usage:
    # Format for brevity (default 1-2 sentences)
    python tools/adhd/response_formatter.py --action format --content "Your long response..."

    # Format with custom sentence limit
    python tools/adhd/response_formatter.py --action format --content "..." --max-sentences 3

    # Expand response (user said "more")
    python tools/adhd/response_formatter.py --action expand --content "..." --user alice

    # Extract one thing to do
    python tools/adhd/response_formatter.py --action one-thing --content "1. Do X 2. Do Y 3. Do Z"

    # Check if user requested expansion
    python tools/adhd/response_formatter.py --action should-expand --user alice --message "tell me more"

Examples:
    Input:  "That's a great question! So, there are several ways to approach this. First, you could..."
    Output: "Check the API docs first. Say 'more' for details."

    Input:  "Here are your tasks: 1. Send invoice 2. Review PR 3. Call Sarah"
    Output: "Send the invoice to Marcus. Say 'something else' for alternatives."

Dependencies:
    - pyyaml (configuration)
    - re (pattern matching)
    - tools.adhd.language_filter (RSD protection)

Output:
    JSON result with success status, formatted content, and metadata
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration path
CONFIG_PATH = PROJECT_ROOT / "args" / "adhd_mode.yaml"

# Track user expansion requests (in-memory, per-session)
# In production, this would be stored in a database
_expansion_requests: dict[str, datetime] = {}


def load_config() -> dict[str, Any]:
    """Load ADHD mode configuration from YAML file."""
    try:
        import yaml

        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                return yaml.safe_load(f)
        else:
            return get_default_config()
    except ImportError:
        return get_default_config()


def get_default_config() -> dict[str, Any]:
    """Return default config if YAML unavailable."""
    return {
        "adhd_mode": {
            "brevity": {
                "default_max_sentences": 2,
                "default_max_chars": 280,
                "expand_on_keywords": ["more", "details", "explain", "why"],
                "strip_preamble": [
                    "Sure!",
                    "Of course!",
                    "Absolutely!",
                    "Great question!",
                    "That's a great question!",
                    "I'd be happy to",
                    "I'd be glad to",
                    "No problem!",
                    "Certainly!",
                    "Let me help you with that",
                ],
            },
            "one_thing": {
                "enabled": True,
                "trigger_phrases": [
                    "what should i do",
                    "what's next",
                    "where do i start",
                    "i'm stuck",
                    "i'm overwhelmed",
                    "help me decide",
                ],
                "alternative_phrases": ["something else", "another option", "not that"],
            },
        }
    }


def get_brevity_config() -> dict[str, Any]:
    """Get the brevity section of the config."""
    config = load_config()
    return config.get("adhd_mode", {}).get("brevity", {})


def get_one_thing_config() -> dict[str, Any]:
    """Get the one-thing section of the config."""
    config = load_config()
    return config.get("adhd_mode", {}).get("one_thing", {})


def strip_preamble(content: str) -> str:
    """
    Remove filler phrases from the start of a response.

    Args:
        content: Response text potentially starting with preamble

    Returns:
        Content with preamble stripped

    Examples:
        >>> strip_preamble("Sure! I'd be happy to help. Here's the answer.")
        "Here's the answer."

        >>> strip_preamble("That's a great question! So basically...")
        "So basically..."
    """
    config = get_brevity_config()
    preambles = config.get("strip_preamble", [])

    result = content.strip()

    # Keep stripping until no more preambles found
    changed = True
    while changed:
        changed = False
        for preamble in preambles:
            # Check start of string (case-insensitive)
            if result.lower().startswith(preamble.lower()):
                result = result[len(preamble) :].strip()
                changed = True
                break

            # Also check if it's a sentence at the start
            pattern = re.compile(r"^" + re.escape(preamble) + r"[.!?\s]+", re.IGNORECASE)
            if pattern.match(result):
                result = pattern.sub("", result).strip()
                changed = True
                break

    return result


def split_sentences(content: str) -> list[str]:
    """
    Split content into sentences, handling common edge cases.

    Args:
        content: Text to split

    Returns:
        List of sentences
    """
    # Handle common abbreviations
    content = re.sub(r"\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e)\.", r"\1<PERIOD>", content)

    # Split on sentence endings
    sentences = re.split(r"(?<=[.!?])\s+", content)

    # Restore abbreviations
    sentences = [s.replace("<PERIOD>", ".") for s in sentences]

    # Filter empty
    return [s.strip() for s in sentences if s.strip()]


def truncate_to_sentences(content: str, max_sentences: int = 2) -> str:
    """
    Truncate content to a maximum number of sentences.

    Args:
        content: Text to truncate
        max_sentences: Maximum sentences to keep

    Returns:
        Truncated content

    Examples:
        >>> truncate_to_sentences("First. Second. Third. Fourth.", 2)
        "First. Second."
    """
    sentences = split_sentences(content)

    if len(sentences) <= max_sentences:
        return content

    # Take first N sentences
    truncated = sentences[:max_sentences]
    result = " ".join(truncated)

    # Ensure proper ending punctuation
    if result and result[-1] not in ".!?":
        result += "."

    return result


def format_response(
    content: str,
    max_sentences: int | None = None,
    max_chars: int | None = None,
    add_more_hint: bool = True,
    apply_rsd_filter: bool = True,
) -> dict[str, Any]:
    """
    Format a response for ADHD-friendly consumption.

    Args:
        content: The full response to format
        max_sentences: Override default sentence limit
        max_chars: Override default character limit
        add_more_hint: Whether to add "Say 'more' for details"
        apply_rsd_filter: Whether to apply RSD language filter

    Returns:
        dict with success, original, formatted content, and metadata

    Examples:
        >>> format_response("Sure! That's a great question. Here's a long explanation...")
        {
            "success": True,
            "formatted": "Here's a long explanation. Say 'more' for details.",
            "was_truncated": True,
            "original_sentences": 5,
            "kept_sentences": 2
        }
    """
    config = get_brevity_config()
    max_sent = max_sentences or config.get("default_max_sentences", 2)
    max_ch = max_chars or config.get("default_max_chars", 280)

    # Step 1: Strip preamble
    cleaned = strip_preamble(content)

    # Step 2: Apply RSD filter
    if apply_rsd_filter:
        try:
            from tools.adhd.language_filter import filter_content

            filter_result = filter_content(cleaned)
            cleaned = filter_result.get("filtered", cleaned)
        except ImportError:
            pass  # RSD filter not available

    # Step 3: Count original sentences
    original_sentences = split_sentences(cleaned)
    original_count = len(original_sentences)

    # Step 4: Truncate to max sentences
    formatted = truncate_to_sentences(cleaned, max_sent)

    # Step 5: Check character limit (if still too long)
    if len(formatted) > max_ch:
        formatted = formatted[:max_ch].rsplit(" ", 1)[0]
        if not formatted.endswith((".", "!", "?")):
            formatted += "..."

    # Step 6: Add "more" hint if truncated
    was_truncated = original_count > max_sent or len(cleaned) > len(formatted)
    if was_truncated and add_more_hint:
        formatted = formatted.rstrip(".!?") + ". Say 'more' for details."

    return {
        "success": True,
        "original": content,
        "formatted": formatted,
        "was_truncated": was_truncated,
        "original_sentences": original_count,
        "kept_sentences": min(original_count, max_sent),
        "original_chars": len(content),
        "formatted_chars": len(formatted),
    }


def expand_response(content: str, user: str, apply_rsd_filter: bool = True) -> dict[str, Any]:
    """
    Return full response when user requests expansion.

    Args:
        content: The full response to return
        user: User ID requesting expansion
        apply_rsd_filter: Whether to apply RSD language filter

    Returns:
        dict with success and full content

    Examples:
        >>> expand_response("Full detailed explanation here...", "alice")
        {
            "success": True,
            "expanded": "Full detailed explanation here...",
            "user": "alice"
        }
    """
    # Track that this user requested expansion
    _expansion_requests[user] = datetime.now()

    # Still strip preamble even on expansion
    cleaned = strip_preamble(content)

    # Apply RSD filter
    if apply_rsd_filter:
        try:
            from tools.adhd.language_filter import filter_content

            filter_result = filter_content(cleaned)
            cleaned = filter_result.get("filtered", cleaned)
        except ImportError:
            pass

    return {"success": True, "expanded": cleaned, "user": user, "expansion_tracked": True}


def should_expand(user: str, message: str) -> dict[str, Any]:
    """
    Check if user's message indicates they want expanded response.

    Args:
        user: User ID
        message: User's message to check

    Returns:
        dict with should_expand boolean

    Examples:
        >>> should_expand("alice", "tell me more")
        {"success": True, "should_expand": True, "matched_keyword": "more"}

        >>> should_expand("alice", "thanks")
        {"success": True, "should_expand": False, "matched_keyword": None}
    """
    config = get_brevity_config()
    keywords = config.get("expand_on_keywords", ["more", "details", "explain", "why"])

    message_lower = message.lower()

    for keyword in keywords:
        if keyword.lower() in message_lower:
            return {
                "success": True,
                "should_expand": True,
                "matched_keyword": keyword,
                "user": user,
            }

    # Also check if user recently requested expansion (within 5 minutes)
    # This provides continuity in conversation
    if user in _expansion_requests:
        last_request = _expansion_requests[user]
        if datetime.now() - last_request < timedelta(minutes=5):
            return {
                "success": True,
                "should_expand": True,
                "matched_keyword": None,
                "reason": "recent_expansion_context",
                "user": user,
            }

    return {"success": True, "should_expand": False, "matched_keyword": None, "user": user}


def extract_one_thing(content: str, context: str | None = None) -> dict[str, Any]:
    """
    Extract THE single most important actionable item from content.

    When user asks "what should I do?" - this returns exactly ONE action,
    not a list. A list of 5 things is actually zero things for ADHD brains.

    Args:
        content: Text containing tasks, options, or actions
        context: Optional context about user's current state (energy, time, etc.)

    Returns:
        dict with the one selected action

    Examples:
        >>> extract_one_thing("Tasks: 1. Send invoice 2. Review PR 3. Call Sarah")
        {
            "success": True,
            "one_thing": "Send the invoice.",
            "alternatives_available": True,
            "total_found": 3
        }
    """
    # Parse potential list items
    items = []

    # Pattern 1: Numbered list (1. item, 2. item)
    numbered = re.findall(r"\d+[.)]\s*([^\n\d]+?)(?=\d+[.)]|\n|$)", content)
    items.extend([i.strip() for i in numbered if i.strip()])

    # Pattern 2: Bullet list (- item, * item)
    bulleted = re.findall(r"[-*]\s*([^\n-*]+?)(?=[-*]|\n|$)", content)
    items.extend([i.strip() for i in bulleted if i.strip()])

    # Pattern 3: Comma-separated (do X, do Y, do Z)
    if not items and "," in content:
        parts = content.split(",")
        items = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]

    # Pattern 4: "or" separated (do X or do Y or do Z)
    if not items and " or " in content.lower():
        parts = re.split(r"\s+or\s+", content, flags=re.IGNORECASE)
        items = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]

    # If no list found, the content itself might be the one thing
    if not items:
        # Just return a cleaned version of the first sentence
        sentences = split_sentences(content)
        if sentences:
            items = [sentences[0]]

    if not items:
        return {
            "success": True,
            "one_thing": "Let's figure out what's most important. What's on your mind?",
            "alternatives_available": False,
            "total_found": 0,
        }

    # Select the first item (in production, this would use LLM for smart selection)
    # For now, prefer shorter items (less overwhelming) with action verbs
    action_verbs = ["send", "call", "email", "write", "review", "check", "finish", "start"]

    # Score items
    scored = []
    for item in items:
        score = 100 - len(item)  # Prefer shorter
        item_lower = item.lower()
        for verb in action_verbs:
            if verb in item_lower:
                score += 20  # Bonus for action verbs
                break
        scored.append((item, score))

    # Sort by score and take best
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[0][0]

    # Clean up the selected item
    selected = selected.strip().rstrip(".")
    if selected and not selected[0].isupper():
        selected = selected[0].upper() + selected[1:]
    selected += "."

    # Add hint about alternatives
    if len(items) > 1:
        selected += " Say 'something else' for an alternative."

    return {
        "success": True,
        "one_thing": selected,
        "alternatives_available": len(items) > 1,
        "total_found": len(items),
        "all_items": items,  # Include for debugging/logging
    }


def is_one_thing_trigger(message: str) -> dict[str, Any]:
    """
    Check if user's message should trigger one-thing mode.

    Args:
        message: User's message to check

    Returns:
        dict with is_trigger boolean

    Examples:
        >>> is_one_thing_trigger("what should I do?")
        {"success": True, "is_trigger": True, "matched_phrase": "what should i do"}

        >>> is_one_thing_trigger("how do I configure this?")
        {"success": True, "is_trigger": False, "matched_phrase": None}
    """
    config = get_one_thing_config()
    triggers = config.get("trigger_phrases", [])

    message_lower = message.lower()

    for phrase in triggers:
        if phrase.lower() in message_lower:
            return {"success": True, "is_trigger": True, "matched_phrase": phrase}

    return {"success": True, "is_trigger": False, "matched_phrase": None}


def format_with_rsd(content: str, **kwargs) -> dict[str, Any]:
    """
    Convenience function: format + RSD filter in one call.

    Args:
        content: Response to format
        **kwargs: Additional args passed to format_response

    Returns:
        dict with formatted and RSD-safe content
    """
    return format_response(content, apply_rsd_filter=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="ADHD Response Formatter - brevity-first, one-thing mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Format response for brevity
  python response_formatter.py --action format --content "Sure! Here's a long explanation..."

  # Expand response (user said "more")
  python response_formatter.py --action expand --content "Full details..." --user alice

  # Extract one thing from a list
  python response_formatter.py --action one-thing --content "1. Do X 2. Do Y 3. Do Z"

  # Check if user wants expansion
  python response_formatter.py --action should-expand --user alice --message "tell me more"

  # Check if message triggers one-thing mode
  python response_formatter.py --action is-trigger --message "what should I do?"
        """,
    )

    parser.add_argument(
        "--action",
        required=True,
        choices=["format", "expand", "one-thing", "should-expand", "is-trigger", "strip-preamble"],
        help="Action to perform",
    )
    parser.add_argument("--content", help="Text content to format")
    parser.add_argument("--message", help="User message to check")
    parser.add_argument("--user", help="User ID")
    parser.add_argument("--max-sentences", type=int, help="Override max sentences")
    parser.add_argument("--max-chars", type=int, help="Override max characters")
    parser.add_argument("--no-more-hint", action="store_true", help='Skip adding "say more" hint')
    parser.add_argument("--no-rsd-filter", action="store_true", help="Skip RSD language filter")

    args = parser.parse_args()
    result = None

    if args.action == "format":
        if not args.content:
            print("Error: --content required for format action")
            sys.exit(1)
        result = format_response(
            args.content,
            max_sentences=args.max_sentences,
            max_chars=args.max_chars,
            add_more_hint=not args.no_more_hint,
            apply_rsd_filter=not args.no_rsd_filter,
        )

    elif args.action == "expand":
        if not args.content:
            print("Error: --content required for expand action")
            sys.exit(1)
        if not args.user:
            print("Error: --user required for expand action")
            sys.exit(1)
        result = expand_response(args.content, args.user, apply_rsd_filter=not args.no_rsd_filter)

    elif args.action == "one-thing":
        if not args.content:
            print("Error: --content required for one-thing action")
            sys.exit(1)
        result = extract_one_thing(args.content)

    elif args.action == "should-expand":
        if not args.user or not args.message:
            print("Error: --user and --message required for should-expand action")
            sys.exit(1)
        result = should_expand(args.user, args.message)

    elif args.action == "is-trigger":
        if not args.message:
            print("Error: --message required for is-trigger action")
            sys.exit(1)
        result = is_one_thing_trigger(args.message)

    elif args.action == "strip-preamble":
        if not args.content:
            print("Error: --content required for strip-preamble action")
            sys.exit(1)
        cleaned = strip_preamble(args.content)
        result = {
            "success": True,
            "original": args.content,
            "cleaned": cleaned,
            "chars_removed": len(args.content) - len(cleaned),
        }

    if result:
        if result.get("success"):
            print("OK Formatted")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
