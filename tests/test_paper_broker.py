from __future__ import annotations

import pytest

from quant_pilot.adapters.broker.paper_broker import PaperBroker
from quant_pilot.domain import ports
from quant_pilot.domain.models import Order, OrderSide, OrderStatus, OrderType
from quant_pilot.engine.backtest.costs import CostConfig, compute_costs


def _order(symbol="AAA", side=OrderSide.BUY, qty=100, otype=OrderType.MARKET, limit=None):
    return Order(symbol=symbol, side=side, quantity=qty, order_type=otype, limit_price=limit)


def test_conforms_to_broker_port():
    assert isinstance(PaperBroker(), ports.Broker)


def test_market_buy_fills_and_updates_cash_and_position():
    broker = PaperBroker(initial_cash=1_000_000.0)
    broker.set_mark("AAA", 100.0)
    filled = broker.place_order(_order(qty=100))

    assert filled.status is OrderStatus.FILLED
    assert filled.broker_order_id
    # 5bps slippage default -> fill at 100.05
    pos = broker.get_positions()[0]
    assert pos.symbol == "AAA"
    assert pos.quantity == 100
    assert pos.avg_price == pytest.approx(100.05)

    expected_cost = compute_costs("buy", 100.05, 100, CostConfig()).total
    assert 1_000_000.0 - broker.cash == pytest.approx(100 * 100.05 + expected_cost)


def test_insufficient_buying_power_is_rejected():
    broker = PaperBroker(initial_cash=100.0)
    broker.set_mark("AAA", 100.0)
    rejected = broker.place_order(_order(qty=100))  # needs ~10,020
    assert rejected.status is OrderStatus.REJECTED
    assert "buying power" in (rejected.reason or "")
    assert broker.get_positions() == []
    assert broker.cash == 100.0


def test_limit_order_rests_then_fills_on_mark_move():
    broker = PaperBroker()
    broker.set_mark("AAA", 100.0)
    order = broker.place_order(_order(otype=OrderType.LIMIT, limit=99.0))  # below market -> rests
    assert order.status is OrderStatus.PENDING

    broker.update_marks({"AAA": 98.0})  # now marketable (99 >= 98)
    assert broker.get_orders()[0].status is OrderStatus.FILLED
    assert broker.get_positions()[0].quantity == 100


def test_cancel_pending_order():
    broker = PaperBroker()
    broker.set_mark("AAA", 100.0)
    order = broker.place_order(_order(otype=OrderType.LIMIT, limit=90.0))
    cancelled = broker.cancel_order(order.id)
    assert cancelled.status is OrderStatus.CANCELLED


def test_sell_closes_position_and_returns_cash():
    broker = PaperBroker()
    broker.set_mark("AAA", 100.0)
    broker.place_order(_order(side=OrderSide.BUY, qty=100))
    cash_after_buy = broker.cash

    broker.place_order(_order(side=OrderSide.SELL, qty=100))
    assert broker.get_positions() == []  # flat
    assert broker.cash > cash_after_buy  # sale proceeds returned (net of costs)


def test_kill_switch_blocks_orders():
    broker = PaperBroker()
    broker.set_mark("AAA", 100.0)
    broker.halt()
    rejected = broker.place_order(_order())
    assert rejected.status is OrderStatus.REJECTED
    assert "halt" in (rejected.reason or "")
    broker.resume()
    assert broker.place_order(_order(qty=10)).status is OrderStatus.FILLED


def test_margin_reflects_exposure():
    broker = PaperBroker(initial_cash=1_000_000.0)
    broker.set_mark("AAA", 100.0)
    broker.place_order(_order(qty=100))
    margin = broker.get_margin()
    assert margin.used == pytest.approx(100 * 100.0)  # 100 shares marked at 100
    assert margin.total == pytest.approx(margin.available + margin.used)
