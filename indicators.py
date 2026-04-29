"""
Technische Indikatoren Engine für Binary Options Scalping.
Berechnet alle relevanten Indikatoren aus Candlestick-Daten (OHLCV).
Keine externen Dependencies — alles in reinem Python mit math.
"""
import math
from typing import Optional


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def _sma(values: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            window = values[i - period + 1 : i + 1]
            result.append(sum(window) / period)
    return result


def _ema(values: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    result = []
    k = 2.0 / (period + 1)
    for i, v in enumerate(values):
        if i == 0:
            result.append(v)
        else:
            result.append(v * k + result[-1] * (1 - k))
    return result


def _std(values: list[float], period: int) -> list[float]:
    """Standardabweichung (Rolling)."""
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            window = values[i - period + 1 : i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            result.append(math.sqrt(variance))
    return result


def _true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    """True Range Berechnung."""
    tr = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return tr


# ---------------------------------------------------------------------------
# Haupt-Indikatoren
# ---------------------------------------------------------------------------
def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index (0-100). >70 = überkauft, <30 = überverkauft."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD Line, Signal Line, Histogram."""
    if len(closes) < slow + signal:
        return {"macd_line": None, "signal_line": None, "histogram": None}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return {"macd_line": macd_line[-1], "signal_line": signal_line[-1], "histogram": hist}


def bollinger_bands(closes: list[float], period: int = 20, num_std: float = 2.0) -> dict:
    """Bollinger Bands: upper, middle, lower, %B."""
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None, "percent_b": None}
    sma_vals = _sma(closes, period)
    std_vals = _std(closes, period)
    mid = sma_vals[-1]
    std_val = std_vals[-1]
    upper = mid + num_std * std_val
    lower = mid - num_std * std_val
    price = closes[-1]
    pct_b = (price - lower) / (upper - lower) if upper != lower else 0.5
    return {"upper": upper, "middle": mid, "lower": lower, "percent_b": pct_b}


def stochastic(highs: list[float], lows: list[float], closes: list[float],
               k_period: int = 14, d_period: int = 3) -> dict:
    """Stochastic Oscillator: %K und %D."""
    if len(closes) < k_period:
        return {"k": None, "d": None}
    k_values = []
    for i in range(k_period - 1, len(closes)):
        h = max(highs[i - k_period + 1 : i + 1])
        l = min(lows[i - k_period + 1 : i + 1])
        if h == l:
            k_values.append(50.0)
        else:
            k_values.append(100.0 * (closes[i] - l) / (h - l))
    d_values = _sma(k_values, d_period)
    return {"k": k_values[-1] if k_values else None, "d": d_values[-1] if d_values else None}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Optional[float]:
    """Average True Range — Volatilitäts-Indikator."""
    if len(closes) < period + 1:
        return None
    tr = _true_range(highs, lows, closes)
    atr_vals = _ema(tr, period)
    return atr_vals[-1]


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> dict:
    """Average Directional Index + DI+ / DI-. >25 = starker Trend."""
    if len(closes) < period * 2:
        return {"adx": None, "di_plus": None, "di_minus": None}
    plus_dm, minus_dm = [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr = _true_range(highs, lows, closes)[1:]
    sm_tr = _ema(tr, period)
    sm_plus = _ema(plus_dm, period)
    sm_minus = _ema(minus_dm, period)
    di_p = 100.0 * sm_plus[-1] / sm_tr[-1] if sm_tr[-1] != 0 else 0
    di_m = 100.0 * sm_minus[-1] / sm_tr[-1] if sm_tr[-1] != 0 else 0
    dx_sum = di_p + di_m
    dx = 100.0 * abs(di_p - di_m) / dx_sum if dx_sum != 0 else 0
    return {"adx": dx, "di_plus": di_p, "di_minus": di_m}


def cci(highs: list[float], lows: list[float], closes: list[float], period: int = 20) -> Optional[float]:
    """Commodity Channel Index. >100 = überkauft, <-100 = überverkauft."""
    if len(closes) < period:
        return None
    tp = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
    tp_window = tp[-period:]
    mean_tp = sum(tp_window) / period
    mean_dev = sum(abs(t - mean_tp) for t in tp_window) / period
    if mean_dev == 0:
        return 0.0
    return (tp[-1] - mean_tp) / (0.015 * mean_dev)


def williams_r(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> Optional[float]:
    """Williams %R (-100 bis 0). <-80 = überverkauft, >-20 = überkauft."""
    if len(closes) < period:
        return None
    h = max(highs[-period:])
    l = min(lows[-period:])
    if h == l:
        return -50.0
    return -100.0 * (h - closes[-1]) / (h - l)


def ichimoku(highs: list[float], lows: list[float], closes: list[float]) -> dict:
    """Ichimoku Cloud: Tenkan, Kijun, Senkou A/B."""
    def midpoint(h, l, p):
        if len(h) < p:
            return None
        return (max(h[-p:]) + min(l[-p:])) / 2.0
    tenkan = midpoint(highs, lows, 9)
    kijun = midpoint(highs, lows, 26)
    senkou_a = (tenkan + kijun) / 2.0 if tenkan and kijun else None
    senkou_b = midpoint(highs, lows, 52)
    price = closes[-1] if closes else None
    signal = "neutral"
    if senkou_a and senkou_b and price:
        cloud_top = max(senkou_a, senkou_b)
        cloud_bot = min(senkou_a, senkou_b)
        if price > cloud_top:
            signal = "bullish"
        elif price < cloud_bot:
            signal = "bearish"
    return {"tenkan": tenkan, "kijun": kijun, "senkou_a": senkou_a, "senkou_b": senkou_b, "signal": signal}


def pivot_points(high: float, low: float, close: float) -> dict:
    """Pivot Points: PP, S1-S3, R1-R3."""
    pp = (high + low + close) / 3.0
    return {
        "pp": pp,
        "r1": 2 * pp - low, "r2": pp + (high - low), "r3": high + 2 * (pp - low),
        "s1": 2 * pp - high, "s2": pp - (high - low), "s3": low - 2 * (high - pp),
    }


def ema_crossover(closes: list[float], fast: int = 9, slow: int = 21) -> dict:
    """EMA Crossover Signal."""
    if len(closes) < slow + 2:
        return {"signal": "neutral", "ema_fast": None, "ema_slow": None}
    ef = _ema(closes, fast)
    es = _ema(closes, slow)
    signal = "neutral"
    if ef[-1] > es[-1] and ef[-2] <= es[-2]:
        signal = "bullish_cross"
    elif ef[-1] < es[-1] and ef[-2] >= es[-2]:
        signal = "bearish_cross"
    elif ef[-1] > es[-1]:
        signal = "bullish"
    else:
        signal = "bearish"
    return {"signal": signal, "ema_fast": ef[-1], "ema_slow": es[-1]}


def momentum(closes: list[float], period: int = 10) -> Optional[float]:
    """Price Momentum (aktueller Preis / Preis vor N Perioden)."""
    if len(closes) < period + 1:
        return None
    return closes[-1] / closes[-period - 1] * 100.0 - 100.0


def obv_trend(closes: list[float], volumes: list[float], period: int = 10) -> Optional[str]:
    """On-Balance Volume Trend (steigend/fallend/neutral)."""
    if len(closes) < period + 1 or not volumes:
        return None
    obv = [0.0]
    for i in range(1, len(closes)):
        vol = volumes[i] if i < len(volumes) else 0
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + vol)
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - vol)
        else:
            obv.append(obv[-1])
    if obv[-1] > obv[-period]:
        return "rising"
    elif obv[-1] < obv[-period]:
        return "falling"
    return "flat"


# ---------------------------------------------------------------------------
# Master-Analyse: Alle Indikatoren auf einmal berechnen
# ---------------------------------------------------------------------------
def analyze_all(candles: list[dict]) -> dict:
    """
    Berechnet ALLE Indikatoren aus einer Liste von Candle-Dicts.
    Erwartet: [{"open": .., "high": .., "low": .., "close": .., "volume": ..}, ...]
    
    Returns: Dict mit allen Indikator-Werten + einem aggregierten Score.
    """
    if len(candles) < 2:
        return {"error": "Zu wenige Candles", "score": 0, "signal": "neutral"}

    opens = [c.get("open", c.get("o", 0)) for c in candles]
    highs = [c.get("high", c.get("h", 0)) for c in candles]
    lows = [c.get("low", c.get("l", 0)) for c in candles]
    closes = [c.get("close", c.get("c", 0)) for c in candles]
    volumes = [c.get("volume", c.get("v", 0)) for c in candles]

    # Alle Indikatoren berechnen
    rsi_val = rsi(closes, 14)
    rsi_fast = rsi(closes, 7)
    macd_val = macd(closes)
    bb = bollinger_bands(closes, 20)
    stoch = stochastic(highs, lows, closes)
    atr_val = atr(highs, lows, closes)
    adx_val = adx(highs, lows, closes)
    cci_val = cci(highs, lows, closes)
    wr = williams_r(highs, lows, closes)
    ichi = ichimoku(highs, lows, closes)
    ema_cross = ema_crossover(closes, 9, 21)
    mom = momentum(closes)
    obv = obv_trend(closes, volumes)
    pp = pivot_points(highs[-1], lows[-1], closes[-1])
    sma_20 = _sma(closes, 20)
    sma_50 = _sma(closes, 50)
    ema_12 = _ema(closes, 12)

    # --- Aggregierter Score (-10 bis +10, positiv = BUY, negativ = SELL) ---
    score = 0
    signals = {}

    # RSI
    if rsi_val is not None:
        if rsi_val < 30:
            score += 2; signals["rsi"] = "oversold_BUY"
        elif rsi_val < 40:
            score += 1; signals["rsi"] = "low_BUY"
        elif rsi_val > 70:
            score -= 2; signals["rsi"] = "overbought_SELL"
        elif rsi_val > 60:
            score -= 1; signals["rsi"] = "high_SELL"
        else:
            signals["rsi"] = "neutral"

    # MACD
    if macd_val["histogram"] is not None:
        if macd_val["histogram"] > 0 and macd_val["macd_line"] > macd_val["signal_line"]:
            score += 2; signals["macd"] = "bullish"
        elif macd_val["histogram"] < 0 and macd_val["macd_line"] < macd_val["signal_line"]:
            score -= 2; signals["macd"] = "bearish"
        else:
            signals["macd"] = "neutral"

    # Bollinger Bands
    if bb["percent_b"] is not None:
        if bb["percent_b"] < 0.1:
            score += 2; signals["bb"] = "below_lower_BUY"
        elif bb["percent_b"] < 0.3:
            score += 1; signals["bb"] = "near_lower_BUY"
        elif bb["percent_b"] > 0.9:
            score -= 2; signals["bb"] = "above_upper_SELL"
        elif bb["percent_b"] > 0.7:
            score -= 1; signals["bb"] = "near_upper_SELL"
        else:
            signals["bb"] = "neutral"

    # Stochastic
    if stoch["k"] is not None and stoch["d"] is not None:
        if stoch["k"] < 20 and stoch["k"] > stoch["d"]:
            score += 2; signals["stoch"] = "oversold_cross_BUY"
        elif stoch["k"] < 20:
            score += 1; signals["stoch"] = "oversold_BUY"
        elif stoch["k"] > 80 and stoch["k"] < stoch["d"]:
            score -= 2; signals["stoch"] = "overbought_cross_SELL"
        elif stoch["k"] > 80:
            score -= 1; signals["stoch"] = "overbought_SELL"
        else:
            signals["stoch"] = "neutral"

    # ADX + DI
    if adx_val["adx"] is not None:
        if adx_val["adx"] > 25:
            if adx_val["di_plus"] > adx_val["di_minus"]:
                score += 1; signals["adx"] = "strong_trend_BUY"
            else:
                score -= 1; signals["adx"] = "strong_trend_SELL"
        else:
            signals["adx"] = "weak_trend"

    # CCI
    if cci_val is not None:
        if cci_val < -100:
            score += 1; signals["cci"] = "oversold_BUY"
        elif cci_val > 100:
            score -= 1; signals["cci"] = "overbought_SELL"
        else:
            signals["cci"] = "neutral"

    # Williams %R
    if wr is not None:
        if wr < -80:
            score += 1; signals["williams_r"] = "oversold_BUY"
        elif wr > -20:
            score -= 1; signals["williams_r"] = "overbought_SELL"
        else:
            signals["williams_r"] = "neutral"

    # Ichimoku
    if ichi["signal"] == "bullish":
        score += 1; signals["ichimoku"] = "bullish"
    elif ichi["signal"] == "bearish":
        score -= 1; signals["ichimoku"] = "bearish"
    else:
        signals["ichimoku"] = "neutral"

    # EMA Crossover
    if "cross" in ema_cross["signal"]:
        if "bullish" in ema_cross["signal"]:
            score += 2; signals["ema_cross"] = "bullish_cross"
        else:
            score -= 2; signals["ema_cross"] = "bearish_cross"
    elif ema_cross["signal"] == "bullish":
        score += 1; signals["ema_cross"] = "bullish"
    elif ema_cross["signal"] == "bearish":
        score -= 1; signals["ema_cross"] = "bearish"

    # Momentum
    if mom is not None:
        if mom > 0.1:
            score += 1; signals["momentum"] = "positive"
        elif mom < -0.1:
            score -= 1; signals["momentum"] = "negative"
        else:
            signals["momentum"] = "neutral"

    # Pivot Points
    if closes[-1] > pp["r1"]:
        score += 1; signals["pivot"] = "above_R1_bullish"
    elif closes[-1] < pp["s1"]:
        score -= 1; signals["pivot"] = "below_S1_bearish"
    else:
        signals["pivot"] = "neutral"

    # Finales Signal
    if score >= 3:
        final_signal = "strong_buy"
    elif score >= 1:
        final_signal = "buy"
    elif score <= -3:
        final_signal = "strong_sell"
    elif score <= -1:
        final_signal = "sell"
    else:
        final_signal = "neutral"

    confidence = min(abs(score) / 10.0, 1.0)

    return {
        "signal": final_signal,
        "score": score,
        "confidence": confidence,
        "indicators": {
            "rsi_14": round(rsi_val, 2) if rsi_val else None,
            "rsi_7": round(rsi_fast, 2) if rsi_fast else None,
            "macd": {k: round(v, 6) if v else None for k, v in macd_val.items()},
            "bollinger": {k: round(v, 5) if v else None for k, v in bb.items()},
            "stochastic": {k: round(v, 2) if v else None for k, v in stoch.items()},
            "atr": round(atr_val, 6) if atr_val else None,
            "adx": {k: round(v, 2) if isinstance(v, float) else v for k, v in adx_val.items()},
            "cci": round(cci_val, 2) if cci_val else None,
            "williams_r": round(wr, 2) if wr else None,
            "ichimoku": ichi,
            "ema_cross": ema_cross,
            "momentum": round(mom, 4) if mom else None,
            "obv_trend": obv,
            "pivot_points": {k: round(v, 5) for k, v in pp.items()},
            "price": closes[-1],
            "sma_20": round(sma_20[-1], 5) if sma_20[-1] else None,
            "sma_50": round(sma_50[-1], 5) if sma_50 and sma_50[-1] else None,
            "ema_12": round(ema_12[-1], 5) if ema_12 else None,
        },
        "sub_signals": signals,
    }
