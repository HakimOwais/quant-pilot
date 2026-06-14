"""PaperBroker — the Broker port, simulated (SYSTEM_DESIGN §4: PaperBroker now, Kite later).

Stateful in-memory broker for paper trading and live-shaped testing. Fills market orders at the
current mark adjusted by the impact model (buy pays up, sell receives less) and charges the Indian
explicit cost stack; limit orders rest until marketable. Tracks cash, positions, and orders, and
honours a kill switch. Pre-trade portfolio/sector limits live in the API/risk layer; the broker
enforces buying power and the halt flag.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from quant_pilot.domain.models import (
    MarginInfo,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from quant_pilot.engine.backtest.costs import CostConfig, compute_costs
from quant_pilot.engine.backtest.impact import ImpactConfig, compute_impact


class PaperBroker:
    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        cost_config: CostConfig | None = None,
        impact_config: ImpactConfig | None = None,
    ) -> None:
        self.cash = initial_cash
        self.cost = cost_config or CostConfig()
        self.impact = impact_config or ImpactConfig()
        self._positions: dict[str, list[float]] = {}  # symbol -> [shares, avg_price]
        self._orders: dict[str, Order] = {}
        self._marks: dict[str, float] = {}
        self.halted = False

    # --- market data / controls --------------------------------------------

    def set_mark(self, symbol: str, price: float) -> None:
        self._marks[symbol] = price
        self._process_pending()

    def update_marks(self, prices: dict[str, float]) -> None:
        self._marks.update(prices)
        self._process_pending()

    def halt(self) -> None:
        self.halted = True

    def resume(self) -> None:
        self.halted = False

    # --- Broker port --------------------------------------------------------

    def place_order(self, order: Order) -> Order:
        o = order.model_copy()
        o.broker_order_id = uuid4().hex
        if self.halted:
            return self._reject(o, "trading halted (kill switch)")
        mark = self._marks.get(o.symbol)
        if mark is None or mark <= 0:
            return self._reject(o, "no market price")
        if o.order_type == OrderType.LIMIT and not self._marketable(o, mark):
            o.status = OrderStatus.PENDING
            self._orders[o.id] = o
            return o
        return self._fill(o, mark)

    def modify_order(self, order_id: str, **changes: Any) -> Order:
        o = self._orders.get(order_id)
        if o is None:
            raise KeyError(order_id)
        if o.status != OrderStatus.PENDING:
            raise ValueError("can only modify a pending order")
        if "quantity" in changes:
            o.quantity = int(changes["quantity"])
        if "limit_price" in changes:
            o.limit_price = changes["limit_price"]
        mark = self._marks.get(o.symbol)
        if mark and self._marketable(o, mark):
            self._fill(o, mark)
        return o

    def cancel_order(self, order_id: str) -> Order:
        o = self._orders.get(order_id)
        if o is None:
            raise KeyError(order_id)
        if o.status == OrderStatus.PENDING:
            o.status = OrderStatus.CANCELLED
        return o

    def get_orders(self) -> list[Order]:
        return list(self._orders.values())

    def get_positions(self) -> list[Position]:
        return [
            Position(
                symbol=sym, quantity=int(shares), avg_price=avg, last_price=self._marks.get(sym)
            )
            for sym, (shares, avg) in self._positions.items()
        ]

    def get_margin(self) -> MarginInfo:
        used = sum(
            abs(sh) * self._marks.get(sym, avg) for sym, (sh, avg) in self._positions.items()
        )
        return MarginInfo(available=self.cash, used=used, total=self.cash + used)

    # --- internals ----------------------------------------------------------

    def _marketable(self, o: Order, mark: float) -> bool:
        if o.limit_price is None:
            return True
        return (o.side == OrderSide.BUY and o.limit_price >= mark) or (
            o.side == OrderSide.SELL and o.limit_price <= mark
        )

    def _fill(self, o: Order, mark: float) -> Order:
        frac = compute_impact(o.quantity, mark, 0.0, 0.0, self.impact).impact_fraction
        fill_price = mark * (1 + frac) if o.side == OrderSide.BUY else mark * (1 - frac)
        cost = compute_costs(o.side.value, fill_price, o.quantity, self.cost).total
        notional = fill_price * o.quantity

        if o.side == OrderSide.BUY:
            if notional + cost > self.cash:
                return self._reject(o, "insufficient buying power")
            self.cash -= notional + cost
            self._apply_position(o.symbol, float(o.quantity), fill_price)
        else:
            self.cash += notional - cost
            self._apply_position(o.symbol, -float(o.quantity), fill_price)

        o.status = OrderStatus.FILLED
        o.reason = f"filled {o.quantity} @ {fill_price:.4f} (cost {cost:.2f})"
        self._orders[o.id] = o
        return o

    def _apply_position(self, symbol: str, signed_qty: float, price: float) -> None:
        shares, avg = self._positions.get(symbol, [0.0, 0.0])
        new_shares = shares + signed_qty
        if shares == 0 or (shares > 0) == (signed_qty > 0):
            avg = (
                (avg * abs(shares) + price * abs(signed_qty)) / abs(new_shares)
                if new_shares
                else 0.0
            )
        elif abs(signed_qty) > abs(shares):
            avg = price  # position flipped sign: residual carries the new fill price
        if new_shares == 0:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = [new_shares, avg]

    def _process_pending(self) -> None:
        for o in list(self._orders.values()):
            if o.status == OrderStatus.PENDING:
                mark = self._marks.get(o.symbol)
                if mark and self._marketable(o, mark):
                    self._fill(o, mark)

    def _reject(self, o: Order, reason: str) -> Order:
        o.status = OrderStatus.REJECTED
        o.reason = reason
        self._orders[o.id] = o
        return o
