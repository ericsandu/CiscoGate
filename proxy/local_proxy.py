import asyncio
import sys
import uuid
import websockets

from ssh_bridge import SSHBridge

BACKEND_HOST = "localhost:8000"


async def main():
    target_ip = (
        input("Enter Switch/Router IP [default: 192.168.1.1]: ").strip()
        or "192.168.1.1"
    )
    target_port = int(input("Enter SSH Port [default: 22]: ").strip() or "22")
    user = input("Enter SSH Username [default: admin]: ").strip() or "admin"
    password = input("Enter SSH Password: ").strip()

    proxy_id = str(uuid.uuid4())
    print("\n[LocalProxy] Proxy started!")
    print(f"[LocalProxy] Your PROXY ID is: {proxy_id}")
    print("-> Give this Proxy ID to the Frontend user to connect!\n")

    print("[LocalProxy] Initializing SSH session to detect device OS...")

    # Transmitem proxy_id
    bridge = SSHBridge(
        target=target_ip,
        port=target_port,
        user=user,
        password=password,
        proxy_id=proxy_id,
        websocket=None,
    )

    try:
        device_os = await asyncio.to_thread(bridge.connect)
    except Exception as e:
        print(f"[LocalProxy] Failed to connect to switch via SSH: {e}")
        return

    uri = f"ws://{BACKEND_HOST}/ws/proxy/{proxy_id}?device_os={device_os}"
    print(f"[LocalProxy] Connecting to Cloud Backend at {uri}...")

    async with websockets.connect(uri) as websocket:
        print("[LocalProxy] Tunnel established with Cloud Backend!")
        bridge.websocket = websocket
        await bridge.start_bridging_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[LocalProxy] Shutting down...")
        sys.exit(0)
