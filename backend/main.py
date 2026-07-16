import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from translation_trie import TranslationTrie
from websocket import manager

app = FastAPI(title="CiscoGate Backend")

# Ensure the dictionary data directory exists
os.makedirs("data", exist_ok=True)


# Helper to initialize blank dictionaries if they don't exist yet
def init_trie(filename: str) -> TranslationTrie:
    path = f"data/{filename}"
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"modes": {"exec": {}, "global_config": {}, "interface_config": {}}}, f
            )
    return TranslationTrie.from_json_file(path)


# Initialize the Dual-Tree Sync Dictionaries in memory
cisco_to_fortios = init_trie("cisco_ios_to_fortios.json")
fortios_to_cisco = init_trie("fortios_to_cisco_ios.json")

# ====================================================================
# 1. FRONTEND WEBSITE INTEGRATION (TODO)
# ====================================================================
# The Frontend Engineer will build the xterm.js UI in a /frontend folder.
# We will mount it statically here so this FastAPI server hosts the web app directly.
#
# from fastapi.staticfiles import StaticFiles
# from fastapi.responses import FileResponse
#
# app.mount("/static", StaticFiles(directory="../frontend"), name="static")
#
# @app.get("/")
# async def serve_frontend():
#     return FileResponse("../frontend/index.html")
# ====================================================================


# ====================================================================
# 2. WEBSOCKET RELAY ENDPOINTS
# ====================================================================


@app.websocket("/ws/frontend/{session_id}")
async def websocket_frontend(
    websocket: WebSocket, session_id: str, syntax: str, role: str
):
    """
    Endpoint for the Frontend Web UI to connect.
    Expects query params: ?syntax=cisco_ios&role=firewall
    """
    await manager.connect_frontend(
        websocket, session_id, preferred_syntax=syntax, role=role
    )
    try:
        while True:
            # 1. Receive JSON command payload from the user's browser
            data = await websocket.receive_json()

            # 2. The manager automatically translates the command
            # and relays it to the appropriate Proxy WebSocket!
            await manager.handle_frontend_message(
                session_id,
                data,
                cisco_trie=cisco_to_fortios,
                forti_trie=fortios_to_cisco,
            )
    except WebSocketDisconnect:
        manager.disconnect_frontend(session_id)


# ====================================================================
# 3. PROXY TIER INTEGRATION (TODO)
# ====================================================================
# The Proxy Engineer will build `proxy/local_proxy.py` and `proxy/ssh_bridge.py`.
# The local_proxy will use `netmiko` to connect to the target hardware,
# autodetect the `device_os`, and generate a secure `proxy_id`.
# 
# It will then dial out and establish a reverse tunnel to the endpoint below:
# ws://<backend_url>/ws/proxy/{proxy_id}?device_os={device_os}
#
# Once connected, it listens for {"action": "execute", "command": "..."} JSON payloads,
# executes them via Netmiko, and streams the raw terminal output back up the tunnel.
# ====================================================================

@app.websocket("/ws/proxy/{proxy_id}")
async def websocket_proxy(websocket: WebSocket, proxy_id: str, device_os: str):
    """
    Endpoint for the Python Local Proxy (or Direct Connect module)
    to connect from behind a firewall.
    Expects query param: ?device_os=fortios
    """
    await manager.connect_proxy(websocket, proxy_id)

    # When the proxy connects, find any frontends waiting for it
    # and update their state with the newly discovered OS!
    for sid, session in manager.active_clients.items():
        if session.proxy_id == proxy_id:
            session.device_os = device_os
            await manager.send_to_frontend(
                sid,
                {
                    "action": "stream_output",
                    "data": f"\n[System] Proxy {proxy_id} connected. Detected OS: {device_os}\n",
                },
            )

    try:
        while True:
            # 1. Receive raw terminal output string from the physical switch via the proxy
            data = await websocket.receive_json()

            # 2. Relay the raw text directly back to the frontend browser terminal
            for sid, session in manager.active_clients.items():
                if session.proxy_id == proxy_id:
                    await manager.send_to_frontend(sid, data)
    except WebSocketDisconnect:
        manager.disconnect_proxy(proxy_id)
        # Notify attached frontends that their proxy dropped
        for sid, session in manager.active_clients.items():
            if session.proxy_id == proxy_id:
                session.device_os = None
                await manager.send_to_frontend(
                    sid,
                    {
                        "action": "stream_output",
                        "data": "\n[System] Proxy connection lost.\n",
                    },
                )
