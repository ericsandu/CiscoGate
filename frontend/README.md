# CiscoGate Frontend (Tier 1 only)

Acest folder conține strict partea de frontend. Nu include și nu modifică niciun fișier din `backend/` sau `proxy/`.

## Ce implementează

- formularul de conectare: sintaxă, rol, IP, port, utilizator, parolă și Proxy ID;
- terminal web bazat pe xterm.js;
- local echo, Backspace, Ctrl+C și istoric cu săgețile sus/jos;
- autocomplete local cu `?` și `Tab`;
- parsarea comenzilor folosind arborele primit de la backend;
- înlocuirea valorilor dinamice cu `<VAR>`;
- criptarea variabilelor cu AES-GCM înainte de transmitere;
- modul `PASSTHROUGH` când frontend-ul află că sintaxa preferată coincide cu OS-ul echipamentului;
- dialog pentru marcarea manuală a variabilelor într-o comandă necunoscută;
- tratarea mesajelor `stream_output`, `cli_prompt` și, opțional, `connection_state`.

## Rulare în dezvoltare

Backend-ul original trebuie să ruleze pe portul `8000`. În alt terminal:

```bash
cd frontend
npm install
npm run dev
```

Deschide apoi:

```text
http://localhost:5173
```

Vite redirecționează automat `/api` și `/ws` către backend-ul de pe `127.0.0.1:8000`.

## Contractul backend folosit

### Arbore de sintaxă

```http
GET /api/syntax-tree?syntax=cisco_ios
GET /api/syntax-tree?syntax=fortios
```

Frontend-ul elimină imediat câmpurile `_translate` și `_allowed_roles` și păstrează doar structura necesară pentru autocomplete și detectarea `<VAR>`.

### WebSocket

```text
/ws/frontend/{session_id}?syntax=cisco_ios&role=firewall
```

Mesajul inițial trimis de frontend:

```json
{
  "action": "connect",
  "proxy_id": "UUID sau șir gol",
  "target": "192.168.1.1",
  "port": 22,
  "user": "admin",
  "pass": "secret"
}
```

Comandă cunoscută:

```json
{
  "action": "execute_command",
  "template": "ping <VAR>",
  "e2e_vars": {
    "version": 1,
    "algorithm": "AES-GCM",
    "iv": "base64",
    "ciphertext": "base64"
  }
}
```

Fallback AI:

```json
{
  "action": "prompt_llm",
  "template": "show <VAR>",
  "e2e_vars": {}
}
```

## Limitări care aparțin backend-ului original

Frontend-ul trimite schema `connect`, însă versiunea originală a `backend/websocket.py` nu tratează încă acțiunea și nu setează `session.proxy_id`. Din acest motiv, execuția prin proxy nu poate fi completă până când taskul backend-ului implementează asocierea sesiunii cu Proxy ID-ul. Nu este necesară nicio modificare în frontend pentru acel pas.

Endpointul actual `/api/syntax-tree` trimite și valorile `_translate`. Frontend-ul le elimină din memorie, dar pentru ZKT real backend-ul ar trebui ulterior să servească un arbore syntax-only.

Direct Connect fără Proxy ID este menționat în arhitectură, dar nu este implementat în backend-ul original.

## Integrare în repository

Copiază folderul `frontend/` în rădăcina repository-ului CiscoGate. Pentru commitul tău poți include exclusiv:

```text
frontend/
```

Nu copia fișiere backend din alte pachete demonstrative.
