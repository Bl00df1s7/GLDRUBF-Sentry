"""
Instrument discovery and management.
SIGNAL ONLY MODE - Uses t_tech.invest if available.
"""

try:
    from t_tech.invest import Client, CandleInterval
    T_TECH_AVAILABLE = True
except ImportError:
    T_TECH_AVAILABLE = False
    Client = None
    CandleInterval = None


def get_gldrubf_instrument(token: str) -> dict:
    """
    Find GLDRUBF futures instrument.
    
    Args:
        token: T-Invest API token
        
    Returns:
        Instrument object with uid, figi, ticker, etc.
        
    Raises:
        RuntimeError: If t_tech not available or instrument not found
    """
    from config.settings import TARGET_TICKER
    
    if not T_TECH_AVAILABLE:
        raise RuntimeError("t_tech.invest module not available. Install with: pip install t-tech")
    
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
