"""
AI Memory & Self-Learning System
=================================
Persistente Wissensbasis für den Trading-Bot.
Die KI analysiert nach jeder Session ihre Trades,
erkennt Muster und Fehler, passt Indikator-Gewichte an
und speichert alles für zukünftige Sessions.

Datei: ai_memory.json (wird automatisch erstellt)

Struktur:
  - trade_log: Alle Trades mit vollem Kontext (Indikatoren, KI-Reasoning, Ergebnis)
  - learned_rules: Regeln die die KI aus Erfahrung gelernt hat
  - indicator_weights: Angepasste Gewichte für jeden Indikator
  - asset_patterns: Asset-spezifische Muster (z.B. "EURUSD_otc → RSI reversal works")
  - session_reviews: Post-Session Analysen der KI
  - config_evolution: Wie sich die Konfiguration über Zeit verändert hat
"""
import json
import logging
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_FILE = os.getenv("AI_MEMORY_FILE", "ai_memory.json")

# Default Indikator-Gewichte (Score-Multiplikatoren)
DEFAULT_WEIGHTS = {
    "rsi": 1.0,
    "macd": 1.0,
    "bollinger": 1.0,
    "stochastic": 1.0,
    "adx": 1.0,
    "cci": 1.0,
    "williams_r": 1.0,
    "ichimoku": 1.0,
    "ema_cross": 1.0,
    "momentum": 1.0,
    "pivot": 1.0,
}


class AIMemory:
    """Persistente Wissensbasis mit Self-Learning Fähigkeiten."""

    def __init__(self, path: str = MEMORY_FILE):
        self.path = Path(path)
        self.data = self._load()

    # ------------------------------------------------------------------
    # Laden / Speichern
    # ------------------------------------------------------------------
    def _load(self) -> dict:
        """Lädt die Memory-Datei oder erstellt eine neue."""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("AI Memory geladen: %d Trades, %d Regeln, %d Sessions",
                           len(data.get("trade_log", [])),
                           len(data.get("learned_rules", [])),
                           len(data.get("session_reviews", [])))
                return data
            except Exception as e:
                logger.error("Memory-Datei beschädigt, starte neu: %s", e)

        return {
            "trade_log": [],
            "learned_rules": [],
            "indicator_weights": dict(DEFAULT_WEIGHTS),
            "asset_patterns": {},
            "session_reviews": [],
            "config_evolution": [],
            "stats": {
                "total_trades": 0,
                "total_wins": 0,
                "total_losses": 0,
                "total_sessions": 0,
                "best_streak": 0,
                "worst_streak": 0,
                "created_at": datetime.now().isoformat(),
            },
        }

    def save(self):
        """Speichert die Memory-Datei."""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("AI Memory gespeichert: %s", self.path)
        except Exception as e:
            logger.error("Fehler beim Speichern der Memory: %s", e)

    # ------------------------------------------------------------------
    # Trade Logging (nach jedem Trade)
    # ------------------------------------------------------------------
    def log_trade(self, trade_data: dict, indicators: dict, ai_response: dict | None,
                  scan_results: list, final_action: str, confidence: float,
                  reasoning: str, balance_before: float, balance_after: float):
        """Speichert einen kompletten Trade mit allem Kontext."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "trade_number": trade_data.get("trade_number", 0),
            "asset": trade_data.get("asset", "?"),
            "action": final_action,
            "amount": trade_data.get("amount", 0),
            "status": trade_data.get("status", "?"),
            "confidence": confidence,
            "reasoning": reasoning,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "profit": balance_after - balance_before,
            # Voller Indikator-Snapshot
            "indicators": indicators,
            # KI-Antwort
            "ai_prediction": ai_response.get("prediction") if ai_response else None,
            "ai_confidence": ai_response.get("confidence") if ai_response else None,
            "ai_reasoning": ai_response.get("reasoning") if ai_response else None,
            "ai_override": ai_response.get("override_local", False) if ai_response else False,
            # Scan-Kontext (Top 3)
            "top_assets": [
                {"asset": r["asset"], "score": r["score"], "signal": r["signal"]}
                for r in scan_results[:3]
            ] if scan_results else [],
            # Score & Signal
            "score": trade_data.get("score", 0),
            "strategy": trade_data.get("strategy", "flat"),
        }

        self.data["trade_log"].append(entry)

        # Stats aktualisieren
        stats = self.data["stats"]
        stats["total_trades"] += 1
        if trade_data.get("status") == "win":
            stats["total_wins"] += 1
        else:
            stats["total_losses"] += 1

        # Asset-Pattern aktualisieren
        asset = trade_data.get("asset", "?")
        if asset not in self.data["asset_patterns"]:
            self.data["asset_patterns"][asset] = {
                "trades": 0, "wins": 0, "losses": 0,
                "best_indicators": {}, "avg_score_win": 0, "avg_score_loss": 0,
            }
        ap = self.data["asset_patterns"][asset]
        ap["trades"] += 1
        if trade_data.get("status") == "win":
            ap["wins"] += 1
        else:
            ap["losses"] += 1

        # Nur periodisch speichern (nicht nach jedem Trade)
        if stats["total_trades"] % 3 == 0:
            self.save()

    # ------------------------------------------------------------------
    # Kontext für Pre-Trade Analyse
    # ------------------------------------------------------------------
    def get_pre_trade_context(self, asset: str, current_indicators: dict) -> str:
        """Generiert Kontext aus dem Memory für die KI vor einem Trade.

        Enthält:
        - Gelernte Regeln
        - Asset-spezifische Patterns
        - Letzte Trades auf diesem Asset
        - Indikator-Gewichte
        """
        parts = []

        # 1. Gelernte Regeln (max 10 neueste)
        rules = self.data.get("learned_rules", [])
        if rules:
            parts.append("=== GELERNTE REGELN (aus vergangenen Sessions) ===")
            for rule in rules[-10:]:
                parts.append(f"  • [{rule.get('type', '?')}] {rule.get('rule', '?')}")
                if rule.get("confidence"):
                    parts.append(f"    Vertrauen: {rule['confidence']:.0%}")

        # 2. Asset-spezifische Patterns
        ap = self.data.get("asset_patterns", {}).get(asset, {})
        if ap.get("trades", 0) > 0:
            wr = ap["wins"] / ap["trades"] if ap["trades"] > 0 else 0
            parts.append(f"\n=== ASSET PATTERN: {asset} ===")
            parts.append(f"  Trades: {ap['trades']} | WR: {wr:.0%}")
            if ap.get("notes"):
                for note in ap["notes"][-5:]:
                    parts.append(f"  📝 {note}")

        # 3. Letzte Trades auf diesem Asset
        asset_trades = [t for t in self.data.get("trade_log", []) if t["asset"] == asset]
        if asset_trades:
            recent = asset_trades[-5:]
            parts.append(f"\n=== LETZTE {len(recent)} TRADES AUF {asset} ===")
            for t in recent:
                emoji = "✅" if t["status"] == "win" else "❌"
                parts.append(
                    f"  {emoji} {t['action'].upper()} | Score:{t.get('score', '?')} "
                    f"| Conf:{t.get('confidence', '?'):.0%} "
                    f"| {t.get('reasoning', '')[:60]}"
                )

        # 4. Aktuelle Indikator-Gewichte
        weights = self.data.get("indicator_weights", DEFAULT_WEIGHTS)
        modified = {k: v for k, v in weights.items() if v != 1.0}
        if modified:
            parts.append("\n=== ANGEPASSTE INDIKATOR-GEWICHTE ===")
            for k, v in modified.items():
                direction = "↑" if v > 1.0 else "↓"
                parts.append(f"  {k}: {v:.1f}x {direction}")

        # 5. Gesamtstatistiken
        stats = self.data.get("stats", {})
        if stats.get("total_trades", 0) > 0:
            overall_wr = stats["total_wins"] / stats["total_trades"]
            parts.append(f"\n=== GESAMTPERFORMANCE ===")
            parts.append(f"  {stats['total_trades']} Trades | WR: {overall_wr:.0%}")
            parts.append(f"  Sessions: {stats.get('total_sessions', 0)}")

        # 6. Letzte Session-Review Zusammenfassung
        reviews = self.data.get("session_reviews", [])
        if reviews:
            last_review = reviews[-1]
            parts.append(f"\n=== LETZTE SESSION-ANALYSE ===")
            if last_review.get("key_learnings"):
                for learning in last_review["key_learnings"][:5]:
                    parts.append(f"  💡 {learning}")

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Post-Session Review Prompt
    # ------------------------------------------------------------------
    def build_review_prompt(self, session_trades: list, start_balance: float,
                            end_balance: float) -> str:
        """Baut den Prompt für die Post-Session KI-Analyse."""
        wins = sum(1 for t in session_trades if t.get("status") == "win")
        losses = sum(1 for t in session_trades if t.get("status") == "loss")
        profit = end_balance - start_balance

        # Volle Trade-Details für die Analyse
        trade_details = []
        for t in session_trades:
            detail = {
                "nr": t.get("trade_number", "?"),
                "asset": t.get("asset", "?"),
                "action": t.get("action", "?"),
                "status": t.get("status", "?"),
                "score": t.get("score", 0),
                "confidence": t.get("confidence", 0),
                "reasoning": t.get("reasoning", ""),
                "indicators": t.get("indicators", {}),
                "ai_prediction": t.get("ai_prediction"),
                "ai_confidence": t.get("ai_confidence"),
                "ai_reasoning": t.get("ai_reasoning"),
                "profit": t.get("profit", 0),
            }
            trade_details.append(detail)

        # Bisherige Regeln mitgeben
        existing_rules = self.data.get("learned_rules", [])
        existing_weights = self.data.get("indicator_weights", DEFAULT_WEIGHTS)

        return f"""POST-SESSION ANALYSE — Selbstlernende Trading-KI

=== SESSION ERGEBNIS ===
Trades: {len(session_trades)} | Wins: {wins} | Losses: {losses}
Win Rate: {wins/len(session_trades):.0%}
Start-Balance: ${start_balance:.2f} | End-Balance: ${end_balance:.2f}
Profit: ${profit:+.2f}

=== ALLE TRADES DIESER SESSION ===
{json.dumps(trade_details, indent=1, default=str)}

=== AKTUELLE INDIKATOR-GEWICHTE ===
{json.dumps(existing_weights, indent=1)}

=== BISHERIGE GELERNTE REGELN ({len(existing_rules)}) ===
{json.dumps(existing_rules[-10:], indent=1, default=str) if existing_rules else 'Keine — erste Session!'}

DEINE AUFGABEN:
1. ANALYSIERE jeden einzelnen Trade: Warum hat er gewonnen/verloren?
2. ERKENNE Muster: Welche Indikatoren waren zuverlässig, welche nicht?
3. LERNE daraus: Formuliere konkrete Regeln für die Zukunft
4. PASSE Indikator-Gewichte an: Welche Indikatoren sollten stärker/schwächer gewichtet werden?
5. SCHLAGE neue Strategien vor: Was könnte die Performance verbessern?

ANTWORT NUR ALS JSON:
{{{{
  "session_summary": "Kurze Zusammenfassung der Session",
  "trade_analysis": [
    {{{{
      "trade_nr": 1,
      "was_correct": true/false,
      "why": "Erklärung warum der Trade gut/schlecht war",
      "what_to_improve": "Was hätte besser sein können"
    }}}}
  ],
  "key_learnings": [
    "Konkretes Learning 1",
    "Konkretes Learning 2"
  ],
  "new_rules": [
    {{{{
      "type": "entry"/"exit"/"risk"/"indicator",
      "rule": "Konkrete Regel in einem Satz",
      "confidence": 0.0-1.0,
      "based_on": "Aus welchen Trades abgeleitet"
    }}}}
  ],
  "indicator_weight_changes": {{{{
    "rsi": 1.0,
    "macd": 1.2,
    "bollinger": 0.8
  }}}},
  "strategy_suggestions": [
    "Vorschlag 1",
    "Vorschlag 2"
  ],
  "asset_notes": {{{{
    "EURUSD_otc": "Notiz über dieses Asset basierend auf den Trades"
  }}}}
}}}}"""

    # ------------------------------------------------------------------
    # Review-Ergebnis verarbeiten
    # ------------------------------------------------------------------
    def apply_review(self, review: dict, session_trades: list):
        """Wendet die KI-Analyse auf die Memory an."""

        timestamp = datetime.now().isoformat()

        # 1. Session Review speichern
        self.data["session_reviews"].append({
            "timestamp": timestamp,
            "trades": len(session_trades),
            "summary": review.get("session_summary", ""),
            "key_learnings": review.get("key_learnings", []),
            "trade_analysis": review.get("trade_analysis", []),
            "strategy_suggestions": review.get("strategy_suggestions", []),
        })
        self.data["stats"]["total_sessions"] += 1

        # 2. Neue Regeln hinzufügen
        new_rules = review.get("new_rules", [])
        for rule in new_rules:
            rule["added_at"] = timestamp
            rule["source_session"] = self.data["stats"]["total_sessions"]
            self.data["learned_rules"].append(rule)
        if new_rules:
            logger.info("AI Memory: %d neue Regeln gelernt", len(new_rules))

        # 3. Indikator-Gewichte anpassen (sanft — maximal ±0.3 pro Session)
        weight_changes = review.get("indicator_weight_changes", {})
        current_weights = self.data["indicator_weights"]
        changes_applied = []
        for indicator, new_weight in weight_changes.items():
            if indicator in current_weights:
                old = current_weights[indicator]
                # Limitiere Änderung auf ±0.3 pro Session
                delta = max(-0.3, min(0.3, new_weight - old))
                adjusted = max(0.2, min(2.5, old + delta))  # Absolute Grenzen
                if abs(adjusted - old) > 0.01:
                    current_weights[indicator] = round(adjusted, 2)
                    changes_applied.append(f"{indicator}: {old:.1f} → {adjusted:.1f}")

        if changes_applied:
            self.data["config_evolution"].append({
                "timestamp": timestamp,
                "type": "weight_adjustment",
                "changes": changes_applied,
            })
            logger.info("AI Memory: Gewichte angepasst: %s", ", ".join(changes_applied))

        # 4. Asset-Notizen aktualisieren
        asset_notes = review.get("asset_notes", {})
        for asset, note in asset_notes.items():
            if asset not in self.data["asset_patterns"]:
                self.data["asset_patterns"][asset] = {
                    "trades": 0, "wins": 0, "losses": 0,
                    "notes": [],
                }
            ap = self.data["asset_patterns"][asset]
            if "notes" not in ap:
                ap["notes"] = []
            ap["notes"].append(f"[{timestamp[:10]}] {note}")
            # Max 20 Notizen pro Asset
            ap["notes"] = ap["notes"][-20:]

        # 5. Regeln aufräumen (max 50, älteste mit niedrigster Confidence entfernen)
        rules = self.data["learned_rules"]
        if len(rules) > 50:
            rules.sort(key=lambda r: r.get("confidence", 0.5))
            self.data["learned_rules"] = rules[-50:]

        self.save()
        return changes_applied

    # ------------------------------------------------------------------
    # Indikator-Gewichte abrufen
    # ------------------------------------------------------------------
    def get_weights(self) -> dict:
        """Gibt die aktuellen Indikator-Gewichte zurück."""
        return self.data.get("indicator_weights", dict(DEFAULT_WEIGHTS))

    # ------------------------------------------------------------------
    # Pre-Trade Analyse (KI analysiert VOR dem Trade)
    # ------------------------------------------------------------------
    def build_pretrade_analysis_prompt(self, trade_nr: int, asset: str,
                                       indicators: dict, score: int,
                                       recent_trades: list) -> str:
        """Prompt für die Vor-Trade-Analyse basierend auf Memory."""
        # Letzten Trade auf gleichem Asset finden
        last_same_asset = None
        for t in reversed(self.data.get("trade_log", [])):
            if t["asset"] == asset:
                last_same_asset = t
                break

        context = ""
        if last_same_asset:
            emoji = "✅" if last_same_asset["status"] == "win" else "❌"
            context = (
                f"\nLetzter Trade auf {asset}: {emoji} {last_same_asset['action'].upper()} "
                f"Score:{last_same_asset.get('score', '?')} "
                f"Indikatoren damals: {json.dumps(last_same_asset.get('indicators', {}), default=str)[:200]}"
            )

        return context

    # ------------------------------------------------------------------
    # Zusammenfassung der gelernten Regeln für Telegram
    # ------------------------------------------------------------------
    def get_rules_summary(self) -> str:
        """Formatierte Zusammenfassung für /memory Telegram-Befehl."""
        rules = self.data.get("learned_rules", [])
        weights = self.data.get("indicator_weights", DEFAULT_WEIGHTS)
        stats = self.data.get("stats", {})
        reviews = self.data.get("session_reviews", [])

        lines = ["🧠 *AI Memory Status*\n"]

        # Stats
        total = stats.get("total_trades", 0)
        if total > 0:
            wr = stats.get("total_wins", 0) / total
            lines.append(f"📊 {total} Trades | WR: {wr:.0%} | {stats.get('total_sessions', 0)} Sessions\n")

        # Gewichte die von 1.0 abweichen
        modified = {k: v for k, v in weights.items() if abs(v - 1.0) > 0.05}
        if modified:
            lines.append("⚖️ *Angepasste Gewichte:*")
            for k, v in sorted(modified.items(), key=lambda x: x[1], reverse=True):
                arrow = "↑" if v > 1.0 else "↓"
                lines.append(f"  {k}: {v:.1f}x {arrow}")
            lines.append("")

        # Letzte Regeln
        if rules:
            lines.append(f"📝 *Gelernte Regeln ({len(rules)}):*")
            for r in rules[-5:]:
                lines.append(f"  • {r.get('rule', '?')[:80]}")
            lines.append("")

        # Letzte Session
        if reviews:
            last = reviews[-1]
            lines.append(f"📋 *Letzte Session-Analyse:*")
            lines.append(f"  {last.get('summary', 'Keine')[:120]}")

        return "\n".join(lines) if len(lines) > 1 else "🧠 Noch keine Daten — starte eine Trading-Session!"
"""
