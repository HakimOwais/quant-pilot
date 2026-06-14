"""FastAPI application factory (SYSTEM_DESIGN §6).

Wires middleware (security headers, signed session cookie, CORS) and routers.
Concrete adapters (Repository, Broker, etc.) are injected via api/deps.py as each
port is implemented — the app itself stays thin.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from quant_pilot.api.routers import backtests, jobs, orders, portfolio, system, universe
from quant_pilot.api.security.headers import SecurityHeadersMiddleware
from quant_pilot.config.settings import get_settings
from quant_pilot.log import configure_logging, get_logger

API_V1 = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log = get_logger("api")
    log.info("api.startup", env=settings.env, trading_enabled=settings.trading_enabled)
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Quant Pilot API",
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Order matters: outermost added last. Security headers wrap everything.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="qp_session",
        https_only=settings.is_prod,
        same_site="strict",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(system.router_v1, prefix=API_V1)
    app.include_router(backtests.router, prefix=API_V1)
    app.include_router(jobs.router, prefix=API_V1)
    app.include_router(universe.router, prefix=API_V1)
    app.include_router(orders.router, prefix=API_V1)
    app.include_router(portfolio.router, prefix=API_V1)
    return app


app = create_app()
