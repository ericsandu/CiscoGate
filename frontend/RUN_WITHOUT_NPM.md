# Rulează frontend-ul fără npm

Acest folder conține exact frontend-ul CiscoGate precompilat în `dist/`.
Nu modifică și nu include backend-ul.

1. Pornește backend-ul vechi pe portul 8000.
2. Deschide alt terminal în folderul `frontend`.
3. Activează mediul virtual în care ai instalat backend-ul, de exemplu:

   ```bash
   source ../backend/.venv/bin/activate
   ```

4. Pornește serverul frontend:

   ```bash
   python3 serve_frontend.py
   ```

5. Deschide `http://localhost:5173`.

`serve_frontend.py` servește doar fișierele web și redirecționează `/api` și `/ws`
către backend-ul existent de la `127.0.0.1:8000`.
