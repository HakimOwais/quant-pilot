"""VaR / CVaR risk sizing (MASTER_PROMPT Phase: risk).

Thin risk-layer wrapper over the Monte-Carlo VaR/CVaR engine, driven by RiskConfig (fat-tailed
Student-t and CVaR by default). `cvar_position_size` turns a per-trade risk budget into a position
size: budget / tail-risk.
"""

from __future__ import annotations

import pandas as pd

from quant_pilot.engine.models.monte_carlo import VaRResult, var_cvar
from quant_pilot.engine.risk.config import RiskConfig


def portfolio_var_cvar(returns: pd.Series, config: RiskConfig | None = None) -> VaRResult:
    cfg = config or RiskConfig()
    return var_cvar(returns, alpha=cfg.daily_var_confidence, method=cfg.var_distribution)


def cvar_position_size(
    risk_budget: float, returns: pd.Series, config: RiskConfig | None = None
) -> float:
    """Position size = risk_budget / tail-risk (CVaR by default, VaR if configured)."""
    cfg = config or RiskConfig()
    res = portfolio_var_cvar(returns, cfg)
    risk = res.cvar if cfg.risk_measure == "cvar" else res.var
    return risk_budget / risk if risk > 0 else 0.0
