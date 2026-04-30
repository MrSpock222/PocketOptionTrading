# PocketOption Trading Bot

Ein asynchroner PocketOption AI Scalping Bot, gesteuert via Telegram.
Dieser Bot nutzt `BinaryOptionsTools-v2` von ChipaDevTeam für High-Performance Trading und `NemoClaw/OpenClaw` KI-Integration für intelligente Trade-Analyse.

## Features
- **NemoClaw KI-Integration:** Echtzeit-Analyse via NVIDIA Nemotron-3-Super-120B
- **Multi-Asset OTC Scanner:** Scannt 15+ OTC-Währungspaare gleichzeitig
- **15+ Technische Indikatoren:** RSI, MACD, Bollinger, Stochastic, ADX, Ichimoku, etc.
- **Dynamisches Risk Management:** Soft-Martingale, Kelly, Anti-Martingale, Flat — KI passt Strategie an
- **Telegram Interface:** Steuerung per Befehle (Start, Stop, Demo/Real, Continuous-Modus)
- **High-Performance:** Basiert auf der Rust-Library `BinaryOptionsTools-v2` für WebSocket-Trading

## Architektur

```
┌──────────────────────────────────────┐
│          Ubuntu Server                │
│                                       │
│  ┌─────────┐   ┌────────────────┐    │
│  │ bot.py   │──→│ nemoclaw_proxy │    │
│  │ (Trading)│   │ :18790         │    │
│  └────┬─────┘   └───────┬────────┘   │
│       │                  │             │
│       │          ┌───────▼────────┐   │
│       │          │ OpenClaw CLI   │   │
│       │          │ (Sandbox)      │   │
│       │          └────────────────┘   │
└───────┼───────────────────────────────┘
        │
 ┌──────┴───────┐
 │  Telegram     │
 │  + PocketOpt. │
 └──────────────┘
```

**Warum ein Proxy?** Der OpenClaw Gateway auf Port 18789 hat den `chatCompletions`-Endpoint durch Sandbox-Beschränkungen gesperrt. Unser `nemoclaw_proxy.py` umgeht das, indem er Requests über die OpenClaw CLI weiterleitet.

## Installation

### Lokal (Entwicklung)
```bash
python -m venv venv
source venv/bin/activate  # Linux
# .\\venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

### Server (Ubuntu)
```bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

## Konfiguration

Kopiere `.env.example` nach `.env` und trage deine Werte ein:

```bash
cp .env.example .env
nano .env
```

| Variable | Beschreibung |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token vom [@BotFather](https://t.me/botfather) |
| `POCKET_OPTION_SSID_DEMO` | Demo-Account Session-ID |
| `POCKET_OPTION_SSID_REAL` | Real-Account Session-ID |
| `NEMOCLAW_URL` | Proxy-URL (default: `http://localhost:18790`) |
| `NEMOCLAW_TOKEN` | Bearer Token für den Proxy |

## Ausführung

### 1. NemoClaw Proxy starten
```bash
# Als Service (empfohlen):
sudo systemctl start nemoclaw-proxy

# Oder manuell:
python nemoclaw_proxy.py
```

### 2. Bot starten
```bash
python bot.py
```

### 3. Telegram
Gehe zu deinem Bot und sende `/start`, um das Steuerungs-Menü aufzurufen.


## Disclaimer & Risiko-Warnung
**Nutzung auf eigene Gefahr!**
Binary Options Trading beinhaltet ein extrem hohes Risiko, insbesondere wenn Strategien wie Martingale angewendet werden. Dieser Bot ist ein Proof-of-Concept. Der Autor oder die Entwickler der verwendeten Libraries übernehmen keinerlei Haftung für finanzielle Verluste. Teste den Bot immer zuerst im **DEMO**-Modus!