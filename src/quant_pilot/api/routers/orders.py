"""Gated order/approval path (SYSTEM_DESIGN §6/§7/§8).

propose -> PENDING (trading_enabled, pre-trade checks, audited)
approve -> 2FA step-up -> broker.place_order -> FILLED/REJECTED (audited)

Every order action is appended to the audit log. The broker's kill switch + buying-power check are
the last line of defense at execution.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from quant_pilot.api.deps import get_broker, get_repository
from quant_pilot.api.schemas.orders import OrderCreate
from quant_pilot.api.security.auth import require_trading_enabled, verify_totp
from quant_pilot.domain import ports
from quant_pilot.domain.models import AuditEvent, Order, OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])


def _actor(_request: Request) -> str:
    return "local-user"  # single-user; real auth identity wires in here


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _audit(
    repo: ports.Repository, request: Request, action: str, order_id: str, payload: dict
) -> None:
    repo.append_audit(
        AuditEvent(
            actor=_actor(request),
            action=action,
            resource_type="order",
            resource_id=order_id,
            payload=payload,
            ip=_ip(request),
        )
    )


@router.post(
    "", status_code=201, response_model=Order, dependencies=[Depends(require_trading_enabled)]
)
def propose_order(
    body: OrderCreate, request: Request, repo: ports.Repository = Depends(get_repository)
) -> Order:
    if body.quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity must be positive")
    order = Order(
        symbol=body.symbol,
        side=body.side,
        quantity=body.quantity,
        order_type=body.order_type,
        limit_price=body.limit_price,
        status=OrderStatus.PENDING,
    )
    saved = repo.save_order(order)
    _audit(repo, request, "order.proposed", order.id, body.model_dump(mode="json"))
    return saved


@router.post(
    "/{order_id}/approve",
    response_model=Order,
    dependencies=[Depends(require_trading_enabled), Depends(verify_totp)],
)
def approve_order(
    order_id: str,
    request: Request,
    repo: ports.Repository = Depends(get_repository),
    broker: ports.Broker = Depends(get_broker),
) -> Order:
    order = repo.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status is not OrderStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"order is {order.status.value}, not pending")

    result = broker.place_order(order)  # broker enforces kill switch + buying power
    saved = repo.save_order(result)
    _audit(
        repo,
        request,
        f"order.{result.status.value}",
        order_id,
        {"broker_order_id": result.broker_order_id, "reason": result.reason},
    )
    return saved


@router.get("", response_model=list[Order])
def list_orders(limit: int = 100, repo: ports.Repository = Depends(get_repository)) -> list[Order]:
    return repo.list_orders(limit=limit)


@router.get("/{order_id}", response_model=Order)
def get_order(order_id: str, repo: ports.Repository = Depends(get_repository)) -> Order:
    order = repo.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order
