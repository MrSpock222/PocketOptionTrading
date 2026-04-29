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
echo "[4/4] Erstelle .env Datei..."

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

# OpenClaw — läuft auf localhost, kein externer Server nötig!
OPENCLAW_URL="http://localhost:$GATEWAY_PORT"
OPENCLAW_TOKEN="$GATEWAY_TOKEN"
EOF
    echo "  ✅ .env erstellt: $ENV_FILE"
    echo ""
    echo "  ⚠️  Trage jetzt dein TELEGRAM_BOT_TOKEN und die SSIDs ein:"
    echo "     nano $ENV_FILE"
else
    echo "  .env existiert bereits. Übersprungen."
    echo "  Falls nötig, aktualisiere OPENCLAW_TOKEN auf: $GATEWAY_TOKEN"
fi

echo ""
echo "============================================="
echo " ✅ Setup abgeschlossen!"
echo "============================================="
echo ""
echo " Architektur auf diesem Server:"
echo ""
echo "   ┌──────────────────────────────┐"
echo "   │      Ubuntu Server           │"
echo "   │                              │"
echo "   │  ┌─────────┐  ┌──────────┐  │"
echo "   │  │ bot.py   │→→│ OpenClaw │  │"
echo "   │  │ (Trading)│  │ (KI)     │  │"
echo "   │  └────┬─────┘  └──────────┘  │"
echo "   │       │ localhost:$GATEWAY_PORT       │"
echo "   └───────┼──────────────────────┘"
echo "           │"
echo "    ┌──────┴───────┐"
echo "    │  Telegram     │"
echo "    │  + PocketOpt. │"
echo "    └──────────────┘"
echo ""
echo " Nächste Schritte:"
echo "   1. Trage Tokens ein:  nano $ENV_FILE"
echo "   2. Starte OpenClaw:   openclaw restart"
echo "   3. Starte den Bot:    cd $BOT_DIR && python3 bot.py"
echo ""
echo " Dein OpenClaw Gateway Token ist:"
echo "   $GATEWAY_TOKEN"
echo ""
echo " ⚠️  MERKE DIR DIESEN TOKEN — er steht auch in .env"
echo ""
