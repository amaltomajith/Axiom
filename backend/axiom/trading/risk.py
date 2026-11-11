"""The Risk Kernel: deterministic rules between every decision and the broker.

Pure functions, no I/O, no LLM. The brain proposes an `OrderIntent` without a quantity; the kernel either
sizes it or blocks it, and says which rule decided. Exits that reduce risk are always allowed, even while
killed or halted, because refusing to sell is never the safe choice.

Rules (entries only):
  R0  kill switch is off            R7   position <= max_position_pct of equity
  R1  broker is a paper account     R8   gross exposure <= max_gross_pct, paid from cash (no margin)
  R2  symbol is on the allowlist    R9   open positions < max_open_positions
  R3  daily loss limit not hit      R10  entries today < max_trades_per_day
  R4  market data is fresh          R11  no re-entry within cooldown_bars of a stop-out
  R5  stop is set, below price and  R12  the autonomy level permits trading
      min_stop_pct..max_stop_pct away
  R6  the kernel sizes the trade at risk_per_trade of equity (a request for more is refused)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from axiom.quant.risk import check_limits, size_position

from .models import AccountState, AssetKind, Autonomy, OrderIntent, RiskVerdict, RuleCheck

RULE_NAMES = {
    "R0": "Kill switch",
    "R1": "Paper account only",
    "R2": "Symbol allowlist",
    "R3": "Daily loss limit",
    "R4": "Fresh market data",
    "R5": "Mandatory stop-loss",
    "R6": "Kernel sizes the trade",
    "R7": "Max position size",
    "R8": "Gross exposure, cash only",
    "R9": "Max open positions",
    "R10": "Max trades per day",
    "R11": "Cooldown after a stop-out",
    "R12": "Autonomy level",
}


@dataclass(frozen=True)
class RiskLimits:
    daily_loss_limit_pct: float = 0.025
    risk_per_trade: float = 0.01
    max_position_pct: float = 0.20
    max_gross_pct: float = 1.0
    max_open_positions: int = 4
    max_trades_per_day: int = 10
    min_stop_pct: float = 0.002
    max_stop_pct: float = 0.15
    cooldown_bars: int = 3
    min_notional: float = 10.0
    allowlist: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_settings(cls, s, allowlist: list[str]) -> RiskLimits:
        return cls(
            daily_loss_limit_pct=s.trader_daily_loss_limit_pct,
            risk_per_trade=s.trader_risk_per_trade,
            max_position_pct=s.trader_max_position_pct,
            max_gross_pct=s.trader_max_gross_pct,
            max_open_positions=s.trader_max_open_positions,
            max_trades_per_day=s.trader_max_trades_per_day,
            min_stop_pct=s.trader_min_stop_pct,
            max_stop_pct=s.trader_max_stop_pct,
            cooldown_bars=s.trader_cooldown_bars,
            allowlist=frozenset(allowlist),
        )

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "allowlist"}
        d["allowlist"] = sorted(self.allowlist)
        return d


@dataclass
class RiskContext:
    """Everything outside the intent and the account that a rule needs. Built by the engine each tick."""

    now: float
    price: float
    kind: AssetKind
    day_start_equity: float
    killed: bool = False
    halted: str | None = None
    trades_today: int = 0
    last_stopout: float | None = None  # when this symbol last stopped out
    bar_seconds: float = 86_400
    data_age_seconds: float = 0.0
    max_data_age_seconds: float = 3 * 86_400
    autonomy: Autonomy = "AUTONOMOUS"
    broker_is_paper: bool = True


def daily_pl_pct(equity: float, day_start_equity: float) -> float:
    return (equity - day_start_equity) / day_start_equity if day_start_equity > 0 else 0.0


def daily_loss_breached(equity: float, day_start_equity: float, limit_pct: float) -> bool:
    return daily_pl_pct(equity, day_start_equity) <= -abs(limit_pct)


def _floor(x: float, decimals: int) -> float:
    f = 10**decimals
    return math.floor(x * f + 1e-9) / f


def _qty(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.6f}".rstrip("0").rstrip(".")


class RiskKernel:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    # ------------------------------------------------------------------ public
    def review(self, intent: OrderIntent, account: AccountState, ctx: RiskContext) -> RiskVerdict:
        if intent.action == "exit":
            return self._review_exit(intent, account, ctx)
        return self._review_entry(intent, account, ctx)

    # ------------------------------------------------------------------- exits
    def _review_exit(self, intent: OrderIntent, account: AccountState, ctx: RiskContext) -> RiskVerdict:
        pos = account.positions.get(intent.symbol)
        if pos is None or pos.qty <= 0:
            check = RuleCheck(rule="EXIT", ok=False, detail=f"No open position in {intent.symbol} to exit.")
            return RiskVerdict(approved=False, blocked_by="EXIT", reason=check.detail, checks=[check])
        check = RuleCheck(rule="EXIT", ok=True, detail="Exits that reduce risk are always allowed.")
        return RiskVerdict(
            approved=True,
            qty=pos.qty,
            price=ctx.price,
            notional=round(pos.qty * ctx.price, 2),
            reason=check.detail,
            checks=[check],
        )

    # ----------------------------------------------------------------- entries
    def _review_entry(self, intent: OrderIntent, account: AccountState, ctx: RiskContext) -> RiskVerdict:
        lim = self.limits
        checks: list[RuleCheck] = []

        def add(rule: str, ok: bool, detail: str) -> bool:
            checks.append(RuleCheck(rule=rule, ok=ok, detail=detail))
            return ok

        add("R0", not ctx.killed, "Kill switch is engaged." if ctx.killed else "Kill switch is off.")
        add(
            "R1",
            ctx.broker_is_paper and account.is_paper,
            "Paper account."
            if ctx.broker_is_paper and account.is_paper
            else "Refusing: not a paper account.",
        )
        on_list = not lim.allowlist or intent.symbol in lim.allowlist
        add("R2", on_list, f"{intent.symbol} is {'on' if on_list else 'not on'} the allowlist.")
        pl = daily_pl_pct(account.equity, ctx.day_start_equity)
        hit = ctx.halted is not None or pl <= -lim.daily_loss_limit_pct
        add(
            "R3",
            not hit,
            f"Halted: {ctx.halted}."
            if ctx.halted
            else f"Today's P&L is {pl:+.2%} against a limit of -{lim.daily_loss_limit_pct:.2%}.",
        )
        fresh = ctx.data_age_seconds <= ctx.max_data_age_seconds
        add("R4", fresh, f"Latest bar is {ctx.data_age_seconds / 60:.0f} minutes old.")
        stop_ok, stop_detail = self._stop_ok(intent.stop_price, ctx.price)
        add("R5", stop_ok, stop_detail)
        n_open = sum(1 for p in account.positions.values() if p.qty > 0)
        held = intent.symbol in account.positions and account.positions[intent.symbol].qty > 0
        add(
            "R9",
            n_open < lim.max_open_positions and not held,
            f"Already holding {intent.symbol}; no adding to positions."
            if held
            else f"{n_open} open positions, limit {lim.max_open_positions}.",
        )
        add(
            "R10",
            ctx.trades_today < lim.max_trades_per_day,
            f"{ctx.trades_today} entries today, limit {lim.max_trades_per_day}.",
        )
        cooling = (
            ctx.last_stopout is not None
            and (ctx.now - ctx.last_stopout) < lim.cooldown_bars * ctx.bar_seconds
        )
        add(
            "R11",
            not cooling,
            f"{intent.symbol} stopped out recently; cooling down for {lim.cooldown_bars} bars."
            if cooling
            else "No recent stop-out.",
        )
        level_ok = ctx.autonomy != "SHADOW" or intent.source == "human"
        add(
            "R12",
            level_ok,
            "Shadow mode: the decision is logged, nothing is traded."
            if not level_ok
            else f"Autonomy level {ctx.autonomy}.",
        )

        sized: dict | None = None
        if stop_ok:
            sized = self._size(intent, account, ctx)
            add(sized.get("rule", "R6"), sized["ok"], sized["detail"])
            if sized["ok"]:
                notional = sized["qty"] * ctx.price
                pos_issue = check_limits({intent.symbol: notional}, account.equity, lim.max_position_pct, 1e9)
                add(
                    "R7",
                    not pos_issue,
                    pos_issue[0] if pos_issue else f"{notional / account.equity:.1%} of equity.",
                )
                gross = {**account.exposure(), intent.symbol: notional}
                gross_issue = check_limits(gross, account.equity, 1e9, lim.max_gross_pct)
                cash_ok = notional <= account.cash + 1e-6
                add(
                    "R8",
                    not gross_issue and cash_ok,
                    gross_issue[0]
                    if gross_issue
                    else (
                        f"Gross exposure {sum(gross.values()) / account.equity:.0%}, paid from cash."
                        if cash_ok
                        else "Not enough cash; margin is never used."
                    ),
                )

        order = ["R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12"]
        checks.sort(key=lambda c: order.index(c.rule))
        failed = next((c for c in checks if not c.ok), None)
        if failed is not None:
            return RiskVerdict(
                approved=False,
                price=ctx.price,
                stop_price=intent.stop_price,
                blocked_by=failed.rule,
                reason=f"{RULE_NAMES[failed.rule]}: {failed.detail}",
                checks=checks,
            )
        assert sized is not None
        qty = sized["qty"]
        return RiskVerdict(
            approved=True,
            needs_approval=ctx.autonomy == "SUPERVISED" and intent.source != "human",
            qty=qty,
            price=ctx.price,
            stop_price=intent.stop_price,
            notional=round(qty * ctx.price, 2),
            risk_amount=round(qty * (ctx.price - (intent.stop_price or 0)), 2),
            reason=sized["detail"],
            checks=checks,
        )

    # ----------------------------------------------------------------- helpers
    def _stop_ok(self, stop: float | None, price: float) -> tuple[bool, str]:
        lim = self.limits
        if stop is None:
            return False, "No stop-loss given; every entry needs one."
        if price <= 0 or stop >= price:
            return False, f"Stop {stop:,.2f} must be below the price {price:,.2f}."
        dist = (price - stop) / price
        if dist < lim.min_stop_pct:
            return False, f"Stop is {dist:.2%} away; minimum {lim.min_stop_pct:.2%} (noise would trigger it)."
        if dist > lim.max_stop_pct:
            return False, f"Stop is {dist:.2%} away; maximum {lim.max_stop_pct:.0%}."
        return True, f"Stop at {stop:,.2f}, {dist:.2%} below {price:,.2f}."

    def _size(self, intent: OrderIntent, account: AccountState, ctx: RiskContext) -> dict:
        """Size at `risk_per_trade` of equity to the stop, then cap by position size, gross room and cash."""
        lim = self.limits
        assert intent.stop_price is not None
        dist = ctx.price - intent.stop_price
        if account.equity <= 0:
            return {"ok": False, "qty": 0.0, "detail": "Equity is not positive."}
        gross_room = lim.max_gross_pct * account.equity - sum(account.exposure().values())
        cash_room = account.cash * 0.995  # leave room for fees
        room_qty = max(0.0, min(gross_room, cash_room)) / ctx.price
        if ctx.kind == "equity":
            s = size_position(
                account.equity, ctx.price, dist, lim.risk_per_trade, 1.0, lim.max_position_pct
            )  # atr=dist with a 1x multiple puts the stop exactly at intent.stop_price
            qty = float(min(s["shares"], math.floor(room_qty)))
            binding = s["binding_constraint"]
        else:
            by_risk = account.equity * lim.risk_per_trade / dist
            by_cap = account.equity * lim.max_position_pct / ctx.price
            qty = _floor(min(by_risk, by_cap, room_qty), 6)
            binding = "risk_per_trade" if by_risk <= by_cap else "max_position_pct"
        if qty >= room_qty - 1e-6 and room_qty * ctx.price < account.equity * lim.max_position_pct:
            binding = "cash_or_gross_room"
        if room_qty * ctx.price < lim.min_notional:
            return {
                "ok": False,
                "rule": "R8",
                "qty": 0.0,
                "detail": f"Only {max(0.0, min(gross_room, cash_room)):,.2f} of cash and exposure room left; "
                "margin is never used.",
            }
        if qty * ctx.price < lim.min_notional:
            return {
                "ok": False,
                "qty": 0.0,
                "detail": f"Size would be {qty * ctx.price:,.2f}, below the {lim.min_notional:,.0f} minimum.",
            }
        if intent.requested_qty is not None and intent.requested_qty > qty + 1e-9:
            return {
                "ok": False,
                "qty": 0.0,
                "detail": f"Requested {_qty(intent.requested_qty)} but the risk budget allows {_qty(qty)}. "
                "The kernel sizes trades; requests can only be smaller.",
            }
        if intent.requested_qty is not None:
            qty = intent.requested_qty
        risk = qty * dist
        return {
            "ok": True,
            "qty": qty,
            "detail": f"{qty:g} units, risking {risk:,.2f} ({risk / account.equity:.2%} of equity) "
            f"to the stop; bound by {binding.replace('_', ' ')}.",
        }
