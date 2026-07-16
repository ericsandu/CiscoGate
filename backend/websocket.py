import asyncio
import time
from typing import Dict, Optional

from fastapi import WebSocket

from llm_client import translate_and_learn_command
from translation_trie import TranslationTrie


class TokenBucket:
    """A simple token bucket for rate limiting LLM requests to prevent abuse."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_updated = time.time()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.time()
        self.tokens += (now - self.last_updated) * self.rate
        if self.tokens > self.capacity:
            self.tokens = self.capacity
        self.last_updated = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class ClientSession:
    def __init__(self, ws: WebSocket, preferred_syntax: str, role: str):
        self.ws = ws
        self.preferred_syntax = preferred_syntax
        self.role = role
        self.current_mode = "exec"
        self.proxy_id: Optional[str] = None
        self.device_os: Optional[str] = None

        # Guardrail: Limit LLM fallback to 5 requests per minute
        self.llm_rate_limiter = TokenBucket(rate=5.0 / 60.0, capacity=5.0)


class ConnectionManager:
    def __init__(self):
        # Maps session_id (frontend) to ClientSession state
        self.active_clients: Dict[str, ClientSession] = {}
        # Maps proxy_id to Proxy WebSocket
        self.active_proxies: Dict[str, WebSocket] = {}

    async def connect_frontend(
        self, ws: WebSocket, session_id: str, preferred_syntax: str, role: str
    ):
        await ws.accept()
        self.active_clients[session_id] = ClientSession(ws, preferred_syntax, role)

    async def connect_proxy(self, ws: WebSocket, proxy_id: str):
        await ws.accept()
        self.active_proxies[proxy_id] = ws

    def disconnect_frontend(self, session_id: str):
        if session_id in self.active_clients:
            del self.active_clients[session_id]

    def disconnect_proxy(self, proxy_id: str):
        if proxy_id in self.active_proxies:
            del self.active_proxies[proxy_id]

    async def send_to_frontend(self, session_id: str, message: dict):
        if session_id in self.active_clients:
            await self.active_clients[session_id].ws.send_json(message)

    async def send_to_proxy(self, proxy_id: str, message: dict):
        if proxy_id in self.active_proxies:
            await self.active_proxies[proxy_id].send_json(message)

    async def handle_frontend_message(
        self,
        session_id: str,
        message: dict,
        cisco_trie: TranslationTrie,
        forti_trie: TranslationTrie,
    ):
        """
        Handles incoming JSON commands from the frontend UI.
        """
        session = self.active_clients.get(session_id)
        if not session:
            return

        action = message.get("action")
        command = message.get("command", "")

        # ---------------------------------------------------------
        # COMMAND EXECUTION ROUTING
        # ---------------------------------------------------------
        if action == "execute_command":
            # 1. Determine Bidirectional Mode
            if session.preferred_syntax == session.device_os:
                # Passthrough Mode (No translation needed)
                translated_cmd = command
            else:
                # Translation Mode
                forward_trie = (
                    cisco_trie
                    if session.preferred_syntax == "cisco_ios"
                    else forti_trie
                )

                try:
                    translated_cmd, new_mode = forward_trie.translate_command(
                        command, session.current_mode, session.role
                    )
                    session.current_mode = new_mode
                except Exception as e:
                    # Zero-Cost Guardrail: Command not in dictionary. Prompt user for LLM.
                    await self.send_to_frontend(
                        session_id,
                        {
                            "action": "cli_prompt",
                            "data": f"Command not found. Error: {str(e)}\n[1] Query AI Engine  [2] Cancel",
                        },
                    )
                    return

            # 2. Route to Proxy (Tier 3)
            # Note: For Direct Connect, this logic would branch to the imported SSHBridge module instead.
            if session.proxy_id and session.proxy_id in self.active_proxies:
                await self.send_to_proxy(
                    session.proxy_id, {"action": "execute", "command": translated_cmd}
                )
            else:
                await self.send_to_frontend(
                    session_id,
                    {
                        "action": "stream_output",
                        "data": "\nError: No active proxy connection established.",
                    },
                )

        # ---------------------------------------------------------
        # LLM AI FALLBACK
        # ---------------------------------------------------------
        elif action == "prompt_llm":
            # Rate limiting guardrail
            if not session.llm_rate_limiter.consume(1.0):
                await self.send_to_frontend(
                    session_id,
                    {
                        "action": "stream_output",
                        "data": "\nRate limit exceeded. Please wait before querying AI again.",
                    },
                )
                return

            forward_trie = (
                cisco_trie if session.preferred_syntax == "cisco_ios" else forti_trie
            )
            reverse_trie = (
                forti_trie if session.preferred_syntax == "cisco_ios" else cisco_trie
            )
            target_os = (
                "fortios" if session.preferred_syntax == "cisco_ios" else "cisco_ios"
            )

            await self.send_to_frontend(
                session_id,
                {
                    "action": "stream_output",
                    "data": "\nQuerying AI translation engine...\n",
                },
            )

            try:
                # Offload the blocking LLM network call to a separate thread
                # so we don't freeze the async WebSocket event loop.
                translated_cmd = await asyncio.to_thread(
                    translate_and_learn_command,
                    command,
                    session.preferred_syntax,
                    target_os,
                    session.role,
                    session.current_mode,
                    forward_trie,
                    reverse_trie,
                )

                # Persist the newly synced logic trees to disk
                forward_trie.to_json_file(
                    f"data/{session.preferred_syntax}_to_{target_os}.json"
                )
                reverse_trie.to_json_file(
                    f"data/{target_os}_to_{session.preferred_syntax}.json"
                )

                # Forward the freshly learned command to the proxy
                if session.proxy_id and session.proxy_id in self.active_proxies:
                    await self.send_to_proxy(
                        session.proxy_id,
                        {"action": "execute", "command": translated_cmd},
                    )
            except Exception as e:
                await self.send_to_frontend(
                    session_id,
                    {
                        "action": "stream_output",
                        "data": f"AI Translation Failed: {str(e)}\n",
                    },
                )


# Global instance to be imported by the FastAPI router
manager = ConnectionManager()
