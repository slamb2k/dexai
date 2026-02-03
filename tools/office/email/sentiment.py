"""
Tool: Email Sentiment Analysis
Purpose: Detect emotional content in outgoing emails for ADHD users

ADHD users may impulsively send emails they later regret. This tool analyzes
email content for emotional indicators that suggest the user should wait
before sending.

Detection patterns:
- Negative language (similar to RSD detection in tools/adhd/language_filter.py)
- Strong emotional words ("furious", "disappointed", "unacceptable")
- ALL CAPS sections
- Excessive punctuation (!!!, ???)
- Reactive phrasing ("in response to your...", "I can't believe...")

Usage:
    # Analyze email content
    python tools/office/email/sentiment.py --subject "Re: Issue" --body "I can't believe..."

    # Check if safe to send
    python tools/office/email/sentiment.py --subject "Meeting" --body "Let's discuss" --check-safe

    # JSON output
    python tools/office/email/sentiment.py --subject "Hello" --body "Hi there" --json

Dependencies:
    - re (pattern matching)

Output:
    JSON result with score, flags, suggestion, and safe_to_send boolean
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Emotional word lists
STRONG_NEGATIVE_WORDS = [
    "furious",
    "outraged",
    "disgusted",
    "appalled",
    "unacceptable",
    "ridiculous",
    "incompetent",
    "pathetic",
    "terrible",
    "horrible",
    "worst",
    "hate",
    "stupid",
    "idiotic",
    "useless",
    "worthless",
    "failure",
    "disaster",
    "nightmare",
    "unbelievable",
    "insane",
    "absurd",
    "outrageous",
]

MODERATE_NEGATIVE_WORDS = [
    "disappointed",
    "frustrated",
    "annoyed",
    "concerned",
    "upset",
    "bothered",
    "confused",
    "worried",
    "unhappy",
    "dissatisfied",
    "inadequate",
    "insufficient",
    "poor",
    "bad",
    "wrong",
    "mistake",
    "error",
    "problem",
    "issue",
    "complaint",
]

REACTIVE_PHRASES = [
    r"i can't believe",
    r"how dare",
    r"are you serious",
    r"are you kidding",
    r"what were you thinking",
    r"this is insane",
    r"in response to your",
    r"to your point about",
    r"i take offense",
    r"i am writing to complain",
    r"i demand",
    r"you need to",
    r"you must",
    r"you should have",
    r"you failed to",
    r"you never",
    r"you always",
    r"thanks for nothing",
    r"nice try but",
    r"with all due respect",  # Often passive-aggressive
    r"as per my previous email",  # Frustration indicator
    r"as i mentioned before",  # Frustration indicator
    r"to be clear",  # Can be condescending
    r"let me be frank",
    r"frankly",
    r"honestly",
    r"clearly you",
]

AGGRESSIVE_CLOSING_PHRASES = [
    r"fix this immediately",
    r"resolve this now",
    r"handle this today",
    r"expecting immediate",
    r"or else",
    r"you have until",
    r"final warning",
    r"last chance",
    r"no excuses",
]


def analyze_email_sentiment(subject: str, body: str) -> dict[str, Any]:
    """
    Analyze email for emotional content that ADHD users might regret sending.

    Args:
        subject: Email subject line
        body: Email body text

    Returns:
        {
            "score": float,           # 0.0 (calm) to 1.0 (highly emotional)
            "flags": list[str],       # ["negative_tone", "strong_language", etc.]
            "details": list[dict],    # Specific issues found
            "suggestion": str | None, # "Consider waiting before sending"
            "safe_to_send": bool      # True if no significant emotional content
        }
    """
    combined_text = f"{subject}\n{body}"
    text_lower = combined_text.lower()

    flags = []
    details = []
    score = 0.0

    # Check for ALL CAPS sections (more than 3 consecutive caps words)
    caps_pattern = r"\b[A-Z]{2,}(?:\s+[A-Z]{2,}){2,}\b"
    caps_matches = re.findall(caps_pattern, combined_text)
    if caps_matches:
        flags.append("all_caps")
        score += 0.2
        for match in caps_matches[:3]:  # Limit to first 3
            details.append({
                "type": "all_caps",
                "text": match,
                "severity": "medium",
            })

    # Check for excessive punctuation
    if re.search(r"[!?]{3,}", combined_text):
        flags.append("excessive_punctuation")
        score += 0.15
        details.append({
            "type": "excessive_punctuation",
            "text": "Multiple exclamation or question marks detected",
            "severity": "medium",
        })

    # Check for strong negative words
    for word in STRONG_NEGATIVE_WORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text_lower):
            if "strong_negative" not in flags:
                flags.append("strong_negative")
            score += 0.25
            details.append({
                "type": "strong_negative_word",
                "text": word,
                "severity": "high",
            })

    # Check for moderate negative words (lower weight)
    moderate_count = 0
    for word in MODERATE_NEGATIVE_WORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text_lower):
            moderate_count += 1

    if moderate_count >= 3:
        flags.append("negative_tone")
        score += 0.1 * min(moderate_count, 5)
        details.append({
            "type": "negative_tone",
            "text": f"{moderate_count} moderately negative words detected",
            "severity": "low",
        })

    # Check for reactive phrases
    for phrase in REACTIVE_PHRASES:
        if re.search(phrase, text_lower):
            if "reactive_phrasing" not in flags:
                flags.append("reactive_phrasing")
            score += 0.2
            details.append({
                "type": "reactive_phrase",
                "text": phrase.replace(r"\b", "").replace("\\", ""),
                "severity": "high",
            })

    # Check for aggressive closing
    for phrase in AGGRESSIVE_CLOSING_PHRASES:
        if re.search(phrase, text_lower):
            if "aggressive_closing" not in flags:
                flags.append("aggressive_closing")
            score += 0.15
            details.append({
                "type": "aggressive_closing",
                "text": phrase.replace(r"\b", "").replace("\\", ""),
                "severity": "medium",
            })

    # Check for passive-aggressive indicators
    passive_aggressive = [
        r"per my last email",
        r"as previously stated",
        r"i already told you",
        r"once again",
        r"for the nth time",
        r"as you should know",
        r"if you had read",
    ]
    for phrase in passive_aggressive:
        if re.search(phrase, text_lower):
            if "passive_aggressive" not in flags:
                flags.append("passive_aggressive")
            score += 0.15
            details.append({
                "type": "passive_aggressive",
                "text": phrase.replace(r"\b", "").replace("\\", ""),
                "severity": "medium",
            })

    # Normalize score to 0-1 range
    score = min(1.0, score)

    # Determine if safe to send
    safe_to_send = score < 0.3 and "strong_negative" not in flags and "reactive_phrasing" not in flags

    # Generate suggestion based on flags
    suggestion = None
    if not safe_to_send:
        if score >= 0.7:
            suggestion = "This email has significant emotional content. Consider waiting 24 hours before sending."
        elif score >= 0.5:
            suggestion = "This email shows signs of frustration. Consider taking a break and reviewing later."
        elif score >= 0.3:
            suggestion = "This email may come across more strongly than intended. Consider softening the tone."

    return {
        "score": round(score, 2),
        "flags": flags,
        "details": details,
        "suggestion": suggestion,
        "safe_to_send": safe_to_send,
    }


def get_sentiment_summary(analysis: dict[str, Any]) -> str:
    """
    Get a human-readable summary of the sentiment analysis.

    Args:
        analysis: Result from analyze_email_sentiment()

    Returns:
        Short summary string
    """
    score = analysis["score"]
    flags = analysis["flags"]

    if score < 0.1:
        return "Calm and professional"
    elif score < 0.3:
        return "Mostly neutral with minor concerns"
    elif score < 0.5:
        return "Moderate emotional content detected"
    elif score < 0.7:
        return "High emotional content - review recommended"
    else:
        return "Very high emotional content - delay sending strongly recommended"


def check_for_impulsive_indicators(body: str) -> dict[str, Any]:
    """
    Additional check for ADHD-specific impulsive email patterns.

    Args:
        body: Email body text

    Returns:
        dict with impulsive indicators found
    """
    indicators = []

    # Very short aggressive response
    word_count = len(body.split())
    if word_count < 15 and any(c in body for c in "!?"):
        indicators.append({
            "type": "short_reactive",
            "description": "Very short response with punctuation - may be reactive",
        })

    # Late night writing (can't detect time, but note this in docs)

    # All response, no greeting
    if not any(greeting in body.lower()[:50] for greeting in ["hi", "hello", "dear", "hey", "good morning", "good afternoon"]):
        if word_count > 20 and any(word in body.lower() for word in MODERATE_NEGATIVE_WORDS):
            indicators.append({
                "type": "no_greeting",
                "description": "No greeting on a longer email - may indicate frustration",
            })

    # Multiple recipients on emotional email
    # (Can't check recipients here, but tool using this should consider)

    return {
        "has_impulsive_indicators": len(indicators) > 0,
        "indicators": indicators,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Email Sentiment Analysis for ADHD-Safe Communication",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze email
  python sentiment.py --subject "Issue" --body "I can't believe this happened!"

  # Check if safe to send
  python sentiment.py --subject "Hello" --body "Hi there" --check-safe

  # JSON output
  python sentiment.py --subject "Meeting" --body "Let's discuss" --json
        """,
    )

    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--body", required=True, help="Email body text")
    parser.add_argument("--check-safe", action="store_true", help="Only output if safe to send")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Analyze the email
    analysis = analyze_email_sentiment(args.subject, args.body)

    # Add impulsive indicators
    impulsive = check_for_impulsive_indicators(args.body)
    if impulsive["has_impulsive_indicators"]:
        analysis["impulsive_indicators"] = impulsive["indicators"]

    # Add summary
    analysis["summary"] = get_sentiment_summary(analysis)

    if args.check_safe:
        # Just output safe/unsafe
        if analysis["safe_to_send"]:
            print("SAFE")
            sys.exit(0)
        else:
            print(f"REVIEW: {analysis['suggestion'] or 'Review recommended'}")
            sys.exit(1)
    elif args.json:
        print(json.dumps(analysis, indent=2))
    else:
        # Human-readable output
        safe_status = "SAFE" if analysis["safe_to_send"] else "REVIEW"
        print(f"{safe_status}: {analysis['summary']}")
        print(f"Score: {analysis['score']}")

        if analysis["flags"]:
            print(f"Flags: {', '.join(analysis['flags'])}")

        if analysis.get("suggestion"):
            print(f"\nSuggestion: {analysis['suggestion']}")

        if analysis.get("details"):
            print("\nDetails:")
            for detail in analysis["details"][:5]:  # Limit output
                print(f"  - [{detail['severity']}] {detail['type']}: {detail['text']}")


if __name__ == "__main__":
    main()
