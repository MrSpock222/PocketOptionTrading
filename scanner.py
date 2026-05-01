"""
OTC Asset Scanner — Scannt alle OTC Währungspaare auf PocketOption
und findet den besten Entry-Point basierend auf Indikator-Analyse.
"""
import asyncio
import logging
import indicators

logger = logging.getLogger(__name__)

# Alle OTC Währungspaare auf PocketOption
OTC_ASSETS = [
    "EURUSD_otc", "EURGBP_otc", "EURJPY_otc", "EURCHF_otc", "EURAUD_otc",
    "EURCAD_otc", "EURNZD_otc",
    "GBPUSD_otc", "GBPJPY_otc", "GBPCHF_otc", "GBPAUD_otc", "GBPCAD_otc",
    "GBPNZD_otc",
    "USDJPY_otc", "USDCHF_otc", "USDCAD_otc",
    "AUDUSD_otc", "AUDCAD_otc", "AUDCHF_otc", "AUDJPY_otc", "AUDNZD_otc",
    "NZDUSD_otc", "NZDJPY_otc", "NZDCAD_otc", "NZDCHF_otc",
    "CADJPY_otc", "CADCHF_otc",
    "CHFJPY_otc",
]


def _candle_to_dict(c) -> dict:
    """Konvertiert eine Candle (egal ob dict, Objekt, oder Liste) in ein dict."""
    if isinstance(c, dict):
        return {
            "open": float(c.get("open", c.get("o", 0))),
            "high": float(c.get("high", c.get("h", 0))),
            "low": float(c.get("low", c.get("l", 0))),
            "close": float(c.get("close", c.get("c", 0))),
            "volume": float(c.get("volume", c.get("v", 0))),
        }
    # Objekt mit Attributen
    try:
        return {
            "open": float(getattr(c, "open", getattr(c, "o", 0))),
            "high": float(getattr(c, "high", getattr(c, "h", 0))),
            "low": float(getattr(c, "low", getattr(c, "l", 0))),
            "close": float(getattr(c, "close", getattr(c, "c", 0))),
            "volume": float(getattr(c, "volume", getattr(c, "v", 0))),
        }
    except Exception:
        # Liste/Tuple: [open, high, low, close, volume]
        if isinstance(c, (list, tuple)) and len(c) >= 4:
            return {
                "open": float(c[0]),
                "high": float(c[1]),
                "low": float(c[2]),
                "close": float(c[3]),
                "volume": float(c[4]) if len(c) > 4 else 0,
            }
        return {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}


async def get_candles(client, asset: str, count: int = 60) -> list[dict]:
    """Holt historische Candles für ein Asset. Probiert history() und get_candles()."""
    try:
        # Methode 1: history(asset, period)
        raw = await client.history(asset, 60)
        if raw and len(raw) > 0:
            candles = [_candle_to_dict(c) for c in raw[-count:]]
            # Prüfe ob Daten sinnvoll sind (nicht alles 0)
            valid = [c for c in candles if c["close"] > 0]
            if valid:
                return valid
    except Exception as e:
        logger.info(f"history() für {asset} fehlgeschlagen: {e}")

    try:
        # Methode 2: get_candles(asset, period, offset)
        raw = await client.get_candles(asset, 60, 3600)
        if raw and len(raw) > 0:
            candles = [_candle_to_dict(c) for c in raw[-count:]]
            valid = [c for c in candles if c["close"] > 0]
            if valid:
                return valid
    except Exception as e:
        logger.info(f"get_candles() für {asset} fehlgeschlagen: {e}")

    return []


async def scan_single(client, asset: str, weights: dict = None) -> dict | None:
    """Scannt ein einzelnes Asset und berechnet Indikatoren."""
    candles = await get_candles(client, asset)
    if len(candles) < 20:
        logger.info(f"{asset}: Nur {len(candles)} Candles — übersprungen")
        return None
    try:
        analysis = indicators.analyze_all(candles, weights=weights)
        return {
            "asset": asset,
            "signal": analysis["signal"],
            "score": analysis["score"],
            "confidence": analysis["confidence"],
            "indicators": analysis["indicators"],
            "sub_signals": analysis["sub_signals"],
        }
    except Exception as e:
        logger.warning(f"Analyse für {asset} fehlgeschlagen: {e}")
        return None


async def scan_all(client, max_concurrent: int = 5, weights: dict = None) -> list[dict]:
    """
    Scannt ALLE OTC-Paare parallel und gibt eine nach Score sortierte
    Liste zurück.
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def limited_scan(asset):
        async with sem:
            return await scan_single(client, asset, weights=weights)

    tasks = [limited_scan(a) for a in OTC_ASSETS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scanned = []
    errors = 0
    for r in results:
        if isinstance(r, dict) and r is not None:
            scanned.append(r)
        else:
            errors += 1

    if errors > 0:
        logger.info(f"Scanner: {len(scanned)} OK, {errors} fehlgeschlagen von {len(OTC_ASSETS)}")

    # Sortiere nach absolutem Score (stärkstes Signal zuerst)
    scanned.sort(key=lambda x: abs(x["score"]), reverse=True)
    return scanned


def find_best_entry(scan_results: list[dict]) -> dict | None:
    """Findet den besten Entry-Point aus den Scan-Ergebnissen.
    Gibt IMMER das beste Paar zurück — die KI entscheidet ob getradet wird."""
    if not scan_results:
        return None

    # Immer das Paar mit dem stärksten Signal nehmen
    return scan_results[0]


def format_scan_summary(results: list[dict], top_n: int = 5) -> str:
    """Formatiert die Top-N Scan-Ergebnisse für Telegram."""
    if not results:
        return "⚠️ Kein OTC-Paar konnte gescannt werden (API-Fehler — siehe Server-Log)"

    lines = [f"🔍 *{len(results)} Paare gescannt:*\n"]
    for r in results[:top_n]:
        score = r["score"]
        arrow = "🟢" if score > 0 else "🔴" if score < 0 else "⚪"
        direction = "BUY" if score > 0 else "SELL" if score < 0 else "FLAT"
        lines.append(
            f"{arrow} `{r['asset']:15s}` {direction:4s} Score:{score:+3d} "
            f"Conf:{r['confidence']:.0%}"
        )

    if len(results) > top_n:
        lines.append(f"\n... und {len(results) - top_n} weitere")

    return "\n".join(lines)
