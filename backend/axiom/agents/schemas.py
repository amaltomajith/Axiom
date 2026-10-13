"""Structured outputs. Every claim carries evidence ids so it can be checked against real tool results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Stance = Literal["bullish", "bearish", "neutral", "insufficient_data"]
Rating = Literal["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL", "NO_CALL"]

RATING_ORDER: list[Rating] = ["STRONG_SELL", "SELL", "HOLD", "BUY", "STRONG_BUY"]


class Claim(BaseModel):
    text: str = Field(min_length=5, max_length=400)
    evidence: list[str] = Field(default_factory=list, description="Evidence ids such as T3")

    @field_validator("evidence", mode="before")
    @classmethod
    def _norm_ids(cls, v):
        return [str(x).strip().upper() for x in (v or [])]


class Finding(BaseModel):
    agent: str = ""
    stance: Stance
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=5, max_length=500)
    claims: list[Claim] = Field(min_length=1, max_length=8)
    caveats: list[str] = Field(default_factory=list, max_length=5)


class Critique(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list, max_length=6)


class Memo(BaseModel):
    ticker: str = ""
    rating: Rating
    conviction: float = Field(ge=0, le=1)
    horizon_days: int = Field(default=30, ge=1, le=365)
    thesis: str = Field(min_length=10, max_length=900)
    bull_case: list[Claim] = Field(min_length=1, max_length=4)
    bear_case: list[Claim] = Field(min_length=1, max_length=4)
    key_risks: list[str] = Field(min_length=1, max_length=5)
    what_would_change_my_mind: list[str] = Field(default_factory=list, max_length=4)
    prior_theses_addressed: str = ""

    @property
    def all_claims(self) -> list[Claim]:
        return [*self.bull_case, *self.bear_case]


class PositionPlan(BaseModel):
    """Deterministic output of the Risk Guard (never written by an LLM)."""

    action: Literal["open_long", "avoid", "none"]
    shares: int = 0
    entry_reference: float | None = None
    stop_price: float | None = None
    risk_amount: float | None = None
    position_pct: float | None = None
    violations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
