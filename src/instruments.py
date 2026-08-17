"""
Instrument discovery and management.
"""

from t_tech.invest import Client, CandleInterval


def get_gldrubf_instrument(token: str) -> dict:
    """
    Find GLDRUBF futures instrument.
    
    Args:
        token: T-Invest API token
        
    Returns:
        Instrument object with uid, figi, ticker, etc.
        
    Raises:
        RuntimeError: If instrument not found
    """
    from config.settings import TARGET_TICKER
    
    with Client(token) as client:
        response = client.instruments.futures()
        futures = response.instruments
    
    instrument = None
    
    for x in futures:
        if x.ticker.upper() == TARGET_TICKER:
            instrument = x
            break
    
    if instrument is None:
        raise RuntimeError(f"Фьючерс {TARGET_TICKER} не найден")
    
    print("=== INSTRUMENT ===")
    print(f"Ticker:       {instrument.ticker}")
    print(f"Name:         {instrument.name}")
    print(f"UID:          {instrument.uid}")
    print(f"FIGI:         {instrument.figi}")
    print(f"Class code:   {instrument.class_code}")
    print(f"Lot:          {instrument.lot}")
    print(f"Min tick:     {instrument.min_price_increment}")
    
    return instrument
