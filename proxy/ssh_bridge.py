import asyncio
import base64
import hashlib
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from netmiko import ConnectHandler


class SSHBridge:
    def __init__(self, target, port, user, password, proxy_id, websocket=None):
        self.device = {
            "device_type": "autodetect",
            "host": target,
            "username": user,
            "password": password,
            "port": port,
        }
        self.proxy_id = proxy_id
        self.websocket = websocket
        self.net_connect = None

    def connect(self):
        """Stabilește conexiunea SSH cu echipamentul."""
        print(f"[SSHBridge] Connecting to switch at {self.device['host']}...")
        self.net_connect = ConnectHandler(**self.device)
        detected_os = self.net_connect.device_type
        
        # Normalize netmiko's specific OS types to our backend dictionary schemas
        detected_os_lower = detected_os.lower()
        if "cisco" in detected_os_lower:
            detected_os = "cisco_ios"
        elif "forti" in detected_os_lower:
            detected_os = "fortios"
            
        print(f"[SSHBridge] Successfully connected! Detected OS: {detected_os}")
        return detected_os

    def decrypt_vars(self, encrypted_vars):
        """Decriptează e2e_vars folosind AES-GCM și cheia derivată din SHA256(proxy_id)."""
        if not encrypted_vars:
            return ""
        try:
            # Derivăm cheia SHA-256 de 32 bytes din proxy_id
            key = hashlib.sha256(self.proxy_id.encode()).digest()

            # Decodificăm din Base64
            raw_data = base64.b64decode(encrypted_vars)

            # Primii 12 bytes reprezintă Initialization Vector (IV), iar restul e ciphertext-ul
            iv, ciphertext = raw_data[:12], raw_data[12:]

            # Decriptăm
            decrypted_bytes = AESGCM(key).decrypt(iv, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            print(f"[SSHBridge] Decryption error / fallback: {e}")
            # Fallback în caz că în dev/testing variabilele vin ca text simplu necriptat
            return str(encrypted_vars)

    def reconstruct_command(self, template, encrypted_vars):
        """Reconstruiește comanda prin decriptare și înlocuire în sloturile <VAR>."""
        decrypted_string = self.decrypt_vars(encrypted_vars)

        if template == "PASSTHROUGH" or not template:
            # În PASSTHROUGH, datele decriptate reprezintă comanda întreagă
            return decrypted_string

        # Încercăm să parsăm array-ul de variabile JSON decriptate
        try:
            variables = json.loads(decrypted_string)
            if not isinstance(variables, list):
                variables = [decrypted_string]
        except Exception:
            variables = [decrypted_string]

        # Înlocuim fiecare slot <VAR> cu valoarea corespunzătoare
        final_command = template
        for var in variables:
            final_command = final_command.replace("<VAR>", str(var), 1)

        return final_command

    async def start_bridging_loop(self):
        """Bucla asincronă care primește comenzi de la WebSocket, le decriptează și le execută."""
        try:
            async for message in self.websocket:
                msg = json.loads(message) if isinstance(message, str) else message

                action = msg.get("action")

                if action == "execute":
                    template = msg.get("template", "")
                    encrypted_vars = msg.get("e2e_vars")

                    # Decriptare AES-GCM & Reconstructie ZKT
                    final_command = self.reconstruct_command(template, encrypted_vars)

                    print(f"[SSHBridge] Executing command: {final_command}")

                    # Executăm pe router/switch
                    output = await asyncio.to_thread(
                        self.net_connect.send_command, final_command
                    )

                    # Trimitem output-ul înapoi
                    response_payload = {
                        "action": "stream_output",
                        "data": f"\n{output}\n",
                    }

                    await self.websocket.send(json.dumps(response_payload))

        except Exception as e:
            print(f"[SSHBridge] Error in bridging loop: {e}")
            error_payload = {
                "action": "stream_output",
                "data": f"\n[Proxy SSH Error]: {str(e)}\n",
            }
            await self.websocket.send(json.dumps(error_payload))
