"""
Strategy logic - entry and exit signals.
"""

import numpy as np

from config.settings import SL_ATR, TP_PCT, BE_PCT


def check_entry_signal(last_closed: dict, current_price: float) -> str:
    """
    Check for entry signal when no position exists.
    
    Args:
        last_closed: Last closed candle data with indicators
        current_price: Current market price
        
    Returns:
        "LONG", "SHORT", or None
    """
    if last_closed.get("long_signal", False):
        return "LONG"
    elif last_closed.get("short_signal", False):
        return "SHORT"
    else:
        return None


def check_exit_conditions(
    position_state: dict,
    current_price: float,
    last_closed: dict
) -> str:
    """
    Check for exit conditions when position exists.
    
    Args:
        position_state: Position state dictionary
        current_price: Current market price
        last_closed: Last closed candle data
        previous_closed: Previous closed candle data
        
    Returns:
        Exit reason string or None
    """
    if np.isnan(position_state["entry_price"]):
        return None
    
    direction = position_state["direction"]
    sl_price = position_state["sl_price"]
    tp_price = position_state["tp_price"]
    be_trigger = position_state["be_trigger"]
    
    # Get SAR trend change
    sar_trend = int(last_closed["sar_trend"])
    
    if direction == "LONG":
        hit_sl = current_price <= sl_price
        hit_tp = current_price >= tp_price
        hit_be = current_price >= be_trigger
        sar_exit = sar_trend == -1
        
    else:  # SHORT
        hit_sl = current_price >= sl_price
        hit_tp = current_price <= tp_price
        hit_be = current_price <= be_trigger
        sar_exit = sar_trend == 1
    
    # Priority: SL > TP > SAR > BE
    if hit_sl:
        return "EXIT — SL"
    elif hit_tp:
        return "EXIT — TP"
    elif sar_exit:
        return "EXIT — SAR"
    elif hit_be:
        return "BE TRIGGER"
    else:
        return None
