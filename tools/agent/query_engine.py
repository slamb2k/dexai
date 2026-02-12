from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, AsyncIterator, AsyncGenerator, Optional, Union, TYPE_CHECKING

from tools.agent import PROJECT_ROOT
from tools.agent.constants import OWNER_USER_ID
from tools.agent.subagents import get_agents_for_sdk
from tools.agent.schemas import get_schema
from tools.agent.client_factory import (
    load_config,
    build_system_prompt,
    DEFAULT_CONFIG,
)
from tools.agent.response_formatter import (
    QueryResult,
    StructuredQueryResult,
    strip_preamble,
)

if TYPE_CHECKING:
    from tools.agent.model_router import TaskComplexity

logger = logging.getLogger(__name__)


def _extract_session_id(msg: Any, client: Any = None) -> str | None:
    if hasattr(msg, "session_id") and msg.session_id:
        return msg.session_id

    if hasattr(msg, "data") and isinstance(msg.data, dict):
        sid = msg.data.get("session_id")
        if sid:
            return sid

    if hasattr(msg, "data") and hasattr(msg.data, "session_id"):
        sid = msg.data.session_id
        if sid:
            return sid

    if client is not None:
        if hasattr(client, "session_id") and client.session_id:
            return client.session_id

    return None


class DexAIClient:
    def __init__(
        self,
        working_dir: str | None = None,
        config: dict | None = None,
        explicit_complexity: "TaskComplexity | None" = None,
        session_type: str = "main",
        channel: str = "direct",
        resume_session_id: str | None = None,
        ask_user_handler: Optional[callable] = None,
    ):
        self.config = config or load_config()
        self.working_dir = working_dir or str(
            self.config.get("agent", {}).get("working_directory") or PROJECT_ROOT
        )
        self.explicit_complexity = explicit_complexity
        self.session_type = session_type
        self.channel = channel
        self.resume_session_id = resume_session_id
        self.ask_user_handler = ask_user_handler
        self._client = None
        self._session_id: str | None = None
        self._total_cost: float = 0.0
        self._router = None
        self._pending_prompt: str | None = None
        self._last_routing_decision = None

    def _get_authorized_mcp_tools(self) -> list[str]:
        prefix = "mcp__dexai__"
        tools = []

        always_available = [
            "memory_search", "memory_write",
            "commitments_add", "commitments_list",
            "context_capture", "context_resume",
            "task_decompose", "friction_check",
            "current_step", "energy_match",
            "schedule", "notify", "reminder",
            "channel_pair", "generate_image",
            "get_skill_dependency_setting", "verify_package", "install_package",
        ]
        tools.extend(f"{prefix}{name}" for name in always_available)

        try:
            import sqlite3 as _sqlite3
            from pathlib import Path as _Path

            db_path = _Path(__file__).parent.parent.parent / "data" / "office.db"
            if db_path.exists():
                conn = _sqlite3.connect(str(db_path))
                conn.row_factory = _sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT MAX(integration_level) as max_level FROM office_accounts"
                )
                row = cursor.fetchone()
                conn.close()

                if row and row["max_level"]:
                    max_level = int(row["max_level"])

                    if max_level >= 2:
                        tools.extend(f"{prefix}{name}" for name in [
                            "email_list", "email_read",
                            "calendar_today", "calendar_propose",
                        ])

                    if max_level >= 3:
                        tools.append(f"{prefix}email_draft")
        except Exception as e:
            logger.debug(f"Office tools authorization check failed: {e}")

        return tools

    async def __aenter__(self) -> "DexAIClient":
        await self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._cleanup()

    def _init_router(self):
        agent_config = self.config.get("agent", {})

        if not agent_config.get("use_routing", True):
            return None

        try:
            from tools.agent.model_router import ModelRouter, ROUTING_CONFIG_PATH

            if ROUTING_CONFIG_PATH.exists():
                router = ModelRouter.from_config(ROUTING_CONFIG_PATH)
                if router.enabled and router.openrouter_api_key:
                    logger.info(f"Model router initialized (profile={router.profile.value})")
                    return router
                elif not router.openrouter_api_key:
                    logger.warning("OPENROUTER_API_KEY not set, routing disabled")
            else:
                logger.debug("Routing config not found, using default model")
        except Exception as e:
            logger.warning(f"Failed to initialize router: {e}")

        return None

    def _build_options(self, prompt_for_routing: str | None = None) -> dict:
        """
        Build the common ClaudeAgentOptions kwargs dict.

        Handles config loading, routing, sandbox, hooks, subagents, and permissions.
        Both _init_client() and query_structured() call this to avoid duplication.

        Args:
            prompt_for_routing: Optional prompt text used for routing decisions.
                If None, uses self._pending_prompt.

        Returns:
            Dict of kwargs suitable for ClaudeAgentOptions(**kwargs).
        """
        from tools.agent.permissions import create_permission_callback
        from tools.agent.hooks import create_hooks
        from tools.agent.sdk_tools import dexai_server

        agent_config = self.config.get("agent", {})
        tools_config = self.config.get("tools", {})
        sandbox_config = self.config.get("sandbox", {})

        allowed_tools = tools_config.get("allowed_builtin", []).copy()
        allowed_tools.extend(self._get_authorized_mcp_tools())

        if self._router is None:
            self._router = self._init_router()

        model = agent_config.get("model", "claude-sonnet-4-20250514")
        env = {}

        routing_prompt = prompt_for_routing or self._pending_prompt
        if self._router and routing_prompt:
            from tools.agent.model_router import TaskComplexity

            decision = self._router.route(
                routing_prompt,
                explicit_complexity=self.explicit_complexity,
                tool_count=len(allowed_tools),
            )

            routing_options = self._router.build_options_dict(decision)

            model = routing_options["model"]
            env = routing_options["env"]
            self._last_routing_decision = decision

            logger.info(f"Routed to {model}: {routing_options['reasoning']}")

            self._record_routing_to_dashboard(decision)
        elif self._router:
            from tools.agent.model_router import TaskComplexity

            decision = self._router.route(
                "",
                explicit_complexity=self.explicit_complexity or TaskComplexity.MODERATE,
                tool_count=len(allowed_tools),
            )
            routing_options = self._router.build_options_dict(decision)
            model = routing_options["model"]
            env = routing_options["env"]
            self._last_routing_decision = decision

        sandbox_settings = None
        if sandbox_config.get("enabled", False):
            sandbox_settings = {
                "enabled": True,
                "autoAllowBashIfSandboxed": sandbox_config.get(
                    "auto_allow_bash_if_sandboxed", True
                ),
                "excludedCommands": sandbox_config.get("excluded_commands", []),
                "allowUnsandboxedCommands": sandbox_config.get(
                    "allow_unsandboxed_commands", True
                ),
            }
            network_config = sandbox_config.get("network", {})
            if network_config:
                sandbox_settings["network"] = {
                    "allowLocalBinding": network_config.get("allow_local_binding", True),
                    "allowUnixSockets": network_config.get("allow_unix_sockets", []),
                }

        workspace_root = Path(self.working_dir) if self.working_dir else None

        hooks = create_hooks(
            user_id=OWNER_USER_ID,
            channel=self.channel,
            enable_security=True,
            enable_audit=True,
            enable_dashboard=True,
            enable_context_save=True,
            workspace_path=workspace_root,
        )

        subagents_config = self.config.get("subagents", {})
        agents = None
        if subagents_config.get("enabled", True):
            try:
                agents = get_agents_for_sdk()
                logger.debug(f"Registered {len(agents)} ADHD subagents")
            except Exception as e:
                logger.warning(f"Failed to load subagents: {e}")

        options_kwargs = {
            "model": model,
            "allowed_tools": allowed_tools,
            "mcp_servers": {"dexai": dexai_server},
            "cwd": self.working_dir,
            "permission_mode": agent_config.get("permission_mode", "default"),
            "system_prompt": build_system_prompt(
                config=self.config,
                channel=self.channel,
                session_type=self.session_type,
                workspace_root=workspace_root,
            ),
            "can_use_tool": create_permission_callback(
                config=self.config,
                channel=self.channel,
                ask_user_handler=self.ask_user_handler,
            ),
            "env": env or {},
        }

        if agents:
            options_kwargs["agents"] = agents

        if sandbox_settings:
            options_kwargs["sandbox"] = sandbox_settings

        if hooks:
            options_kwargs["hooks"] = hooks

        if self.resume_session_id:
            options_kwargs["resume"] = self.resume_session_id
            logger.info(f"Resuming session: {self.resume_session_id}")

        return options_kwargs

    async def _init_client(self) -> None:
        try:
            from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        options_kwargs = self._build_options()
        options = ClaudeAgentOptions(**options_kwargs)

        self._client = ClaudeSDKClient(options=options)
        await self._client.__aenter__()

    def _record_routing_to_dashboard(self, decision) -> None:
        try:
            from tools.dashboard.backend.database import record_routing_decision
            record_routing_decision(
                user_id=OWNER_USER_ID,
                complexity=decision.complexity.value,
                model=decision.primary_model.routed_id,
                exacto=decision.primary_model.use_exacto,
                reasoning=decision.reasoning,
            )
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Failed to record routing decision: {e}")

    async def _cleanup(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def query(self, message: str) -> "QueryResult":
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
        except ImportError:
            raise ImportError("claude-agent-sdk required")

        self._pending_prompt = message

        await self._client.query(message)

        response_parts = []
        tool_uses = []
        total_cost = 0.0

        async for msg in self._client.receive_response():
            extracted_sid = _extract_session_id(msg, self._client)
            if extracted_sid and extracted_sid != self._session_id:
                self._session_id = extracted_sid
                logger.debug(f"Captured session_id: {self._session_id}")

            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_uses.append({
                            "tool": block.name,
                            "input": block.input,
                        })
            elif isinstance(msg, ResultMessage):
                if hasattr(msg, "total_cost_usd"):
                    total_cost = msg.total_cost_usd or 0.0
                extracted_sid = _extract_session_id(msg, self._client)
                if extracted_sid and extracted_sid != self._session_id:
                    self._session_id = extracted_sid
                    logger.debug(f"Captured session_id from result: {self._session_id}")
                break

        self._total_cost += total_cost

        text = "\n".join(response_parts)
        adhd_config = self.config.get("adhd", {}).get("response", {})

        if adhd_config.get("strip_preamble", True):
            text = strip_preamble(text)

        max_length = adhd_config.get("max_length_chat", 500)
        if len(text) > max_length * 2:
            text = text[:max_length * 2] + "..."

        model = None
        complexity = None
        routing_reasoning = None
        if self._last_routing_decision:
            model = self._last_routing_decision.primary_model.routed_id
            complexity = self._last_routing_decision.complexity.value
            routing_reasoning = self._last_routing_decision.reasoning

        return QueryResult(
            text=text,
            tool_uses=tool_uses,
            cost_usd=total_cost,
            session_total_cost_usd=self._total_cost,
            model=model,
            complexity=complexity,
            routing_reasoning=routing_reasoning,
        )

    async def receive_response(self) -> AsyncIterator[Any]:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        async for msg in self._client.receive_response():
            yield msg

    async def query_stream(
        self,
        message_generator: AsyncGenerator[Union[str, dict], None],
    ) -> AsyncIterator[Any]:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        async def normalized_generator():
            async for msg in message_generator:
                if isinstance(msg, str):
                    yield {
                        "type": "user",
                        "message": {"role": "user", "content": msg}
                    }
                elif isinstance(msg, dict):
                    if "type" not in msg:
                        yield {
                            "type": "user",
                            "message": {"role": "user", "content": msg.get("content", str(msg))}
                        }
                    else:
                        yield msg
                else:
                    yield {
                        "type": "user",
                        "message": {"role": "user", "content": str(msg)}
                    }

        try:
            from claude_agent_sdk import query
        except ImportError:
            raise ImportError(
                "claude-agent-sdk required. Install with: uv pip install claude-agent-sdk"
            )

        async for msg in query(
            prompt=normalized_generator(),
            options=self._client._options if hasattr(self._client, "_options") else None,
        ):
            extracted_sid = _extract_session_id(msg, self._client)
            if extracted_sid and extracted_sid != self._session_id:
                self._session_id = extracted_sid
                logger.debug(f"Captured session_id from stream: {self._session_id}")

            yield msg

    async def interrupt(self) -> None:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        if hasattr(self._client, "interrupt"):
            await self._client.interrupt()
        else:
            logger.warning("Interrupt not supported by current SDK client")

    async def query_structured(
        self,
        message: str,
        schema_name: str | None = None,
        output_format: dict[str, Any] | None = None,
    ) -> "StructuredQueryResult":
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        if output_format:
            selected_format = output_format
        elif schema_name:
            selected_format = get_schema(schema_name)
            if not selected_format:
                raise ValueError(
                    f"Unknown schema: {schema_name}. "
                    f"Available: task_decomposition, energy_assessment, "
                    f"commitment_list, friction_check, current_step"
                )
        else:
            raise ValueError(
                "Either schema_name or output_format must be provided"
            )

        try:
            from claude_agent_sdk import (
                ClaudeSDKClient,
                ClaudeAgentOptions,
                AssistantMessage,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
            )
        except ImportError:
            raise ImportError("claude-agent-sdk required")

        self._pending_prompt = message

        options_kwargs = self._build_options(prompt_for_routing=message)
        options_kwargs["output_format"] = selected_format

        options = ClaudeAgentOptions(**options_kwargs)

        structured_client = ClaudeSDKClient(options=options)
        await structured_client.__aenter__()

        try:
            await structured_client.query(message)

            response_parts = []
            tool_uses = []
            total_cost = 0.0
            structured_output = None

            async for msg in structured_client.receive_response():
                extracted_sid = _extract_session_id(msg, structured_client)
                if extracted_sid and extracted_sid != self._session_id:
                    self._session_id = extracted_sid

                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_uses.append({
                                "tool": block.name,
                                "input": block.input,
                            })
                elif isinstance(msg, ResultMessage):
                    if hasattr(msg, "total_cost_usd"):
                        total_cost = msg.total_cost_usd or 0.0
                    if hasattr(msg, "structured_output"):
                        structured_output = msg.structured_output
                    break

            self._total_cost += total_cost

            if structured_output is None and response_parts:
                import json
                text = "\n".join(response_parts).strip()
                try:
                    if text.startswith("{"):
                        structured_output = json.loads(text)
                    elif "```json" in text:
                        json_start = text.find("```json") + 7
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            json_str = text[json_start:json_end].strip()
                            structured_output = json.loads(json_str)
                    elif "```" in text:
                        json_start = text.find("```") + 3
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            json_str = text[json_start:json_end].strip()
                            if json_str.startswith("{"):
                                structured_output = json.loads(json_str)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse JSON from response text")

            model_used = None
            complexity = None
            routing_reasoning = None
            if self._last_routing_decision:
                model_used = self._last_routing_decision.primary_model.routed_id
                complexity = self._last_routing_decision.complexity.value
                routing_reasoning = self._last_routing_decision.reasoning

            return StructuredQueryResult(
                structured_output=structured_output or {},
                raw_text="\n".join(response_parts),
                tool_uses=tool_uses,
                cost_usd=total_cost,
                session_total_cost_usd=self._total_cost,
                schema_name=schema_name,
                model=model_used,
                complexity=complexity,
                routing_reasoning=routing_reasoning,
            )

        finally:
            await structured_client.__aexit__(None, None, None)

    def _strip_preamble(self, text: str) -> str:
        return strip_preamble(text)

    @property
    def total_cost(self) -> float:
        return self._total_cost

    @property
    def session_id(self) -> str | None:
        return self._session_id


def main():
    import argparse
    import asyncio

    import yaml

    from tools.agent.client_factory import load_config
    from tools.agent.response_formatter import quick_query

    parser = argparse.ArgumentParser(description="DexAI SDK Client")
    parser.add_argument("--query", help="Query to send")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--show-config", action="store_true", help="Show configuration")
    parser.add_argument("--session", default="main",
                        choices=["main", "subagent", "heartbeat", "cron"],
                        help="Session type (controls prompt content)")
    parser.add_argument("--channel", default="direct", help="Channel (direct, telegram, discord)")

    args = parser.parse_args()

    if args.show_config:
        config = load_config()
        print(yaml.dump(config, default_flow_style=False))
        return

    if args.query:
        async def run_query():
            result = await quick_query(
                args.query,
                session_type=args.session,
                channel=args.channel,
            )
            print(result)
            return result

        asyncio.run(run_query())

    elif args.interactive:
        async def interactive():
            async with DexAIClient(
                session_type=args.session,
                channel=args.channel,
            ) as client:
                print(f"DexAI Interactive Mode (session={args.session}, channel={args.channel})")
                print("Type 'exit' to quit")
                print("-" * 40)

                while True:
                    try:
                        user_input = input("\nYou: ").strip()
                        if user_input.lower() in ("exit", "quit", "q"):
                            break
                        if not user_input:
                            continue

                        result = await client.query(user_input)
                        print(f"\nDex: {result.text}")
                        if result.cost_usd > 0:
                            print(f"[Cost: ${result.cost_usd:.4f}]")

                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Error: {e}")

                print(f"\nSession total cost: ${client.total_cost:.4f}")

        asyncio.run(interactive())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
