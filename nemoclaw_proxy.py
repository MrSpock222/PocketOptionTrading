"""
NemoClaw → OpenAI-kompatibler HTTP Proxy
=========================================
Leitet Requests durch die NemoClaw Sandbox an den NVIDIA Inference Server.

Methode:
  Piped curl durch `nemoclaw money connect` — der einzige stabile Weg,
  da der Gateway chatCompletions gesperrt ist und der Inference-Server
  (inference.local) nur innerhalb der Sandbox erreichbar ist.

Architektur:
  Bot (httpx.post) → localhost:18790/v1/chat/completions
                    → dieser Proxy
                    → echo '...' | nemoclaw money connect
                    → curl -sk https://inference.local/v1/chat/completions
                    → OpenAI-JSON zurück

Start:
  python nemoclaw_proxy.py

Env-Variablen:
  NEMOCLAW_PROXY_PORT   — Port (default: 18790)
  NEMOCLAW_PROXY_TOKEN  — Bearer Token für Auth (default: leer = kein Auth)
  NEMOCLAW_SANDBOX      — Sandbox-Name (default: money)
  NEMOCLAW_TIMEOUT      — Timeout in Sekunden (default: 120)
  NEMOCLAW_MODEL        — Default-Modell (default: nvidia/nemotron-3-super-120b-a12b)
"""
import asyncio
import base64
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# .env laden (gleiche Logik wie bot.py)
# ---------------------------------------------------------------------------
def _load_dotenv(path: str = ".env"):
    env_path = Path(path)
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2:
                    if (value[0] == '"' and value[-1] == '"') or \
                       (value[0] == "'" and value[-1] == "'"):
                        value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value

_load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("nemoclaw-proxy")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROXY_PORT = int(os.getenv("NEMOCLAW_PROXY_PORT", "18790"))
PROXY_TOKEN = os.getenv("NEMOCLAW_PROXY_TOKEN", "")
SANDBOX_NAME = os.getenv("NEMOCLAW_SANDBOX", "money")
CLI_TIMEOUT = int(os.getenv("NEMOCLAW_TIMEOUT", "120"))
DEFAULT_MODEL = os.getenv("NEMOCLAW_MODEL", "nvidia/nemotron-3-super-120b-a12b")
INFERENCE_URL = "https://inference.local/v1/chat/completions"


# ---------------------------------------------------------------------------
# NemoClaw Sandbox Inference Call
# ---------------------------------------------------------------------------
async def call_inference(messages: list[dict], model: str = "",
                         temperature: float = 0.3) -> dict:
    """
    Sendet Request an den NVIDIA Inference Server DURCH die NemoClaw Sandbox.

    Methode: Piped curl durch `nemoclaw <sandbox> connect`
    - Base64-kodiert den Payload (vermeidet Escaping-Probleme)
    - Dekodiert in der Sandbox und piped an curl
    - Parst die JSON-Antwort aus dem Output
    """
    payload = json.dumps({
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
    })

    # Base64-Encoding verhindert Escaping-Probleme mit Quotes/Sonderzeichen
    payload_b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")

    # Sandbox-Befehl: Base64 dekodieren → an curl pipen
    sandbox_cmd = (
        f"echo '{payload_b64}' | base64 -d | "
        f"curl -sk {INFERENCE_URL} "
        f"-X POST -H 'Content-Type: application/json' -d @- "
        f"2>/dev/null && exit"
    )

    # Durch nemoclaw connect pipen
    shell_cmd = f"echo {_shell_quote(sandbox_cmd)} | nemoclaw {SANDBOX_NAME} connect"

    logger.info("Sende Request an Inference Server (model=%s, %d messages)", model or DEFAULT_MODEL, len(messages))

    try:
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CLI_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error("Timeout nach %ds", CLI_TIMEOUT)
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError(f"NemoClaw Sandbox Timeout nach {CLI_TIMEOUT}s")
    except Exception as e:
        logger.error("Subprocess-Fehler: %s", e)
        raise RuntimeError(f"NemoClaw Subprocess-Fehler: {e}")

    output = stdout.decode("utf-8", errors="replace")

    if stderr:
        err = stderr.decode("utf-8", errors="replace").strip()
        if err and "Connecting" not in err:
            logger.warning("stderr: %s", err[:300])

    # JSON aus dem Output extrahieren
    result = _extract_json(output)
    if result is None:
        logger.error("Keine JSON-Antwort gefunden. Output (%d Zeichen): %s", len(output), output[:500])
        raise RuntimeError("Keine gültige JSON-Antwort vom Inference Server erhalten")

    logger.info("Inference-Antwort erhalten (%d Zeichen)", len(json.dumps(result)))
    return result


def _shell_quote(s: str) -> str:
    """Shell-sicheres Quoting für den Befehl."""
    return "'" + s.replace("'", "'\\''") + "'"


def _extract_json(output: str) -> dict | None:
    """
    Extrahiert das erste vollständige JSON-Objekt aus dem Output.
    Der Output enthält Banner-Text, den Echo des Befehls, die JSON-Antwort und 'exit'.
    """
    # Strategie 1: Suche nach dem typischen OpenAI-Response-Start
    patterns = [
        r'\{"id":"chatcmpl-[^}]+.*?\}(?=\s*exit|\s*$)',  # chatcmpl response
        r'\{"id":".+?"choices":.+?\}',  # Generic OpenAI response
        r'\{"error":.+?\}',  # Error response
    ]

    # Strategie 2: Finde alle JSON-Objekte mit Brace-Matching
    depth = 0
    start = -1
    for i, ch in enumerate(output):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = output[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    # Prüfe ob es eine OpenAI-Response oder Error ist
                    if isinstance(parsed, dict) and ("choices" in parsed or "error" in parsed or "id" in parsed):
                        return parsed
                except json.JSONDecodeError:
                    continue
                start = -1

    # Strategie 3: Fallback — finde irgendeinen JSON-Block
    depth = 0
    start = -1
    for i, ch in enumerate(output):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = output[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                start = -1

    return None


# ---------------------------------------------------------------------------
# HTTP Server (aiohttp)
# ---------------------------------------------------------------------------
async def handle_chat_completions(request):
    """POST /v1/chat/completions — OpenAI-kompatibles Format."""
    from aiohttp import web

    # Auth prüfen
    if PROXY_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        expected = f"Bearer {PROXY_TOKEN}"
        if auth_header != expected:
            return web.json_response(
                {"error": {"message": "Unauthorized", "type": "auth_error"}},
                status=401,
            )

    # Request parsen
    try:
        body = await request.json()
    except Exception:
        return web.json_response(
            {"error": {"message": "Invalid JSON", "type": "invalid_request"}},
            status=400,
        )

    messages = body.get("messages", [])
    model = body.get("model", DEFAULT_MODEL)
    temperature = body.get("temperature", 0.3)

    if not messages:
        return web.json_response(
            {"error": {"message": "No messages provided", "type": "invalid_request"}},
            status=400,
        )

    logger.info(
        "Request: model=%s, %d messages, temp=%.1f",
        model, len(messages), temperature,
    )

    # An Inference Server weiterleiten (durch Sandbox)
    try:
        result = await call_inference(messages, model, temperature)
    except RuntimeError as e:
        return web.json_response(
            {"error": {"message": str(e), "type": "server_error"}},
            status=502,
        )

    # Die Inference-Antwort ist bereits im OpenAI-Format — direkt weiterleiten
    return web.json_response(result)


async def handle_models(request):
    """GET /v1/models — Listet verfügbare Modelle."""
    from aiohttp import web
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": DEFAULT_MODEL,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "nvidia",
            }
        ],
    })


async def handle_health(request):
    """GET /health — Health-Check."""
    from aiohttp import web
    return web.json_response({
        "status": "ok",
        "proxy": "nemoclaw-proxy",
        "sandbox": SANDBOX_NAME,
        "model": DEFAULT_MODEL,
    })


async def start_server():
    """Startet den aiohttp Server."""
    from aiohttp import web

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PROXY_PORT)
    await site.start()

    logger.info("=" * 60)
    logger.info("NemoClaw Proxy gestartet!")
    logger.info("  Endpoint:  http://localhost:%d/v1/chat/completions", PROXY_PORT)
    logger.info("  Health:    http://localhost:%d/health", PROXY_PORT)
    logger.info("  Auth:      %s", "Bearer Token aktiv" if PROXY_TOKEN else "DEAKTIVIERT")
    logger.info("  Sandbox:   %s", SANDBOX_NAME)
    logger.info("  Model:     %s", DEFAULT_MODEL)
    logger.info("  Inference: %s", INFERENCE_URL)
    logger.info("  Timeout:   %ds", CLI_TIMEOUT)
    logger.info("  Methode:   Piped curl durch nemoclaw connect")
    logger.info("=" * 60)

    # Laufe endlos
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Proxy wird beendet...")
        await runner.cleanup()


def main():
    """Entry point."""
    # Prüfe ob aiohttp installiert ist
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        logger.error("aiohttp nicht installiert! Installiere mit: pip install aiohttp")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════╗
║       NemoClaw → OpenAI Proxy Server                 ║
╠══════════════════════════════════════════════════════╣
║  Port:     {PROXY_PORT:<42}║
║  Auth:     {"Aktiv (Bearer Token)" if PROXY_TOKEN else "Deaktiviert":<42}║
║  Sandbox:  {SANDBOX_NAME:<42}║
║  Model:    {DEFAULT_MODEL:<42}║
║  Timeout:  {CLI_TIMEOUT}s{" " * (40 - len(str(CLI_TIMEOUT)))}║
║  Methode:  Piped curl → nemoclaw connect             ║
╚══════════════════════════════════════════════════════╝
""")
    asyncio.run(start_server())


if __name__ == "__main__":
    main()
