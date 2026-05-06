"""
Dynamisches Risk Management System für Binary Options Scalping.
Verwaltet Einsatzstrategien, Drawdown-Limits, Performance-Tracking
und passt sich automatisch basierend auf Ergebnissen an.
"""
import math
import logging
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Einsatz-Strategien
# ---------------------------------------------------------------------------
class Strategy:
    """Basis-Klasse für Einsatz-Strategien."""
    name: str = "base"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        return base


class FlatStrategy(Strategy):
    """Fester Einsatz — kein Risiko-Scaling."""
    name = "flat"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        return base


class MartingaleStrategy(Strategy):
    """Klassisches Martingale — Verdopplung nach Verlust."""
    name = "martingale"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        multiplier = params.get("martingale_multiplier", 2.0)
        max_steps = params.get("martingale_max_steps", 4)
        consecutive_losses = 0
        for t in reversed(history):
            if t["status"] == "loss":
                consecutive_losses += 1
            else:
                break
        steps = min(consecutive_losses, max_steps)
        return base * (multiplier ** steps)


class SoftMartingaleStrategy(Strategy):
    """Sanftes Martingale — erhöht nur um 50% statt Verdopplung."""
    name = "soft_martingale"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        multiplier = params.get("soft_multiplier", 1.5)
        max_steps = params.get("soft_max_steps", 5)
        consecutive_losses = 0
        for t in reversed(history):
            if t["status"] == "loss":
                consecutive_losses += 1
            else:
                break
        steps = min(consecutive_losses, max_steps)
        return base * (multiplier ** steps)


class AntiMartingaleStrategy(Strategy):
    """Anti-Martingale — erhöht nach Gewinn, senkt nach Verlust."""
    name = "anti_martingale"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        multiplier = params.get("anti_multiplier", 1.5)
        if not history:
            return base
        if history[-1]["status"] == "win":
            return min(base * multiplier, base * 4)
        return base


class KellyStrategy(Strategy):
    """Kelly Criterion — mathematisch optimale Einsatzhöhe."""
    name = "kelly"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        if len(history) < 5:
            return base
        wins = sum(1 for t in history if t["status"] == "win")
        total = len(history)
        win_rate = wins / total
        payout = params.get("payout_ratio", 0.85)
        # Kelly: f = (bp - q) / b  wobei b=payout, p=winrate, q=1-p
        kelly_f = (payout * win_rate - (1 - win_rate)) / payout
        kelly_f = max(0.0, min(kelly_f, 0.25))  # Max 25% Kelly
        fraction = params.get("kelly_fraction", 0.5)  # Half-Kelly
        amount = base * (1 + kelly_f * fraction * 10)
        return max(base * 0.5, min(amount, base * 4))


class PercentBalanceStrategy(Strategy):
    """Setzt einen festen % des Kontostands."""
    name = "percent_balance"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        balance = params.get("current_balance", 100)
        pct = params.get("balance_percent", 0.02)  # 2% Standard
        return max(base * 0.5, balance * pct)


class TargetRecoveryStrategy(Strategy):
    """Erzwingt einen Session-Profit am Ende. Erhöht den Einsatz dynamisch, um alle Session-Verluste mit einem Trade auszugleichen."""
    name = "target_recovery"

    def next_amount(self, base: float, history: list[dict], params: dict) -> float:
        net_profit = params.get("session_net_profit", 0.0)
        payout = params.get("payout_ratio", 0.85)
        
        # Wenn wir im Minus sind: Wie viel Einsatz brauchen wir für Recovery + Base?
        # Auch wenn wir im Plus sind, aber der letzte Trade ein Verlust war, wollen wir diesen EINEN Verlust 
        # ggf. schneller zurückholen (Nachtrade-Logik).
        
        deficit = 0.0
        if net_profit < 0:
            deficit = abs(net_profit)
        else:
            # Check ob wir in einer Verlustserie sind (für Nachtrades innerhalb einer Sequenz)
            last_losses = 0.0
            for t in reversed(history):
                if t.get("status") == "loss":
                    last_losses += float(t.get("amount", 0))
                else:
                    break
            deficit = last_losses

        if deficit <= 0:
            return base
            
        # target_amount = (deficit + (base * payout)) / payout
        target_amount = (deficit + (base * payout)) / payout
        
        logger.info(f"TargetRecovery: Deficit={deficit:.2f}, Payout={payout:.2f}, Result={target_amount:.2f}")
        
        # Zur Sicherheit: Max-Multiplier auf 10x begrenzen
        return min(target_amount, base * 10)


STRATEGIES = {
    "flat": FlatStrategy(),
    "martingale": MartingaleStrategy(),
    "soft_martingale": SoftMartingaleStrategy(),
    "anti_martingale": AntiMartingaleStrategy(),
    "kelly": KellyStrategy(),
    "percent_balance": PercentBalanceStrategy(),
    "target_recovery": TargetRecoveryStrategy(),
}


# ---------------------------------------------------------------------------
# Performance Tracker
# ---------------------------------------------------------------------------
@dataclass
class SessionStats:
    """Trackt alle Performance-Metriken einer Session."""
    start_balance: float = 0.0
    current_balance: float = 0.0
    peak_balance: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    current_drawdown_pct: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0  # positiv = wins, negativ = losses
    strategy_used: str = "martingale"
    strategy_params: dict = field(default_factory=dict)
    trade_log: list = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / max(self.trades, 1)

    @property
    def profit_factor(self) -> float:
        return self.total_profit / max(self.total_loss, 0.01)

    @property
    def net_profit(self) -> float:
        return self.current_balance - self.start_balance

    @property
    def roi(self) -> float:
        return self.net_profit / max(self.start_balance, 1) * 100

    def record_trade(self, amount: float, status: str, balance_after: float, payout_rate: float = 0.85):
        self.trades += 1
        self.current_balance = balance_after

        if status == "win":
            self.wins += 1
            profit = amount * payout_rate
            self.total_profit += profit
            if self.current_streak > 0:
                self.current_streak += 1
            else:
                self.current_streak = 1
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.current_streak)
        else:
            self.losses += 1
            self.total_loss += amount
            if self.current_streak < 0:
                self.current_streak -= 1
            else:
                self.current_streak = -1
            self.max_consecutive_losses = max(
                self.max_consecutive_losses, abs(self.current_streak)
            )

        # Drawdown berechnen
        if balance_after > self.peak_balance:
            self.peak_balance = balance_after
        dd_abs = self.peak_balance - balance_after
        dd_pct = dd_abs / max(self.peak_balance, 1) * 100
        self.current_drawdown_pct = dd_pct
        if dd_abs > self.max_drawdown_abs:
            self.max_drawdown_abs = dd_abs
            self.max_drawdown_pct = dd_pct

    def to_summary(self) -> str:
        return (
            f"Trades: {self.trades} | W/L: {self.wins}/{self.losses} "
            f"({self.win_rate:.0%})\n"
            f"Net: ${self.net_profit:+.2f} | ROI: {self.roi:+.1f}%\n"
            f"Max DD: {self.max_drawdown_pct:.1f}% (${self.max_drawdown_abs:.2f})\n"
            f"Streaks: W{self.max_consecutive_wins} / L{self.max_consecutive_losses}\n"
            f"Profit Factor: {self.profit_factor:.2f}\n"
            f"Strategie: {self.strategy_used}"
        )


# ---------------------------------------------------------------------------
# Risk Manager — Entscheidet über Einsatz, Limits, Strategie-Wechsel
# ---------------------------------------------------------------------------
class RiskManager:
    """
    Dynamisches Risk Management:
    - Wählt Einsatzstrategie basierend auf Performance
    - Enforced Drawdown-Limits
    - Passt Parameter automatisch an
    - Speichert Optimierungs-Daten für NemoClaw
    """

    def __init__(self, base_amount: float = 1.0, initial_balance: float = 100.0):
        self.base_amount = base_amount
        self.stats = SessionStats(
            start_balance=initial_balance,
            current_balance=initial_balance,
            peak_balance=initial_balance,
        )

        # Aktive Strategie + Parameter
        self.strategy_name = "target_recovery"
        self.params = {
            "martingale_multiplier": 2.0,
            "martingale_max_steps": 4,
            "max_martingale_steps": 3,
            "soft_multiplier": 1.5,
            "soft_max_steps": 5,
            "anti_multiplier": 1.5,
            "payout_ratio": 0.85,
            "kelly_fraction": 0.5,
            "balance_percent": 0.02,
            "current_balance": initial_balance,
        }

        # Risk Limits
        self.max_drawdown_pct = 15.0       # Stoppe bei 15% Drawdown
        self.max_consecutive_losses = 5     # Stoppe bei 5 Verlusten hintereinander
        self.min_confidence = 0.3           # Trade nur bei Konfidenz > 30%
        self.daily_loss_limit_pct = 10.0    # Max 10% Tagesverlust

        # Auto-Optimierung
        self.optimization_interval = 5      # Alle 5 Trades optimieren
        self.optimization_log: list[dict] = []

        # Persistence
        self.save_path = Path("risk_state.json")

    def reset_session(self, current_balance: float):
        """Setzt die Streaks und Drawdowns für eine neue Trainings-Session zurück."""
        self.stats.current_balance = current_balance
        self.stats.peak_balance = current_balance
        self.stats.current_streak = 0
        self.stats.current_drawdown_pct = 0.0
        self.stats.max_drawdown_abs = 0.0
        self.stats.max_drawdown_pct = 0.0
        # Optional: Behalte Gesamt-Wins/Losses für Langzeit-Stats,
        # aber resette die Session-Blocker.

    @property
    def strategy(self) -> Strategy:
        return STRATEGIES.get(self.strategy_name, STRATEGIES["soft_martingale"])

    def get_next_amount(self, history: list[dict], balance: float) -> float:
        """Berechnet den nächsten Einsatz basierend auf aktiver Strategie."""
        self.params["current_balance"] = balance
        self.params["session_net_profit"] = self.stats.net_profit
        amount = self.strategy.next_amount(self.base_amount, history, self.params)

        # Safety Caps
        max_amount = balance * 0.10  # Nie mehr als 10% der Balance
        amount = min(amount, max_amount)
        amount = max(amount, 1.0)  # PocketOption absolutes Minimum ist $1.0
        amount = max(amount, self.base_amount * 0.5)  # Minimum halber Base (falls Base > 2.0)
        amount = round(amount, 2)

        return amount

    def should_trade(self, confidence: float, balance: float) -> tuple[bool, str]:
        """Prüft ob ein Trade erlaubt ist basierend auf Risk-Regeln."""
        # Drawdown-Check
        if self.stats.current_drawdown_pct >= self.max_drawdown_pct:
            return False, f"Max Drawdown erreicht ({self.stats.current_drawdown_pct:.1f}%)"

        # Verlustserie-Check
        if abs(self.stats.current_streak) >= self.max_consecutive_losses and self.stats.current_streak < 0:
            return False, f"Max Verlustserie ({abs(self.stats.current_streak)}x)"

        # Tagesverlust
        daily_loss = (self.stats.start_balance - balance) / max(self.stats.start_balance, 1) * 100
        if daily_loss >= self.daily_loss_limit_pct:
            return False, f"Tages-Verlustlimit ({daily_loss:.1f}%)"

        # Konfidenz-Check
        if confidence < self.min_confidence:
            return False, f"Konfidenz zu niedrig ({confidence:.0%} < {self.min_confidence:.0%})"

        return True, "OK"

    def record_result(self, amount: float, status: str, balance: float, payout_rate: float = 0.85):
        """Zeichnet Ergebnis auf und triggert ggf. Optimierung."""
        self.stats.record_trade(amount, status, balance, payout_rate)
        self.stats.strategy_used = self.strategy_name

        # Auto-Optimierung alle N Trades
        if self.stats.trades % self.optimization_interval == 0 and self.stats.trades > 0:
            self._auto_optimize()

    def _auto_optimize(self):
        """
        Analysiert bisherige Performance und passt Strategie/Parameter an.
        Dies ist die lokale Optimierung — NemoClaw kann zusätzlich überschreiben.
        """
        stats = self.stats
        old_strategy = self.strategy_name
        changes = []

        # Regel 1: Winrate-basierter Strategiewechsel
        if stats.trades >= 5:
            wr = stats.win_rate

            if wr >= 0.65:
                # Hohe Winrate → Anti-Martingale (Gewinne ausbauen)
                if self.strategy_name != "anti_martingale":
                    self.strategy_name = "anti_martingale"
                    changes.append(f"Strategie → anti_martingale (WR={wr:.0%})")

            elif wr >= 0.55:
                # Gute Winrate → Kelly (mathematisch optimal)
                if self.strategy_name != "kelly":
                    self.strategy_name = "kelly"
                    changes.append(f"Strategie → kelly (WR={wr:.0%})")

            elif wr >= 0.45:
                # Mittelmäßig → Soft Martingale (vorsichtig)
                if self.strategy_name != "soft_martingale":
                    self.strategy_name = "soft_martingale"
                    changes.append(f"Strategie → soft_martingale (WR={wr:.0%})")

            elif wr < 0.45:
                # Schlechte Winrate → Flat (Schaden begrenzen)
                if self.strategy_name != "flat":
                    self.strategy_name = "flat"
                    changes.append(f"Strategie → flat (WR={wr:.0%})")

        # Regel 2: Drawdown-Anpassung
        if stats.max_drawdown_pct > 10:
            # Bei hohem Drawdown: konservativer werden
            if self.params.get("soft_multiplier", 1.5) > 1.2:
                self.params["soft_multiplier"] = 1.2
                changes.append("Soft-Multiplier 1.5 → 1.2 (hoher DD)")
            if self.params.get("martingale_max_steps", 4) > 2:
                self.params["martingale_max_steps"] = 2
                changes.append("Max-Martingale-Steps 4 → 2")

        # Regel 3: Konfidenz-Schwelle anpassen
        if stats.trades >= 10:
            if wr < 0.4:
                self.min_confidence = min(self.min_confidence + 0.05, 0.6)
                changes.append(f"Min-Konfidenz → {self.min_confidence:.0%}")
            elif wr > 0.6 and self.min_confidence > 0.2:
                self.min_confidence = max(self.min_confidence - 0.05, 0.2)
                changes.append(f"Min-Konfidenz → {self.min_confidence:.0%}")

        # Regel 4: Bei vielen Verlusten am Stück → Pause erzwingen
        if stats.max_consecutive_losses >= 4:
            self.max_consecutive_losses = 3  # Früher stoppen
            changes.append("Max-Verlustserie → 3 (war schon 4+ erreicht)")

        if changes:
            log_entry = {
                "trade_nr": stats.trades,
                "old_strategy": old_strategy,
                "new_strategy": self.strategy_name,
                "changes": changes,
                "win_rate": stats.win_rate,
                "drawdown": stats.max_drawdown_pct,
                "profit_factor": stats.profit_factor,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.optimization_log.append(log_entry)
            logger.info(f"Risk-Optimierung: {changes}")

    def apply_ai_adjustments(self, adjustments: dict):
        """
        NemoClaw kann über die API Parameter anpassen:
        - strategy: Name der neuen Strategie
        - base_amount: Neuer Grundeinsatz
        - max_drawdown: Neues Drawdown-Limit
        - min_confidence: Neue Mindest-Konfidenz
        - params: Dict mit Strategie-Parametern
        """
        if not adjustments:
            return []

        changes = []

        if "strategy" in adjustments and adjustments["strategy"] in STRATEGIES:
            old = self.strategy_name
            self.strategy_name = adjustments["strategy"]
            changes.append(f"KI: Strategie {old} → {self.strategy_name}")

        if "base_amount" in adjustments:
            new_base = float(adjustments["base_amount"])
            if 0.5 <= new_base <= 50:
                self.base_amount = new_base
                changes.append(f"KI: Base-Einsatz → ${new_base}")

        if "max_drawdown" in adjustments:
            dd = float(adjustments["max_drawdown"])
            if 5 <= dd <= 30:
                self.max_drawdown_pct = dd
                changes.append(f"KI: Max-DD → {dd}%")

        if "min_confidence" in adjustments:
            mc = float(adjustments["min_confidence"])
            if 0.1 <= mc <= 0.8:
                self.min_confidence = mc
                changes.append(f"KI: Min-Konfidenz → {mc:.0%}")

        if "params" in adjustments and isinstance(adjustments["params"], dict):
            for k, v in adjustments["params"].items():
                if k in self.params:
                    self.params[k] = v
                    changes.append(f"KI: {k} → {v}")

        if changes:
            logger.info(f"NemoClaw Risk-Anpassung: {changes}")

        return changes

    def get_state_for_ai(self) -> dict:
        """Gibt den kompletten Risk-State für NemoClaw zurück."""
        return {
            "strategy": self.strategy_name,
            "base_amount": self.base_amount,
            "params": self.params,
            "limits": {
                "max_drawdown_pct": self.max_drawdown_pct,
                "max_consecutive_losses": self.max_consecutive_losses,
                "min_confidence": self.min_confidence,
                "daily_loss_limit_pct": self.daily_loss_limit_pct,
            },
            "stats": {
                "trades": self.stats.trades,
                "win_rate": round(self.stats.win_rate, 3),
                "net_profit": round(self.stats.net_profit, 2),
                "roi": round(self.stats.roi, 2),
                "max_drawdown_pct": round(self.stats.max_drawdown_pct, 2),
                "current_drawdown_pct": round(self.stats.current_drawdown_pct, 2),
                "profit_factor": round(self.stats.profit_factor, 3),
                "max_consecutive_losses": self.stats.max_consecutive_losses,
                "current_streak": self.stats.current_streak,
            },
            "optimization_log": self.optimization_log[-3:],
        }

    def save_state(self):
        """Speichert Risk-State für Persistenz."""
        try:
            data = {
                "strategy": self.strategy_name,
                "base_amount": self.base_amount,
                "params": self.params,
                "max_drawdown_pct": self.max_drawdown_pct,
                "min_confidence": self.min_confidence,
                "optimization_log": self.optimization_log,
            }
            self.save_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Risk-State speichern fehlgeschlagen: {e}")

    def load_state(self):
        """Lädt gespeicherten Risk-State."""
        try:
            if self.save_path.exists():
                data = json.loads(self.save_path.read_text())
                self.strategy_name = data.get("strategy", self.strategy_name)
                self.base_amount = data.get("base_amount", self.base_amount)
                self.params.update(data.get("params", {}))
                self.max_drawdown_pct = data.get("max_drawdown_pct", self.max_drawdown_pct)
                self.min_confidence = data.get("min_confidence", self.min_confidence)
                self.optimization_log = data.get("optimization_log", [])
                logger.info(f"Risk-State geladen: {self.strategy_name}, Base=${self.base_amount}")
        except Exception as e:
            logger.warning(f"Risk-State laden fehlgeschlagen: {e}")

    def format_telegram_status(self) -> str:
        """Formatiert Risk-Status für Telegram."""
        s = self.stats
        return (
            f"📊 *Risk Management*\n"
            f"  Strategie: `{self.strategy_name}`\n"
            f"  Base: ${self.base_amount:.2f}\n"
            f"  W/L: {s.wins}/{s.losses} ({s.win_rate:.0%})\n"
            f"  Profit: ${s.net_profit:+.2f} ({s.roi:+.1f}%)\n"
            f"  Drawdown: {s.current_drawdown_pct:.1f}% (Max: {s.max_drawdown_pct:.1f}%)\n"
            f"  PF: {s.profit_factor:.2f} | Streak: {s.current_streak:+d}\n"
            f"  Limit DD: {self.max_drawdown_pct}% | Min Conf: {self.min_confidence:.0%}"
        )
