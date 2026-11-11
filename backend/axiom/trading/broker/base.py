"""The broker seam. Only the engine talks to a broker, and only with sizes the kernel approved."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import AccountState, Order, OrderRequest


class BrokerError(Exception):
    pass


@runtime_checkable
class Broker(Protocol):
    name: str
    is_paper: bool

    async def account(self) -> AccountState: ...

    async def submit(self, req: OrderRequest) -> Order:
        """Send an order. For a buy with `stop_price`, the broker also holds a protective stop once it fills."""
        ...

    async def close(self, symbol: str, reason: str = "") -> Order | None:
        """Sell the whole position and cancel its open orders. None if there is nothing to close."""
        ...

    async def flatten_all(self, reason: str = "") -> list[Order]:
        """Cancel every open order and close every position."""
        ...

    async def poll(self) -> list[Order]:
        """Orders that changed state since the last call: fills, partial fills, stops the broker triggered."""
        ...

    async def last_price(self, symbol: str) -> float | None: ...
