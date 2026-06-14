from __future__ import annotations

import pytest

from quant_pilot.adapters.broker.smartapi_broker import SmartApiBroker
from quant_pilot.domain import ports
from quant_pilot.domain.models import Order, OrderSide, OrderStatus, OrderType


class FakeSmartApiClient:
    def __init__(self):
        self.placed: list[dict] = []

    def placeOrder(self, params):
        self.placed.append(params)
        return {"status": True, "data": {"orderid": "BRK123"}}

    def modifyOrder(self, params):
        return {"status": True, "data": {"orderid": params["orderid"]}}

    def cancelOrder(self, variety, orderid):
        return {"status": True, "data": {"orderid": orderid}}

    def orderBook(self):
        return {
            "data": [
                {
                    "orderid": "BRK123",
                    "tradingsymbol": "RELIANCE-EQ",
                    "transactiontype": "BUY",
                    "status": "complete",
                    "ordertype": "MARKET",
                    "quantity": "100",
                    "price": "0",
                }
            ]
        }

    def position(self):
        return {
            "data": [
                {
                    "tradingsymbol": "RELIANCE-EQ",
                    "netqty": "100",
                    "avgnetprice": "2900.5",
                    "ltp": "2910",
                }
            ]
        }

    def rmsLimit(self):
        return {"data": {"availablecash": "500000", "utiliseddebits": "290050"}}


def _broker():
    return SmartApiBroker(FakeSmartApiClient(), token_map={"RELIANCE-EQ": "2885"})


def test_conforms_to_broker_port():
    assert isinstance(_broker(), ports.Broker)


def test_place_order_builds_params_and_submits():
    broker = _broker()
    order = Order(
        symbol="RELIANCE-EQ", side=OrderSide.BUY, quantity=100, order_type=OrderType.MARKET
    )
    result = broker.place_order(order)

    assert result.status is OrderStatus.SUBMITTED
    assert result.broker_order_id == "BRK123"
    sent = broker._client.placed[0]  # type: ignore[attr-defined]
    assert sent["symboltoken"] == "2885"
    assert sent["transactiontype"] == "BUY"
    assert sent["quantity"] == "100"


def test_place_order_requires_token():
    broker = SmartApiBroker(FakeSmartApiClient(), token_map={})
    with pytest.raises(ValueError):
        broker.place_order(Order(symbol="UNKNOWN", side=OrderSide.BUY, quantity=1))


def test_order_book_maps_status():
    orders = _broker().get_orders()
    assert orders[0].status is OrderStatus.FILLED
    assert orders[0].broker_order_id == "BRK123"
    assert orders[0].quantity == 100


def test_positions_and_margin_mapping():
    broker = _broker()
    pos = broker.get_positions()[0]
    assert pos.symbol == "RELIANCE-EQ" and pos.quantity == 100
    assert pos.avg_price == pytest.approx(2900.5)

    margin = broker.get_margin()
    assert margin.available == pytest.approx(500000.0)
    assert margin.used == pytest.approx(290050.0)


def test_cancel_returns_cancelled_ack():
    assert _broker().cancel_order("BRK123").status is OrderStatus.CANCELLED
