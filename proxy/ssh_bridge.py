import asyncio
import json
from netmiko import ConnectHandler


class SSHBridge:

    def __init__(self, target, port, user, password, websocket):
        self.device = {
            "device_type": "autodetect",  # Netmiko va încerca să detecteze automat OS-ul (cisco_ios, fortinet etc.)
            "host": target,
            "username": user,
            "password": password,
            "port": port,
        }
        self.websocket = websocket
        self.net_connect = None

    def connect(self):
        """Stabilește conexiunea SSH cu echipamentul fizic/virtual."""
        print(f"[SSHBridge] Connecting to switch/router at {self.device['host']}...")
        self.net_connect = ConnectHandler(**self.device)
        detected_os = self.net_connect.device_type
        print(f"[SSHBridge] Successfully connected! Detected OS: {detected_os}")
        return detected_os

    async def start_bridging_loop(self):
        """Bucla asincronă care primește comenzi de la WebSocket,

        le execută pe switch și trimite răspunsul înapoi.
        """
        try:
            # Ascultăm mesajele primite de la backend pe WebSocket
            async for message in self.websocket:
                # Daca backend-ul trimite text JSON, îl parsăm (dacă e deja dict, îl folosim direct)
                msg = json.loads(message) if isinstance(message, str) else message

                action = msg.get("action")

                if action == "execute":
                    template = msg.get("template", "")
                    e2e_vars = msg.get("e2e_vars")

                    # Logica de comanda ZKT / Passthrough
                    if template == "PASSTHROUGH" or not template:
                        # Dacă e Passthrough sau simplu, comanda e direct în e2e_vars / template
                        final_command = (
                            e2e_vars if isinstance(e2e_vars, str) else template
                        )
                    else:
                        # Recompunerea comenzii din template
                        final_command = template

                    print(f"[SSHBridge] Executing command: {final_command}")

                    # 1. Executăm comanda pe switch (rulează în thread separat ca să nu blocheze asyncio)
                    output = await asyncio.to_thread(
                        self.net_connect.send_command, final_command
                    )

                    # 2. Trimitem răspunsul înapoi pe WebSocket la Backend
                    response_payload = {
                        "action": "stream_output",
                        "data": f"\n{output}\n",
                    }

                    # Librăria websockets suportă json.dumps
                    await self.websocket.send(json.dumps(response_payload))

        except Exception as e:
            print(f"[SSHBridge] Error in bridging loop: {e}")
            error_payload = {
                "action": "stream_output",
                "data": f"\n[Proxy SSH Error]: {str(e)}\n",
            }
            await self.websocket.send(json.dumps(error_payload))