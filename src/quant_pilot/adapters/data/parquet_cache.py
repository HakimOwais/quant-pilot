"""Parquet-based OHLCV datalake (SYSTEM_DESIGN §5). One file per symbol, merge-on-write.

Abstracted so it can be swapped for S3/MinIO later; the provider only depends on this small
surface. Index is a DatetimeIndex named 'date'.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


class OHLCVCache:
    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base = Path(base_dir) / "ohlcv"
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self.base / f"{symbol}.parquet"

    def read(self, symbol: str) -> pd.DataFrame | None:
        path = self._path(symbol)
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def write(self, symbol: str, df: pd.DataFrame) -> None:
        df.sort_index().to_parquet(self._path(symbol))

    def merge_write(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """Union new rows with any existing cache, last-write-wins per date, sorted."""
        existing = self.read(symbol)
        if existing is not None and not existing.empty:
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        else:
            combined = df.sort_index()
        self.write(symbol, combined)
        return combined
