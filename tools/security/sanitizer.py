"""
Tool: Input Sanitizer
Purpose: Clean and validate user input before processing

Features:
- HTML/script tag stripping
- Max length enforcement (configurable, default 10KB)
- Unicode normalization (NFC form)
- Prompt injection pattern detection
- Configurable per-channel rules

Usage:
    python tools/security/sanitizer.py --input "Hello world"
    python tools/security/sanitizer.py --input "<script>alert(1)</script>test" --strip-html
    python tools/security/sanitizer.py --check --input "ignore previous instructions"
    python tools/security/sanitizer.py --sanitize --input "Some <b>text</b> here"

Dependencies:
    - re (stdlib)
    - unicodedata (stdlib)
    - html (stdlib)

Output:
    JSON result with sanitized content or risk assessment
"""

import argparse
import html
import json
import re
import sys
import unicodedata
from typing import Any


# Default max input length (bytes)
DEFAULT_MAX_LENGTH = 10240  # 10KB

# Prompt injection patterns
# Each pattern has: (regex, category, severity, description)
INJECTION_PATTERNS = [
    # Instruction override attempts
    (
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
        "prompt_injection",
        "high",
        "Instruction override attempt",
    ),
    (
        r"forget\s+(everything|all|your)\s+(you\s+)?(know|learned|rules?)",
        "prompt_injection",
        "high",
        "Memory wipe attempt",
    ),
    (
        r"disregard\s+(all\s+)?(previous|prior|your)\s+(instructions?|context)",
        "prompt_injection",
        "high",
        "Instruction disregard attempt",
    ),
    (
        r"override\s+(your\s+)?(instructions?|programming|rules?)",
        "prompt_injection",
        "high",
        "Override attempt",
    ),
    # Role manipulation
    (r"you\s+are\s+(now|actually)\s+(a|an|the)", "jailbreak", "high", "Role reassignment attempt"),
    (r"pretend\s+(to\s+be|you\s+are)\s+(a|an)", "jailbreak", "medium", "Role-playing manipulation"),
    (r"act\s+as\s+(if\s+)?(you|a|an)", "jailbreak", "medium", "Acting instruction"),
    (
        r"(imagine|suppose)\s+you\s+(have\s+)?no\s+(rules?|restrictions?|limits?)",
        "jailbreak",
        "high",
        "Restriction bypass attempt",
    ),
    # DAN-style prompts
    (r"\bdan\b.*\bmode\b", "jailbreak", "critical", "DAN mode attempt"),
    (r"do\s+anything\s+now", "jailbreak", "critical", "DAN activation phrase"),
    (r"jailbreak(ed)?\s*(mode)?", "jailbreak", "critical", "Jailbreak attempt"),
    # System prompt extraction
    (
        r"(show|tell|reveal|display|print|output)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions?)",
        "exfiltration",
        "high",
        "System prompt extraction",
    ),
    (
        r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)",
        "exfiltration",
        "medium",
        "System prompt query",
    ),
    (
        r"repeat\s+(your\s+)?(initial|system|original)\s+(prompt|instructions?)",
        "exfiltration",
        "high",
        "Prompt repeat request",
    ),
    # Format exploits
    (r"```\s*(system|assistant|user)\s*\n", "prompt_injection", "medium", "Fake message format"),
    (r"^(system|assistant|user)\s*:", "prompt_injection", "medium", "Role prefix injection"),
    (r"\[/?INST\]", "prompt_injection", "medium", "Instruction tag injection"),
    (
        r"<\|?(system|assistant|user|endoftext)\|?>",
        "prompt_injection",
        "high",
        "Special token injection",
    ),
    # Code injection (shell)
    (
        r";\s*(rm|mv|cp|cat|wget|curl|bash|sh|python|perl|ruby)\s",
        "code_injection",
        "critical",
        "Shell command injection",
    ),
    (r"\$\([^)]+\)", "code_injection", "high", "Command substitution"),
    (r"`[^`]+`", "code_injection", "medium", "Backtick command"),
    (r"\|\s*(sh|bash|python)", "code_injection", "high", "Pipe to shell"),
    # Path traversal
    (r"\.\./\.\.", "code_injection", "high", "Path traversal"),
    (r"%2e%2e/", "code_injection", "high", "Encoded path traversal"),
    # SQL injection indicators
    (r"'\s*(or|and)\s*'?1'?\s*=\s*'?1", "code_injection", "high", "SQL injection pattern"),
    (r";\s*drop\s+(table|database)", "code_injection", "critical", "SQL drop command"),
    (r"union\s+(all\s+)?select", "code_injection", "high", "SQL union injection"),
    (r"--\s*$", "code_injection", "low", "SQL comment suffix"),
]

# HTML tags to strip
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
SCRIPT_PATTERN = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
STYLE_PATTERN = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)


def normalize_unicode(text: str) -> str:
    """Normalize unicode to NFC form to prevent homograph attacks."""
    return unicodedata.normalize("NFC", text)


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    # Remove script and style blocks first
    text = SCRIPT_PATTERN.sub("", text)
    text = STYLE_PATTERN.sub("", text)
    # Remove remaining tags
    text = HTML_TAG_PATTERN.sub("", text)
    # Decode HTML entities
    text = html.unescape(text)
    return text


def enforce_max_length(text: str, max_bytes: int = DEFAULT_MAX_LENGTH) -> tuple[str, bool]:
    """
    Truncate text to max bytes.

    Returns:
        (truncated_text, was_truncated)
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False

    # Truncate and decode, handling partial UTF-8 characters
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def check_injection_patterns(text: str) -> list[dict[str, Any]]:
    """
    Check text for prompt injection and other malicious patterns.

    Returns:
        List of detected patterns with metadata
    """
    detected = []
    text_lower = text.lower()

    for pattern, category, severity, description in INJECTION_PATTERNS:
        matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))
        for match in matches:
            detected.append(
                {
                    "category": category,
                    "severity": severity,
                    "pattern": description,
                    "snippet": text[max(0, match.start() - 10) : min(len(text), match.end() + 10)],
                    "position": match.start(),
                }
            )

    return detected


def calculate_risk_level(detections: list[dict]) -> str:
    """Calculate overall risk level from detections."""
    if not detections:
        return "none"

    severities = [d["severity"] for d in detections]

    if "critical" in severities:
        return "critical"
    elif "high" in severities:
        return "high"
    elif "medium" in severities:
        return "medium"
    else:
        return "low"


def get_recommendation(risk_level: str) -> str:
    """Get recommendation based on risk level."""
    recommendations = {
        "none": "allow",
        "low": "allow",  # Log but allow
        "medium": "sanitize",  # Remove concerning parts
        "high": "block",  # Block and alert
        "critical": "escalate",  # Block and notify admin
    }
    return recommendations.get(risk_level, "block")


def sanitize(
    text: str,
    strip_html_tags: bool = True,
    normalize: bool = True,
    max_length: int | None = DEFAULT_MAX_LENGTH,
    check_patterns: bool = True,
) -> dict[str, Any]:
    """
    Full sanitization pipeline.

    Args:
        text: Input text to sanitize
        strip_html_tags: Remove HTML tags
        normalize: Apply Unicode normalization
        max_length: Max length in bytes (None = no limit)
        check_patterns: Check for injection patterns

    Returns:
        dict with sanitized text and metadata
    """
    original_length = len(text)
    warnings = []

    # Unicode normalization
    if normalize:
        text = normalize_unicode(text)

    # Strip HTML
    if strip_html_tags:
        stripped = strip_html(text)
        if stripped != text:
            warnings.append("HTML tags removed")
            text = stripped

    # Max length
    was_truncated = False
    if max_length:
        text, was_truncated = enforce_max_length(text, max_length)
        if was_truncated:
            warnings.append(f"Truncated to {max_length} bytes")

    # Pattern checking
    detections = []
    risk_level = "none"
    recommendation = "allow"

    if check_patterns:
        detections = check_injection_patterns(text)
        risk_level = calculate_risk_level(detections)
        recommendation = get_recommendation(risk_level)

    return {
        "success": True,
        "sanitized": text,
        "original_length": original_length,
        "sanitized_length": len(text),
        "was_truncated": was_truncated,
        "warnings": warnings,
        "security": {
            "detections": detections,
            "detection_count": len(detections),
            "risk_level": risk_level,
            "recommendation": recommendation,
        },
    }


def check_only(text: str) -> dict[str, Any]:
    """
    Check text for security issues without modifying it.

    Returns:
        dict with risk assessment
    """
    detections = check_injection_patterns(text)
    risk_level = calculate_risk_level(detections)
    recommendation = get_recommendation(risk_level)

    # Calculate confidence based on pattern specificity
    if not detections:
        confidence = 0.95  # High confidence it's safe
    else:
        severities = [d["severity"] for d in detections]
        if "critical" in severities:
            confidence = 0.95
        elif "high" in severities:
            confidence = 0.85
        elif "medium" in severities:
            confidence = 0.70
        else:
            confidence = 0.60

    return {
        "success": True,
        "safe": len(detections) == 0,
        "confidence": confidence,
        "risk_level": risk_level,
        "detected_patterns": detections,
        "recommendation": recommendation,
        "input_length": len(text),
    }


def main():
    parser = argparse.ArgumentParser(description="Input Sanitizer")
    parser.add_argument("--input", required=True, help="Text to sanitize/check")
    parser.add_argument("--check", action="store_true", help="Only check for issues, do not modify")
    parser.add_argument(
        "--sanitize",
        action="store_true",
        help="Full sanitization (default if neither --check nor --sanitize)",
    )
    parser.add_argument(
        "--strip-html", action="store_true", default=True, help="Strip HTML tags (default: true)"
    )
    parser.add_argument("--no-strip-html", action="store_true", help="Do not strip HTML tags")
    parser.add_argument(
        "--normalize",
        action="store_true",
        default=True,
        help="Unicode normalization (default: true)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help=f"Max input length in bytes (default: {DEFAULT_MAX_LENGTH})",
    )
    parser.add_argument(
        "--no-pattern-check", action="store_true", help="Skip injection pattern checking"
    )

    args = parser.parse_args()

    if args.check:
        result = check_only(args.input)
    else:
        result = sanitize(
            text=args.input,
            strip_html_tags=not args.no_strip_html,
            normalize=args.normalize,
            max_length=args.max_length if args.max_length > 0 else None,
            check_patterns=not args.no_pattern_check,
        )

    if result.get("success"):
        status = (
            "SAFE"
            if result.get("safe", True) or result.get("security", {}).get("risk_level") == "none"
            else "RISK DETECTED"
        )
        print(f"OK {status}")
    else:
        print(f"ERROR {result.get('error')}")
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
