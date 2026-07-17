import asyncio
import json
import sys
import uuid
import websockets

from ssh_bridge import SSHBridge

# Backend URL - poți schimba localhost cu IP-ul/Domeniul real la Demo
BACKEND_HOST = "localhost:8000"


async def main():
    # 1. Datele echipamentului local (pot fi hardcodate pentru Demo sau citite din consolă)
    target_ip = input("Enter Switch/Router IP [default: 192.168.1.1]: ").strip() or "192.168.1.1"
    target_port = int(input("Enter SSH Port [default: 22]: ").strip() or "22")
    user = input("Enter SSH Username [default: admin]: ").strip() or "admin"
    password = input("Enter SSH Password: ").strip()

    # 2. Generăm un ID unic pentru acest Proxy
    proxy_id = str(uuid.uuid4())
    print(f"\n[LocalProxy] Proxy started!")
    print(f"[LocalProxy] Your PROXY ID is: {proxy_id}")
    print("-> Give this Proxy ID to the Frontend user to connect!\n")

    # 3. Ne conectăm mai întâi la echipamentul SSH ca să îi aflăm OS-ul (cisco_ios / fortinet)
    print("[LocalProxy] Initializing SSH session to detect device OS...")
    dummy_ws = None
    bridge = SSHBridge(
        target=target_ip,
        port=target_port,
        user=user,
        password=password,
        websocket=dummy_ws,
    )

    try:
        device_os = await asyncio.to_thread(bridge.connect)
    except Exception as e:
        print(f"[LocalProxy] Failed to connect to switch via SSH: {e}")
        return

    # 4. Ne conectăm la Backend-ul FastAPI pe WebSocket-ul definit de colegul tău în main.py
    # URL format: ws://localhost:8000/ws/proxy/{proxy_id}?device_os={device_os}
    uri = f"ws://{BACKEND_HOST}/ws/proxy/{proxy_id}?device_os={device_os}"
    print(f"[LocalProxy] Connecting to Cloud Backend at {uri}...")

    async with websockets.connect(uri) as websocket:
        print(f"[LocalProxy] Tunnel established with Cloud Backend!")
        # Anasăm WebSocket-ul deschis la instanța noastră de bridge
        bridge.websocket = websocket

        # 5. Pornim bucla care ascultă comenzi de la Backend
        await bridge.start_bridging_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[LocalProxy] Shutting down...")
        sys.exit(0)