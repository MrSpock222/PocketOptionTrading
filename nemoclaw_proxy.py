"""
NemoClaw → OpenAI-kompatibler HTTP Proxy
=========================================
Da der OpenClaw Gateway chatCompletions Endpoint in der Sandbox
gesperrt ist, leiten wir Requests über die OpenClaw CLI weiter.

Architektur:
  Bot (httpx.post) → localhost:18790/v1/chat/completions
                    → dieser Proxy
                    → openclaw agent -m "..." (Subprocess)
                    → Antwort als OpenAI-JSON zurück

Start:
  python nemoclaw_proxy.py

Env-Variablen:
  NEMOCLAW_PROXY_PORT   — Port (default: 18790)
  NEMOCLAW_PROXY_TOKEN  — Bearer Token für Auth (default: leer = kein Auth)
  NEMOCLAW_AGENT        — Agent-Name (default: main)
  NEMOCLAW_SESSION_ID   — Session-ID für OpenClaw (default: trading-bot)
  NEMOCLAW_TIMEOUT      — Timeout in Sekunden für CLI (default: 120)
"""
import asyncio
import json
import logging
import os
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
AGENT_NAME = os.getenv("NEMOCLAW_AGENT", "main")
SESSION_ID = os.getenv("NEMOCLAW_SESSION_ID", "trading-bot")
CLI_TIMEOUT = int(os.getenv("NEMOCLAW_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# OpenClaw CLI Wrapper
# ---------------------------------------------------------------------------
async def call_openclaw(messages: list[dict], model: str = "",
                        temperature: float = 0.3) -> str:
    """
    Ruft OpenClaw über die CLI auf und gibt die Antwort als Text zurück.

    Versucht mehrere Methoden:
    1. openclaw agent --agent <name> --local -m "<prompt>"
    2. Falls das nicht verfügbar: nemoclaw exec openclaw agent ...
    3. Fallback: Direkter HTTP-Call an den Gateway (für den Fall,
       dass chatCompletions doch irgendwann aktiviert wird)
    """
    # Baue den vollständigen Prompt aus den Messages zusammen
    prompt_parts = []
    system_prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        elif role == "user":
            prompt_parts.append(content)
        elif role == "assistant":
            prompt_parts.append(f"[Assistant]: {content}")

    full_prompt = "\n\n".join(prompt_parts)
    if system_prompt:
        full_prompt = f"[System Instructions]: {system_prompt}\n\n{full_prompt}"

    # Methode 1: openclaw agent CLI
    result = await _try_openclaw_cli(full_prompt)
    if result:
        return result

    # Methode 2: nemoclaw exec
    result = await _try_nemoclaw_exec(full_prompt)
    if result:
        return result

    # Methode 3: Direkter HTTP-Call (Fallback)
    result = await _try_http_gateway(messages, model, temperature)
    if result:
        return result

    raise RuntimeError(
        "Alle NemoClaw-Kommunikationswege fehlgeschlagen. "
        "Prüfe ob OpenClaw/NemoClaw installiert und erreichbar ist."
    )


async def _try_openclaw_cli(prompt: str) -> str | None:
    """Versucht openclaw agent CLI."""
    cmd = [
        "openclaw", "agent",
        "--agent", AGENT_NAME,
        "--local",
        "-m", prompt,
        "--session-id", SESSION_ID,
    ]
    return await _run_subprocess(cmd, "openclaw CLI")


async def _try_nemoclaw_exec(prompt: str) -> str | None:
    """Versucht nemoclaw exec openclaw agent CLI."""
    cmd = [
        "nemoclaw", "exec", "--",
        "openclaw", "agent",
        "--agent", AGENT_NAME,
        "-m", prompt,
        "--session-id", SESSION_ID,
    ]
    return await _run_subprocess(cmd, "nemoclaw exec")


async def _run_subprocess(cmd: list[str], label: str) -> str | None:
    """Führt einen Subprocess aus und gibt stdout zurück."""
    try:
        logger.info("[%s] Starte: %s", label, " ".join(cmd[:4]) + "...")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CLI_TIMEOUT
        )
        if proc.returncode == 0 and stdout:
            text = stdout.decode("utf-8", errors="replace").strip()
            if text:
                logger.info("[%s] Erfolg (%d Zeichen)", label, len(text))
                return text
        if stderr:
            err = stderr.decode("utf-8", errors="replace").strip()
            logger.warning("[%s] stderr: %s", label, err[:200])
        return None
    except FileNotFoundError:
        logger.info("[%s] Nicht installiert/gefunden", label)
        return None
    except asyncio.TimeoutError:
        logger.warning("[%s] Timeout nach %ds", label, CLI_TIMEOUT)
        try:
            proc.kill()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.warning("[%s] Fehler: %s", label, e)
        return None


async def _try_http_gateway(messages: list[dict], model: str,
                            temperature: float) -> str | None:
    """Fallback: Versucht direkten HTTP-Call an den Gateway."""
    try:
        import httpx
    except ImportError:
        return None

    gateway_url = os.getenv("NEMOCLAW_GATEWAY_URL", "http://localhost:18789")
    gateway_token = os.getenv("NEMOCLAW_TOKEN", "")

    payload = {
        "model": model or "nvidia/nemotron-3-super-120b-a12b",
        "messages": messages,
        "temperature": temperature,
    }
    headers = {"Content-Type": "application/json"}
    if gateway_token:
        headers["Authorization"] = f"Bearer {gateway_token}"

    try:
        async with httpx.AsyncClient(timeout=CLI_TIMEOUT) as client:
            resp = await client.post(
                f"{gateway_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data:
                    text = data["choices"][0]["message"]["content"]
                    logger.info("[HTTP Gateway] Erfolg (%d Zeichen)", len(text))
                    return text
            logger.warning(
                "[HTTP Gateway] Status %d: %s", resp.status_code, resp.text[:200]
            )
            return None
    except Exception as e:
        logger.warning("[HTTP Gateway] Fehler: %s", e)
        return None


# ---------------------------------------------------------------------------
# HTTP Server (aiohttp — leichtgewichtig, keine FastAPI-Dependency nötig)
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
    model = body.get("model", "nvidia/nemotron-3-super-120b-a12b")
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

    # An NemoClaw weiterleiten
    try:
        content = await call_openclaw(messages, model, temperature)
    except RuntimeError as e:
        return web.json_response(
            {"error": {"message": str(e), "type": "server_error"}},
            status=502,
        )

    # OpenAI-kompatible Response
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
            "completion_tokens": len(content) // 4,
            "total_tokens": (sum(len(m.get("content", "")) for m in messages) + len(content)) // 4,
        },
    }

    logger.info("Response: %d Zeichen Content", len(content))
    return web.json_response(response)


async def handle_models(request):
    """GET /v1/models — Listet verfügbare Modelle."""
    from aiohttp import web
    return web.json_response({
        "object": "list",
        "data": [
            {
                "id": "nvidia/nemotron-3-super-120b-a12b",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "nvidia",
            }
        ],
    })


async def handle_health(request):
    """GET /health — Health-Check."""
    from aiohttp import web
    return web.json_response({"status": "ok", "proxy": "nemoclaw-proxy"})


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
    logger.info("  Endpoint: http://localhost:%d/v1/chat/completions", PROXY_PORT)
    logger.info("  Health:   http://localhost:%d/health", PROXY_PORT)
    logger.info("  Auth:     %s", "Bearer Token aktiv" if PROXY_TOKEN else "DEAKTIVIERT")
    logger.info("  Agent:    %s (Session: %s)", AGENT_NAME, SESSION_ID)
    logger.info("  Timeout:  %ds", CLI_TIMEOUT)
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
        logger.error("Oder füge 'aiohttp' zu requirements.txt hinzu")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════╗
║       NemoClaw → OpenAI Proxy Server             ║
╠══════════════════════════════════════════════════╣
║  Port:    {PROXY_PORT:<39}║
║  Auth:    {"Aktiv (Bearer Token)" if PROXY_TOKEN else "Deaktiviert":<39}║
║  Agent:   {AGENT_NAME:<39}║
║  Session: {SESSION_ID:<39}║
║  Timeout: {CLI_TIMEOUT}s{" " * (37 - len(str(CLI_TIMEOUT)))}║
╚══════════════════════════════════════════════════╝
""")
    asyncio.run(start_server())


if __name__ == "__main__":
    main()
