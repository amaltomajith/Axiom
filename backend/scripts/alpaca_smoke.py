"""Settle the Alpaca facts the docs left open, on the real PAPER account. Run it once before a demo.

    cd backend && uv run python scripts/alpaca_smoke.py            # read-only checks
    cd backend && uv run python scripts/alpaca_smoke.py --trade    # also a ~$10 BTC/USD round trip with a stop

Reads ALPACA_API_KEY / ALPACA_SECRET_KEY from the environment or backend/.env. Paper only: the client is
created with paper=True and there is no flag to change it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from axiom.config import get_settings  # noqa: E402
from axiom.trading.broker.alpaca import AlpacaPaperBroker  # noqa: E402
from axiom.trading.models import OrderRequest  # noqa: E402


def ok(label: str, value) -> None:
    print(f"  {label:<34} {value}")


async def main(trade: bool) -> int:
    s = get_settings()
    if not (s.alpaca_api_key and s.alpaca_secret_key):
        print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY (paper keys) in backend/.env first.")
        return 2
    b = AlpacaPaperBroker(s.alpaca_api_key, s.alpaca_secret_key)
    print("Account")
    pre = await b.preflight()
    for k, v in pre.items():
        ok(k, v)
    if pre["crypto_status"].upper() != "ACTIVE":
        print("  !! crypto_status is not ACTIVE: the 24/7 crypto demo will not trade on this account.")
    print("Market")
    ok("US equity market open now", await b.market_open())
    ok("BTC/USD last trade", await b.last_price("BTC/USD"))
    ok("SPY last trade (IEX)", await b.last_price("SPY"))
    acct = await b.account()
    ok("equity / cash", f"{acct.equity:,.2f} / {acct.cash:,.2f}")
    ok("open positions", list(acct.positions))
    if not trade:
        print("Read-only checks done. Add --trade for a ~$10 BTC/USD round trip.")
        return 0

    print("Round trip: buy ~$10 of BTC/USD, place the stop-limit, then close")
    px = await b.last_price("BTC/USD")
    if not px:
        print("  no BTC/USD price; aborting")
        return 1
    qty = round(10 / px, 6)
    order = await b.submit(
        OrderRequest(symbol="BTC/USD", side="buy", qty=qty, stop_price=round(px * 0.97, 2))
    )
    ok("submitted", f"{order.id} status={order.status} error={order.error}")
    for _ in range(20):
        await asyncio.sleep(1)
        for o in await b.poll():
            ok("update", f"{o.id} {o.side} {o.status} filled={o.filled_qty} @ {o.filled_avg_price}")
        if "BTC/USD" in b._stops:
            break
    ok("stop order placed", b._stops.get("BTC/USD"))
    closed = await b.close("BTC/USD", "smoke test")
    ok("close", None if closed is None else f"{closed.id} {closed.status} {closed.error or ''}")
    await asyncio.sleep(2)
    for o in await b.poll():
        ok("update", f"{o.id} {o.side} {o.status} filled={o.filled_qty} @ {o.filled_avg_price}")
    acct = await b.account()
    ok("BTC/USD still held", "BTC/USD" in acct.positions)
    print(
        "Check the orders in the Alpaca dashboard. Crypto fees show up as CFEE activities at end of day, if charged."
    )
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--trade", action="store_true")
    sys.exit(asyncio.run(main(p.parse_args().trade)))
