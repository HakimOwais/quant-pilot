"""SmartAPI (Angel One) broker adapter — the Broker port for live trading.

Translates domain Order/Position/Margin to/from the Angel One SmartConnect API. The SDK client is
INJECTED (and lazily imported in the live factory), so the translation logic is fully testable
offline with a fake client and no network/credentials.

Live orders are asynchronous: place_order returns SUBMITTED with the broker order id; fill status
is learned via get_orders() (the order book). Field names follow Angel One SmartConnect — adjust to
the live SDK if it changes. Credentials/session come from the SecretStore, never the repo/DB.
"""

from __future__ import annotations

from typing import Any, Protocol

from quant_pilot.domain.models import (
    MarginInfo,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

_STATUS_MAP = {
    "complete": OrderStatus.FILLED,
    "rejected": OrderStatus.REJECTED,
    "cancelled": OrderStatus.CANCELLED,
    "open": OrderStatus.SUBMITTED,
    "open pending": OrderStatus.PENDING,
    "pending": OrderStatus.PENDING,
    "trigger pending": OrderStatus.PENDING,
    "validation pending": OrderStatus.PENDING,
    "modified": OrderStatus.SUBMITTED,
}


class SmartApiClient(Protocol):
    def placeOrder(self, params: dict[str, Any]) -> Any: ...
    def modifyOrder(self, params: dict[str, Any]) -> Any: ...
    def cancelOrder(self, variety: str, orderid: str) -> Any: ...
    def orderBook(self) -> Any: ...
    def position(self) -> Any: ...
    def rmsLimit(self) -> Any: ...


def _rows(resp: Any) -> list[dict[str, Any]]:
    if isinstance(resp, dict):
        data = resp.get("data")
        return data if isinstance(data, list) else []
    return resp if isinstance(resp, list) else []


def _data(resp: Any) -> dict[str, Any]:
    if isinstance(resp, dict):
        data = resp.get("data")
        return data if isinstance(data, dict) else resp
    return {}


def _order_id(resp: Any) -> str | None:
    if isinstance(resp, str):
        return resp
    return _data(resp).get("orderid") if isinstance(resp, dict) else None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SmartApiBroker:
    def __init__(
        self,
        client: SmartApiClient,
        token_map: dict[str, str],
        exchange: str = "NSE",
        product: str = "DELIVERY",
    ) -> None:
        self._client = client
        self.token_map = token_map
        self.exchange = exchange
        self.product = product

    def place_order(self, order: Order) -> Order:
        token = self.token_map.get(order.symbol)
        if token is None:
            raise ValueError(f"no symboltoken for {order.symbol!r}")
        params = {
            "variety": "NORMAL",
            "tradingsymbol": order.symbol,
            "symboltoken": token,
            "transactiontype": order.side.value.upper(),
            "exchange": self.exchange,
            "ordertype": order.order_type.value.upper(),
            "producttype": self.product,
            "duration": "DAY",
            "price": str(order.limit_price or 0),
            "quantity": str(order.quantity),
        }
        resp = self._client.placeOrder(params)
        o = order.model_copy()
        o.broker_order_id = _order_id(resp)
        o.status = OrderStatus.SUBMITTED
        o.reason = "submitted to SmartAPI"
        return o

    def modify_order(self, order_id: str, **changes: Any) -> Order:
        params = {"variety": "NORMAL", "orderid": order_id, **changes}
        self._client.modifyOrder(params)
        return Order(
            id=order_id,
            symbol=str(changes.get("tradingsymbol", "")),
            side=OrderSide.BUY,
            quantity=int(changes.get("quantity", 0)),
            broker_order_id=order_id,
            status=OrderStatus.SUBMITTED,
        )

    def cancel_order(self, order_id: str) -> Order:
        self._client.cancelOrder("NORMAL", order_id)
        return Order(
            id=order_id,
            symbol="",
            side=OrderSide.BUY,
            quantity=0,
            broker_order_id=order_id,
            status=OrderStatus.CANCELLED,
        )

    def get_orders(self) -> list[Order]:
        orders = []
        for r in _rows(self._client.orderBook()):
            oid = str(r.get("orderid", ""))
            side = (
                OrderSide.BUY
                if str(r.get("transactiontype", "")).upper() == "BUY"
                else OrderSide.SELL
            )
            otype = (
                OrderType.MARKET
                if str(r.get("ordertype", "")).upper() == "MARKET"
                else OrderType.LIMIT
            )
            status = _STATUS_MAP.get(str(r.get("status", "")).lower(), OrderStatus.SUBMITTED)
            fields: dict[str, Any] = {
                "symbol": str(r.get("tradingsymbol", "")),
                "side": side,
                "quantity": int(_f(r.get("quantity"))),
                "order_type": otype,
                "limit_price": _f(r.get("price")) or None,
                "status": status,
                "broker_order_id": oid,
            }
            orders.append(Order(id=oid, **fields) if oid else Order(**fields))
        return orders

    def get_positions(self) -> list[Position]:
        return [
            Position(
                symbol=str(r.get("tradingsymbol", "")),
                quantity=int(_f(r.get("netqty"))),
                avg_price=_f(r.get("avgnetprice")),
                last_price=_f(r.get("ltp")) or None,
            )
            for r in _rows(self._client.position())
        ]

    def get_margin(self) -> MarginInfo:
        d = _data(self._client.rmsLimit())
        available = _f(d.get("availablecash", d.get("net")))
        used = _f(d.get("utiliseddebits"))
        return MarginInfo(available=available, used=used, total=available + used)
