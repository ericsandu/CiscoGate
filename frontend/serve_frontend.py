"""Frontend-only development server for CiscoGate.

Serves the prebuilt web UI and forwards only browser API/WebSocket traffic to the
existing backend at http://127.0.0.1:8000. It does not modify or replace backend
code.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

BACKEND_HTTP = "http://127.0.0.1:8000"
BACKEND_WS = "ws://127.0.0.1:8000"
DIST_DIR = Path(__file__).resolve().parent / "dist"

if not DIST_DIR.joinpath("index.html").exists():
    raise RuntimeError("Lipsește frontend/dist. Folosește arhiva frontend runnable completă.")

app = FastAPI(title="CiscoGate Frontend Server")


def _forward_http(method: str, url: str, body: bytes, content_type: str | None) -> tuple[int, bytes, dict[str, str]]:
    headers: dict[str, str] = {}
    if content_type:
        headers["Content-Type"] = content_type

    request = UrlRequest(url=url, data=body or None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            response_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"content-type", "cache-control"}
            }
            return response.status, response.read(), response_headers
    except HTTPError as error:
        response_headers = {
            key: value
            for key, value in error.headers.items()
            if key.lower() in {"content-type", "cache-control"}
        }
        return error.code, error.read(), response_headers
    except URLError as error:
        return 502, f"Backend indisponibil: {error.reason}".encode(), {"content-type": "text/plain; charset=utf-8"}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(path: str, request: Request) -> Response:
    query = request.url.query
    target = f"{BACKEND_HTTP}/api/{path}"
    if query:
        target += f"?{query}"

    status, content, headers = await asyncio.to_thread(
        _forward_http,
        request.method,
        target,
        await request.body(),
        request.headers.get("content-type"),
    )
    return Response(content=content, status_code=status, headers=headers)


@app.websocket("/ws/{path:path}")
async def proxy_websocket(browser_socket: WebSocket, path: str) -> None:
    await browser_socket.accept()
    query = browser_socket.url.query
    target = f"{BACKEND_WS}/ws/{path}"
    if query:
        target += f"?{query}"

    try:
        async with websockets.connect(target, max_size=None) as backend_socket:
            async def browser_to_backend() -> None:
                while True:
                    message = await browser_socket.receive()
                    message_type = message.get("type")
                    if message_type == "websocket.disconnect":
                        return
                    if message.get("text") is not None:
                        await backend_socket.send(message["text"])
                    elif message.get("bytes") is not None:
                        await backend_socket.send(message["bytes"])

            async def backend_to_browser() -> None:
                async for message in backend_socket:
                    if isinstance(message, bytes):
                        await browser_socket.send_bytes(message)
                    else:
                        await browser_socket.send_text(message)

            tasks = {
                asyncio.create_task(browser_to_backend()),
                asyncio.create_task(backend_to_browser()),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, return_exceptions=True)
            await asyncio.gather(*pending, return_exceptions=True)
    except (OSError, websockets.WebSocketException) as error:
        try:
            await browser_socket.send_json({
                "action": "connection_state",
                "status": "error",
                "message": f"Backend WebSocket indisponibil: {error}",
            })
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await browser_socket.close()
        except Exception:
            pass


# Must remain last so /api and /ws are matched before static files.
app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")


if __name__ == "__main__":
    print("CiscoGate frontend: http://localhost:5173")
    print("Backend așteptat la: http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=5173, log_level="info")
