"""
Chat Service Module

Wraps DexAIClient for dashboard chat context with conversation history,
streaming responses, and ADHD-aware formatting.
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# Database path (same as dashboard.db)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dashboard.db"


def get_db_connection() -> sqlite3.Connection:
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_chat_tables():
    """Initialize chat-related database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Chat conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            model TEXT,
            complexity TEXT,
            cost_usd REAL,
            tool_uses TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
        )
    """)

    # Indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
        ON chat_messages(conversation_id, created_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_conversations_user
        ON chat_conversations(user_id, updated_at DESC)
    """)

    conn.commit()
    conn.close()


# Initialize tables on module load
init_chat_tables()


class ChatService:
    """
    Service for handling chat interactions with DexAI.

    Provides:
    - Conversation persistence in SQLite
    - Integration with DexAIClient for LLM responses
    - Streaming response support
    - ADHD-aware message formatting
    """

    def __init__(self, user_id: str = "anonymous"):
        """
        Initialize chat service.

        Args:
            user_id: User identifier for context and permissions
        """
        self.user_id = user_id
        self._current_conversation_id: str | None = None

    def get_or_create_conversation(self, conversation_id: str | None = None) -> str:
        """
        Get existing conversation or create a new one.

        Args:
            conversation_id: Optional existing conversation ID

        Returns:
            Conversation ID
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        if conversation_id:
            # Check if exists
            cursor.execute(
                "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, self.user_id),
            )
            if cursor.fetchone():
                conn.close()
                self._current_conversation_id = conversation_id
                return conversation_id

        # Create new conversation
        new_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO chat_conversations (id, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (new_id, self.user_id, datetime.now().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        self._current_conversation_id = new_id
        return new_id

    def get_conversation_history(
        self,
        conversation_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Get message history for a conversation.

        Args:
            conversation_id: Conversation to get history for (uses current if None)
            limit: Maximum messages to return

        Returns:
            List of message dicts with id, role, content, created_at
        """
        conv_id = conversation_id or self._current_conversation_id
        if not conv_id:
            return []

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, role, content, model, complexity, cost_usd, tool_uses, created_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (conv_id, limit),
        )

        messages = []
        for row in cursor.fetchall():
            msg = dict(row)
            if msg.get("tool_uses"):
                try:
                    msg["tool_uses"] = json.loads(msg["tool_uses"])
                except json.JSONDecodeError:
                    pass
            messages.append(msg)

        conn.close()
        return messages

    def get_conversations(self, limit: int = 20) -> list[dict]:
        """
        Get list of conversations for the user.

        Args:
            limit: Maximum conversations to return

        Returns:
            List of conversation dicts
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT content FROM chat_messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.created_at DESC LIMIT 1) as last_message
            FROM chat_conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (self.user_id, limit),
        )

        conversations = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return conversations

    def save_message(
        self,
        role: str,
        content: str,
        conversation_id: str | None = None,
        model: str | None = None,
        complexity: str | None = None,
        cost_usd: float | None = None,
        tool_uses: list[dict] | None = None,
    ) -> str:
        """
        Save a message to the conversation.

        Args:
            role: 'user' or 'assistant'
            content: Message content
            conversation_id: Conversation ID (uses current if None)
            model: Model used for response
            complexity: Complexity level for routing
            cost_usd: Cost of the response
            tool_uses: List of tools used

        Returns:
            Message ID
        """
        conv_id = conversation_id or self._current_conversation_id
        if not conv_id:
            conv_id = self.get_or_create_conversation()

        message_id = str(uuid.uuid4())

        conn = get_db_connection()
        cursor = conn.cursor()

        tool_uses_json = json.dumps(tool_uses) if tool_uses else None

        cursor.execute(
            """
            INSERT INTO chat_messages
            (id, conversation_id, role, content, model, complexity, cost_usd, tool_uses, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conv_id,
                role,
                content,
                model,
                complexity,
                cost_usd,
                tool_uses_json,
                datetime.now().isoformat(),
            ),
        )

        # Update conversation timestamp
        cursor.execute(
            "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), conv_id),
        )

        # Auto-set title from first user message if not set
        cursor.execute(
            "SELECT title FROM chat_conversations WHERE id = ?",
            (conv_id,),
        )
        row = cursor.fetchone()
        if row and not row["title"] and role == "user":
            # Use first 50 chars as title
            title = content[:50] + ("..." if len(content) > 50 else "")
            cursor.execute(
                "UPDATE chat_conversations SET title = ? WHERE id = ?",
                (title, conv_id),
            )

        conn.commit()
        conn.close()

        return message_id

    async def send_message(
        self,
        message: str,
        conversation_id: str | None = None,
        stream: bool = False,
    ) -> dict:
        """
        Send a message and get a response from DexAI.

        Uses SessionManager to maintain conversation context across messages.
        The same session is reused for all messages in a conversation, allowing
        Claude to remember previous context.

        Args:
            message: User message to send
            conversation_id: Conversation ID to continue
            stream: Whether to stream the response

        Returns:
            Response dict with text, model, complexity, cost_usd
        """
        # Get or create conversation
        conv_id = self.get_or_create_conversation(conversation_id)

        # Save user message
        self.save_message(role="user", content=message, conversation_id=conv_id)

        try:
            # Use SessionManager to maintain conversation context
            from tools.channels.session_manager import get_session_manager

            manager = get_session_manager()

            # Use conversation_id as part of session key for web chat
            # This ensures each conversation maintains its own context
            session_user_id = f"web:{self.user_id}:{conv_id}"

            result = await manager.handle_message(
                user_id=session_user_id,
                channel="web",
                content=message,
            )

            # Clear any pending generated images — web chat doesn't use the
            # thread-local image delivery mechanism (that's for channel adapters).
            try:
                from tools.agent.mcp.channel_tools import get_pending_image, clear_pending_image
                if get_pending_image():
                    clear_pending_image()
            except ImportError:
                pass

            if result.get("success"):
                # Save assistant response
                self.save_message(
                    role="assistant",
                    content=result.get("content", ""),
                    conversation_id=conv_id,
                    model=result.get("model"),
                    complexity=result.get("complexity"),
                    cost_usd=result.get("cost_usd", 0.0),
                    tool_uses=result.get("tool_uses", []),
                )

                return {
                    "conversation_id": conv_id,
                    "message_id": str(uuid.uuid4()),
                    "content": result.get("content", ""),
                    "role": "assistant",
                    "model": result.get("model"),
                    "complexity": result.get("complexity"),
                    "cost_usd": result.get("cost_usd", 0.0),
                    "tool_uses": result.get("tool_uses", []),
                }
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"Session query failed: {error_msg}")

                error_response = f"I encountered an error: {error_msg}"
                self.save_message(
                    role="assistant",
                    content=error_response,
                    conversation_id=conv_id,
                )

                return {
                    "conversation_id": conv_id,
                    "message_id": str(uuid.uuid4()),
                    "content": error_response,
                    "role": "assistant",
                    "model": None,
                    "complexity": None,
                    "cost_usd": 0.0,
                    "tool_uses": [],
                    "error": error_msg,
                }

        except ImportError as e:
            logger.warning(f"SessionManager not available: {e}")
            # Fallback response when SDK not available
            fallback_response = (
                "I'm sorry, but I'm currently unable to process your request. "
                "The AI service is temporarily unavailable. Please try again later."
            )

            self.save_message(
                role="assistant",
                content=fallback_response,
                conversation_id=conv_id,
            )

            return {
                "conversation_id": conv_id,
                "message_id": str(uuid.uuid4()),
                "content": fallback_response,
                "role": "assistant",
                "model": None,
                "complexity": None,
                "cost_usd": 0.0,
                "tool_uses": [],
                "error": "SDK not available",
            }

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            import traceback
            traceback.print_exc()
            error_response = f"I encountered an error: {str(e)}"

            self.save_message(
                role="assistant",
                content=error_response,
                conversation_id=conv_id,
            )

            return {
                "conversation_id": conv_id,
                "message_id": str(uuid.uuid4()),
                "content": error_response,
                "role": "assistant",
                "model": None,
                "complexity": None,
                "cost_usd": 0.0,
                "tool_uses": [],
                "error": str(e),
            }

    async def stream_message(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """
        Stream a response from DexAI.

        Uses SessionManager to maintain conversation context.

        Args:
            message: User message to send
            conversation_id: Conversation ID to continue

        Yields:
            Dicts with type ('chunk' or 'done') and content/metadata
        """
        conv_id = self.get_or_create_conversation(conversation_id)

        # Save user message
        self.save_message(role="user", content=message, conversation_id=conv_id)

        try:
            from tools.channels.session_manager import get_session_manager
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

            manager = get_session_manager()

            # Use conversation_id as part of session key for web chat
            session_user_id = f"web:{self.user_id}:{conv_id}"

            full_response = []
            tool_uses = []
            cost_usd = 0.0
            model = None
            complexity = None

            async for msg in manager.stream_message(
                user_id=session_user_id,
                channel="web",
                content=message,
            ):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            full_response.append(block.text)
                            yield {
                                "type": "chunk",
                                "content": block.text,
                                "conversation_id": conv_id,
                            }
                elif isinstance(msg, ResultMessage):
                    if hasattr(msg, "total_cost_usd"):
                        cost_usd = msg.total_cost_usd or 0.0
                    break

            # Clear any pending generated images (same as send_message)
            try:
                from tools.agent.mcp.channel_tools import get_pending_image, clear_pending_image
                if get_pending_image():
                    clear_pending_image()
            except ImportError:
                pass

            # Save complete response
            response_text = "".join(full_response)
            self.save_message(
                role="assistant",
                content=response_text,
                conversation_id=conv_id,
                model=model,
                complexity=complexity,
                cost_usd=cost_usd,
                tool_uses=tool_uses,
            )

            yield {
                "type": "done",
                "conversation_id": conv_id,
                "model": model,
                "complexity": complexity,
                "cost_usd": cost_usd,
            }

        except ImportError:
            fallback = "AI service temporarily unavailable."
            self.save_message(role="assistant", content=fallback, conversation_id=conv_id)
            yield {"type": "chunk", "content": fallback, "conversation_id": conv_id}
            yield {"type": "done", "conversation_id": conv_id, "error": "SDK not available"}

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.save_message(role="assistant", content=error_msg, conversation_id=conv_id)
            yield {"type": "chunk", "content": error_msg, "conversation_id": conv_id}
            yield {"type": "done", "conversation_id": conv_id, "error": str(e)}

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation and all its messages.

        Args:
            conversation_id: Conversation to delete

        Returns:
            True if deleted, False if not found
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check ownership
        cursor.execute(
            "SELECT id FROM chat_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, self.user_id),
        )
        if not cursor.fetchone():
            conn.close()
            return False

        # Delete messages first (foreign key)
        cursor.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )

        # Delete conversation
        cursor.execute(
            "DELETE FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        )

        conn.commit()
        conn.close()
        return True
