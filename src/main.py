"""
GLDRUBF Trading Strategy - Main Entry Point

This script runs the complete GLDRUBF trading strategy analysis
and sends results to Telegram.

Usage:
    python -m src.main
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import TARGET_TICKER
from src.instruments import get_gldrubf_instrument
from src.market_data import load_candles, get_current_price, quotation_to_float
from src.indicators import calculate_atr, calculate_sar, prepare_indicators
from src.positions import find_gldrubf_position, get_position_state
from src.strategy import check_entry_signal, check_exit_conditions
from src.telegram_bot import send_telegram_message, format_status_message


def get_last_closed_candle(df):
    """Get the last fully closed 4H candle."""
    now_utc = datetime.now(timezone.utc)
    candle_duration = timedelta(hours=4)
    
    df = df.copy()
    df["candle_close_time"] = df["time"] + candle_duration
    
    closed_candidates = df[df["candle_close_time"] <= now_utc]
    
    if closed_candidates.empty:
        raise RuntimeError("No closed 4H candles found")
    
    return closed_candidates.iloc[-1]


def main():
    """Main entry point for the strategy."""
    
    # Validate required environment variables
    token = os.environ.get("T_SANDAPI")
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token:
        raise RuntimeError("Secret T_SANDAPI not found")
    if not bot_token:
        raise RuntimeError("Secret BOT_TOKEN not found")
    if not chat_id:
        raise RuntimeError("Secret TELEGRAM_CHAT_ID not found")
    
    print("=" * 70)
    print("GLDRUBF STRATEGY - STARTING")
    print("=" * 70)
    
    # Get instrument details
    print("\n📊 Getting instrument info...")
    instrument = get_gldrubf_instrument(token)
    print(f"   Ticker: {instrument.ticker}")
    print(f"   UID: {instrument.uid}")
    
    # Load market data
    print("\n📈 Loading market data...")
    df_raw = load_candles(token, instrument.uid, candles_count=200)
    
    if df_raw.empty:
        raise RuntimeError("Failed to load GLDRUBF candles")
    
    # Calculate indicators
    print("📐 Calculating indicators...")
    from config.settings import SAR_START, SAR_INC, SAR_MAX
    df = prepare_indicators(df_raw)
    df["sar"], df["sar_trend"] = calculate_sar(
        df,
        SAR_START,
        SAR_INC,
        SAR_MAX
    )
    
    # Get current price and last closed candle
    current_price = get_current_price(token, instrument.uid)
    last_closed = get_last_closed_candle(df)
    
    print(f"   Current price: {current_price:.2f}")
    print(f"   Last closed: {last_closed['close']:.2f}")
    
    # Find existing position
    print("\n🔍 Searching for GLDRUBF position...")
    position_info = find_gldrubf_position(token, instrument)
    
    # Get full position state with levels
    position_state = get_position_state(
        position_info,
        last_closed,
        current_price,
        token
    )
    
    # Check for entry signal (if no position)
    entry_signal = None
    if position_state["direction"] == "NONE":
        entry_signal = check_entry_signal(last_closed, current_price)
    
    # Check for exit conditions (if has position)
    exit_signal = None
    if position_state["direction"] in ("LONG", "SHORT"):
        exit_signal = check_exit_conditions(
            position_state,
            current_price,
            last_closed
        )
    
    # Determine action
    if position_state["direction"] == "NONE":
        if entry_signal == "LONG":
            action = "OPEN LONG"
        elif entry_signal == "SHORT":
            action = "OPEN SHORT"
        else:
            action = "WAIT"
    elif exit_signal:
        action = exit_signal
    else:
        action = "HOLD"
    
    # Format and send Telegram message
    print("\n📱 Sending status to Telegram...")
    message = format_status_message(
        current_price=current_price,
        last_closed=last_closed,
        position_state=position_state,
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        action=action
    )
    
    send_telegram_message(bot_token, chat_id, message)
    print("✅ Status sent successfully")
    
    # Print final status
    print("\n" + "=" * 70)
    print("FINAL STATUS")
    print("=" * 70)
    print(f"Action: {action}")
    print(f"Position: {position_state['direction']}")
    if position_state["direction"] in ("LONG", "SHORT"):
        print(f"Quantity: {position_state['quantity']}")
        print(f"Entry: {position_state['entry_price']}")
        print(f"SL: {position_state['sl_price']}")
        print(f"TP: {position_state['tp_price']}")
    
    print("\n✅ Strategy execution completed")


if __name__ == "__main__":
    main()
