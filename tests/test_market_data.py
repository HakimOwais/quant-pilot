from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_pilot.adapters.data.parquet_cache import OHLCVCache
from quant_pilot.adapters.data.yfinance_provider import YFinanceMarketDataProvider
from quant_pilot.adapters.persistence.repository import SqlAlchemyRepository
from quant_pilot.domain import ports


def _yf_style_frame(start: str, periods: int) -> pd.DataFrame:
    """Mimic yfinance output: Title-case columns, Adj Close, DatetimeIndex."""
    idx = pd.date_range(start, periods=periods, freq="B")
    return pd.DataFrame(
        {
            "Open": range(100, 100 + periods),
            "High": range(101, 101 + periods),
            "Low": range(99, 99 + periods),
            "Close": range(100, 100 + periods),
            "Adj Close": range(100, 100 + periods),
            "Volume": [1_000_000] * periods,
        },
        index=idx,
    )


class _FakeDownloader:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = 0

    def __call__(self, symbol, start, end, interval):  # matches Downloader signature
        self.calls += 1
        return self.frame


def _provider(session, downloader, tmp_path):
    repo = SqlAlchemyRepository(session)
    return YFinanceMarketDataProvider(repo, OHLCVCache(tmp_path), downloader=downloader)


def test_provider_conforms_to_port(session, tmp_path):
    provider = _provider(session, _FakeDownloader(_yf_style_frame("2020-01-01", 5)), tmp_path)
    assert isinstance(provider, ports.MarketDataProvider)


def test_get_ohlcv_normalizes_columns(session, tmp_path):
    dl = _FakeDownloader(_yf_style_frame("2020-01-01", 10))
    provider = _provider(session, dl, tmp_path)
    df = provider.get_ohlcv("TCS.NS", date(2020, 1, 1), date(2020, 1, 31))
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert df.index.name == "date"
    assert len(df) > 0


def test_get_ohlcv_uses_cache_on_second_call(session, tmp_path):
    dl = _FakeDownloader(_yf_style_frame("2020-01-01", 20))
    provider = _provider(session, dl, tmp_path)
    provider.get_ohlcv("TCS.NS", date(2020, 1, 1), date(2020, 1, 10))
    provider.get_ohlcv("TCS.NS", date(2020, 1, 1), date(2020, 1, 10))
    assert dl.calls == 1  # second call served from the Parquet cache


def test_get_liquidity_from_cache(session, tmp_path):
    dl = _FakeDownloader(_yf_style_frame("2020-01-01", 30))
    provider = _provider(session, dl, tmp_path)
    provider.get_ohlcv("TCS.NS", date(2020, 1, 1), date(2020, 2, 28))
    liq = provider.get_liquidity("TCS.NS", date(2020, 2, 1), window=20)
    assert liq["adv_shares"] == 1_000_000
    assert liq["adv_value"] > 0
    assert liq["sessions"] == 20


def test_get_liquidity_requires_data(session, tmp_path):
    provider = _provider(session, _FakeDownloader(_yf_style_frame("2020-01-01", 1)), tmp_path)
    with pytest.raises(ValueError):
        provider.get_liquidity("UNKNOWN.NS", date(2020, 1, 1))


def test_option_chain_deferred(session, tmp_path):
    provider = _provider(session, _FakeDownloader(_yf_style_frame("2020-01-01", 1)), tmp_path)
    with pytest.raises(NotImplementedError):
        provider.get_option_chain("NIFTY")
