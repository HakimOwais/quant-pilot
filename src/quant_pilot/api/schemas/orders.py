"""API request schema for proposing an order. Responses reuse the domain Order model."""

from __future__ import annotations

from pydantic import BaseModel

from quant_pilot.domain.models import OrderSide, OrderType


class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
