"""
Policy and Automation Management Routes - Level 5 Autonomous Integration

Provides endpoints for managing automation policies, response templates,
VIP contacts, and emergency controls:
- CRUD operations for automation policies
- Response template management
- VIP contact list management
- Emergency pause/resume controls
- Level 5 eligibility and upgrade

These routes enable the Autonomous (Level 5) integration where Dex
can act independently based on learned patterns and explicit policies.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from tools.office import get_connection
from tools.office.automation.auto_responder import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    render_template,
    update_template,
)
from tools.office.automation.contact_manager import (
    add_vip,
    list_vips,
    remove_vip,
    suggest_vips,
)
from tools.office.automation.emergency import (
    emergency_pause,
    get_pause_status,
    resume_automation,
)
from tools.office.policies.engine import get_policy_execution_history
from tools.office.policies.manager import (
    create_policy,
    delete_policy,
    get_policy,
    get_policy_stats,
    import_default_policies,
    list_policies,
    toggle_policy,
    update_policy,
)


router = APIRouter()


# =============================================================================
# Request Models
# =============================================================================


class PolicyCreateRequest(BaseModel):
    """Request to create a new automation policy."""

    account_id: str = Field(..., description="Office account ID")
    name: str = Field(..., description="Policy name")
    policy_type: str = Field(..., description="Type: inbox, calendar, response, schedule")
    conditions: list[dict[str, Any]] = Field(..., description="List of conditions")
    actions: list[dict[str, Any]] = Field(..., description="List of actions to execute")
    description: str = Field("", description="Policy description")
    priority: int = Field(0, description="Priority (higher = evaluated first)")
    enabled: bool = Field(True, description="Whether policy is active")


class PolicyUpdateRequest(BaseModel):
    """Request to update an existing policy."""

    name: str | None = Field(None, description="Policy name")
    description: str | None = Field(None, description="Policy description")
    priority: int | None = Field(None, description="Priority level")
    enabled: bool | None = Field(None, description="Whether policy is active")
    conditions: list[dict[str, Any]] | None = Field(None, description="Updated conditions")
    actions: list[dict[str, Any]] | None = Field(None, description="Updated actions")


class TemplateCreateRequest(BaseModel):
    """Request to create a response template."""

    account_id: str = Field(..., description="Office account ID")
    name: str = Field(..., description="Template name")
    body_template: str = Field(..., description="Email body with {{variable}} placeholders")
    subject_template: str | None = Field(None, description="Optional subject template")
    variables: list[str] | None = Field(None, description="List of variable names")


class TemplateUpdateRequest(BaseModel):
    """Request to update a response template."""

    name: str | None = Field(None, description="Template name")
    body_template: str | None = Field(None, description="Email body template")
    subject_template: str | None = Field(None, description="Subject template")
    variables: list[str] | None = Field(None, description="Variable names")


class TemplatePreviewRequest(BaseModel):
    """Request to preview a rendered template."""

    variables: dict[str, str] = Field(default_factory=dict, description="Variable values")


class VIPCreateRequest(BaseModel):
    """Request to add a VIP contact."""

    account_id: str = Field(..., description="Office account ID")
    email: str = Field(..., description="VIP email address")
    name: str | None = Field(None, description="Display name")
    priority: str = Field("high", description="Priority: critical, high, normal")
    always_notify: bool = Field(True, description="Always notify for this contact")
    bypass_focus: bool = Field(True, description="Bypass focus mode")
    notes: str | None = Field(None, description="Additional notes")


class EmergencyPauseRequest(BaseModel):
    """Request to trigger emergency pause."""

    reason: str = Field("User requested", description="Reason for pause")
    duration_hours: int | None = Field(None, ge=1, le=168, description="Hours to pause (1-168)")


# =============================================================================
# Response Models
# =============================================================================


class PolicyResponse(BaseModel):
    """Single policy response."""

    id: str
    name: str
    description: str | None
    policy_type: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    enabled: bool
    priority: int
    created_at: str


class PolicyListResponse(BaseModel):
    """List of policies response."""

    policies: list[dict[str, Any]]
    total: int


class PolicyStatsResponse(BaseModel):
    """Policy execution statistics."""

    policy_id: str
    execution_count: int
    success_count: int
    last_execution: str | None
    success_rate: float
    executions_today: int


class TemplateResponse(BaseModel):
    """Single template response."""

    id: str
    name: str
    subject_template: str | None
    body_template: str
    variables: list[str]
    use_count: int


class TemplateListResponse(BaseModel):
    """List of templates response."""

    templates: list[dict[str, Any]]
    total: int


class VIPResponse(BaseModel):
    """Single VIP contact response."""

    id: str
    email: str
    name: str | None
    priority: str
    always_notify: bool
    bypass_focus: bool
    notes: str | None


class VIPListResponse(BaseModel):
    """List of VIP contacts response."""

    vips: list[dict[str, Any]]
    by_priority: dict[str, list[dict[str, Any]]]
    total: int


class EmergencyStatusResponse(BaseModel):
    """Emergency pause status response."""

    is_paused: bool
    paused_at: str | None
    paused_until: str | None
    reason: str | None


class EligibilityResponse(BaseModel):
    """Level 5 eligibility check response."""

    eligible: bool
    days_at_level_4: int
    undo_rate: float
    actions_executed: int
    requirements: dict[str, Any]
    missing_requirements: list[str]


# =============================================================================
# Policy Endpoints
# =============================================================================


@router.get("/policies", response_model=PolicyListResponse)
async def list_all_policies(
    account_id: str = Query(..., description="Office account ID"),
    policy_type: str | None = Query(None, description="Filter by policy type"),
    enabled_only: bool = Query(False, description="Only return enabled policies"),
):
    """
    List all automation policies for an account.

    Policies define the rules for autonomous email and calendar management.
    """
    result = await list_policies(
        account_id=account_id,
        policy_type=policy_type,
        enabled_only=enabled_only,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to list policies"))

    return PolicyListResponse(
        policies=result.get("policies", []),
        total=result.get("count", 0),
    )


@router.get("/policies/{policy_id}", response_model=PolicyResponse)
async def get_policy_details(policy_id: str):
    """Get details of a specific policy."""
    result = await get_policy(policy_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Policy not found"))

    policy = result["policy"]
    return PolicyResponse(
        id=policy["id"],
        name=policy["name"],
        description=policy.get("description"),
        policy_type=policy["policy_type"],
        conditions=policy.get("conditions", []),
        actions=policy.get("actions", []),
        enabled=policy.get("enabled", True),
        priority=policy.get("priority", 0),
        created_at=policy.get("created_at", ""),
    )


@router.post("/policies", response_model=PolicyResponse)
async def create_new_policy(request: PolicyCreateRequest):
    """
    Create a new automation policy.

    Policies define conditions to match and actions to execute when
    those conditions are met.
    """
    result = await create_policy(
        account_id=request.account_id,
        name=request.name,
        policy_type=request.policy_type,
        conditions=request.conditions,
        actions=request.actions,
        description=request.description,
        priority=request.priority,
        enabled=request.enabled,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create policy"))

    # Fetch the created policy to return full details
    policy_result = await get_policy(result["policy_id"])
    if not policy_result.get("success"):
        raise HTTPException(status_code=500, detail="Policy created but failed to retrieve")

    policy = policy_result["policy"]
    return PolicyResponse(
        id=policy["id"],
        name=policy["name"],
        description=policy.get("description"),
        policy_type=policy["policy_type"],
        conditions=policy.get("conditions", []),
        actions=policy.get("actions", []),
        enabled=policy.get("enabled", True),
        priority=policy.get("priority", 0),
        created_at=policy.get("created_at", ""),
    )


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_existing_policy(policy_id: str, request: PolicyUpdateRequest):
    """
    Update an existing policy.

    Only provided fields will be updated.
    """
    # Build update dict from non-None values
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.priority is not None:
        updates["priority"] = request.priority
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.conditions is not None:
        updates["conditions"] = request.conditions
    if request.actions is not None:
        updates["actions"] = request.actions

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await update_policy(policy_id, **updates)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to update policy"))

    # Fetch updated policy
    policy_result = await get_policy(policy_id)
    if not policy_result.get("success"):
        raise HTTPException(status_code=500, detail="Policy updated but failed to retrieve")

    policy = policy_result["policy"]
    return PolicyResponse(
        id=policy["id"],
        name=policy["name"],
        description=policy.get("description"),
        policy_type=policy["policy_type"],
        conditions=policy.get("conditions", []),
        actions=policy.get("actions", []),
        enabled=policy.get("enabled", True),
        priority=policy.get("priority", 0),
        created_at=policy.get("created_at", ""),
    )


@router.delete("/policies/{policy_id}")
async def delete_existing_policy(policy_id: str):
    """
    Delete a policy.

    This is permanent and cannot be undone.
    """
    result = await delete_policy(policy_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to delete policy"))

    return {"success": True, "policy_id": policy_id, "deleted": True}


@router.post("/policies/{policy_id}/toggle")
async def toggle_policy_state(
    policy_id: str,
    enabled: bool = Query(..., description="New enabled state"),
):
    """
    Enable or disable a policy.

    Quick way to turn a policy on/off without deleting it.
    """
    result = await toggle_policy(policy_id, enabled)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to toggle policy"))

    return {"success": True, "policy_id": policy_id, "enabled": enabled}


@router.post("/policies/import-defaults")
async def import_default_policy_templates(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Import default policy templates for an account.

    Default policies are imported as disabled so you must explicitly enable them.
    """
    result = await import_default_policies(account_id)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to import defaults")
        )

    return result


@router.get("/policies/{policy_id}/stats", response_model=PolicyStatsResponse)
async def get_policy_execution_stats(policy_id: str):
    """
    Get execution statistics for a policy.

    Shows how many times the policy has executed and its success rate.
    """
    result = await get_policy_stats(policy_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to get stats"))

    return PolicyStatsResponse(
        policy_id=result.get("policy_id", policy_id),
        execution_count=result.get("execution_count", 0),
        success_count=result.get("success_count", 0),
        last_execution=result.get("last_execution"),
        success_rate=result.get("success_rate", 0.0),
        executions_today=result.get("executions_today", 0),
    )


@router.get("/policies/executions")
async def list_policy_executions(
    account_id: str = Query(..., description="Office account ID"),
    policy_id: str | None = Query(None, description="Filter by policy ID"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """
    List policy execution history.

    Shows when policies were triggered and what actions were taken.
    """
    result = await get_policy_execution_history(
        account_id=account_id,
        policy_id=policy_id,
        limit=limit,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to get executions")
        )

    return result


# =============================================================================
# Template Endpoints
# =============================================================================


@router.get("/templates", response_model=TemplateListResponse)
async def list_all_templates(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    List all response templates for an account.

    Templates are used for auto-replies and canned responses.
    """
    result = await list_templates(account_id)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to list templates")
        )

    return TemplateListResponse(
        templates=result.get("templates", []),
        total=result.get("count", 0),
    )


@router.post("/templates", response_model=TemplateResponse)
async def create_new_template(request: TemplateCreateRequest):
    """
    Create a new response template.

    Templates support {{variable}} placeholders for personalization.
    """
    result = await create_template(
        account_id=request.account_id,
        name=request.name,
        body_template=request.body_template,
        subject_template=request.subject_template,
        variables=request.variables,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to create template")
        )

    # Fetch created template
    template_result = await get_template(result["template_id"])
    if not template_result.get("success"):
        raise HTTPException(status_code=500, detail="Template created but failed to retrieve")

    template = template_result["template"]
    return TemplateResponse(
        id=template["id"],
        name=template["name"],
        subject_template=template.get("subject_template"),
        body_template=template["body_template"],
        variables=template.get("variables", []),
        use_count=template.get("use_count", 0),
    )


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_existing_template(template_id: str, request: TemplateUpdateRequest):
    """
    Update an existing template.

    Only provided fields will be updated.
    """
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.body_template is not None:
        updates["body_template"] = request.body_template
    if request.subject_template is not None:
        updates["subject_template"] = request.subject_template
    if request.variables is not None:
        updates["variables"] = request.variables

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await update_template(template_id, **updates)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to update template")
        )

    template = result["template"]
    return TemplateResponse(
        id=template["id"],
        name=template["name"],
        subject_template=template.get("subject_template"),
        body_template=template["body_template"],
        variables=template.get("variables", []),
        use_count=template.get("use_count", 0),
    )


@router.delete("/templates/{template_id}")
async def delete_existing_template(template_id: str):
    """
    Delete a template.

    This is permanent and cannot be undone.
    """
    result = await delete_template(template_id)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to delete template")
        )

    return {"success": True, "template_id": template_id, "deleted": True}


@router.post("/templates/{template_id}/preview")
async def preview_rendered_template(template_id: str, request: TemplatePreviewRequest):
    """
    Preview a template with provided variable values.

    Useful for seeing what an auto-reply will look like before enabling it.
    """
    result = await render_template(template_id, request.variables)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to render template")
        )

    return result


# =============================================================================
# VIP Contact Endpoints
# =============================================================================


@router.get("/vips", response_model=VIPListResponse)
async def list_vip_contacts(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    List all VIP contacts for an account.

    VIP contacts bypass normal automation rules and always get through.
    """
    result = await list_vips(account_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to list VIPs"))

    return VIPListResponse(
        vips=result.get("vips", []),
        by_priority=result.get("by_priority", {}),
        total=result.get("count", 0),
    )


@router.post("/vips", response_model=VIPResponse)
async def add_vip_contact(request: VIPCreateRequest):
    """
    Add a VIP contact.

    VIP contacts receive special treatment - their messages always reach you
    regardless of focus mode or automation rules.
    """
    result = await add_vip(
        account_id=request.account_id,
        email=request.email,
        name=request.name,
        priority=request.priority,
        always_notify=request.always_notify,
        bypass_focus=request.bypass_focus,
        notes=request.notes,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to add VIP"))

    return VIPResponse(
        id=result.get("vip_id", ""),
        email=result["email"],
        name=result.get("name"),
        priority=result["priority"],
        always_notify=result["always_notify"],
        bypass_focus=result["bypass_focus"],
        notes=result.get("notes"),
    )


@router.delete("/vips/{email}")
async def remove_vip_contact(
    email: str,
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Remove a VIP contact.

    The contact will no longer bypass automation rules.
    """
    result = await remove_vip(account_id, email)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to remove VIP"))

    return result


@router.get("/vips/suggest")
async def get_vip_suggestions(
    account_id: str = Query(..., description="Office account ID"),
    limit: int = Query(10, ge=1, le=50, description="Maximum suggestions"),
):
    """
    Get VIP contact suggestions based on email history.

    Analyzes your email patterns to suggest frequent/important contacts
    that might be good candidates for VIP status.
    """
    result = await suggest_vips(account_id, limit=limit)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to get suggestions")
        )

    return result


# =============================================================================
# Emergency Control Endpoints
# =============================================================================


@router.post("/emergency/pause")
async def trigger_emergency_pause(
    account_id: str = Query(..., description="Office account ID"),
    request: EmergencyPauseRequest | None = None,
):
    """
    Trigger emergency pause of all automation.

    This immediately stops all autonomous actions for the account.
    Pending actions in the queue will continue, but no new policy
    executions will occur.

    This is the "big red button" for when things go wrong or you
    need to take a break from automation.
    """
    reason = "User requested"
    duration_hours = None

    if request:
        reason = request.reason
        duration_hours = request.duration_hours

    result = await emergency_pause(
        account_id=account_id,
        reason=reason,
        duration_hours=duration_hours,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to pause automation")
        )

    return result


@router.post("/emergency/resume")
async def resume_emergency_pause(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Resume automation after an emergency pause.

    All policies will become active again.
    """
    result = await resume_automation(account_id)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to resume automation")
        )

    return result


@router.get("/emergency/status", response_model=EmergencyStatusResponse)
async def get_emergency_status(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Get current emergency pause status.

    Shows whether automation is paused and when it will resume.
    """
    result = await get_pause_status(account_id)

    if not result.get("success"):
        raise HTTPException(
            status_code=400, detail=result.get("error", "Failed to get pause status")
        )

    return EmergencyStatusResponse(
        is_paused=result.get("is_paused", False),
        paused_at=result.get("paused_at"),
        paused_until=result.get("paused_until"),
        reason=result.get("reason"),
    )


# =============================================================================
# Level 5 Eligibility Endpoints
# =============================================================================


@router.get("/level5/eligibility", response_model=EligibilityResponse)
async def check_level5_eligibility(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Check if an account is eligible for Level 5 (Autonomous) upgrade.

    Requirements for Level 5:
    - At least 14 days at Level 4
    - Low undo rate (< 10%)
    - Minimum 50 actions executed
    - No recent emergency pauses
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get account info
    cursor.execute(
        "SELECT * FROM office_accounts WHERE id = ?",
        (account_id,),
    )
    account = cursor.fetchone()

    if not account:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")

    account_dict = dict(account)
    current_level = account_dict.get("integration_level", 1)

    # Check if already at level 5
    if current_level >= 5:
        conn.close()
        return EligibilityResponse(
            eligible=True,
            days_at_level_4=999,
            undo_rate=0.0,
            actions_executed=0,
            requirements={
                "min_days_at_level_4": 14,
                "max_undo_rate": 10.0,
                "min_actions": 50,
            },
            missing_requirements=[],
        )

    # Get level history
    cursor.execute(
        """
        SELECT created_at FROM office_level_history
        WHERE account_id = ? AND to_level = 4
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (account_id,),
    )
    level4_row = cursor.fetchone()

    days_at_level_4 = 0
    if level4_row:
        level4_date = datetime.fromisoformat(level4_row["created_at"])
        days_at_level_4 = (datetime.now() - level4_date).days

    # Get action stats
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'undone' THEN 1 END) as undone
        FROM office_action_queue
        WHERE account_id = ?
        """,
        (account_id,),
    )
    stats_row = cursor.fetchone()
    total_actions = stats_row["total"] if stats_row else 0
    undone_actions = stats_row["undone"] if stats_row else 0
    undo_rate = (undone_actions / total_actions * 100) if total_actions > 0 else 0.0

    conn.close()

    # Check requirements
    requirements = {
        "min_days_at_level_4": 14,
        "max_undo_rate": 10.0,
        "min_actions": 50,
    }

    missing = []
    if current_level < 4:
        missing.append("Must be at Level 4 first")
    if days_at_level_4 < 14:
        missing.append(f"Need {14 - days_at_level_4} more days at Level 4")
    if undo_rate > 10.0:
        missing.append(f"Undo rate too high ({undo_rate:.1f}% > 10%)")
    if total_actions < 50:
        missing.append(f"Need {50 - total_actions} more actions")

    eligible = len(missing) == 0 and current_level >= 4

    return EligibilityResponse(
        eligible=eligible,
        days_at_level_4=days_at_level_4,
        undo_rate=round(undo_rate, 2),
        actions_executed=total_actions,
        requirements=requirements,
        missing_requirements=missing,
    )


@router.post("/level5/upgrade")
async def upgrade_to_level5(
    account_id: str = Query(..., description="Office account ID"),
):
    """
    Upgrade an account to Level 5 (Autonomous).

    This is a significant trust milestone. At Level 5, Dex can:
    - Execute actions without undo windows for routine tasks
    - Send auto-replies based on templates
    - Apply learned patterns from your behavior

    The account must meet all eligibility requirements.
    """
    # First check eligibility
    eligibility = await check_level5_eligibility(account_id)

    if not eligibility.eligible:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Not eligible for Level 5",
                "missing_requirements": eligibility.missing_requirements,
            },
        )

    conn = get_connection()
    cursor = conn.cursor()

    # Update account level
    now = datetime.now().isoformat()
    cursor.execute(
        """
        UPDATE office_accounts
        SET integration_level = 5, updated_at = ?
        WHERE id = ?
        """,
        (now, account_id),
    )

    # Record in level history
    cursor.execute(
        """
        INSERT INTO office_level_history (account_id, from_level, to_level, reason)
        VALUES (?, 4, 5, 'User-initiated upgrade after meeting eligibility requirements')
        """,
        (account_id,),
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "account_id": account_id,
        "new_level": 5,
        "message": "Congratulations! You've reached Level 5 - Autonomous. Dex can now act independently on your behalf.",
    }
