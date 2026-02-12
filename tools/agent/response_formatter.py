from __future__ import annotations

from typing import Any


class QueryResult:
    def __init__(
        self,
        text: str,
        tool_uses: list[dict],
        cost_usd: float,
        session_total_cost_usd: float,
        model: str | None = None,
        complexity: str | None = None,
        routing_reasoning: str | None = None,
    ):
        self.text = text
        self.tool_uses = tool_uses
        self.cost_usd = cost_usd
        self.session_total_cost_usd = session_total_cost_usd
        self.model = model
        self.complexity = complexity
        self.routing_reasoning = routing_reasoning

    def __str__(self) -> str:
        return self.text


class StructuredQueryResult:
    def __init__(
        self,
        structured_output: dict[str, Any],
        raw_text: str,
        tool_uses: list[dict],
        cost_usd: float,
        session_total_cost_usd: float,
        schema_name: str | None = None,
        model: str | None = None,
        complexity: str | None = None,
        routing_reasoning: str | None = None,
    ):
        self.structured_output = structured_output
        self.raw_text = raw_text
        self.tool_uses = tool_uses
        self.cost_usd = cost_usd
        self.session_total_cost_usd = session_total_cost_usd
        self.schema_name = schema_name
        self.model = model
        self.complexity = complexity
        self.routing_reasoning = routing_reasoning

    def __str__(self) -> str:
        import json
        return json.dumps(self.structured_output, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.structured_output.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.structured_output[key]

    def __contains__(self, key: str) -> bool:
        return key in self.structured_output

    @property
    def current_step(self) -> dict[str, Any] | None:
        return self.structured_output.get("current_step")

    @property
    def blockers(self) -> list[dict[str, Any]]:
        return self.structured_output.get("blockers", [])

    @property
    def remaining_steps(self) -> int:
        return self.structured_output.get("remaining_steps", 0)


def strip_preamble(text: str) -> str:
    preambles = [
        "Certainly!", "Of course!", "Sure!", "Absolutely!",
        "Great question!", "Good question!", "Happy to help!",
        "I'd be happy to", "I'll be glad to", "Let me help you with that.",
    ]
    stripped = text.strip()
    for preamble in preambles:
        if stripped.startswith(preamble):
            stripped = stripped[len(preamble):].lstrip()
    return stripped


async def quick_query(
    message: str,
    session_type: str = "main",
    channel: str = "direct",
) -> str:
    from tools.agent.query_engine import DexAIClient

    async with DexAIClient(
        session_type=session_type,
        channel=channel,
    ) as client:
        result = await client.query(message)
        return result.text


async def quick_decompose(
    task: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    from tools.agent.query_engine import DexAIClient

    async with DexAIClient(
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Break down this task into small steps: {task}",
            schema_name="task_decomposition",
        )


async def quick_energy_match(
    context: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    from tools.agent.query_engine import DexAIClient

    async with DexAIClient(
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Assess energy and match tasks: {context}",
            schema_name="energy_assessment",
        )


async def quick_friction_check(
    task: str,
    channel: str = "direct",
) -> StructuredQueryResult:
    from tools.agent.query_engine import DexAIClient

    async with DexAIClient(
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(
            f"Check for friction/blockers: {task}",
            schema_name="friction_check",
        )


async def quick_current_step(
    context: str = "",
    channel: str = "direct",
) -> StructuredQueryResult:
    from tools.agent.query_engine import DexAIClient

    prompt = "What's the ONE thing I should do right now?"
    if context:
        prompt = f"{prompt} Context: {context}"

    async with DexAIClient(
        session_type="main",
        channel=channel,
    ) as client:
        return await client.query_structured(prompt, schema_name="current_step")
