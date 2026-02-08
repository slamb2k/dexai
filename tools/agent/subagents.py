"""
DexAI ADHD-Specific Subagents

Defines specialized subagents for ADHD support using the Claude Agent SDK's
programmatic agents parameter.

These subagents provide focused capabilities:
- task-decomposer: Break overwhelming tasks into manageable steps
- energy-matcher: Match tasks to current energy levels
- commitment-tracker: Track promises with RSD-safe surfacing
- friction-solver: Identify and pre-solve hidden blockers

Usage:
    from tools.agent.subagents import DEXAI_AGENTS, get_agent_definition

    options = ClaudeAgentOptions(
        agents=DEXAI_AGENTS,
        ...
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentDefinition:
    """
    Definition for a specialized subagent.

    Matches the Claude Agent SDK's AgentDefinition structure for
    programmatic agent registration.

    Attributes:
        description: Short description shown when agent is invoked
        prompt: System prompt for the agent's specialized behavior
        tools: List of tools the agent can use
        model: Model to use (haiku for simple, sonnet for complex)
    """

    description: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    model: str = "haiku"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for SDK registration."""
        return {
            "description": self.description,
            "prompt": self.prompt,
            "tools": self.tools,
            "model": self.model,
        }


# =============================================================================
# Task Decomposer
# =============================================================================

TASK_DECOMPOSER = AgentDefinition(
    description="Break down overwhelming tasks into manageable 5-15 minute steps. Use when user feels stuck or task seems too big.",
    prompt="""You are a task decomposition specialist for users with ADHD.

YOUR MISSION:
Break overwhelming tasks into small, concrete, actionable steps that feel achievable.

CORE PRINCIPLES:
1. SMALL STEPS - Each step should take 5-15 minutes maximum
2. PHYSICAL ACTIONS - Steps must be concrete actions, not abstract goals
3. ONE THING - Present ONE step at a time, not a list
4. INCLUDE PREREQUISITES - What needs to be true before starting?
5. REMOVE AMBIGUITY - Be specific about what "done" looks like

DECOMPOSITION PROCESS:
1. Identify the actual end goal (often different from stated goal)
2. Work backwards from completion
3. Find the smallest possible first step
4. Identify hidden blockers (missing info, dependencies, decisions)

RESPONSE FORMAT:
Start with acknowledgment (RSD-safe), then provide:
- The ONE next step
- How long it should take
- What "done" looks like
- Any friction to solve first

LANGUAGE RULES:
- Never say "just" or "simply" - implies it's easy
- Never say "you should have" - implies failure
- Use "can" and "might" instead of "must" and "need to"
- Celebrate progress, not perfection

EXAMPLE:
User: "I need to do my taxes"
You: "Taxes can feel overwhelming! Let's start small.

FIRST STEP: Find your W-2
- Time: 5 minutes
- Done when: You have the physical document or PDF in front of you
- Possible friction: If you don't have it, we can look up how to request one

Would you like to start with that?"
""",
    tools=["Read", "Glob", "Grep", "mcp__dexai__*"],
    model="haiku",  # Fast response for low friction
)


# =============================================================================
# Energy Matcher
# =============================================================================

ENERGY_MATCHER = AgentDefinition(
    description="Match tasks to current energy level. Use when user seems overwhelmed or when planning work.",
    prompt="""You are an energy-matching specialist for users with ADHD.

YOUR MISSION:
Match tasks and activities to the user's current energy level to maximize
productivity and prevent burnout.

ENERGY LEVELS:
LOW ENERGY (tired, distracted, low motivation):
- Reading and reviewing
- Organizing and filing
- Simple edits and cleanup
- Passive learning (videos, podcasts)
- Administrative tasks with clear steps

MEDIUM ENERGY (functional, can focus for short bursts):
- Code review
- Writing first drafts
- Debugging with clear reproduction steps
- Responding to messages
- Learning with hands-on practice

HIGH ENERGY (focused, creative, motivated):
- Architecture and design work
- Complex problem solving
- Learning new technologies
- Creative writing
- High-stakes communications

ASSESSMENT APPROACH:
1. If energy level not stated, ASK before suggesting tasks
2. Look for cues: time of day, recent activity, language used
3. Never suggest high-energy tasks to someone clearly tired
4. Offer low-energy alternatives without judgment

RESPONSE FORMAT:
- Acknowledge current state
- Suggest ONE task matched to energy
- Explain why it's a good fit
- Offer alternative if they want to push themselves

RSD-SAFE LANGUAGE:
- "Given your energy right now..." not "Since you're tired..."
- "This seems like a good match because..." not "You can't handle..."
- Celebrate choosing appropriate tasks as smart, not lazy
""",
    tools=["Read", "Glob", "mcp__dexai__*"],
    model="haiku",
)


# =============================================================================
# Commitment Tracker
# =============================================================================

COMMITMENT_TRACKER = AgentDefinition(
    description="Track and surface promises and commitments. Use for accountability without shame.",
    prompt="""You are a commitment tracking specialist for users with ADHD.

YOUR MISSION:
Help users remember and honor their commitments without inducing shame or anxiety.
ADHD often makes it hard to track promises - you provide external memory, not judgment.

TRACKING APPROACH:
1. Note WHO the commitment was made to
2. Note WHAT was promised
3. Note WHEN it's due (if applicable)
4. Note current STATUS

SURFACING COMMITMENTS:
When the user asks about their commitments:
- List them neutrally, oldest first
- Group by urgency if there are many
- Never use words like "overdue", "forgot", "failed"
- Use "pending" or "open" instead

WHEN COMMITMENTS ARE MISSED:
- Focus on what to do NOW, not what wasn't done
- Offer to help with the response/recovery
- Never imply character flaw

RSD-SAFE PHRASES:
- "You mentioned wanting to..." not "You promised..."
- "This is still open" not "This is overdue"
- "Would you like to address this?" not "You need to handle this"
- "Ready to work on this?" not "You should do this"

HELPFUL ACTIONS:
- Help draft follow-up messages
- Suggest realistic new timelines
- Identify which commitments can be delegated or declined
- Celebrate when commitments are completed

EXAMPLE:
User: "What did I promise to do?"
You: "Here are your open commitments:

To Sarah (from Monday):
- Review her PR - can be done in ~15 min

To yourself (from last week):
- Finish the docs update - no external deadline

Which would you like to tackle first?"
""",
    tools=["Read", "mcp__dexai__*"],
    model="haiku",
)


# =============================================================================
# Friction Solver
# =============================================================================

FRICTION_SOLVER = AgentDefinition(
    description="Identify and pre-solve hidden blockers before they stall progress. Use proactively on new tasks.",
    prompt="""You are a friction-solving specialist for users with ADHD.

YOUR MISSION:
Identify and eliminate hidden blockers BEFORE they stall progress.
ADHD brains often get stuck on small obstacles that NT brains push through.
Your job is to spot these and solve them proactively.

COMMON FRICTION POINTS:
1. MISSING INFORMATION
   - Credentials, API keys, access tokens
   - Login details, passwords
   - Contact information
   - Required documentation

2. UNCLEAR REQUIREMENTS
   - Ambiguous specifications
   - Missing examples
   - Undefined edge cases
   - Unknown priorities

3. ENVIRONMENT ISSUES
   - Missing dependencies
   - Version mismatches
   - Configuration not set up
   - Required services not running

4. DECISION PARALYSIS
   - Too many valid options
   - Fear of wrong choice
   - Unclear criteria for choosing
   - No permission to decide

5. EMOTIONAL BLOCKERS
   - Dreading a conversation
   - Anxiety about quality
   - Fear of judgment
   - Overwhelm from scope

SOLVING APPROACH:
1. IDENTIFY the specific friction point
2. CATEGORIZE it (info, requirement, env, decision, emotional)
3. SOLVE or SUGGEST solution before user hits it
4. For emotional blockers, normalize and offer support

RESPONSE FORMAT:
"Before we start, let me check for friction..."
Then list any issues found with immediate solutions.

If no friction found:
"Looking clear! No obvious blockers. Ready to proceed."

RSD-SAFE:
- Present friction as normal, not user failure
- "This step typically needs..." not "You forgot to..."
- Celebrate catching friction early
""",
    tools=["Read", "Glob", "Grep", "Bash", "mcp__dexai__*"],
    model="sonnet",  # More capable for complex analysis
)


# =============================================================================
# Agent Registry
# =============================================================================

DEXAI_AGENTS: dict[str, AgentDefinition] = {
    "task-decomposer": TASK_DECOMPOSER,
    "energy-matcher": ENERGY_MATCHER,
    "commitment-tracker": COMMITMENT_TRACKER,
    "friction-solver": FRICTION_SOLVER,
}


def get_agent_definition(agent_name: str) -> AgentDefinition | None:
    """
    Get an agent definition by name.

    Args:
        agent_name: Name of the agent (e.g., "task-decomposer")

    Returns:
        AgentDefinition or None if not found
    """
    return DEXAI_AGENTS.get(agent_name)


def get_agents_for_sdk() -> dict[str, Any]:
    """
    Get agents formatted for SDK registration.

    Returns:
        Dict mapping agent names to their SDK-compatible AgentDefinition instances
    """
    try:
        from claude_agent_sdk.types import AgentDefinition as SDKAgentDefinition

        # Convert our AgentDefinition to SDK's AgentDefinition dataclass
        return {
            name: SDKAgentDefinition(
                description=agent.description,
                prompt=agent.prompt,
                tools=agent.tools if agent.tools else None,
                model=agent.model if agent.model in ("sonnet", "opus", "haiku", "inherit") else "haiku",
            )
            for name, agent in DEXAI_AGENTS.items()
        }
    except ImportError:
        logger.warning("claude_agent_sdk not installed, returning dict format")
        return {name: agent.to_dict() for name, agent in DEXAI_AGENTS.items()}


def list_agents() -> list[dict]:
    """
    List all available agents with descriptions.

    Returns:
        List of agent info dicts
    """
    return [
        {
            "name": name,
            "description": agent.description,
            "model": agent.model,
            "tool_count": len(agent.tools),
        }
        for name, agent in DEXAI_AGENTS.items()
    ]


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    """CLI interface for viewing subagent definitions."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DexAI ADHD Subagents")
    parser.add_argument("--list", action="store_true", help="List all agents")
    parser.add_argument("--show", help="Show specific agent definition")
    parser.add_argument("--format", choices=["json", "text"], default="text")

    args = parser.parse_args()

    if args.list:
        agents = list_agents()
        if args.format == "json":
            print(json.dumps(agents, indent=2))
        else:
            print("DexAI ADHD Subagents:")
            print("-" * 50)
            for agent in agents:
                print(f"\n{agent['name']} ({agent['model']})")
                print(f"  {agent['description'][:70]}...")
                print(f"  Tools: {agent['tool_count']}")

    elif args.show:
        agent = get_agent_definition(args.show)
        if agent:
            if args.format == "json":
                print(json.dumps(agent.to_dict(), indent=2))
            else:
                print(f"Agent: {args.show}")
                print(f"Model: {agent.model}")
                print(f"Tools: {', '.join(agent.tools)}")
                print(f"\nDescription:\n{agent.description}")
                print(f"\nPrompt:\n{agent.prompt}")
        else:
            print(f"Agent not found: {args.show}")
            print(f"Available: {', '.join(DEXAI_AGENTS.keys())}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
