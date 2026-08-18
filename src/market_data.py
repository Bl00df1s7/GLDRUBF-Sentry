"""
Market data loading and price retrieval.
SIGNAL ONLY MODE - Uses t_tech.invest if available, otherwise mock data for testing.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

try:
    from t_tech.invest import Client, CandleInterval
    T_TECH_AVAILABLE = True
except ImportError:
    T_TECH_AVAILABLE = False
    Client = None
    CandleInterval = None


def quotation_to_float(value) -> float:
    """
    Safe conversion of Quotation to float.
    
    Args:
        value: Quotation object or numeric value
        
    Returns:
        Float value or np.nan if None
    """
    if value is None:
        return np.nan
    
    if isinstance(value, (int, float, np.number)):
        return float(value)
    
    if hasattr(value, "units") and hasattr(value, "nano"):
        return float(value.units) + float(value.nano) / 1_000_000_000
    
    if hasattr(value, "value"):
        return float(value.value)
    
    return float(value)


def candle_to_row(candle) -> dict:
    """Convert candle object to dictionary row."""
    return {
        "time": candle.time,
        "open": quotation_to_float(candle.open),
        "high": quotation_to_float(candle.high),
        "low": quotation_to_float(candle.low),
        "close": quotation_to_float(candle.close),
        "volume": candle.volume,
    }


def load_candles(token: str, uid: str, candles_count: int = 200) -> pd.DataFrame:
    """
    Load recent candles from T-Invest API.
    
    Args:
        token: T-Invest API token
        uid: Instrument UID
        candles_count: Number of candles to load
        
    Returns:
        DataFrame with OHLCV data
        
    Raises:
        RuntimeError: If t_tech is not available or data cannot be loaded
    """
    if not T_TECH_AVAILABLE:
        raise RuntimeError("t_tech.invest module not available. Install with: pip install t-tech")
    
    now_utc = datetime.now(timezone.utc)
    
    # 4H = 6 candles per day, add buffer
    days = int(candles_count / 6) + 10
    start_date = now_utc - timedelta(days=days)
    
    rows = []
    current = start_date
    chunk = timedelta(days=90)
    
    while current < now_utc:
        chunk_end = min(current + chunk, now_utc)
        
        with Client(token) as services:
            response = services.market_data.get_candles(
                instrument_id=uid,
                from_=current,
                to=chunk_end,
                interval=CandleInterval.CANDLE_INTERVAL_4_HOUR,
            )
        
        rows.extend(candle_to_row(candle) for candle in response.candles)
        current = chunk_end
    
    df = pd.DataFrame(rows)
    
    if df.empty:
        return df
    
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    
    return df.tail(candles_count).reset_index(drop=True)


def get_current_price(token: str, uid: str) -> float:
    """
    Get current last price for instrument.
    
    Args:
        token: T-Invest API token
        uid: Instrument UID
        
    Returns:
        Current price as float
        
    Raises:
        RuntimeError: If t_tech is not available or price cannot be retrieved
    """
    if not T_TECH_AVAILABLE:
        raise RuntimeError("t_tech.invest module not available")
    
    with Client(token) as services:
        response = services.market_data.get_last_prices(
            instrument_id=[uid]
        )
    
    if not response.last_prices:
        raise RuntimeError("Не удалось получить текущую цену GLDRUBF")
    
    return quotation_to_float(response.last_prices[0].price)
