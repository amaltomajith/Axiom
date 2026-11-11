"""One symbol, three spellings: Alpaca orders use `BTC/USD`, Alpaca positions report `BTCUSD`, Yahoo wants `BTC-USD`."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AssetKind

CRYPTO_BASES = {
    "BTC",
    "ETH",
    "SOL",
    "LTC",
    "DOGE",
    "AVAX",
    "LINK",
    "UNI",
    "AAVE",
    "BCH",
    "XRP",
    "DOT",
    "SHIB",
}
_EQUITY_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


@dataclass(frozen=True)
class Symbol:
    name: str  # canonical: "BTC/USD" or "SPY"
    kind: AssetKind

    @property
    def alpaca_position(self) -> str:
        return self.name.replace("/", "")

    @property
    def yahoo(self) -> str:
        return self.name.replace("/", "-")

    @property
    def is_crypto(self) -> bool:
        return self.kind == "crypto"


def parse(raw: str) -> Symbol:
    s = raw.strip().upper().replace("-", "/")
    if "/" in s:
        base, quote = s.split("/", 1)
        if base in CRYPTO_BASES and quote in ("USD", "USDT", "USDC"):
            return Symbol(f"{base}/{quote}", "crypto")
        raise ValueError(f"Unknown crypto pair {raw!r}")
    for quote in ("USDT", "USDC", "USD"):
        if s.endswith(quote) and s[: -len(quote)] in CRYPTO_BASES:
            return Symbol(f"{s[: -len(quote)]}/{quote}", "crypto")
    if _EQUITY_RE.match(s):
        return Symbol(s, "equity")
    raise ValueError(f"Not a valid symbol: {raw!r}")


def parse_list(raw: str) -> list[Symbol]:
    out: list[Symbol] = []
    for part in raw.split(","):
        if part.strip():
            sym = parse(part)
            if sym not in out:
                out.append(sym)
    return out
