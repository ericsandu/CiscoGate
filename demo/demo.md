# CiscoGate - Unprivileged Commands Demo

Acest document conține o listă de comenzi "unprivileged" (care pot fi rulate direct din modul de bază `>` sau `#` fără a necesita privilegii de configurare / enable mode). Acestea pot fi folosite pentru a testa traducerea și funcționalitatea streaming-ului proxy-ului.

## Testare din tab-ul Cisco iOS

Dacă aveți terminalul setat pe sintaxa **Cisco iOS** și doriți să controlați un echipament Fortinet, introduceți următoarele comenzi. Backend-ul (AI + Trie) le va traduce automat în formatul FortiOS.

| Comanda introdusă (Cisco) | Comanda tradusă (FortiOS) | Explicație |
| :--- | :--- | :--- |
| `show version` | `get system status` | Afișează informații generale despre sistem și versiune. |
| `show arp` | `get system arp` | Afișează tabela ARP. |
| `show clock` | `get system time` | Afișează ora și data curentă a sistemului. |
| `ping 8.8.8.8` | `execute ping 8.8.8.8` | Testează conectivitatea către 8.8.8.8 (folosește extragerea `<VAR>`). |
| `traceroute 8.8.8.8` | `execute traceroute 8.8.8.8` | Afișează ruta pachetelor către destinație. |
| `ssh -l admin 10.0.0.1` | `execute ssh admin@10.0.0.1` | Inițiază o conexiune SSH (folosește extragerea `<VAR>`). |

---

## Testare din tab-ul FortiOS

Dacă aveți terminalul setat pe sintaxa **FortiOS** și doriți să controlați un router/switch Cisco, introduceți următoarele comenzi. Acestea vor fi traduse automat în formatul Cisco iOS.

| Comanda introdusă (FortiOS) | Comanda tradusă (Cisco) | Explicație |
| :--- | :--- | :--- |
| `get system status` | `show version` | Afișează versiunea sistemului de operare. |
| `get system arp` | `show arp` | Listează tabela ARP a echipamentului. |
| `get system time` | `show clock` | Verifică ora configurată. |
| `execute ping 1.1.1.1` | `ping 1.1.1.1` | Pinging 1.1.1.1 pentru teste de rețea. |
| `execute traceroute 1.1.1.1` | `traceroute 1.1.1.1` | Identifică hop-urile până la 1.1.1.1. |
| `get hardware memory` | `show processes memory` | Verifică utilizarea memoriei. |
