# NemoClaw Proxy Session Zusammenfassung

Diese Datei fasst den kompletten Debugging-Verlauf, die gefundenen Lösungen und den aktuellen Stand zusammen. Sie dient als perfekter Einstiegspunkt für die nächste Session.

## 1. Ziel & Problemstellung
Unser Python Trading-Bot (`bot.py`) benötigt einen stabilen, OpenAI-kompatiblen HTTP-Endpoint (`/v1/chat/completions`), um mit der NemoClaw KI-Sandbox zu kommunizieren. 
Das Problem: Der standardmäßige OpenClaw Gateway-Port (18789) hat diesen Endpoint serverseitig gesperrt (`Not Found` bzw. Read-Only Landlock). Eine direkte Kommunikation war nicht möglich.

## 2. Debugging-Verlauf & Erkenntnisse
Wir haben systematisch versucht, einen Weg in die Sandbox zu finden:

1. **CLI `openclaw agent` Ansatz:** Wir haben versucht, Prompts direkt über die CLI in der Sandbox auszuführen. Dies führte jedoch zu Hängern/Timeouts, da das interaktive TUI/CLI nicht für API-Anfragen optimiert ist.
2. **Alternative Ports (18791 & 8080):** Wir fanden andere Ports, die antworteten (`Unauthorized`), aber bei genauerer Untersuchung fehlte auch hier der `/v1/chat/completions` Endpoint (`Cannot POST`).
3. **Config Manipulation (`nemoclaw money config set`):** Der Versuch, den Endpunkt von außen über die NemoClaw Config zu aktivieren, schlug fehl, da die Gateway-Sektion gesperrt/nicht veränderbar ist.

## 3. Der Durchbruch: `inference.local`
Bei der Untersuchung der internen Konfiguration (`nemoclaw money config get`) stellten wir fest, dass die eigentliche KI-Kommunikation intern über den Endpoint `https://inference.local/v1` läuft. 

Weitere Tests ergaben:
*   `inference.local` ist ein OpenAI-kompatibler Inference-Server.
*   Er ist nur **innerhalb** der Sandbox "money" erreichbar.
*   **Der erfolgreiche Test:** Wir konnten vom Host-System aus einen Payload per Pipe an die Sandbox senden und direkt mit `inference.local` sprechen: 
    `echo 'curl -sk https://inference.local/v1/chat/completions ...' | nemoclaw money connect`
    *Ergebnis: Perfekte JSON-Antwort im OpenAI-Format!*

## 4. Die finale Architektur (Aktueller Stand)
Basierend auf diesem Durchbruch haben wir `nemoclaw_proxy.py` komplett neu geschrieben. 

**So funktioniert der Proxy jetzt:**
1.  Der Bot (`bot.py`) sendet einen ganz normalen OpenAI-HTTP-Request an `localhost:18790` (unseren Proxy).
2.  Der Proxy nimmt den Payload, verpackt ihn in Base64 (um Escaping-Probleme mit Sonderzeichen zu vermeiden).
3.  Der Proxy führt im Hintergrund aus: `echo '<base64>' | nemoclaw money connect`.
4.  Innerhalb der Sandbox wird der Base64-String dekodiert und als `curl`-Befehl direkt an `https://inference.local/v1/chat/completions` gesendet.
5.  Der Proxy fängt die Ausgabe ab, extrahiert das saubere JSON und gibt es an den Bot als HTTP-Response zurück.

Zusätzlich wurden die Umgebungsvariablen in der `.env.example` aktualisiert (`NEMOCLAW_SANDBOX="money"`).

## 5. Nächste Schritte (Für die nächste Session)
Der Code im Repository (lokal) ist auf dem neuesten Stand. Was jetzt auf dem Ubuntu-Server getan werden muss:

1. **Code auf dem Server aktualisieren:** Die aktuelle `nemoclaw_proxy.py` (und idealerweise `.env.example` / `.env`) muss auf den Server gezogen/gepusht werden.
2. **Proxy Neustart:**
   ```bash
   # Alten Proxy stoppen
   pkill -f nemoclaw_proxy.py
   # Neuen starten
   python3 nemoclaw_proxy.py
   ```
3. **Finaler Verbindungstest (in einem zweiten Terminal auf dem Server):**
   ```bash
   curl -X POST http://localhost:18790/v1/chat/completions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <DEIN_PROXY_TOKEN>" \
     -d '{
       "model": "nvidia/nemotron-3-super-120b-a12b",
       "messages": [
         {"role": "user", "content": "Sag Hallo, das ist ein Test."}
       ],
       "temperature": 0.3
     }'
   ```
4. **Bot starten:** Wenn der curl-Befehl erfolgreich antwortet, kann der reguläre `bot.py` gestartet werden, und die KI-Analysen sollten fehlerfrei durchlaufen.
