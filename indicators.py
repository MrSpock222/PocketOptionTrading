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
# Advanced Indicators
# ---------------------------------------------------------------------------
def supertrend(highs: list[float], lows: list[float], closes: list[float], period: int = 10, multiplier: float = 3.0) -> dict:
    """Supertrend Indicator."""
    if len(closes) < period + 1:
        return {"value": None, "trend": "neutral"}
    
    tr = _true_range(highs, lows, closes)
    atr = _sma(tr, period)
    
    basic_ub = [(highs[i] + lows[i]) / 2 + multiplier * atr[i] if atr[i] is not None else 0 for i in range(len(closes))]
    basic_lb = [(highs[i] + lows[i]) / 2 - multiplier * atr[i] if atr[i] is not None else 0 for i in range(len(closes))]
    
    final_ub = [0.0] * len(closes)
    final_lb = [0.0] * len(closes)
    trend = [1] * len(closes)  # 1 for bull, -1 for bear
    
    for i in range(period, len(closes)):
        final_ub[i] = basic_ub[i] if basic_ub[i] < final_ub[i-1] or closes[i-1] > final_ub[i-1] else final_ub[i-1]
        final_lb[i] = basic_lb[i] if basic_lb[i] > final_lb[i-1] or closes[i-1] < final_lb[i-1] else final_lb[i-1]
        
        if trend[i-1] == 1 and closes[i] < final_lb[i]:
            trend[i] = -1
        elif trend[i-1] == -1 and closes[i] > final_ub[i]:
            trend[i] = 1
        else:
            trend[i] = trend[i-1]
            
    st = final_lb[-1] if trend[-1] == 1 else final_ub[-1]
    return {"value": st, "trend": "bullish" if trend[-1] == 1 else "bearish"}


def keltner_channels(highs: list[float], lows: list[float], closes: list[float], period: int = 20, multiplier: float = 1.5) -> dict:
    """Keltner Channels."""
    if len(closes) < period + 1:
        return {"upper": None, "middle": None, "lower": None}
    
    ema_center = _ema(closes, period)
    tr = _true_range(highs, lows, closes)
    atr = _ema(tr, period)
    
    upper = ema_center[-1] + multiplier * atr[-1]
    lower = ema_center[-1] - multiplier * atr[-1]
    
    return {"upper": upper, "middle": ema_center[-1], "lower": lower}


def awesome_oscillator(highs: list[float], lows: list[float]) -> dict:
    """Awesome Oscillator (AO). SMA(5) - SMA(34) of median price."""
    if len(highs) < 34:
        return {"ao": None, "signal": "neutral"}
    
    median = [(h + l) / 2 for h, l in zip(highs, lows)]
    sma5 = _sma(median, 5)
    sma34 = _sma(median, 34)
    
    ao = [s5 - s34 if s5 is not None and s34 is not None else 0 for s5, s34 in zip(sma5, sma34)]
    
    signal = "neutral"
    if ao[-1] > 0 and ao[-1] > ao[-2]:
        signal = "bullish"
    elif ao[-1] < 0 and ao[-1] < ao[-2]:
        signal = "bearish"
    
    return {"ao": ao[-1], "signal": signal}


def money_flow_index(highs: list[float], lows: list[float], closes: list[float], volumes: list[float], period: int = 14) -> Optional[float]:
    """Money Flow Index (MFI). RSI weighted by volume."""
    if len(closes) < period + 1 or sum(volumes) == 0:
        return None
    
    typical_price = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    raw_money_flow = [tp * v for tp, v in zip(typical_price, volumes)]
    
    positive_flow = []
    negative_flow = []
    
    for i in range(1, len(typical_price)):
        if typical_price[i] > typical_price[i-1]:
            positive_flow.append(raw_money_flow[i])
            negative_flow.append(0.0)
        elif typical_price[i] < typical_price[i-1]:
            positive_flow.append(0.0)
            negative_flow.append(raw_money_flow[i])
        else:
            positive_flow.append(0.0)
            negative_flow.append(0.0)
            
    if len(positive_flow) < period:
        return None
        
    pos_sum = sum(positive_flow[-period:])
    neg_sum = sum(negative_flow[-period:])
    
    if neg_sum == 0:
        return 100.0
        
    mfi_ratio = pos_sum / neg_sum
    mfi = 100.0 - (100.0 / (1.0 + mfi_ratio))
    return mfi


def parabolic_sar(highs: list[float], lows: list[float], closes: list[float], step: float = 0.02, max_step: float = 0.2) -> dict:
    """Parabolic SAR."""
    if len(closes) < 10:
        return {"sar": None, "trend": "neutral"}
    
    sar = [0.0] * len(closes)
    trend = [1] * len(closes) # 1 bull, -1 bear
    ep = [0.0] * len(closes)
    af = [0.0] * len(closes)
    
    # Initialize
    trend[1] = 1 if closes[1] > closes[0] else -1
    sar[1] = lows[0] if trend[1] == 1 else highs[0]
    ep[1] = highs[1] if trend[1] == 1 else lows[1]
    af[1] = step
    
    for i in range(2, len(closes)):
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
        
        if trend[i-1] == 1:
            if lows[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep[i-1]
                ep[i] = lows[i]
                af[i] = step
            else:
                trend[i] = 1
                ep[i] = max(ep[i-1], highs[i])
                af[i] = min(max_step, af[i-1] + step if ep[i] > ep[i-1] else af[i-1])
        else:
            if highs[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep[i-1]
                ep[i] = highs[i]
                af[i] = step
            else:
                trend[i] = -1
                ep[i] = min(ep[i-1], lows[i])
                af[i] = min(max_step, af[i-1] + step if ep[i] < ep[i-1] else af[i-1])
                
    return {"sar": sar[-1], "trend": "bullish" if trend[-1] == 1 else "bearish"}


# ---------------------------------------------------------------------------
# Master-Analyse: Alle Indikatoren auf einmal berechnen
# ---------------------------------------------------------------------------
def analyze_all(candles: list[dict], weights: dict = None) -> dict:
    """
    Berechnet ALLE Indikatoren aus einer Liste von Candle-Dicts.
    Erwartet: [{"open": .., "high": .., "low": .., "close": .., "volume": ..}, ...]
    
    Args:
        candles: Liste von Candle-Dicts
        weights: Optionale Indikator-Gewichte aus dem AI Memory System.
                 Jeder Wert multipliziert den Score-Beitrag des jeweiligen Indikators.
                 Default: 1.0 für alle.
    
    Returns: Dict mit allen Indikator-Werten + einem aggregierten Score.
    """
    if len(candles) < 2:
        return {"error": "Zu wenige Candles", "score": 0, "signal": "neutral"}

    # Gewichte laden (Default: alles 1.0)
    w = weights or {}

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
    obv_tr = obv_trend(closes, volumes)

    # Advanced Indicators
    st = supertrend(highs, lows, closes)
    kc = keltner_channels(highs, lows, closes)
    ao = awesome_oscillator(highs, lows)
    mfi_val = money_flow_index(highs, lows, closes, volumes)
    psar = parabolic_sar(highs, lows, closes)

    # Pre-compute basic components for AI context
    ema_9 = _ema(closes, 9)
    ema_12 = _ema(closes, 12)
    ema_12 = _ema(closes, 12)

    # --- Aggregierter Score (-10 bis +10, positiv = BUY, negativ = SELL) ---
    # Gewichte beeinflussen wie stark jeder Indikator den Score beeinflusst
    score = 0.0
    signals = {}

    # RSI
    rsi_w = w.get("rsi", 1.0)
    if rsi_val is not None:
        if rsi_val < 30:
            score += 2 * rsi_w; signals["rsi"] = "oversold_BUY"
        elif rsi_val < 40:
            score += 1 * rsi_w; signals["rsi"] = "low_BUY"
        elif rsi_val > 70:
            score -= 2 * rsi_w; signals["rsi"] = "overbought_SELL"
        elif rsi_val > 60:
            score -= 1 * rsi_w; signals["rsi"] = "high_SELL"
        else:
            signals["rsi"] = "neutral"

    # MACD
    macd_w = w.get("macd", 1.0)
    if macd_val["histogram"] is not None:
        if macd_val["histogram"] > 0 and macd_val["macd_line"] > macd_val["signal_line"]:
            score += 2 * macd_w; signals["macd"] = "bullish"
        elif macd_val["histogram"] < 0 and macd_val["macd_line"] < macd_val["signal_line"]:
            score -= 2 * macd_w; signals["macd"] = "bearish"
        else:
            signals["macd"] = "neutral"

    # Bollinger Bands
    bb_w = w.get("bollinger", 1.0)
    if bb["percent_b"] is not None:
        if bb["percent_b"] < 0.1:
            score += 2 * bb_w; signals["bb"] = "below_lower_BUY"
        elif bb["percent_b"] < 0.3:
            score += 1 * bb_w; signals["bb"] = "near_lower_BUY"
        elif bb["percent_b"] > 0.9:
            score -= 2 * bb_w; signals["bb"] = "above_upper_SELL"
        elif bb["percent_b"] > 0.7:
            score -= 1 * bb_w; signals["bb"] = "near_upper_SELL"
        else:
            signals["bb"] = "neutral"

    # Stochastic
    stoch_w = w.get("stochastic", 1.0)
    if stoch["k"] is not None and stoch["d"] is not None:
        if stoch["k"] < 20 and stoch["k"] > stoch["d"]:
            score += 2 * stoch_w; signals["stoch"] = "oversold_cross_BUY"
        elif stoch["k"] < 20:
            score += 1 * stoch_w; signals["stoch"] = "oversold_BUY"
        elif stoch["k"] > 80 and stoch["k"] < stoch["d"]:
            score -= 2 * stoch_w; signals["stoch"] = "overbought_cross_SELL"
        elif stoch["k"] > 80:
            score -= 1 * stoch_w; signals["stoch"] = "overbought_SELL"
        else:
            signals["stoch"] = "neutral"

    # ADX + DI
    adx_w = w.get("adx", 1.0)
    if adx_val["adx"] is not None:
        if adx_val["adx"] > 25:
            if adx_val["di_plus"] > adx_val["di_minus"]:
                score += 1 * adx_w; signals["adx"] = "strong_trend_BUY"
            else:
                score -= 1 * adx_w; signals["adx"] = "strong_trend_SELL"
        else:
            signals["adx"] = "weak_trend"

    # CCI
    cci_w = w.get("cci", 1.0)
    if cci_val is not None:
        if cci_val < -100:
            score += 1 * cci_w; signals["cci"] = "oversold_BUY"
        elif cci_val > 100:
            score -= 1 * cci_w; signals["cci"] = "overbought_SELL"
        else:
            signals["cci"] = "neutral"

    # Williams %R
    wr_w = w.get("williams_r", 1.0)
    if wr is not None:
        if wr < -80:
            score += 1 * wr_w; signals["williams_r"] = "oversold_BUY"
        elif wr > -20:
            score -= 1 * wr_w; signals["williams_r"] = "overbought_SELL"
        else:
            signals["williams_r"] = "neutral"

    # Ichimoku
    ichi_w = w.get("ichimoku", 1.0)
    if ichi["signal"] == "bullish":
        score += 1 * ichi_w; signals["ichimoku"] = "bullish"
    elif ichi["signal"] == "bearish":
        score -= 1 * ichi_w; signals["ichimoku"] = "bearish"
    else:
        signals["ichimoku"] = "neutral"

    # EMA Crossover
    ema_w = w.get("ema_cross", 1.0)
    if "cross" in ema_cross["signal"]:
        if "bullish" in ema_cross["signal"]:
            score += 2 * ema_w; signals["ema_cross"] = "bullish_cross"
        else:
            score -= 2 * ema_w; signals["ema_cross"] = "bearish_cross"
    elif ema_cross["signal"] == "bullish":
        score += 1 * ema_w; signals["ema_cross"] = "bullish"
    elif ema_cross["signal"] == "bearish":
        score -= 1 * ema_w; signals["ema_cross"] = "bearish"



    # --- AI Dynamischer Indikator (Falls vorhanden) ---
    try:
        import sys
        import os
        if os.path.exists("ai_generated_indicator.py"):
            import importlib
            import ai_generated_indicator
            importlib.reload(ai_generated_indicator)
            
            if hasattr(ai_generated_indicator, 'analyze'):
                ai_res = ai_generated_indicator.analyze(candles)
                if isinstance(ai_res, dict) and "score" in ai_res and "signal" in ai_res:
                    ai_w = w.get("ai_indicator", 1.5)  # Etwas höhere Gewichtung initial
                    score += float(ai_res["score"]) * ai_w
                    signals["ai_indicator"] = ai_res["signal"]
    except Exception as e:
        signals["ai_indicator_error"] = str(e)

    # Finale Entscheidung
    final_signal = "neutral"

    # Momentum
    mom_w = w.get("momentum", 1.0)
    if mom is not None:
        if mom > 0.1:
            score += 1 * mom_w; signals["momentum"] = "positive"
        elif mom < -0.1:
            score -= 1 * mom_w; signals["momentum"] = "negative"
        else:
            signals["momentum"] = "neutral"

    # Pivot Points
    piv_w = w.get("pivot", 1.0)
    pp = pivot_points(highs[-1], lows[-1], closes[-1])
    if closes[-1] > pp["r1"]:
        score += 1 * piv_w; signals["pivot"] = "above_R1_bullish"
    elif closes[-1] < pp["s1"]:
        score -= 1 * piv_w; signals["pivot"] = "below_S1_bearish"
    else:
        signals["pivot"] = "neutral"

    # --- Advanced Indicators Scoring ---
    
    # Supertrend
    st_w = w.get("supertrend", 1.0)
    if st["trend"] == "bullish":
        score += 1 * st_w; signals["supertrend"] = "bullish"
    else:
        score -= 1 * st_w; signals["supertrend"] = "bearish"
        
    # Awesome Oscillator
    ao_w = w.get("awesome_oscillator", 1.0)
    if ao["signal"] == "bullish":
        score += 1 * ao_w; signals["awesome_oscillator"] = "bullish"
    elif ao["signal"] == "bearish":
        score -= 1 * ao_w; signals["awesome_oscillator"] = "bearish"
    else:
        signals["awesome_oscillator"] = "neutral"
        
    # MFI
    mfi_w = w.get("mfi", 1.0)
    if mfi_val is not None:
        if mfi_val < 20:
            score += 1 * mfi_w; signals["mfi"] = "oversold_BUY"
        elif mfi_val > 80:
            score -= 1 * mfi_w; signals["mfi"] = "overbought_SELL"
        else:
            signals["mfi"] = "neutral"
            
    # Parabolic SAR
    psar_w = w.get("psar", 1.0)
    if psar["trend"] == "bullish":
        score += 1 * psar_w; signals["psar"] = "bullish"
    else:
        score -= 1 * psar_w; signals["psar"] = "bearish"

    # Score auf int runden für Kompatibilität
    score = int(round(score))

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
            "pivot_points": pp,
            "ema_crossover": ema_cross,
            "momentum": mom,
            "obv_trend": obv_tr,
            "supertrend": st,
            "keltner_channels": kc,
            "awesome_oscillator": ao,
            "mfi": mfi_val,
            "parabolic_sar": psar,
            "current_price": closes[-1],
        },
        "sub_signals": signals,
    }
