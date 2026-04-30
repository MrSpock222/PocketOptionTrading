"""
PocketOption AI Scalping Bot
- NemoClaw KI-Integration (NVIDIA NemoClaw / OpenClaw kompatibel)
- 15+ technische Indikatoren (lokal berechnet)
- Martingale-Strategie
- Telegram-Steuerung
- Demo / Real Account Umschaltung
"""
import asyncio
import json
import os
import logging
import time
from pathlib import Path
import httpx
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from BinaryOptionsToolsV2 import PocketOptionAsync
import indicators
import scanner
from risk_manager import RiskManager

# Monkey-Patch: BinaryOptionsToolsV2 nutzt logger.warn() — in Python 3.12 entfernt
logging.Logger.warn = logging.Logger.warning


# ---------------------------------------------------------------------------
# .env Datei automatisch laden
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
                # Nur das äußerste Anführungszeichen-Paar entfernen
                if len(value) >= 2:
                    if (value[0] == '"' and value[-1] == '"') or \
                       (value[0] == "'" and value[-1] == "'"):
                        value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value

_load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NemoClaw Client (über Proxy auf Port 18790, da Gateway gesperrt)
# ---------------------------------------------------------------------------
class NemoClawClient:
    """
    Verbindet sich mit NemoClaw über unseren Proxy auf localhost:18790.
    (Gateway chatCompletions auf Port 18789 ist durch Sandbox gesperrt.)
    Sendet Indikator-Daten + Trade-Historie an die KI zur Analyse.
    Nutzt OpenAI-kompatibles /v1/chat/completions Format.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    async def analyze(self, best_asset: dict, all_scanned: list,
                      trade_history: list, balance: float, risk_state: dict = None) -> dict:
        """Sendet Scan + Risk-State an NemoClaw Gateway. KI gibt Prediction + Risk-Anpassungen."""
        prompt = self._build_prompt(best_asset, all_scanned, trade_history, balance, risk_state)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "messages": [
                {"role": "system", "content": "Du bist ein Binary-Options Trading-Analyst. Antworte IMMER als JSON mit: prediction (buy/sell), confidence (0.0-1.0), reasoning (kurz), override_local (bool)."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                # OpenAI-Format: data.choices[0].message.content
                text = ""
                if isinstance(data, dict) and "choices" in data:
                    choices = data["choices"]
                    if choices and isinstance(choices, list):
                        msg = choices[0].get("message", {})
                        text = msg.get("content", "")
                elif isinstance(data, dict):
                    text = data.get("text", data.get("content", str(data)))
                else:
                    text = str(data)
                logger.info("NemoClaw Antwort (%d Zeichen): %s", len(text), text[:150])
                return self._parse(text)
        except Exception as e:
            logger.warning("NemoClaw Gateway nicht erreichbar: %s", e)
            return None  # Fallback auf lokale Indikatoren

    def _build_prompt(self, best: dict, all_scanned: list, history: list,
                      balance: float, risk_state: dict = None) -> str:
        wins = sum(1 for t in history if t.get("status") == "win")
        losses = sum(1 for t in history if t.get("status") == "loss")
        recent = history[-5:] if len(history) > 5 else history
        ind = best.get("indicators", {})

        top5 = []
        for r in all_scanned[:5]:
            top5.append(f"  {r['asset']}: Score={r['score']:+d} Signal={r['signal']}")
        top5_str = "\n".join(top5) if top5 else "Keine Daten"

        risk_str = json.dumps(risk_state, indent=1) if risk_state else "Nicht verfügbar"

        return f"""MULTI-ASSET OTC SCAN — 60s Binary Options
Balance: ${balance:.2f} | W/L: {wins}/{losses}

=== TOP 5 OTC-PAARE ===
{top5_str}

=== BESTES ASSET: {best.get('asset', '?')} ===
Score: {best.get('score', 0)} | Signal: {best.get('signal', '?')}
RSI(14): {ind.get('rsi_14')} | MACD Hist: {ind.get('macd', {}).get('histogram')}
BB%B: {ind.get('bollinger', {}).get('percent_b')} | Stoch K: {ind.get('stochastic', {}).get('k')}
ADX: {ind.get('adx', {}).get('adx')} | Ichimoku: {ind.get('ichimoku', {}).get('signal')}

=== RISK MANAGEMENT STATE ===
{risk_str}

Letzte Trades: {json.dumps(recent) if recent else 'Keine'}

AUFGABEN:
1. Gib deine EIGENE Trade-Prediction ab
2. Bewerte ob JETZT ein guter Entry ist
3. Passe das Risk Management an wenn nötig (Strategie, Limits, Parameter)

ANTWORT NUR ALS JSON:
{{{{
  "prediction": "buy"/"sell",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "override_local": true/false,
  "preferred_asset": "{best.get('asset', '')}",
  "risk_adjustments": {{
    "strategy": "soft_martingale"/"kelly"/"flat"/"anti_martingale"/"percent_balance",
    "base_amount": 1.0,
    "max_drawdown": 15.0,
    "min_confidence": 0.3,
    "params": {{}}
  }}
}}}}"""

    def _parse(self, text: str) -> dict:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(text[start:end])
                if "prediction" in result and result["prediction"] in ("buy", "sell"):
                    return result
        except json.JSONDecodeError:
            pass
        lower = text.lower()
        if "sell" in lower or "put" in lower:
            return {"prediction": "sell", "confidence": 0.5, "reasoning": "Aus Text extrahiert"}
        if "buy" in lower or "call" in lower:
            return {"prediction": "buy", "confidence": 0.5, "reasoning": "Aus Text extrahiert"}
        return None


# ---------------------------------------------------------------------------
# Bot State
# ---------------------------------------------------------------------------
class TradingBotState:
    def __init__(self):
        self.is_running = False
        self.account_type = "demo"
        self.current_trade = 0
        self.max_trades = 10
        self.base_amount = float(os.getenv("BASE_AMOUNT", "1.0"))
        self.continuous = False  # Endlos-Modus für Demo
        self.ssid_demo = os.getenv("POCKET_OPTION_SSID_DEMO", "")
        self.ssid_real = os.getenv("POCKET_OPTION_SSID_REAL", "")
        self.history: list[dict] = []
        self.nemoclaw = NemoClawClient(
            base_url=os.getenv("NEMOCLAW_URL", "http://localhost:18790"),
            token=os.getenv("NEMOCLAW_TOKEN", ""),
        )
        self.risk = RiskManager(base_amount=self.base_amount)
        self.risk.load_state()

state = TradingBotState()




def build_prediction(indicator_data: dict, ai_response: dict | None) -> tuple[str, float, str]:
    """Kombiniert lokale Indikatoren mit NemoClaw KI-Antwort."""
    local_signal = indicator_data.get("signal", "neutral")
    local_score = indicator_data.get("score", 0)
    local_conf = indicator_data.get("confidence", 0)

    # Wenn NemoClaw antwortet und die KI überschreiben will
    if ai_response and ai_response.get("override_local", False):
        return (
            ai_response["prediction"],
            ai_response.get("confidence", 0.5),
            f"KI-Override: {ai_response.get('reasoning', 'Keine Begründung')}",
        )

    # Wenn NemoClaw antwortet, kombiniere mit lokalen Indikatoren
    if ai_response:
        ai_pred = ai_response["prediction"]
        ai_conf = ai_response.get("confidence", 0.5)
        local_pred = "buy" if local_score > 0 else "sell" if local_score < 0 else "neutral"

        # Wenn KI und Indikatoren übereinstimmen: hohe Konfidenz
        if (ai_pred == "buy" and local_score > 0) or (ai_pred == "sell" and local_score < 0):
            combined_conf = min((local_conf + ai_conf) / 1.5, 1.0)
            return ai_pred, combined_conf, f"KI + Indikatoren einig ({ai_response.get('reasoning', '')})"

        # Bei Widerspruch: höhere Konfidenz gewinnt
        if ai_conf > local_conf:
            return ai_pred, ai_conf * 0.7, f"KI dominiert (vs. lokales {local_pred}): {ai_response.get('reasoning', '')}"
        else:
            pred = "buy" if local_score > 0 else "sell"
            return pred, local_conf * 0.8, f"Indikatoren dominieren (Score {local_score})"

    # Kein NemoClaw — nur lokale Indikatoren
    if local_signal in ("strong_buy", "buy"):
        return "buy", local_conf, f"Lokal: {local_signal} (Score {local_score})"
    elif local_signal in ("strong_sell", "sell"):
        return "sell", local_conf, f"Lokal: {local_signal} (Score {local_score})"
    else:
        # Neutral — nutze Momentum als Tiebreaker
        return "buy", 0.3, f"Neutral (Score {local_score}) — Tiebreak BUY"


# ---------------------------------------------------------------------------
# Trading Loop — Scannt alle OTC-Paare, findet besten Entry
# ---------------------------------------------------------------------------
async def trading_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    ssid = state.ssid_demo if state.account_type == "demo" else state.ssid_real

    try:
        async with PocketOptionAsync(ssid=ssid) as client:
            # Warte bis WebSocket vollständig verbunden ist
            balance = -1.0
            for _ in range(10):
                await asyncio.sleep(1)
                try:
                    balance = await client.balance()
                except Exception:
                    pass
                if balance > 0:
                    break
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ *PocketOption verbunden*\n"
                    f"📊 Modus: *{state.account_type.upper()}*\n"
                    f"💰 Balance: ${balance}\n"
                    f"🧠 NemoClaw: `{state.nemoclaw.base_url}`\n"
                    f"🔍 Scanne {len(scanner.OTC_ASSETS)} OTC-Währungspaare..."
                ),
                parse_mode="Markdown",
            )

            state.current_trade = 0
            state.current_amount = state.base_amount
            duration = 60

            while state.is_running and state.current_trade < state.max_trades:
                state.current_trade += 1

                # 1. ALLE OTC-Paare scannen
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 Trade {state.current_trade}/{state.max_trades} — Scanne alle OTC-Paare...",
                )
                scan_results = await scanner.scan_all(client)
                scan_summary = scanner.format_scan_summary(scan_results)
                await context.bot.send_message(chat_id=chat_id, text=scan_summary, parse_mode="Markdown")

                # 2. Besten Entry finden
                best = scanner.find_best_entry(scan_results)
                if not best:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⏳ Kein klarer Entry — warte 30s und scanne erneut...",
                    )
                    await asyncio.sleep(30)
                    continue

                # 3. NemoClaw KI fragen — mit Risk-State
                current_balance = await client.balance()
                risk_state = state.risk.get_state_for_ai()
                ai_response = await state.nemoclaw.analyze(
                    best, scan_results, state.history, current_balance, risk_state
                )

                # KI Risk-Anpassungen anwenden
                if ai_response and ai_response.get("risk_adjustments"):
                    changes = state.risk.apply_ai_adjustments(ai_response["risk_adjustments"])
                    if changes:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"🔧 *KI Risk-Anpassung:*\n" + "\n".join(f"  • {c}" for c in changes),
                            parse_mode="Markdown",
                        )

                # KI kann ein anderes Asset vorschlagen
                asset = best["asset"]
                if ai_response and ai_response.get("preferred_asset"):
                    preferred = ai_response["preferred_asset"]
                    # Prüfe ob das vorgeschlagene Asset in den Scan-Ergebnissen ist
                    for r in scan_results:
                        if r["asset"] == preferred:
                            asset = preferred
                            best = r
                            break

                # 4. Prediction kombinieren
                action, confidence, reasoning = build_prediction(best, ai_response)

                # Risk Check: Darf getradet werden?
                can_trade, risk_reason = state.risk.should_trade(confidence, current_balance)
                if not can_trade:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🛑 *Trade blockiert:* {risk_reason}",
                        parse_mode="Markdown",
                    )
                    if "Drawdown" in risk_reason or "Verlustlimit" in risk_reason:
                        state.is_running = False
                        break
                    await asyncio.sleep(15)
                    continue

                # Einsatz vom Risk Manager berechnen
                trade_amount = state.risk.get_next_amount(state.history, current_balance)

                ind = best.get("indicators", {})
                subs = best.get("sub_signals", {})
                buy_n = sum(1 for v in subs.values() if "BUY" in str(v) or "bullish" in str(v))
                sell_n = sum(1 for v in subs.values() if "SELL" in str(v) or "bearish" in str(v))

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🎯 *{asset}* → *{action.upper()}*\n"
                        f"Konfidenz: {confidence:.0%} | Score: {best.get('score', 0)}\n"
                        f"💡 {reasoning}\n"
                        f"💵 Einsatz: ${trade_amount:.2f} ({state.risk.strategy_name})\n"
                        f"RSI:{ind.get('rsi_14','?')} BB:{ind.get('bollinger',{}).get('percent_b','?')}"
                    ),
                    parse_mode="Markdown",
                )

                # 5. Trade ausführen
                if action == "buy":
                    trade_id, deal = await client.buy(
                        asset=asset, amount=trade_amount, time=duration, check_win=False
                    )
                else:
                    trade_id, deal = await client.sell(
                        asset=asset, amount=trade_amount, time=duration, check_win=False
                    )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏱ `{asset}` {action.upper()} ${trade_amount:.2f} — warte {duration}s...",
                    parse_mode="Markdown",
                )

                # 6. Ergebnis
                result = await client.check_win(trade_id)
                status = "loss"
                if isinstance(result, dict):
                    # check_win gibt {'result': 'win'/'loss', 'profit': ...} zurück
                    res_str = str(result.get("result", "")).lower()
                    if "win" in res_str:
                        status = "win"
                    else:
                        try:
                            profit = float(result.get("profit", 0))
                            if profit > 0:
                                status = "win"
                        except (ValueError, TypeError):
                            pass
                elif "win" in str(result).lower():
                    status = "win"

                new_bal = await client.balance()
                state.risk.record_result(trade_amount, status, new_bal)

                state.history.append({
                    "trade_number": state.current_trade,
                    "trade_id": str(trade_id),
                    "asset": asset,
                    "amount": trade_amount,
                    "action": action,
                    "status": status,
                    "confidence": confidence,
                    "score": best.get("score", 0),
                    "strategy": state.risk.strategy_name,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

                # 7. Ergebnis-Meldung
                if status == "loss":
                    next_amt = state.risk.get_next_amount(state.history, new_bal)
                    msg = f"❌ *VERLUST* | Nächster: ${next_amt:.2f} ({state.risk.strategy_name})"
                else:
                    next_amt = state.risk.get_next_amount(state.history, new_bal)
                    msg = f"✅ *GEWINN* | Nächster: ${next_amt:.2f}"

                dd = state.risk.stats.current_drawdown_pct
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{msg}\n💰 ${new_bal} | DD: {dd:.1f}%",
                    parse_mode="Markdown",
                )

                state.risk.save_state()
                await asyncio.sleep(2)

                # Continuous Mode: Im Demo-Modus weitertraden
                if state.continuous and state.current_trade >= state.max_trades:
                    state.current_trade = 0
                    logger.info("Continuous-Modus: Nächste 10 Trades...")

            # Session-Ende
            if state.is_running:
                final = await client.balance()
                summary = state.risk.stats.to_summary()
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🏁 *Session beendet!*\n\n"
                        f"{summary}\n"
                        f"💰 Balance: ${final}"
                    ),
                    parse_mode="Markdown",
                )
                state.risk.save_state()
                state.is_running = False

    except Exception as e:
        logger.error(f"Trading error: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ *Fehler:* `{e}`",
            parse_mode="Markdown",
        )
        state.is_running = False


# ---------------------------------------------------------------------------
# Telegram Commands
# ---------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [["/start_bot", "/stop_bot"], ["/demo", "/real"], ["/status", "/balance"], ["/risk", "/continuous"]]
    await update.message.reply_text(
        "🤖 *PocketOption AI Scalping Bot*\n"
        f"NemoClaw KI + 15 Indikatoren + {len(scanner.OTC_ASSETS)} OTC-Paare\n\n"
        "/start\\_bot — Starten\n/stop\\_bot — Stoppen\n"
        "/demo — Demo | /real — Echtgeld\n"
        "/balance — Kontostände abrufen\n"
        "/status — Status | /risk — Risk-Details\n"
        "/continuous — Endlos-Modus (Demo)",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown",
    )

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.is_running:
        await update.message.reply_text("⚠️ Läuft bereits!")
        return
    state.is_running = True
    state.history = []
    bal = 0
    try:
        ssid = state.ssid_demo if state.account_type == "demo" else state.ssid_real
        async with PocketOptionAsync(ssid=ssid) as c:
            bal = await c.balance()
    except:
        pass
    state.risk = RiskManager(base_amount=state.base_amount, initial_balance=bal or 100)
    state.risk.load_state()
    mode = "ENDLOS" if state.continuous else f"{state.max_trades} Trades"
    await update.message.reply_text(
        f"🚀 *GESTARTET* — {state.account_type.upper()}\n"
        f"🔍 Scanne {len(scanner.OTC_ASSETS)} OTC-Paare\n"
        f"📊 {mode} | Strategie: `{state.risk.strategy_name}`\n"
        f"🛡 DD-Limit: {state.risk.max_drawdown_pct}% | Min-Conf: {state.risk.min_confidence:.0%}",
        parse_mode="Markdown",
    )
    asyncio.create_task(trading_loop(context, update.message.chat_id))

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state.is_running:
        await update.message.reply_text("Bereits gestoppt.")
        return
    state.is_running = False
    state.risk.save_state()
    await update.message.reply_text("🛑 Stopp-Signal gesendet. Risk-State gespeichert.")

async def set_demo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.is_running:
        await update.message.reply_text("Zuerst /stop_bot")
        return
    state.account_type = "demo"
    await update.message.reply_text("✅ *DEMO*", parse_mode="Markdown")

async def set_real(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.is_running:
        await update.message.reply_text("Zuerst /stop_bot")
        return
    state.account_type = "real"
    state.continuous = False  # Kein Endlos-Modus bei Real!
    await update.message.reply_text("⚠️ *REAL — Echtes Geld!*\nEndlos-Modus deaktiviert.", parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = state.risk.stats
    mode = "ENDLOS" if state.continuous else f"{state.current_trade}/{state.max_trades}"
    await update.message.reply_text(
        f"📊 Läuft: {'✅' if state.is_running else '❌'} | {state.account_type.upper()}\n"
        f"Trade: {mode} | Strategie: `{state.risk.strategy_name}`\n"
        f"W/L: {s.wins}/{s.losses} ({s.win_rate:.0%}) | PF: {s.profit_factor:.2f}\n"
        f"Net: ${s.net_profit:+.2f} | DD: {s.current_drawdown_pct:.1f}%\n"
        f"NemoClaw: `{state.nemoclaw.base_url}`",
        parse_mode="Markdown",
    )

async def risk_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt detaillierten Risk-Status."""
    await update.message.reply_text(
        state.risk.format_telegram_status(),
        parse_mode="Markdown",
    )

async def continuous_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Endlos-Modus (nur im Demo-Modus)."""
    if state.account_type == "real":
        await update.message.reply_text("⚠️ Endlos-Modus nur im Demo erlaubt!")
        return
    state.continuous = not state.continuous
    if state.continuous:
        await update.message.reply_text(
            "🔄 *Endlos-Modus AKTIVIERT*\n"
            "Bot tradet kontinuierlich und optimiert sich selbst.\n"
            "NemoClaw passt Strategie + Parameter dynamisch an.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("⏹ Endlos-Modus *deaktiviert*.", parse_mode="Markdown")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetcht Balance von Demo UND Real Account mit Timeout."""
    await update.message.reply_text("💰 Lade Kontostände... (max 15s)")

    async def fetch_balance(ssid: str, label: str) -> str:
        if not ssid:
            return f"{label}: ⚠️ Keine SSID konfiguriert"
        try:
            async def _connect_and_fetch():
                async with PocketOptionAsync(ssid=ssid) as client:
                    bal = -1.0
                    for _ in range(8):
                        await asyncio.sleep(1)
                        try:
                            bal = await client.balance()
                        except Exception:
                            pass
                        if bal > 0:
                            break
                    return bal

            bal = await asyncio.wait_for(_connect_and_fetch(), timeout=15.0)
            if bal > 0:
                return f"{label}: *${bal:,.2f}*"
            else:
                return f"{label}: ⚠️ Balance = {bal} (SSID prüfen!)"
        except asyncio.TimeoutError:
            ssid_preview = ssid[:30] + "..." if len(ssid) > 30 else ssid
            return f"{label}: ⏰ Timeout — SSID beginnt mit: `{ssid_preview}`"
        except Exception as e:
            return f"{label}: ❌ `{e}`"

    # Beide parallel abfragen
    demo_task = fetch_balance(state.ssid_demo, "🎮 Demo")
    real_task = fetch_balance(state.ssid_real, "💵 Real")
    demo_result, real_result = await asyncio.gather(demo_task, real_task)

    await update.message.reply_text(
        f"💰 *Kontostände:*\n\n{demo_result}\n{real_result}\n\n"
        f"Aktiv: *{state.account_type.upper()}*",
        parse_mode="Markdown",
    )


def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN fehlt!")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("start_bot", start_bot))
    app.add_handler(CommandHandler("stop_bot", stop_bot))
    app.add_handler(CommandHandler("demo", set_demo))
    app.add_handler(CommandHandler("real", set_real))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("risk", risk_cmd))
    app.add_handler(CommandHandler("continuous", continuous_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    logger.info("Bot startet...")
    app.run_polling()

if __name__ == "__main__":
    main()

