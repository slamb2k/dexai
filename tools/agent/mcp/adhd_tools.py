"""
DexAI ADHD Communication MCP Tools

Exposes DexAI's ADHD-specific communication features as MCP tools for the SDK.
These ensure all agent output is emotionally safe and cognitively appropriate.

Tools:
- dexai_format_response: Apply brevity rules, strip preamble, one-thing mode
- dexai_check_language: Detect and reframe RSD-triggering language

Key Context:
- RSD (Rejection Sensitive Dysphoria) causes extreme emotional pain from criticism
- Standard productivity language ("overdue", "you haven't") triggers shame spirals
- These tools ensure ALL output is emotionally safe

Usage:
    These tools are registered with the SDK via the agent configuration.
    The SDK agent should use them to post-process responses.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Tool: dexai_format_response
# =============================================================================


def dexai_format_response(
    content: str,
    max_sentences: int = 2,
    max_chars: int = 280,
    one_thing_mode: bool = True,
    strip_preamble: bool = True,
) -> dict[str, Any]:
    """
    Apply ADHD-friendly formatting to a response.

    ADHD brains have specific communication needs:
    1. Short is better - long responses lose attention
    2. No filler - preamble like "Sure!" is noise
    3. One thing at a time - lists of 5 things = zero things
    4. Depth on demand - "more" unlocks expanded response

    Args:
        content: The content to format
        max_sentences: Maximum sentences to include (default 2)
        max_chars: Maximum characters (default 280, like a tweet)
        one_thing_mode: If True, extract only ONE actionable item
        strip_preamble: If True, remove "Sure!", "Of course!", etc.

    Returns:
        Dict with formatted content and metadata

    Example:
        Input: "Sure! That's a great question! There are several ways..."
        Output: "Check the API docs first. (Say 'more' for details)"
    """
    try:
        from tools.adhd import response_formatter

        result = response_formatter.format_for_adhd(
            content=content,
            max_sentences=max_sentences,
            max_chars=max_chars,
        )

        if not result.get("success"):
            # Fall back to simple formatting
            formatted = _simple_format(content, max_chars, strip_preamble)
            return {
                "success": True,
                "tool": "dexai_format_response",
                "formatted": formatted,
                "original_length": len(content),
                "formatted_length": len(formatted),
                "fallback": True,
            }

        return {
            "success": True,
            "tool": "dexai_format_response",
            "formatted": result.get("formatted", content),
            "original_length": len(content),
            "formatted_length": len(result.get("formatted", content)),
            "stripped_preamble": result.get("stripped_preamble", []),
            "one_thing_extracted": result.get("one_thing_extracted", False),
        }

    except ImportError as e:
        # Fallback if module not available
        formatted = _simple_format(content, max_chars, strip_preamble)
        return {
            "success": True,
            "tool": "dexai_format_response",
            "formatted": formatted,
            "original_length": len(content),
            "formatted_length": len(formatted),
            "fallback": True,
            "note": f"Response formatter module not available: {e}",
        }
    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_format_response",
            "error": str(e),
        }


def _simple_format(content: str, max_chars: int, strip_preamble: bool) -> str:
    """Simple fallback formatter."""
    # Strip common preambles
    if strip_preamble:
        preambles = [
            "Sure!", "Of course!", "Absolutely!", "Certainly!",
            "Great question!", "That's a great question!",
            "I'd be happy to", "I'd be glad to", "No problem!",
            "Let me help you with that.",
        ]
        stripped = content.strip()
        for preamble in preambles:
            if stripped.startswith(preamble):
                stripped = stripped[len(preamble):].lstrip()
                content = stripped

    # Truncate if too long
    if len(content) > max_chars:
        # Find last sentence boundary before limit
        truncated = content[:max_chars]
        last_period = truncated.rfind(".")
        if last_period > max_chars // 2:
            return truncated[:last_period + 1] + " (Say 'more' for details)"
        return truncated.rstrip() + "... (Say 'more' for details)"

    return content


# =============================================================================
# Tool: dexai_check_language
# =============================================================================


def dexai_check_language(
    content: str,
    auto_reframe: bool = True,
) -> dict[str, Any]:
    """
    Detect and optionally reframe RSD-triggering language.

    RSD (Rejection Sensitive Dysphoria) is an extreme emotional sensitivity
    to criticism. Standard productivity language can trigger shame spirals
    and system avoidance.

    Blocked phrases (examples):
    - "overdue" → "ready to pick up"
    - "you haven't" → "want to"
    - "you forgot" → "let's revisit"
    - "behind schedule" → "let's catch up"

    Args:
        content: The content to check
        auto_reframe: If True, automatically reframe detected phrases

    Returns:
        Dict with check results and optionally reframed content

    Example:
        Input: "You still haven't sent the invoice (3 days overdue)"
        Output: {
            "is_safe": false,
            "detected_phrases": ["you still haven't", "overdue"],
            "reframed": "Ready when you are to send the invoice. Want to do it now?"
        }
    """
    try:
        from tools.adhd import language_filter

        # Check content
        check_result = language_filter.check_content(content)

        detected = check_result.get("detected_phrases", [])
        is_safe = len(detected) == 0

        result = {
            "success": True,
            "tool": "dexai_check_language",
            "is_safe": is_safe,
            "detected_phrases": detected,
            "phrase_count": len(detected),
        }

        # Reframe if requested and phrases found
        if auto_reframe and not is_safe:
            filter_result = language_filter.filter_content(content)
            if filter_result.get("success"):
                result["reframed"] = filter_result.get("filtered", content)
                result["original"] = content
            else:
                result["reframed"] = _simple_reframe(content, detected)
                result["fallback_reframe"] = True

        return result

    except ImportError as e:
        # Fallback check
        detected = _simple_check(content)
        result = {
            "success": True,
            "tool": "dexai_check_language",
            "is_safe": len(detected) == 0,
            "detected_phrases": detected,
            "phrase_count": len(detected),
            "fallback": True,
            "note": f"Language filter module not available: {e}",
        }

        if auto_reframe and detected:
            result["reframed"] = _simple_reframe(content, detected)

        return result

    except Exception as e:
        return {
            "success": False,
            "tool": "dexai_check_language",
            "error": str(e),
        }


def _simple_check(content: str) -> list[str]:
    """Simple fallback check for blocked phrases."""
    blocked = [
        "overdue", "you haven't", "you still haven't", "failed to",
        "you forgot", "missed deadline", "behind schedule",
        "you should have", "you were supposed to", "you never",
        "past due", "you neglected",
    ]
    content_lower = content.lower()
    return [phrase for phrase in blocked if phrase in content_lower]


def _simple_reframe(content: str, detected: list[str]) -> str:
    """Simple fallback reframing."""
    reframes = {
        "overdue": "ready to pick up",
        "you haven't": "want to",
        "you still haven't": "ready when you are to",
        "failed to": "let's try",
        "you forgot": "let's revisit",
        "missed deadline": "let's get this moving",
        "behind schedule": "let's catch up",
        "you should have": "next time, consider",
        "you were supposed to": "the plan was to",
        "you never": "it's been a while since",
        "past due": "ready to tackle",
        "you neglected": "this needs attention",
    }

    result = content
    for phrase in detected:
        replacement = reframes.get(phrase, "let's focus on")
        # Case-insensitive replacement
        import re
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        result = pattern.sub(replacement, result)

    return result


# =============================================================================
# Tool Registry
# =============================================================================


ADHD_TOOLS = {
    "dexai_format_response": {
        "function": dexai_format_response,
        "description": "Apply ADHD-friendly formatting (brevity, strip preamble, one-thing mode)",
        "parameters": {
            "content": {"type": "string", "required": True},
            "max_sentences": {"type": "integer", "required": False, "default": 2},
            "max_chars": {"type": "integer", "required": False, "default": 280},
            "one_thing_mode": {"type": "boolean", "required": False, "default": True},
            "strip_preamble": {"type": "boolean", "required": False, "default": True},
        },
    },
    "dexai_check_language": {
        "function": dexai_check_language,
        "description": "Detect and reframe RSD-triggering language for emotional safety",
        "parameters": {
            "content": {"type": "string", "required": True},
            "auto_reframe": {"type": "boolean", "required": False, "default": True},
        },
    },
}


def get_tool(tool_name: str):
    """Get a tool function by name."""
    tool_info = ADHD_TOOLS.get(tool_name)
    if tool_info:
        return tool_info["function"]
    return None


def list_tools() -> list[str]:
    """List all available ADHD tools."""
    return list(ADHD_TOOLS.keys())


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for testing ADHD tools."""
    import argparse

    parser = argparse.ArgumentParser(description="DexAI ADHD MCP Tools")
    parser.add_argument("--tool", required=True, help="Tool to invoke")
    parser.add_argument("--args", help="JSON arguments")
    parser.add_argument("--content", help="Content to process")
    parser.add_argument("--list", action="store_true", help="List available tools")

    args = parser.parse_args()

    if args.list:
        print("Available ADHD tools:")
        for name, info in ADHD_TOOLS.items():
            print(f"  {name}: {info['description']}")
        return

    tool_func = get_tool(args.tool)
    if not tool_func:
        print(f"Unknown tool: {args.tool}")
        print(f"Available: {list_tools()}")
        sys.exit(1)

    # Parse arguments
    tool_args = {}
    if args.args:
        tool_args = json.loads(args.args)
    if args.content:
        tool_args["content"] = args.content

    # Invoke tool
    result = tool_func(**tool_args)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
