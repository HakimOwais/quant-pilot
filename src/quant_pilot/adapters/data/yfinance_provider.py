"""MarketDataProvider adapter backed by yfinance + the Parquet cache.

The actual network download is an injectable callable so the whole adapter is testable
offline (tests pass a fake downloader). yfinance is imported lazily inside the default
downloader, so importing this module never requires yfinance or a network connection.

Universe membership is served from the repository (the point-in-time table), NOT from
yfinance — yfinance has no historical constituents.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

from quant_pilot.adapters.data.parquet_cache import OHLCVCache
from quant_pilot.domain import ports
from quant_pilot.domain.models import UniverseMembership

Downloader = Callable[[str, date, date, str], pd.DataFrame]

_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}
_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


def _default_downloader(symbol: str, start: date, end: date, interval: str) -> pd.DataFrame:
    import yfinance as yf

    return yf.download(
        symbol, start=start, end=end, interval=interval, auto_adjust=False, progress=False
    )


def _to_ts(d: date) -> pd.Timestamp:
    return pd.Timestamp(d)


class YFinanceMarketDataProvider:
    def __init__(
        self,
        repository: ports.Repository,
        cache: OHLCVCache,
        downloader: Downloader | None = None,
    ) -> None:
        self.repo = repository
        self.cache = cache
        self._download = downloader or _default_downloader

    # --- prices -------------------------------------------------------------

    def get_ohlcv(self, symbol: str, start: date, end: date, frequency: str = "1d") -> pd.DataFrame:
        cached = self.cache.read(symbol)
        if cached is not None and not cached.empty and self._covers(cached, start, end):
            return self._slice(cached, start, end)
        raw = self._download(symbol, start, end, frequency)
        normalized = self._normalize(raw)
        merged = self.cache.merge_write(symbol, normalized)
        return self._slice(merged, start, end)

    def get_liquidity(self, symbol: str, as_of: date, window: int = 20) -> dict[str, float]:
        df = self.cache.read(symbol)
        if df is None or df.empty:
            raise ValueError(f"no cached OHLCV for {symbol!r}; ingest prices before liquidity")
        recent = df[df.index <= _to_ts(as_of)].tail(window)
        if recent.empty:
            return {"adv_value": 0.0, "adv_shares": 0.0, "sessions": 0.0}
        turnover = (recent["close"].astype(float) * recent["volume"].astype(float)).median()
        return {
            "adv_value": float(turnover),
            "adv_shares": float(recent["volume"].astype(float).median()),
            "sessions": float(len(recent)),
        }

    # --- delegated / deferred ----------------------------------------------

    def get_universe_membership(self, index: str, as_of: date) -> list[UniverseMembership]:
        return self.repo.get_universe_membership(index, as_of)

    def get_option_chain(self, underlying: str, expiry: date | None = None) -> pd.DataFrame:
        raise NotImplementedError("option chains arrive with the VRP / Black-Scholes phase")

    # --- helpers ------------------------------------------------------------

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        df = raw.copy()
        # Newer yfinance returns MultiIndex columns (field, ticker) even for one symbol.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=_COLUMN_MAP)
        keep = [c for c in _COLUMNS if c in df.columns]
        df = df[keep].copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        return df.dropna(how="all")

    @staticmethod
    def _covers(df: pd.DataFrame, start: date, end: date) -> bool:
        return df.index.min() <= _to_ts(start) and df.index.max() >= _to_ts(end)

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        mask = (df.index >= _to_ts(start)) & (df.index <= _to_ts(end))
        return df.loc[mask]
