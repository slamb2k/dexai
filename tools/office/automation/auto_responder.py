"""
Tool: Auto Responder
Purpose: Template-based automatic responses for Level 5 (Autonomous) integration

This module manages response templates and sends automatic replies based on
policies. Templates support variable substitution for personalized responses.

ADHD Philosophy:
    Responding to emails is a major source of decision fatigue. Auto Responder
    handles routine replies with personalized templates, reducing the cognitive
    load of crafting responses. Users define templates once and Dex uses them
    automatically based on policy rules.

Template Variables:
    {{sender_name}} - Sender's display name
    {{sender_email}} - Sender's email address
    {{original_subject}} - Original email subject
    {{current_date}} - Today's date
    {{return_date}} - Return date (for vacation)
    {{user_name}} - User's display name

Usage:
    from tools.office.automation.auto_responder import (
        send_auto_reply,
        create_template,
        get_template,
        list_templates,
        update_template,
        delete_template,
        render_template,
    )

    # Create a template
    result = await create_template("account-123", "vacation", "I'm out of office...")

    # Send an auto-reply
    result = await send_auto_reply("account-123", "sender@example.com", "template-id")

    # Render a template preview
    result = await render_template("template-id", {"sender_name": "John"})

CLI:
    python tools/office/automation/auto_responder.py create <account-id> --name "vacation" --body "..."
    python tools/office/automation/auto_responder.py list <account-id>
    python tools/office/automation/auto_responder.py render <template-id> --vars '{"sender_name": "John"}'
    python tools/office/automation/auto_responder.py send <account-id> --to "user@example.com" --template <id>
"""

import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.office import get_connection
from tools.office.automation.emergency import check_pause_status
from tools.office.models import IntegrationLevel
from tools.office.policies import ensure_policy_tables

# Standard template variables
STANDARD_VARIABLES = {
    "sender_name": "Sender's display name",
    "sender_email": "Sender's email address",
    "original_subject": "Original email subject",
    "current_date": "Today's date (formatted)",
    "return_date": "Return date (for vacation templates)",
    "user_name": "User's display name",
}


def _ensure_tables() -> None:
    """Ensure all required tables exist."""
    ensure_policy_tables()


def _get_account(account_id: str) -> dict | None:
    """Get account details from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def _extract_template_variables(text: str) -> list[str]:
    """
    Extract variable names from template text.

    Args:
        text: Template text with {{variable}} placeholders

    Returns:
        List of variable names found
    """
    pattern = r"\{\{(\w+)\}\}"
    return list(set(re.findall(pattern, text)))


def _render_template_text(
    template_text: str,
    variables: dict[str, str],
) -> str:
    """
    Render template text with variable substitution.

    Args:
        template_text: Template with {{variable}} placeholders
        variables: Dictionary of variable values

    Returns:
        Rendered text with variables substituted
    """
    result = template_text

    for var_name, var_value in variables.items():
        placeholder = "{{" + var_name + "}}"
        result = result.replace(placeholder, str(var_value))

    return result


async def send_auto_reply(
    account_id: str,
    to_email: str,
    template_id: str,
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Send an automatic reply using a template.

    This renders the template with the provided variables and queues
    the email for sending through the action queue.

    Args:
        account_id: Office account ID
        to_email: Recipient email address
        template_id: Template ID to use
        variables: Optional variable values for template substitution

    Returns:
        {
            "success": bool,
            "action_id": str,  # If queued
            "rendered_subject": str,
            "rendered_body": str,
        }
    """
    # Check emergency pause
    if check_pause_status(account_id):
        return {
            "success": False,
            "error": "Automation paused",
        }

    # Get account
    account = _get_account(account_id)
    if not account:
        return {
            "success": False,
            "error": "Account not found",
        }

    if account["integration_level"] < IntegrationLevel.MANAGED_PROXY.value:
        return {
            "success": False,
            "error": f"Requires Level 4+. Current: {account['integration_level']}",
        }

    # Get template
    template_result = await get_template(template_id)
    if not template_result.get("success"):
        return template_result

    template = template_result["template"]

    # Verify template belongs to this account
    if template["account_id"] != account_id:
        return {
            "success": False,
            "error": "Template does not belong to this account",
        }

    # Render template
    render_result = await render_template(template_id, variables or {})
    if not render_result.get("success"):
        return render_result

    rendered_subject = render_result.get("subject") or f"Re: {(variables or {}).get('original_subject', '')}"
    rendered_body = render_result["body"]

    # Import action queue
    from tools.office.actions.queue import queue_action

    # Queue the send action
    action_data = {
        "to": [to_email],
        "subject": rendered_subject,
        "body": rendered_body,
        "template_id": template_id,
        "is_auto_reply": True,
    }

    result = await queue_action(
        account_id=account_id,
        action_type="send_email",
        action_data=action_data,
        undo_window_seconds=60,
    )

    if not result.get("success"):
        return result

    # Increment template use count
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE office_response_templates SET use_count = use_count + 1 WHERE id = ?",
        (template_id,),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "action_id": result["action_id"],
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body,
    }


async def create_template(
    account_id: str,
    name: str,
    body_template: str,
    subject_template: str | None = None,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    """
    Create a new response template.

    Args:
        account_id: Office account ID
        name: Template name
        body_template: Email body with {{variable}} placeholders
        subject_template: Optional email subject with {{variable}} placeholders
        variables: Optional list of variable names (auto-detected if not provided)

    Returns:
        {
            "success": bool,
            "template_id": str,
            "detected_variables": list[str],
        }
    """
    _ensure_tables()

    # Verify account exists
    account = _get_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}

    # Auto-detect variables if not provided
    if variables is None:
        detected_vars = _extract_template_variables(body_template)
        if subject_template:
            detected_vars.extend(_extract_template_variables(subject_template))
        variables = list(set(detected_vars))

    # Generate template ID
    template_id = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO office_response_templates
        (id, account_id, name, subject_template, body_template, variables)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            template_id,
            account_id,
            name,
            subject_template,
            body_template,
            json.dumps(variables),
        ),
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "template_id": template_id,
        "detected_variables": variables,
    }


async def get_template(template_id: str) -> dict[str, Any]:
    """
    Get a template by ID.

    Args:
        template_id: Template ID

    Returns:
        {
            "success": bool,
            "template": dict,
        }
    """
    _ensure_tables()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM office_response_templates WHERE id = ?",
        (template_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": f"Template not found: {template_id}"}

    template = dict(row)
    if template.get("variables"):
        template["variables"] = json.loads(template["variables"])

    return {
        "success": True,
        "template": template,
    }


async def list_templates(account_id: str) -> dict[str, Any]:
    """
    List all templates for an account.

    Args:
        account_id: Office account ID

    Returns:
        {
            "success": bool,
            "templates": list[dict],
            "count": int,
        }
    """
    _ensure_tables()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT * FROM office_response_templates
        WHERE account_id = ?
        ORDER BY use_count DESC, name ASC
        """,
        (account_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    templates = []
    for row in rows:
        template = dict(row)
        if template.get("variables"):
            template["variables"] = json.loads(template["variables"])
        templates.append(template)

    return {
        "success": True,
        "templates": templates,
        "count": len(templates),
    }


async def update_template(
    template_id: str,
    **updates: Any,
) -> dict[str, Any]:
    """
    Update a template.

    Args:
        template_id: Template ID
        **updates: Fields to update (name, subject_template, body_template, variables)

    Returns:
        {
            "success": bool,
            "template": dict,
        }
    """
    _ensure_tables()

    # Verify template exists
    existing = await get_template(template_id)
    if not existing.get("success"):
        return existing

    # Build update query
    allowed_fields = {"name", "subject_template", "body_template", "variables"}
    update_fields = []
    update_values = []

    for field, value in updates.items():
        if field in allowed_fields:
            update_fields.append(f"{field} = ?")
            if field == "variables" and isinstance(value, list):
                update_values.append(json.dumps(value))
            else:
                update_values.append(value)

    if not update_fields:
        return {"success": False, "error": "No valid fields to update"}

    # Add updated_at
    update_fields.append("updated_at = ?")
    update_values.append(datetime.now().isoformat())

    # Add template_id for WHERE clause
    update_values.append(template_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"UPDATE office_response_templates SET {', '.join(update_fields)} WHERE id = ?",
        update_values,
    )
    conn.commit()
    conn.close()

    # Return updated template
    return await get_template(template_id)


async def delete_template(template_id: str) -> dict[str, Any]:
    """
    Delete a template.

    Args:
        template_id: Template ID

    Returns:
        {
            "success": bool,
        }
    """
    _ensure_tables()

    # Verify template exists
    existing = await get_template(template_id)
    if not existing.get("success"):
        return existing

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM office_response_templates WHERE id = ?",
        (template_id,),
    )
    conn.commit()
    conn.close()

    return {"success": True}


async def render_template(
    template_id: str,
    variables: dict[str, str],
) -> dict[str, Any]:
    """
    Render a template with provided variables.

    This is useful for previewing what the template will look like
    before sending.

    Args:
        template_id: Template ID
        variables: Dictionary of variable values

    Returns:
        {
            "success": bool,
            "subject": str | None,
            "body": str,
            "missing_variables": list[str],
        }
    """
    # Get template
    template_result = await get_template(template_id)
    if not template_result.get("success"):
        return template_result

    template = template_result["template"]

    # Add default values for standard variables if not provided
    defaults = {
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "sender_name": "there",
        "sender_email": "",
        "original_subject": "(no subject)",
        "return_date": "(not set)",
        "user_name": "(user)",
    }

    # Merge defaults with provided variables
    merged_vars = {**defaults, **variables}

    # Render subject
    rendered_subject = None
    if template.get("subject_template"):
        rendered_subject = _render_template_text(template["subject_template"], merged_vars)

    # Render body
    rendered_body = _render_template_text(template["body_template"], merged_vars)

    # Check for missing variables
    template_vars = template.get("variables", [])
    provided_vars = set(variables.keys())
    missing_vars = [v for v in template_vars if v not in provided_vars and v not in defaults]

    return {
        "success": True,
        "subject": rendered_subject,
        "body": rendered_body,
        "missing_variables": missing_vars,
    }


async def create_default_templates(account_id: str) -> dict[str, Any]:
    """
    Create default response templates for an account.

    Args:
        account_id: Office account ID

    Returns:
        {
            "success": bool,
            "templates_created": int,
            "template_ids": list[str],
        }
    """
    default_templates = [
        {
            "name": "Out of Office",
            "subject_template": "Out of Office: {{original_subject}}",
            "body_template": """Hi {{sender_name}},

Thank you for your email. I'm currently out of the office and will return on {{return_date}}.

I'll respond to your message when I'm back. If this is urgent, please contact my colleague at [backup email].

Best regards,
{{user_name}}""",
        },
        {
            "name": "Quick Acknowledgment",
            "subject_template": "Re: {{original_subject}}",
            "body_template": """Hi {{sender_name}},

Got it, thanks! I'll take a look and get back to you soon.

{{user_name}}""",
        },
        {
            "name": "Meeting Decline",
            "subject_template": "Re: {{original_subject}}",
            "body_template": """Hi {{sender_name}},

Thank you for the meeting invitation. Unfortunately, I'm not able to attend at the proposed time.

Would any of the following times work instead?
- [Alternative time 1]
- [Alternative time 2]

Let me know what works for you.

Best,
{{user_name}}""",
        },
        {
            "name": "Follow-up Reminder",
            "subject_template": "Following up: {{original_subject}}",
            "body_template": """Hi {{sender_name}},

I wanted to follow up on my previous email regarding {{original_subject}}.

Please let me know if you have any questions or need any additional information.

Thanks,
{{user_name}}""",
        },
        {
            "name": "Thank You",
            "subject_template": "Re: {{original_subject}}",
            "body_template": """Hi {{sender_name}},

Thank you so much for this! I really appreciate it.

Best,
{{user_name}}""",
        },
    ]

    template_ids = []
    for template_data in default_templates:
        result = await create_template(
            account_id=account_id,
            name=template_data["name"],
            body_template=template_data["body_template"],
            subject_template=template_data.get("subject_template"),
        )

        if result.get("success"):
            template_ids.append(result["template_id"])

    return {
        "success": True,
        "templates_created": len(template_ids),
        "template_ids": template_ids,
    }


def main() -> None:
    """CLI entry point for auto responder."""
    parser = argparse.ArgumentParser(
        description="Auto Responder for Level 5 Office Integration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create command
    create_parser = subparsers.add_parser("create", help="Create a template")
    create_parser.add_argument("account_id", help="Account ID")
    create_parser.add_argument("--name", required=True, help="Template name")
    create_parser.add_argument("--body", required=True, help="Body template")
    create_parser.add_argument("--subject", help="Subject template")

    # list command
    list_parser = subparsers.add_parser("list", help="List templates")
    list_parser.add_argument("account_id", help="Account ID")

    # get command
    get_parser = subparsers.add_parser("get", help="Get a template")
    get_parser.add_argument("template_id", help="Template ID")

    # update command
    update_parser = subparsers.add_parser("update", help="Update a template")
    update_parser.add_argument("template_id", help="Template ID")
    update_parser.add_argument("--name", help="New name")
    update_parser.add_argument("--body", help="New body template")
    update_parser.add_argument("--subject", help="New subject template")

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a template")
    delete_parser.add_argument("template_id", help="Template ID")

    # render command
    render_parser = subparsers.add_parser("render", help="Render a template preview")
    render_parser.add_argument("template_id", help="Template ID")
    render_parser.add_argument("--vars", help="Variables as JSON string")

    # send command
    send_parser = subparsers.add_parser("send", help="Send an auto-reply")
    send_parser.add_argument("account_id", help="Account ID")
    send_parser.add_argument("--to", required=True, help="Recipient email")
    send_parser.add_argument("--template", required=True, help="Template ID")
    send_parser.add_argument("--vars", help="Variables as JSON string")

    # init-defaults command
    init_parser = subparsers.add_parser("init-defaults", help="Create default templates")
    init_parser.add_argument("account_id", help="Account ID")

    args = parser.parse_args()

    if args.command == "create":
        result = asyncio.run(create_template(
            args.account_id,
            name=args.name,
            body_template=args.body,
            subject_template=args.subject,
        ))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "list":
        result = asyncio.run(list_templates(args.account_id))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "get":
        result = asyncio.run(get_template(args.template_id))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "update":
        updates = {}
        if args.name:
            updates["name"] = args.name
        if args.body:
            updates["body_template"] = args.body
        if args.subject:
            updates["subject_template"] = args.subject

        result = asyncio.run(update_template(args.template_id, **updates))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "delete":
        result = asyncio.run(delete_template(args.template_id))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "render":
        variables = {}
        if args.vars:
            variables = json.loads(args.vars)

        result = asyncio.run(render_template(args.template_id, variables))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "send":
        variables = {}
        if args.vars:
            variables = json.loads(args.vars)

        result = asyncio.run(send_auto_reply(
            args.account_id,
            to_email=args.to,
            template_id=args.template,
            variables=variables,
        ))
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "init-defaults":
        result = asyncio.run(create_default_templates(args.account_id))
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
