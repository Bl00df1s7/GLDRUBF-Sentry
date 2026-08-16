"""
Technical indicators calculation.
"""

import pandas as pd
import numpy as np

from config.settings import DONCHIAN_LEN, ATR_LEN


def calculate_atr(df: pd.DataFrame, length: int) -> pd.Series:
    """
    Calculate Average True Range (ATR).
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        length: ATR period
        
    Returns:
        ATR series
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    prev_close = close.shift(1)
    
    # True Range calculation
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    
    return tr.rolling(length).mean()


def prepare_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all required indicators.
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        DataFrame with added indicator columns
    """
    data = df.copy().reset_index(drop=True)
    
    # ATR
    data["atr"] = calculate_atr(data, ATR_LEN)
    
    # Donchian Channel (only previous candles, shift by 1)
    data["donchian_upper"] = data["high"].rolling(DONCHIAN_LEN).max().shift(1)
    data["donchian_lower"] = data["low"].rolling(DONCHIAN_LEN).min().shift(1)
    
    # Entry signals
    data["long_signal"] = data["close"] > data["donchian_upper"]
    data["short_signal"] = data["close"] < data["donchian_lower"]
    
    return data


def calculate_sar(
    df: pd.DataFrame,
    start: float,
    inc: float,
    maximum: float
) -> tuple[np.ndarray, np.ndarray]:
    """
    Calculate Parabolic SAR.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        start: Initial acceleration factor
        inc: AF increment
        maximum: Maximum AF value
        
    Returns:
        Tuple of (SAR values, trend direction array)
    """
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    
    n = len(df)
    
    sar = np.full(n, np.nan)
    ep = np.full(n, np.nan)
    af = np.full(n, np.nan)
    trend = np.ones(n, dtype=int)
    
    if n == 0:
        return sar, trend
    
    # Initialize first candle
    sar[0] = close[0]
    ep[0] = close[0]
    af[0] = start
    trend[0] = 1
    
    for i in range(1, n):
        prev_sar = sar[i - 1]
        prev_ep = ep[i - 1]
        prev_af = af[i - 1]
        prev_trend = trend[i - 1]
        
        if prev_trend == 1:  # UP trend
            current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            
            if i >= 2:
                current_sar = min(current_sar, low[i - 1], low[i - 2])
            else:
                current_sar = min(current_sar, low[i - 1])
            
            # Check for reversal
            if low[i] < current_sar:
                trend[i] = -1
                sar[i] = prev_ep
                ep[i] = low[i]
                af[i] = start
            else:
                trend[i] = 1
                sar[i] = current_sar
                
                if high[i] > prev_ep:
                    ep[i] = high[i]
                    af[i] = min(prev_af + inc, maximum)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af
                    
        else:  # DOWN trend
            current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            
            if i >= 2:
                current_sar = max(current_sar, high[i - 1], high[i - 2])
            else:
                current_sar = max(current_sar, high[i - 1])
            
            # Check for reversal
            if high[i] > current_sar:
                trend[i] = 1
                sar[i] = prev_ep
                ep[i] = high[i]
                af[i] = start
            else:
                trend[i] = -1
                sar[i] = current_sar
                
                if low[i] < prev_ep:
                    ep[i] = low[i]
                    af[i] = min(prev_af + inc, maximum)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af
    
    return sar, trend
