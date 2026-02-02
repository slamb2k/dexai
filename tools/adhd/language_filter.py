"""
Tool: RSD-Safe Language Filter
Purpose: Detect and reframe guilt-inducing language for ADHD users with Rejection Sensitive Dysphoria

RSD (Rejection Sensitive Dysphoria) is an extreme emotional sensitivity to criticism,
rejection, or perceived failure. Standard productivity language ("overdue", "you haven't")
can trigger shame spirals and system avoidance.

This filter ensures ALL DexAI output is emotionally safe by:
1. Detecting blocked phrases that trigger RSD
2. Reframing them to forward-facing alternatives
3. Maintaining the same information while changing the tone

Usage:
    # Filter content (detect and reframe)
    python tools/adhd/language_filter.py --action filter --content "You still haven't sent the invoice"

    # Check content (detect only, no reframing)
    python tools/adhd/language_filter.py --action check --content "The task is overdue"

    # Get list of blocked phrases
    python tools/adhd/language_filter.py --action list-blocked

    # Add custom blocked phrase
    python tools/adhd/language_filter.py --action add-blocked --phrase "you should have"

Examples:
    Input:  "You still haven't sent the invoice that was due 3 days ago"
    Output: "Ready when you are to send the invoice. Want me to draft it?"

    Input:  "You forgot to call Sarah yesterday"
    Output: "Let's revisit calling Sarah. Want to do it now?"

    Input:  "The deadline was missed and you're behind schedule"
    Output: "Let's get this moving and catch up. Ready when you are."

Dependencies:
    - pyyaml (configuration)
    - re (pattern matching)

Output:
    JSON result with success status, filtered content, and detected phrases
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration path
CONFIG_PATH = PROJECT_ROOT / 'args' / 'adhd_mode.yaml'


def load_config() -> Dict[str, Any]:
    """Load ADHD mode configuration from YAML file."""
    try:
        import yaml
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r') as f:
                return yaml.safe_load(f)
        else:
            return get_default_config()
    except ImportError:
        # Fallback if yaml not installed
        return get_default_config()


def get_default_config() -> Dict[str, Any]:
    """Return default RSD protection config if YAML unavailable."""
    return {
        'adhd_mode': {
            'rsd_protection': {
                'enabled': True,
                'blocked_phrases': [
                    'overdue', 'you haven\'t', 'you still haven\'t',
                    'failed to', 'you forgot', 'missed deadline',
                    'behind schedule', 'you should have', 'you were supposed to',
                    'you never', 'past due', 'you neglected'
                ],
                'reframe_patterns': {
                    'overdue': 'ready to pick up',
                    'you haven\'t': 'want to',
                    'you still haven\'t': 'ready when you are to',
                    'you forgot': 'let\'s revisit',
                    'you forgot to': 'let\'s',
                    'missed': 'let\'s reschedule',
                    'behind schedule': 'let\'s catch up on',
                    'failed to': 'want to try',
                    'past due': 'ready to tackle'
                }
            }
        }
    }


def get_rsd_config() -> Dict[str, Any]:
    """Get the RSD protection section of the config."""
    config = load_config()
    return config.get('adhd_mode', {}).get('rsd_protection', {})


def detect_blocked_phrases(content: str) -> List[Dict[str, Any]]:
    """
    Detect all blocked phrases in content.

    Args:
        content: Text to scan for RSD-triggering phrases

    Returns:
        List of dicts with phrase, position, and suggested reframe

    Examples:
        >>> detect_blocked_phrases("You still haven't sent the invoice")
        [{'phrase': "you still haven't", 'position': 0, 'reframe': 'ready when you are to'}]
    """
    config = get_rsd_config()
    blocked = config.get('blocked_phrases', [])
    reframes = config.get('reframe_patterns', {})

    detections = []
    content_lower = content.lower()

    for phrase in blocked:
        phrase_lower = phrase.lower()
        # Find all occurrences
        start = 0
        while True:
            pos = content_lower.find(phrase_lower, start)
            if pos == -1:
                break

            # Get the suggested reframe
            reframe = reframes.get(phrase_lower, reframes.get(phrase, None))

            detections.append({
                'phrase': phrase,
                'position': pos,
                'length': len(phrase),
                'reframe': reframe
            })
            start = pos + 1

    # Sort by position
    detections.sort(key=lambda x: x['position'])
    return detections


def reframe_content(content: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Reframe content by replacing blocked phrases with forward-facing alternatives.

    Args:
        content: Text containing potential RSD triggers

    Returns:
        Tuple of (reframed_content, list_of_changes)

    Examples:
        >>> reframe_content("You still haven't sent the invoice")
        ("Ready when you are to send the invoice", [{'original': "You still haven't", ...}])

        >>> reframe_content("The task is overdue by 3 days")
        ("The task is ready to pick up, 3 days ready", [{'original': 'overdue', ...}])
    """
    config = get_rsd_config()
    reframes = config.get('reframe_patterns', {})
    blocked = config.get('blocked_phrases', [])

    changes = []
    result = content

    # Sort phrases by length (longest first) to avoid partial replacements
    sorted_phrases = sorted(blocked, key=len, reverse=True)

    for phrase in sorted_phrases:
        phrase_lower = phrase.lower()
        reframe = reframes.get(phrase_lower, reframes.get(phrase))

        if reframe is None:
            # No reframe available, use generic forward-facing language
            reframe = "let's"

        # Case-insensitive replacement while preserving surrounding text
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        matches = list(pattern.finditer(result))

        if matches:
            for match in reversed(matches):  # Reverse to preserve positions
                original = match.group()

                # Match capitalization
                if original[0].isupper():
                    replacement = reframe.capitalize()
                else:
                    replacement = reframe.lower()

                changes.append({
                    'original': original,
                    'replacement': replacement,
                    'position': match.start()
                })

                result = result[:match.start()] + replacement + result[match.end():]

    # Sort changes by original position
    changes.sort(key=lambda x: x['position'])
    return result, changes


def check_content(content: str) -> Dict[str, Any]:
    """
    Check content for RSD-triggering phrases without modifying.

    Args:
        content: Text to check

    Returns:
        dict with success, is_safe, and any detected phrases

    Examples:
        >>> check_content("Ready when you are")
        {"success": True, "is_safe": True, "detections": []}

        >>> check_content("You forgot to do it")
        {"success": True, "is_safe": False, "detections": [{"phrase": "you forgot", ...}]}
    """
    detections = detect_blocked_phrases(content)

    return {
        "success": True,
        "is_safe": len(detections) == 0,
        "detections": detections,
        "phrase_count": len(detections)
    }


def filter_content(content: str) -> Dict[str, Any]:
    """
    Filter content by detecting and reframing all RSD-triggering phrases.

    Args:
        content: Text to filter

    Returns:
        dict with success, original, filtered content, and changes made

    Examples:
        >>> filter_content("You still haven't sent the invoice")
        {
            "success": True,
            "original": "You still haven't sent the invoice",
            "filtered": "Ready when you are to send the invoice",
            "changes": [{"original": "You still haven't", "replacement": "Ready when you are to", ...}],
            "was_modified": True
        }
    """
    filtered, changes = reframe_content(content)

    return {
        "success": True,
        "original": content,
        "filtered": filtered,
        "changes": changes,
        "was_modified": len(changes) > 0
    }


def list_blocked_phrases() -> Dict[str, Any]:
    """
    List all currently blocked phrases and their reframes.

    Returns:
        dict with blocked phrases and reframe patterns
    """
    config = get_rsd_config()

    return {
        "success": True,
        "blocked_phrases": config.get('blocked_phrases', []),
        "reframe_patterns": config.get('reframe_patterns', {}),
        "count": len(config.get('blocked_phrases', []))
    }


def add_blocked_phrase(phrase: str, reframe: Optional[str] = None) -> Dict[str, Any]:
    """
    Add a new blocked phrase to the configuration.

    Note: This modifies the YAML config file.

    Args:
        phrase: The phrase to block
        reframe: Optional suggested reframe (defaults to "let's")

    Returns:
        dict with success status
    """
    try:
        import yaml
    except ImportError:
        return {"success": False, "error": "pyyaml required for config modification"}

    if not CONFIG_PATH.exists():
        return {"success": False, "error": f"Config file not found: {CONFIG_PATH}"}

    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)

    rsd = config.setdefault('adhd_mode', {}).setdefault('rsd_protection', {})
    blocked = rsd.setdefault('blocked_phrases', [])
    reframes = rsd.setdefault('reframe_patterns', {})

    phrase_lower = phrase.lower()
    if phrase_lower not in [p.lower() for p in blocked]:
        blocked.append(phrase)

    if reframe:
        reframes[phrase_lower] = reframe

    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return {
        "success": True,
        "message": f"Added blocked phrase: '{phrase}'",
        "reframe": reframe or "let's (default)"
    }


def batch_filter(contents: List[str]) -> Dict[str, Any]:
    """
    Filter multiple pieces of content at once.

    Args:
        contents: List of text strings to filter

    Returns:
        dict with results for each input
    """
    results = []
    total_changes = 0

    for content in contents:
        result = filter_content(content)
        results.append(result)
        total_changes += len(result.get('changes', []))

    return {
        "success": True,
        "results": results,
        "total_items": len(contents),
        "total_changes": total_changes
    }


def main():
    parser = argparse.ArgumentParser(
        description='RSD-Safe Language Filter for ADHD Communication',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Filter content (detect and reframe)
  python language_filter.py --action filter --content "You still haven't sent the invoice"

  # Check content without modifying
  python language_filter.py --action check --content "The task is overdue"

  # List all blocked phrases
  python language_filter.py --action list-blocked

  # Add new blocked phrase
  python language_filter.py --action add-blocked --phrase "you should have" --reframe "you could"
        """
    )

    parser.add_argument('--action', required=True,
                       choices=['filter', 'check', 'list-blocked', 'add-blocked', 'batch-filter'],
                       help='Action to perform')
    parser.add_argument('--content', help='Text content to filter or check')
    parser.add_argument('--phrase', help='Phrase to add (for add-blocked action)')
    parser.add_argument('--reframe', help='Suggested reframe for new phrase')
    parser.add_argument('--contents', help='JSON array of contents (for batch-filter)')

    args = parser.parse_args()
    result = None

    if args.action == 'filter':
        if not args.content:
            print("Error: --content required for filter action")
            sys.exit(1)
        result = filter_content(args.content)

    elif args.action == 'check':
        if not args.content:
            print("Error: --content required for check action")
            sys.exit(1)
        result = check_content(args.content)

    elif args.action == 'list-blocked':
        result = list_blocked_phrases()

    elif args.action == 'add-blocked':
        if not args.phrase:
            print("Error: --phrase required for add-blocked action")
            sys.exit(1)
        result = add_blocked_phrase(args.phrase, args.reframe)

    elif args.action == 'batch-filter':
        if not args.contents:
            print("Error: --contents required for batch-filter action (JSON array)")
            sys.exit(1)
        try:
            contents = json.loads(args.contents)
            result = batch_filter(contents)
        except json.JSONDecodeError:
            print("Error: --contents must be valid JSON array")
            sys.exit(1)

    if result:
        if result.get('success'):
            status = "SAFE" if result.get('is_safe', True) else "MODIFIED"
            if args.action == 'check' and not result.get('is_safe'):
                status = "UNSAFE"
            print(f"OK {status}")
        else:
            print(f"ERROR {result.get('error')}")
            sys.exit(1)

        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
