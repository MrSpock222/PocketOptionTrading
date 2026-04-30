#!/bin/bash
# =============================================================================
# PocketOption AI Scalping Bot — Ubuntu Server Setup
# =============================================================================
# Alles läuft auf EINEM Server: OpenClaw + Trading Bot
#
#   1. OpenClaw Gateway konfigurieren
#   2. Trading-Analyst Skill installieren
#   3. Bot als systemd Service einrichten
#
# Verwendung:
#   chmod +x setup_ubuntu.sh
#   ./setup_ubuntu.sh
# =============================================================================

set -e

# ---------------------------------------------------------------------------
# Konfiguration — PASSE DIESE WERTE AN!
# ---------------------------------------------------------------------------
OPENCLAW_HOME="$HOME/.openclaw"
OPENCLAW_CONFIG="$OPENCLAW_HOME/openclaw.json"
OPENCLAW_SKILLS_DIR="$OPENCLAW_HOME/skills"
GATEWAY_PORT=18789

# Generiere automatisch einen Token, falls keiner angegeben
GATEWAY_TOKEN=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

# Wo liegt dieses Repo auf dem Server?
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$SCRIPT_DIR"

echo "============================================="
echo " PocketOption AI Bot — Server Setup"
echo " Alles läuft auf DIESEM Server (localhost)"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# 1. OpenClaw Gateway konfigurieren
# ---------------------------------------------------------------------------
echo "[1/4] Konfiguriere OpenClaw Gateway..."

if [ ! -d "$OPENCLAW_HOME" ]; then
    echo "  ⚠️  OpenClaw Verzeichnis nicht gefunden: $OPENCLAW_HOME"
    echo "  Installiere OpenClaw zuerst: https://openclaw.ai/docs/install"
    echo ""
fi

mkdir -p "$OPENCLAW_HOME"

if [ ! -f "$OPENCLAW_CONFIG" ]; then
    echo "  Erstelle Gateway-Konfiguration..."
    cat > "$OPENCLAW_CONFIG" << EOF
{
  "gateway": {
    "enabled": true,
    "port": $GATEWAY_PORT,
    "token": "$GATEWAY_TOKEN"
  }
}
EOF
    echo "  ✅ Konfiguration erstellt: $OPENCLAW_CONFIG"
else
    echo "  Konfiguration existiert bereits: $OPENCLAW_CONFIG"
    echo ""
    echo "  WICHTIG: Stelle sicher, dass 'gateway' aktiviert ist."
    echo "  Falls nicht, füge Folgendes manuell in die Datei ein:"
    echo ""
    echo '    "gateway": {'
    echo '      "enabled": true,'
    echo "      \"port\": $GATEWAY_PORT,"
    echo "      \"token\": \"DEIN_TOKEN\""
    echo '    }'
    echo ""
    echo "  Du kannst den existierenden Token behalten oder diesen"
    echo "  neu generierten verwenden: $GATEWAY_TOKEN"
fi

echo ""

# ---------------------------------------------------------------------------
# 2. Trading-Analyst Skill installieren
# ---------------------------------------------------------------------------
echo "[2/4] Installiere Trading-Analyst Skill..."

SKILL_DIR="$OPENCLAW_SKILLS_DIR/trading-analyst"
SKILL_SOURCE="$SCRIPT_DIR/skills/trading-analyst/SKILL.md"

mkdir -p "$SKILL_DIR"

if [ -f "$SKILL_SOURCE" ]; then
    cp "$SKILL_SOURCE" "$SKILL_DIR/SKILL.md"
    echo "  ✅ Skill installiert: $SKILL_DIR/SKILL.md"
else
    echo "  ⚠️  SKILL.md nicht gefunden unter: $SKILL_SOURCE"
    echo "  Kopiere die Datei manuell nach: $SKILL_DIR/"
fi

echo ""

# ---------------------------------------------------------------------------
# 3. Python Dependencies installieren
# ---------------------------------------------------------------------------
echo "[3/4] Installiere Python-Abhängigkeiten..."

if [ -f "$BOT_DIR/requirements.txt" ]; then
    pip3 install -r "$BOT_DIR/requirements.txt" 2>&1 | tail -5
    echo "  ✅ Dependencies installiert"
else
    echo "  ⚠️  requirements.txt nicht gefunden"
fi

echo ""

# ---------------------------------------------------------------------------
# 4. .env Datei erstellen
# ---------------------------------------------------------------------------
echo "[4/6] Erstelle .env Datei..."

PROXY_PORT=18790
PROXY_TOKEN=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))")
ENV_FILE="$BOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << EOF
# === PocketOption AI Scalping Bot ===
# Erstellt am: $(date)

# Telegram Bot Token (vom @BotFather)
TELEGRAM_BOT_TOKEN="HIER_DEIN_TELEGRAM_TOKEN"

# PocketOption Session IDs (aus Browser-Cookies)
POCKET_OPTION_SSID_DEMO="HIER_DEINE_DEMO_SSID"
POCKET_OPTION_SSID_REAL="HIER_DEINE_REAL_SSID"

# NemoClaw Proxy (OpenAI-kompatibler Wrapper)
# Der Proxy leitet an OpenClaw CLI weiter (Gateway chatCompletions ist gesperrt)
NEMOCLAW_URL="http://localhost:$PROXY_PORT"
NEMOCLAW_TOKEN="$PROXY_TOKEN"

# Proxy-Server Konfiguration
NEMOCLAW_PROXY_PORT="$PROXY_PORT"
NEMOCLAW_PROXY_TOKEN="$PROXY_TOKEN"
NEMOCLAW_AGENT="main"
NEMOCLAW_SESSION_ID="trading-bot"
NEMOCLAW_TIMEOUT="120"

# Fallback: Direkter Gateway (falls chatCompletions doch aktiviert wird)
NEMOCLAW_GATEWAY_URL="http://localhost:$GATEWAY_PORT"
EOF
    echo "  ✅ .env erstellt: $ENV_FILE"
    echo ""
    echo "  ⚠️  Trage jetzt dein TELEGRAM_BOT_TOKEN und die SSIDs ein:"
    echo "     nano $ENV_FILE"
else
    echo "  .env existiert bereits. Übersprungen."
    echo "  Falls nötig, aktualisiere NEMOCLAW_PROXY_TOKEN auf: $PROXY_TOKEN"
fi

echo ""

# ---------------------------------------------------------------------------
# 5. NemoClaw Proxy als systemd Service einrichten
# ---------------------------------------------------------------------------
echo "[5/6] Richte NemoClaw Proxy Service ein..."

PROXY_SERVICE="/etc/systemd/system/nemoclaw-proxy.service"

if [ -f "$BOT_DIR/nemoclaw-proxy.service" ]; then
    # Service-Datei anpassen (WorkingDirectory + User)
    sed "s|/opt/pocketoption-bot|$BOT_DIR|g" "$BOT_DIR/nemoclaw-proxy.service" | \
    sed "s|User=%i|User=$(whoami)|g" > /tmp/nemoclaw-proxy.service

    if sudo cp /tmp/nemoclaw-proxy.service "$PROXY_SERVICE" 2>/dev/null; then
        sudo systemctl daemon-reload
        sudo systemctl enable nemoclaw-proxy
        echo "  ✅ Proxy-Service installiert und aktiviert"
        echo "  Starte mit: sudo systemctl start nemoclaw-proxy"
    else
        echo "  ⚠️  Konnte Service nicht installieren (sudo nötig)"
        echo "  Manuell starten: python3 $BOT_DIR/nemoclaw_proxy.py"
    fi
    rm -f /tmp/nemoclaw-proxy.service
else
    echo "  ⚠️  nemoclaw-proxy.service nicht gefunden"
    echo "  Manuell starten: python3 $BOT_DIR/nemoclaw_proxy.py"
fi

echo ""

# ---------------------------------------------------------------------------
# 6. Fertig
# ---------------------------------------------------------------------------
echo "[6/6] Fertig!"
echo ""
echo "============================================="
echo " ✅ Setup abgeschlossen!"
echo "============================================="
echo ""
echo " Architektur auf diesem Server:"
echo ""
echo "   ┌──────────────────────────────────────┐"
echo "   │          Ubuntu Server                │"
echo "   │                                       │"
echo "   │  ┌─────────┐   ┌────────────────┐    │"
echo "   │  │ bot.py   │──→│ nemoclaw_proxy │    │"
echo "   │  │ (Trading)│   │ :$PROXY_PORT          │"
echo "   │  └────┬─────┘   └───────┬────────┘   │"
echo "   │       │                  │             │"
echo "   │       │          ┌───────▼────────┐   │"
echo "   │       │          │ OpenClaw CLI   │   │"
echo "   │       │          │ (Sandbox)      │   │"
echo "   │       │          └────────────────┘   │"
echo "   └───────┼───────────────────────────────┘"
echo "           │"
echo "    ┌──────┴───────┐"
echo "    │  Telegram     │"
echo "    │  + PocketOpt. │"
echo "    └──────────────┘"
echo ""
echo " Nächste Schritte:"
echo "   1. Trage Tokens ein:       nano $ENV_FILE"
echo "   2. Starte den Proxy:       sudo systemctl start nemoclaw-proxy"
echo "   3. Teste den Proxy:        curl http://localhost:$PROXY_PORT/health"
echo "   4. Starte den Bot:         cd $BOT_DIR && python3 bot.py"
echo ""
echo " Dein Proxy Token ist:"
echo "   $PROXY_TOKEN"
echo ""
echo " ⚠️  MERKE DIR DIESEN TOKEN — er steht auch in .env"
echo ""

