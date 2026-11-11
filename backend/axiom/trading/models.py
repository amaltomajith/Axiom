"""Plain data shared by the kernel, brokers, engine and API. No I/O here."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

AssetKind = Literal["crypto", "equity"]
Side = Literal["buy", "sell"]
IntentAction = Literal["enter_long", "exit"]
IntentSource = Literal["rule", "llm", "desk", "human", "redteam"]
OrderStatus = Literal["new", "filled", "partially_filled", "canceled", "rejected"]
Autonomy = Literal["SHADOW", "SUPERVISED", "AUTONOMOUS"]
AUTONOMY_LEVELS: tuple[Autonomy, ...] = ("SHADOW", "SUPERVISED", "AUTONOMOUS")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class Bar(BaseModel):
    ts: float  # bar close time, unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class OrderIntent(BaseModel):
    """What the brain wants. It has no quantity: sizing belongs to the kernel."""

    symbol: str
    action: IntentAction
    stop_price: float | None = None  # mandatory for entries
    reason: str = ""
    strategy: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: IntentSource = "rule"
    # The red-team button, a human or the desk may ask for a size; the kernel blocks anything above its own.
    requested_qty: float | None = Field(default=None, gt=0)
    contract_id: str | None = None


class RuleCheck(BaseModel):
    rule: str
    ok: bool
    detail: str


class RiskVerdict(BaseModel):
    approved: bool
    needs_approval: bool = False  # SUPERVISED: a human must approve before it reaches the broker
    qty: float = 0.0
    price: float = 0.0
    stop_price: float | None = None
    notional: float = 0.0
    risk_amount: float = 0.0
    blocked_by: str | None = None
    reason: str = ""
    checks: list[RuleCheck] = Field(default_factory=list)


class OrderRequest(BaseModel):
    symbol: str
    side: Side
    qty: float = Field(gt=0)
    stop_price: float | None = None  # protective stop the broker should hold after an entry fills
    client_order_id: str = Field(default_factory=lambda: new_id("ax-"))
    reason: str = ""


class Order(BaseModel):
    id: str  # our client_order_id
    symbol: str
    side: Side
    qty: float
    status: OrderStatus = "new"
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    fee: float = 0.0
    stop_price: float | None = None
    reason: str = ""
    broker_id: str | None = None
    submitted_at: float = Field(default_factory=time.time)
    filled_at: float | None = None
    realized_pl: float | None = None  # on exits
    error: str | None = None


class Position(BaseModel):
    symbol: str
    qty: float
    avg_entry: float
    market_price: float
    stop_price: float | None = None
    opened_at: float | None = None
    strategy: str | None = None
    contract_id: str | None = None

    @property
    def market_value(self) -> float:
        return self.qty * self.market_price

    @property
    def unrealized_pl(self) -> float:
        return (self.market_price - self.avg_entry) * self.qty


class AccountState(BaseModel):
    equity: float
    cash: float
    positions: dict[str, Position] = Field(default_factory=dict)
    is_paper: bool = True
    broker: str = "sim"

    def exposure(self) -> dict[str, float]:
        return {s: p.market_value for s, p in self.positions.items()}


class JournalEntry(BaseModel):
    session: str
    seq: int
    ts: float
    kind: str  # entry | exit | blocked | stop | halt | kill | resume | decision | contract | autonomy | note
    symbol: str | None = None
    text: str
    facts: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""
