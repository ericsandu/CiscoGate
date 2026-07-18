import asyncio
import base64
import hashlib
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from netmiko import ConnectHandler, SSHDetect


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
        
        # Proper Netmiko autodetection workflow
        guesser = SSHDetect(**self.device)
        best_match = guesser.autodetect()
        print(f"[SSHBridge] Netmiko autodetected best match: {best_match}")
        
        if best_match:
            self.device["device_type"] = best_match
        else:
            # Fallback just in case
            self.device["device_type"] = "cisco_ios"
            best_match = "cisco_ios"
            
        self.net_connect = ConnectHandler(**self.device)
        detected_os = best_match
        
        # Normalize netmiko's specific OS types to our backend dictionary schemas
        detected_os_lower = detected_os.lower()
        if "cisco" in detected_os_lower:
            detected_os = "cisco_ios"
        elif "forti" in detected_os_lower:
            detected_os = "fortios"
            
        print(f"[SSHBridge] Successfully connected! Detected OS: {detected_os}")
        return detected_os

    def decrypt_vars(self, encrypted_vars):
        """Decriptează e2e_vars folosind AES-GCM și cheia derivată din PBKDF2."""
        if not encrypted_vars:
            return ""
        try:
            # Hash proxy_id exact cum se intampla pe frontend
            digest = hashlib.sha256(self.proxy_id.encode("utf-8")).digest()
            key = digest

            if isinstance(encrypted_vars, str):
                try:
                    encrypted_vars = json.loads(encrypted_vars)
                except Exception:
                    pass

            if isinstance(encrypted_vars, dict) and "iv" in encrypted_vars:
                iv = base64.b64decode(encrypted_vars["iv"])
                ciphertext = base64.b64decode(encrypted_vars["ciphertext"])
            else:
                # Decodificăm din Base64 (legacy format)
                raw_data = base64.b64decode(encrypted_vars)
                # Primii 12 bytes reprezintă Initialization Vector (IV), iar restul e ciphertext-ul
                iv, ciphertext = raw_data[:12], raw_data[12:]

            # Decriptăm
            decrypted_bytes = AESGCM(key).decrypt(iv, ciphertext, None)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            print(f"[SSHBridge] Decryption error / fallback: {e}")
            print(f"[SSHBridge] DEBUG encrypted_vars type: {type(encrypted_vars)}")
            print(f"[SSHBridge] DEBUG encrypted_vars: {encrypted_vars}")
            # Fallback în caz că în dev/testing variabilele vin ca text simplu necriptat
            return str(encrypted_vars)

    def reconstruct_command(self, template, encrypted_vars):
        """Reconstruiește comanda prin decriptare și înlocuire în sloturile <VAR>."""
        decrypted_string = self.decrypt_vars(encrypted_vars)

        if template == "PASSTHROUGH" or not template:
            # În PASSTHROUGH, datele decriptate reprezintă comanda întreagă
            # Frontendul le criptează prin JSON.stringify, așa că trebuie să folosim json.loads
            # pentru a scoate ghilimelele literale (ex: '"show ip route"' -> 'show ip route').
            try:
                parsed = json.loads(decrypted_string)
                if isinstance(parsed, str):
                    return parsed
            except Exception:
                pass
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

                    # Executăm pe router/switch cu streaming real-time
                    self.net_connect.write_channel(final_command + "\n")
                    
                    import time
                    start_time = time.time()
                    output_buffer = ""
                    
                    while True:
                        if time.time() - start_time > 120:
                            # Timeout de siguranță de 2 minute
                            break
                            
                        chunk = self.net_connect.read_channel()
                        if chunk:
                            output_buffer += chunk
                            # Stream back to frontend immediately
                            await self.websocket.send(json.dumps({
                                "action": "stream_chunk",
                                "data": chunk
                            }))
                            
                        # Verificăm dacă am primit prompt-ul de final
                        stripped_buffer = output_buffer.strip()
                        if stripped_buffer:
                            lines = stripped_buffer.split("\n")
                            last_line = lines[-1].strip()
                            
                            # Prompt-ul se termină mereu cu > sau #
                            # și conține hostname-ul (base_prompt)
                            if (last_line.endswith(">") or last_line.endswith("#")) and \
                               self.net_connect.base_prompt in last_line:
                                break
                                
                        await asyncio.sleep(0.1)
                        
                    # Notificăm frontend-ul că stream-ul s-a încheiat
                    await self.websocket.send(json.dumps({
                        "action": "stream_end"
                    }))

        except Exception as e:
            print(f"[SSHBridge] Error in bridging loop: {e}")
            error_payload = {
                "action": "stream_output",
                "data": f"\n[Proxy SSH Error]: {str(e)}\n",
            }
            await self.websocket.send(json.dumps(error_payload))
