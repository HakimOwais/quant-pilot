"""Write-path security dependencies (SYSTEM_DESIGN §8.2).

- require_trading_enabled: gates every order/trading endpoint behind the trading_enabled flag
  (off by default).
- verify_totp: TOTP 2FA step-up for sensitive actions (order approval, resume). The shared secret
  lives in the SecretStore (never in repo/DB/plaintext).
"""

from __future__ import annotations

import pyotp
from fastapi import Depends, Header, HTTPException

from quant_pilot.api.deps import get_secret_store
from quant_pilot.config.settings import get_settings
from quant_pilot.domain import ports

TOTP_SECRET_KEY = "totp_secret"


def require_trading_enabled() -> None:
    if not get_settings().trading_enabled:
        raise HTTPException(status_code=403, detail="trading is disabled (trading_enabled=false)")


def verify_totp(
    x_totp: str | None = Header(default=None, alias="X-TOTP"),
    secrets: ports.SecretStore = Depends(get_secret_store),
) -> None:
    secret = secrets.get_secret(TOTP_SECRET_KEY)
    if not secret:
        raise HTTPException(status_code=503, detail="2FA is not provisioned")
    if not x_totp or not pyotp.TOTP(secret).verify(x_totp):
        raise HTTPException(status_code=403, detail="invalid or missing 2FA code")
