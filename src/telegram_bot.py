"""
Telegram bot messaging functions.
"""

import requests


def send_telegram_message(bot_token: str, chat_id: str, message: str) -> dict:
    """
    Send message to Telegram chat.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Chat ID to send message to
        message: Message text (supports HTML)
        
    Returns:
        Telegram API response
        
    Raises:
        RuntimeError: If message sending fails
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }
    
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    
    return data


def fmt_price(value: float) -> str:
    """Format price with space as thousand separator."""
    return f"{float(value):,.2f}".replace(",", " ")


def format_status_message(
    current_price: float,
    last_closed: dict,
    position_state: dict,
    entry_signal: str,
    exit_signal: str,
    action: str,
    signal_time=None
) -> str:
    """
    Format strategy status message for Telegram.
    
    Args:
        current_price: Current market price
        last_closed: Last closed candle data
        position_state: Position state dictionary
        entry_signal: Entry signal ("LONG", "SHORT", or None)
        exit_signal: Exit signal string or None
        action: Action to take
        signal_time: Time when signal was generated (datetime)
        
    Returns:
        Formatted HTML message
    """
    from datetime import timezone, datetime
    
    # Use provided signal time or current time
    if signal_time is None:
        signal_time = datetime.now(timezone.utc)
    
    # Market info - use signal time for display
    signal_msk = signal_time.astimezone(timezone.utc)
    
    # Position block
    direction = position_state["direction"]
    
    if direction == "NONE":
        position_block = "⚪ <b>Нет позиции</b>"
    else:
        pos_icon = "🟢" if direction == "LONG" else "🔴"
        position_block = (
            f"{pos_icon} <b>{direction} × {position_state['quantity']:g}</b>\n"
            f"Вход:        {fmt_price(position_state['entry_price'])}\n"
            f"SL:          {fmt_price(position_state['sl_price'])}\n"
            f"TP:          {fmt_price(position_state['tp_price'])}\n"
            f"BE:          {fmt_price(position_state['be_trigger'])}"
        )
    
    # Signal block
    if entry_signal == "LONG":
        signal_block = "🟢 <b>LONG</b>"
    elif entry_signal == "SHORT":
        signal_block = "🔴 <b>SHORT</b>"
    else:
        signal_block = "⚪ Нет сигнала"
    
    # SAR block
    sar_trend = "LONG" if last_closed["sar_trend"] == 1 else "SHORT"
    sar_icon = "🟢" if last_closed["sar_trend"] == 1 else "🔴"
    sar_block = f"{fmt_price(last_closed['sar'])} · {sar_icon} {sar_trend}"
    
    # Build message
    message = (
        "🟢 <b>GLDRUBF SENTRY</b>\n"
        "\n"
        "💰 <b>Рынок</b>\n"
        f"Цена:        <b>{fmt_price(current_price)}</b>\n"
        f"Закрытие 4H: {fmt_price(last_closed['close'])}\n"
        f"Свеча:       {last_closed['time'].astimezone(timezone.utc).strftime('%d.%m.%Y %H:%M')} MSK\n"
        "\n"
        "📈 <b>Позиция</b>\n"
        f"{position_block}\n"
        "\n"
        "🎯 <b>Сигнал</b>\n"
        f"{signal_block}\n"
        "\n"
        "📐 <b>SAR</b>\n"
        f"{sar_block}\n"
        "\n"
        "➡️ <b>Действие</b>\n"
        f"<b>{action}</b>\n"
        "\n"
        f"⏱ {signal_msk.strftime('%H:%M:%S')} MSK"
    )
    
    return message
