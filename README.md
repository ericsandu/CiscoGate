# CiscoGate

**CiscoGate** is a unified network administration console and real-time translating SSH proxy. It allows network engineers to manage and configure multi-vendor networking equipment (e.g., Cisco iOS, FortiOS) using a single, unified CLI language syntax. 

Rather than learning the nuances of every vendor's CLI, you write commands in your preferred syntax, and CiscoGate transparently translates and streams them to the target device in real-time.

---

## 🏗️ Core Architecture & How It Works

CiscoGate is split into three primary components:

1. **Web Terminal (Frontend)**
   - Built with Vite, React/Vanilla JS, and `xterm.js`.
   - Provides a highly responsive, authentic terminal experience directly in the browser.
   - Handles connection state, local command history, cursor tracking, and sanitizes input to be shipped over WebSockets.

2. **Translation Engine (Backend)**
   - Built with FastAPI and Python.
   - Intercepts your CLI inputs and translates them into the target device's native language using a hybrid approach:
     - **Translation Trie:** A highly optimized data structure for instant, deterministic resolution of known, static commands (e.g., `show version` ↔ `get system status`).
     - **LLM Pipeline:** For complex commands with dynamic arguments, it routes the syntax through a Large Language Model (DeepSeek/LocalAI) to infer the correct translation structure.

3. **SSH Bridge (Proxy)**
   - A `netmiko`-based proxy execution script.
   - Deployed physically near or on the management network of the equipment.
   - Connects to the device, executes the translated commands, and streams the output (chunk-by-chunk) back to the frontend in true real-time.

### 🔒 Zero-Knowledge Translation (ZKT)
Security is a foundational pillar of CiscoGate. When handling commands with sensitive arguments (IP addresses, passwords, BGP ASNs), the backend translator *never* sees the raw data.
- The system extracts dynamic arguments into structural `<VAR>` tokens on the frontend.
- The variables are AES-GCM encrypted.
- The backend LLM translates the generic template (e.g., `execute ping <VAR>`).
- The Proxy receives the translated template and the encrypted variables, decrypts them locally, and constructs the final command string (e.g., `ping 8.8.8.8`) right before injecting it into the SSH channel.

---

## 🚀 Current State & Recent Milestones

During the latest development sessions, we have successfully:
- **Established the Core Pipeline:** End-to-end WebSocket communication from the Web Terminal to the FastAPI backend, and down to the Python proxy.
- **Implemented ZKT (Zero-Knowledge Translation):** Fine-tuned the `llm_client.py` prompts to reliably output sanitized `<VAR>` templates.
- **Built the Translation Trie:** For blazing fast local dictionary lookups.
- **Overhauled Live Streaming:** Rewrote the `ssh_bridge.py` proxy execution loop to use raw `write_channel()` and `read_channel()` chunking. Long-running commands like `ping` and `traceroute` now stream character-by-character back to the browser without timing out or hanging.
- **UI & Presentation:** Created polished demo materials, including a comprehensive LaTeX (`tikz`) architectural diagram showcasing the ZKT data flow.

---

## 📋 TODOs & Future Roadmap

As we continue to evolve CiscoGate, the following features are next on the docket:

- [ ] **Support for Additional Protocols:** Expand the proxy's reach beyond SSH to support Telnet (for legacy equipment), RESTCONF, and NETCONF.
- [ ] **Automatic Proxy Deployment:** Build a mechanism to seamlessly containerize and deploy the `local_proxy` script directly to customer premises, jump-servers, or Raspberry Pis with zero-touch configuration.
- [ ] **Live Language Switching:** Implement the ability for an engineer to change their "preferred input language" mid-session (e.g., swapping from Cisco iOS to FortiOS dynamically) without dropping the SSH connection.
- [ ] **Interactive Prompt Management:** Enhance the proxy streaming loop to intelligently detect and pause for intermediate interactive prompts (like the hidden password request when typing `enable`).
- [ ] **Expanded Vendor Dictionaries:** Grow the internal translation dictionaries and test suites to natively support Juniper Junos, Arista EOS, and Palo Alto PAN-OS.
