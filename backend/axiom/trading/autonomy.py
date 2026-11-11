"""The earned autonomy ladder: SHADOW (decides, trades nothing) -> SUPERVISED (a human approves each entry)
-> AUTONOMOUS. The agent climbs on graded trade contracts and falls on bad days.

Promotion (evidence counts only contracts graded since the last level change):
  SHADOW -> SUPERVISED      >= 8 graded shadow contracts, Brier <= 0.25, net return > 0
  SUPERVISED -> AUTONOMOUS  >= 12 graded real contracts, Brier <= 0.24, net return > 0
Demotion (one level at a time):
  a daily loss halt; the last 10 graded contracts with Brier > 0.30; 4 losing contracts in a row.

A human can set any level. A human-set level is also a ceiling: the ladder may demote below it but never
promotes above it until the human releases the lock.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .contracts import calibration
from .models import AUTONOMY_LEVELS, Autonomy

if TYPE_CHECKING:
    from .engine import Engine


@dataclass
class LadderConfig:
    shadow_min: int = 8
    shadow_max_brier: float = 0.25
    supervised_min: int = 12
    supervised_max_brier: float = 0.24
    demote_window: int = 10
    demote_brier: float = 0.30
    demote_losing_streak: int = 4


def _up(level: Autonomy) -> Autonomy | None:
    i = AUTONOMY_LEVELS.index(level)
    return AUTONOMY_LEVELS[i + 1] if i + 1 < len(AUTONOMY_LEVELS) else None


def _down(level: Autonomy) -> Autonomy | None:
    i = AUTONOMY_LEVELS.index(level)
    return AUTONOMY_LEVELS[i - 1] if i > 0 else None


class AutonomyLadder:
    def __init__(self, cfg: LadderConfig | None = None):
        self.cfg = cfg or LadderConfig()

    # --------------------------------------------------------------- state
    def _state(self, eng: Engine) -> dict:
        return {"since": None, "ceiling": None, **(eng.ledger.get_state("ladder") or {})}

    def _save(self, eng: Engine, st: dict) -> None:
        eng.ledger.set_state("ladder", st)

    def _move(self, eng: Engine, level: Autonomy, why: str, now: float) -> None:
        st = self._state(eng)
        st["since"] = now
        self._save(eng, st)
        eng.set_autonomy(level, why, now)

    # ------------------------------------------------------------- evidence
    def _graded_since(self, eng: Engine, since: float | None) -> list[dict]:
        rows = [
            c for c in eng.ledger.contracts(status="graded") if c.get("result") and not c.get("vetoed_by")
        ]
        if since is not None:
            rows = [c for c in rows if c["result"]["ts"] >= since]
        return sorted(rows, key=lambda c: c["result"]["ts"])

    def progress(self, eng: Engine) -> dict[str, Any]:
        st = self._state(eng)
        level, cfg = eng.level, self.cfg
        rows = self._graded_since(eng, st["since"])
        if level == "SHADOW":
            evidence, need, max_brier = [c for c in rows if c["shadow"]], cfg.shadow_min, cfg.shadow_max_brier
        elif level == "SUPERVISED":
            evidence = [c for c in rows if not c["shadow"]]
            need, max_brier = cfg.supervised_min, cfg.supervised_max_brier
        else:
            evidence, need, max_brier = [], 0, None
        cal = calibration(evidence)
        nxt = _up(level)
        ceiling = st["ceiling"]
        locked = bool(ceiling and nxt and AUTONOMY_LEVELS.index(nxt) > AUTONOMY_LEVELS.index(ceiling))
        ready = (
            nxt is not None
            and not locked
            and cal["n"] >= need
            and cal["brier"] is not None
            and cal["brier"] <= (max_brier or 0)
            and cal["net_return_pct"] > 0
        )
        return {
            "level": level, "next": nxt, "ceiling": ceiling, "locked": locked, "since": st["since"],
            "have": cal["n"], "need": need, "brier": cal["brier"], "max_brier": max_brier,
            "net_return_pct": cal["net_return_pct"], "ready": ready, "rules": asdict(cfg),
        }  # fmt: skip

    # --------------------------------------------------------------- events
    def on_graded(self, eng: Engine, now: float) -> None:
        if self._maybe_demote(eng, now):
            return
        p = self.progress(eng)
        if p["ready"]:
            evidence = "shadow" if p["level"] == "SHADOW" else "real"
            self._move(eng, p["next"], f"{p['have']} graded {evidence} contracts since the last change, Brier "
                       f"{p['brier']:.2f} (needs <= {p['max_brier']:.2f}), net {p['net_return_pct']:+.2f}%.", now)  # fmt: skip

    def _maybe_demote(self, eng: Engine, now: float) -> bool:
        lower = _down(eng.level)
        if lower is None:
            return False
        st = self._state(eng)
        rows = self._graded_since(eng, st["since"])
        cfg = self.cfg
        recent = rows[-cfg.demote_window :]
        if len(recent) >= cfg.demote_window:
            b = calibration(recent)["brier"]
            if b is not None and b > cfg.demote_brier:
                self._move(eng, lower, f"the last {len(recent)} contracts scored Brier {b:.2f}, worse than "
                           f"{cfg.demote_brier:.2f}: its confidence is not trustworthy.", now)  # fmt: skip
                return True
        streak = 0
        for c in reversed(rows):
            if c["result"]["outcome"]:
                break
            streak += 1
        if streak >= cfg.demote_losing_streak:
            self._move(eng, lower, f"{streak} losing contracts in a row.", now)
            return True
        return False

    def on_halt(self, eng: Engine, now: float) -> None:
        lower = _down(eng.level)
        if lower is not None:
            self._move(eng, lower, "the daily loss limit was hit.", now)

    def human_set(self, eng: Engine, level: Autonomy, now: float, *, lock: bool = True) -> None:
        """A human picks the level. With `lock`, it is also the ceiling for automatic promotion."""
        st = self._state(eng)
        st["ceiling"] = level if lock else None
        st["since"] = now
        self._save(eng, st)
        eng.set_autonomy(level, f"set by a human{' (locked as the ceiling)' if lock else ''}.", now)

    def release(self, eng: Engine) -> None:
        st = self._state(eng)
        st["ceiling"] = None
        self._save(eng, st)
