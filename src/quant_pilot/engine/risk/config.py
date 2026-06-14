"""Risk-layer configuration (mirrors config/settings.yaml: risk)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RiskConfig(BaseModel):
    max_position_pct: float = 0.05  # max weight in one position
    max_sector_pct: float = 0.25  # max gross weight in one sector
    daily_var_confidence: float = 0.99
    risk_measure: Literal["var", "cvar"] = "cvar"  # size on expected shortfall
    var_distribution: Literal["historical", "student_t"] = "student_t"  # fat-tailed by default
    kelly_fraction: float = 0.25  # fractional Kelly only (full Kelly blows up)
    max_portfolio_drawdown: float = 0.15  # trip the circuit breaker beyond this
