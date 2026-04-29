# PocketOption Trading Bot

Ein asynchroner PocketOption AI Scalping Bot, gesteuert via Telegram.
Dieser Bot nutzt `BinaryOptionsTools-v2` von ChipaDevTeam für High-Performance Trading und simuliert die Analyse sowie dynamische Parameteranpassung via `OpenClaw` KI-Integration.

## Features
- **Telegram Interface:** Steuerung per Befehle (Start, Stop, Demo/Real Umschaltung) und Custom Keyboard.
- **Scalping & Martingale:** Führt 10 aufeinanderfolgende Trades aus. Geht ein Trade verloren, wird der Einsatz beim nächsten Trade verdoppelt (Martingale). Bei Gewinn wird der Einsatz auf das Basislevel zurückgesetzt.
- **AI Integration (OpenClaw Mock):** Nach jedem Trade werden Gewinne/Verluste von einer KI ("OpenClaw") analysiert, um die Vorhersage (Prediction) für den nächsten Trade anzupassen.
- **High-Performance:** Basiert auf der superschnellen Rust-Library `BinaryOptionsTools-v2` für WebSocket Handling und Trade-Ausführung.

## Installation

1. Erstelle eine virtuelle Python-Umgebung (empfohlen):
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   ```

2. Installiere die Abhängigkeiten:
   ```bash
   pip install -r requirements.txt
   ```

## Setup & Konfiguration

Der Bot benötigt einige Umgebungsvariablen (Environment Variables), um zu funktionieren:

- `TELEGRAM_BOT_TOKEN`: Das Token deines Telegram Bots (erhältst du vom [BotFather](https://t.me/botfather)).
- `POCKET_OPTION_SSID_DEMO`: Deine Session-ID (SSID) für den Demo-Account bei PocketOption.
- `POCKET_OPTION_SSID_REAL`: Deine Session-ID (SSID) für den Real-Account bei PocketOption.

### Wie bekomme ich die PocketOption SSID?
1. Melde dich bei PocketOption im Webbrowser an.
2. Öffne die Entwicklertools (F12) -> Tab "Netzwerk" (Network) oder "Anwendung" (Application -> Cookies).
3. Suche nach einem Websocket-Request (`wss://`) oder in den Cookies nach der Session ID. Diese wird für die API Authentifizierung via `BinaryOptionsToolsV2` benötigt.

## Ausführung

Starte den Bot mit:

```bash
python bot.py
```

Gehe dann in Telegram zu deinem Bot und sende `/start`, um das Steuerungs-Menü aufzurufen.

## Disclaimer & Risiko-Warnung
**Nutzung auf eigene Gefahr!**
Binary Options Trading beinhaltet ein extrem hohes Risiko, insbesondere wenn Strategien wie Martingale angewendet werden. Dieser Bot ist ein Proof-of-Concept. Der Autor oder die Entwickler der verwendeten Libraries übernehmen keinerlei Haftung für finanzielle Verluste. Teste den Bot immer zuerst im **DEMO**-Modus!